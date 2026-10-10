#!/usr/bin/env python3
"""Asistente guiado: pregunta y llama al pipeline de procesar_pleno.py sin terminal ni jerga.

Se ejecuta empaquetado con PyInstaller (PC del Ayuntamiento) o con python (desarrollo).
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

# La consola de Windows usa cp1252: reconfigurar sys.stdout no basta, hay que fijar
# también su codepage a UTF-8 o los acentos salen rotos.
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass  # sin consola propia (salida redirigida a fichero): nada que ajustar

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Al ejecutarse desde el repo, los módulos del pipeline están en esta misma carpeta.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from procesar_pleno import (ErrorDeDescarga, clave_pleno, dir_borrador, extraer_fecha,
                            extraer_video_id, leer_convocatoria, procesar_pleno,
                            _rehacer_acta, _rehacer_informe, _titulo_de_youtube)
from plenos_informe import normalizar_fecha
# El aviso "COMPROBAR ANTES DE SELLAR.txt" vive en plenos_guia.py porque
# procesar_pleno también lo escribe en --rehacer-acta, sin pasar por aquí.
from plenos_guia import (_avisos_legibles, _lineas_aviso, escribir_comprobaciones,
                         texto_comprobaciones)

DIR_CONFIG = "Configuración (no tocar)"
DIR_ACTAS = "Actas generadas"
CLAVES_NECESARIAS = ("ASSEMBLYAI_API_KEY", "OPENROUTER_API_KEY")
RESPONSABLE = "Juan Luján"


class Instalacion(NamedTuple):
    """Dónde vive cada cosa en el ordenador donde se está ejecutando."""
    base: Path
    config: Path
    registros: Path
    actas: Path


def carpeta_base() -> Path:
    """Carpeta de la instalación: la del .exe si está empaquetado, la raíz del repo si no.
    En el .exe __file__ apunta a una carpeta temporal que se borra al salir."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def cargar_configuracion(config: Path) -> list[str]:
    """Lee configuracion.env y devuelve las claves de API que falten.
    Van en un fichero editable con el Bloc de notas, sin reconstruir el ejecutable."""
    ruta = config / "configuracion.env"
    if ruta.exists():
        from dotenv import load_dotenv
        # utf-8-sig: el Bloc de notas guarda con BOM, que se pegaría a la primera clave.
        load_dotenv(ruta, override=True, encoding="utf-8-sig")
    return [c for c in CLAVES_NECESARIAS if not os.environ.get(c)]


def preparar_instalacion() -> Instalacion:
    """Resuelve y crea las carpetas y deja el entorno listo para el pipeline."""
    base = carpeta_base()
    config = base / DIR_CONFIG
    config.mkdir(parents=True, exist_ok=True)
    cargar_configuracion(config)

    if os.environ.get("ACTAS_DIR"):
        actas = Path(os.environ["ACTAS_DIR"])
    elif getattr(sys, "frozen", False):
        actas = base / DIR_ACTAS
    else:
        actas = base / "uploads" / "actas"
    actas.mkdir(parents=True, exist_ok=True)
    os.environ["ACTAS_DIR"] = str(actas)  # lo lee procesar_pleno.dir_borrador

    registros = config / "registros"
    registros.mkdir(parents=True, exist_ok=True)

    # El yt-dlp.exe solo existe empaquetado; desde el repo se usa el de pip.
    descargador = config / "yt-dlp.exe"
    if descargador.exists():
        os.environ["YT_DLP_EXE"] = str(descargador)

    return Instalacion(base, config, registros, actas)


def nuevo_log(registros: Path, etiqueta: str = "") -> Path:
    """Un fichero de registro por ejecución; el nombre indica de qué pleno es."""
    sello = datetime.now().strftime("%Y-%m-%d_%H%M")
    sufijo = f"_pleno-{etiqueta}" if etiqueta else ""
    return registros / f"{sello}{sufijo}.log"


# ── la consola: el registro se lo queda todo, la pantalla solo lo legible ──────
# Todo el pipeline va al registro; a la pantalla solo llegan las líneas traducidas.

_TRADUCCIONES = [
    (re.compile(r"^descargando audio"), "Paso 1 de 3 · Descargando la grabación del pleno."),
    (re.compile(r"^transcribiendo con AssemblyAI"),
     "Paso 2 de 3 · Transcribiendo la grabación. Es la parte más larga."),
    (re.compile(r"^\s*subiendo el audio"), "   Enviando la grabación al servicio de transcripción."),
    # Debe ir ANTES de la entrada genérica de "va lento": ambas podrían casar.
    (re.compile(r"^\s*se cortó la subida"),
     "   El envío se ha interrumpido. Se reintenta solo: NO cierres esta ventana."),
    (re.compile(r"^\s*transcribiendo \(id "), "   Transcribiendo. Esto tarda varios minutos."),
    (re.compile(r"^\s*troceando audio|^transcribiendo \d+ fragmentos"),
     "   Usando el método alternativo de transcripción."),
    (re.compile(r"^transcripción guardada"), "   Transcripción terminada y guardada."),
    (re.compile(r"^generando acta"), "Paso 3 de 3 · Redactando el acta y revisándola."),
    (re.compile(r"→ GENERADOR"), "   Redactando el borrador del acta."),
    (re.compile(r"→ AUDITOR"), "   Revisando lo redactado contra la grabación."),
    (re.compile(r"→ CORRECTOR"), "   Corrigiendo lo que la revisión ha marcado."),
    (re.compile(r"visto bueno, sin objeciones"), "   La revisión no ha encontrado problemas."),
    (re.compile(r"devolvió (429|5\d\d)|el proveedor cortó la respuesta"),
     "   El servicio va lento ahora mismo. Se reintenta solo: NO cierres esta ventana."),
]


def traducir(linea: str, numerar: bool = True) -> str | None:
    """Línea del pipeline → frase para la funcionaria, o None si no debe verla.
    numerar=False quita el "Paso N de 3" (al rehacer el documento no hay 3 pasos)."""
    for patron, amable in _TRADUCCIONES:
        if patron.search(linea):
            return amable if numerar else re.sub(r"^Paso \d de 3 · ", "", amable)
    return None


class Consola:
    """Sustituye a sys.stdout mientras corre el pipeline: registro completo y pantalla
    traducida. Debe cumplir el contrato de un fichero de texto (isatty, encoding...)."""

    encoding = "utf-8"

    def __init__(self, ruta_log: Path, pantalla, numerar: bool = True):
        self.pantalla = pantalla
        self.numerar = numerar
        self.ruta_log = ruta_log
        self.fichero = open(ruta_log, "a", encoding="utf-8")
        self._resto = ""
        self._candado = threading.Lock()

    def write(self, texto: str) -> int:
        # El pipeline escribe por trozos: se reensamblan líneas para poder traducirlas.
        self._resto += texto
        while "\n" in self._resto:
            linea, self._resto = self._resto.split("\n", 1)
            self._linea(linea)
        return len(texto)

    def writelines(self, lineas) -> None:
        for linea in lineas:
            self.write(linea)

    def _linea(self, linea: str) -> None:
        with self._candado:
            self.fichero.write(linea + "\n")
            self.fichero.flush()
            amable = traducir(linea, self.numerar)
            if amable:
                self.pantalla.write(amable + "\n")
                self.pantalla.flush()

    def decir(self, texto: str = "") -> None:
        """Mensaje del propio asistente: a la pantalla y al registro, tal cual."""
        with self._candado:
            self.pantalla.write(texto + "\n")
            self.pantalla.flush()
            self.fichero.write(texto + "\n")
            self.fichero.flush()

    def anotar(self, texto: str) -> None:
        """Solo al registro: detalle técnico que ella no necesita ver."""
        with self._candado:
            self.fichero.write(texto + "\n")
            self.fichero.flush()

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        """El pipeline lo consulta para pintar colores ANSI; aquí no, ensuciarían el registro."""
        return False

    def cerrar(self) -> None:
        if self._resto:
            self._linea(self._resto)
            self._resto = ""
        self.fichero.close()


class Latido:
    """Imprime señales de vida: una consola muda parece colgada y se cierra."""

    def __init__(self, consola: Consola, cada: int = 60):
        self.consola, self.cada = consola, cada
        self._parar = threading.Event()

    def __enter__(self):
        self._inicio = time.monotonic()
        threading.Thread(target=self._latir, daemon=True).start()
        return self

    def _latir(self) -> None:
        while not self._parar.wait(self.cada):
            minutos = int((time.monotonic() - self._inicio) / 60)
            self.consola.decir(f"   ... sigue trabajando (llevamos {minutos} minutos)")

    def __exit__(self, *_) -> bool:
        self._parar.set()
        return False


def ejecutar_pipeline(consola: Consola, tarea):
    """Ejecuta la tarea con stdout redirigido a la consola, restaurándolo siempre."""
    anterior = sys.stdout
    sys.stdout = consola
    try:
        with Latido(consola):
            return tarea()
    finally:
        sys.stdout = anterior


# ── preguntas ─────────────────────────────────────────────────────────────────

_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def limpiar_ruta(texto: str) -> str:
    """Quita las comillas que Windows añade al arrastrar un fichero a la consola."""
    return texto.strip().strip('"').strip("'").strip()


def fecha_en_palabras(iso: str) -> str:
    """'2026-09-02' → '2 de septiembre de 2026'. Sin locale: en Windows no está garantizado."""
    anyo, mes, dia = (int(x) for x in iso.split("-"))
    return f"{dia} de {_MESES[mes - 1]} de {anyo}"


def preguntar_url(consola: Consola) -> str:
    while True:
        consola.decir("\n   Pega aquí la dirección del vídeo del pleno en YouTube.")
        consola.decir("   (cópiala del navegador con Ctrl+C y pégala aquí con Ctrl+V)")
        consola.decir("   Si la grabación está guardada en este ordenador (por ejemplo, un pleno")
        consola.decir("   en dos vídeos ya unidos), arrastra el archivo hasta aquí.")
        url = input("\n>  ").strip()
        if extraer_video_id(url):
            return url
        if Path(limpiar_ruta(url)).is_file():
            return limpiar_ruta(url)
        consola.decir("\n   Eso no parece una dirección de YouTube. Tiene que empezar")
        consola.decir("   por https://www.youtube.com/...  o por https://youtu.be/...")


def preguntar_fecha(consola: Consola, sugerida: str | None) -> str:
    """Pide la fecha a la funcionaria; la del título del vídeo es solo una sugerencia."""
    while True:
        consola.decir("\n   ¿Qué día se celebró este pleno?")
        consola.decir("   Escríbelo así:  02/09/2026   (día / mes / año)")
        if sugerida:
            consola.decir(f"   Si fue el {fecha_en_palabras(sugerida)}, pulsa Enter sin escribir nada.")
        escrito = input("\n>  ").strip()
        fecha = sugerida if (not escrito and sugerida) else normalizar_fecha(escrito)
        if not fecha:
            consola.decir("\n   No he entendido esa fecha. Escríbela como en el ejemplo: 02/09/2026")
            continue
        consola.decir(f"\n   Fecha: {fecha_en_palabras(fecha)}.")
        if input("   ¿Es correcta?  (s/n)  ").strip().lower().startswith("s"):
            return fecha


def preguntar_tipo(consola: Consola) -> str:
    """Ordinario o extraordinario: decide la carpeta, para que dos plenos del mismo día no se pisen."""
    consola.decir("\n   ¿Qué tipo de pleno es?")
    return "extraordinaria" if preguntar_opcion(consola, ["Ordinario", "Extraordinario"]) == 2 else "ordinaria"


def preguntar_convocatoria(consola: Consola) -> str | None:
    """Pide el PDF o JPEG del orden del día (opcional)."""
    while True:
        consola.decir("\n   ¿Tienes el PDF o la foto de la convocatoria (el orden del día)?")
        consola.decir("")
        consola.decir("   Es importante: de ahí salen los títulos exactos de cada punto,")
        consola.decir("   su numeración y los números de expediente. Sin él, el acta usará")
        consola.decir("   solo lo que se entienda en la grabación.")
        consola.decir("")
        consola.decir("   Arrastra el archivo (PDF, o una foto o escaneo en JPEG) hasta esta")
        consola.decir("   ventana y pulsa Enter.")
        consola.decir("   Si no lo tienes a mano, pulsa Enter sin escribir nada.")
        ruta = limpiar_ruta(input("\n>  "))
        if not ruta:
            return None
        try:
            leer_convocatoria(ruta)  # valida que existe y es PDF o JPEG
            return ruta
        except (FileNotFoundError, ValueError) as e:
            consola.anotar(f"convocatoria rechazada: {e}")
            consola.decir("\n   Ese archivo no me vale: tiene que ser un PDF o una imagen")
            consola.decir("   JPEG guardada en este ordenador.")


def preguntar_intervinientes(consola: Consola) -> list[dict] | None:
    """Pregunta quién interviene y cómo lo llaman en la sala (opcional: Enter la salta)."""
    consola.decir("\n   ¿Quieres decirme quién interviene en este pleno?")
    consola.decir("")
    consola.decir("   Me ayuda a escribir bien los nombres y a saber a quién se refieren")
    consola.decir("   cuando dicen, por ejemplo, «Chari». En el acta se seguirá usando el")
    consola.decir("   nombre oficial completo.")
    consola.decir("")
    consola.decir("   Escribe el nombre completo de una persona y pulsa Enter. Te")
    consola.decir("   preguntaré cómo la llaman en el pleno. Cuando hayas terminado, pulsa")
    consola.decir("   Enter sin escribir nada. Si no quieres hacerlo, pulsa Enter ahora.")
    personas: list[dict] = []
    while True:
        nombre = input("\n   Nombre completo:  ").strip()
        if not nombre:
            break
        apodos = input(f"   ¿Cómo llaman a {nombre} en el pleno? (Enter si por su nombre):  ").strip()
        personas.append({"nombre": nombre,
                         "apodos": [a.strip() for a in apodos.split(",") if a.strip()]})
        consola.anotar(f"interviniente: {nombre} · apodos={apodos or '—'}")
    return personas or None


def preguntar_grabacion_local(consola: Consola) -> str | None:
    """Alternativa cuando YouTube bloquea la descarga; AssemblyAI acepta vídeo tal cual."""
    consola.decir("\n   Si tienes la grabación guardada en este ordenador, arrástrala")
    consola.decir("   hasta esta ventana y pulsa Enter, y sigo con ella.")
    consola.decir("   Si no la tienes, pulsa Enter sin escribir nada.")
    ruta = limpiar_ruta(input("\n>  "))
    if not ruta:
        return None
    if not Path(ruta).exists():
        consola.decir("\n   No encuentro ese archivo.")
        return None
    return ruta


def preguntar_opcion(consola: Consola, opciones: list[str]) -> int:
    """Menú numerado. Devuelve el número elegido, de 1 en adelante."""
    while True:
        consola.decir("")
        for i, texto in enumerate(opciones, 1):
            consola.decir(f"   {i}  {texto}")
        elegido = input("\n>  ").strip()
        if elegido.isdigit() and 1 <= int(elegido) <= len(opciones):
            return int(elegido)
        consola.decir(f"\n   Escribe un número del 1 al {len(opciones)}.")


# ── el final: ¿puedo sellar esto o no? ────────────────────────────────────────

def abrir_carpeta(consola: Consola, carpeta: Path) -> None:
    """Le abre la carpeta del pleno para que no tenga que ir a buscarla."""
    try:
        os.startfile(str(carpeta))  # solo Windows, que es donde se usa esto
    except Exception as e:
        consola.anotar(f"no se pudo abrir la carpeta {carpeta}: {e}")


def _anunciar_guia(consola: Consola, resultado) -> None:
    """Anuncia la guía HTML de verificación, si se compuso, y para qué sirve."""
    if resultado.ruta_guia is None:
        return
    consola.decir("\n    También se ha creado una guía de verificación, en un")
    consola.decir(f"    archivo aparte:  {resultado.ruta_guia.name}")
    consola.decir("    Ábrela con doble clic (se abre en el navegador). Dice en qué")
    consola.decir("    minuto de la grabación está cada punto del orden del día, y esos")
    consola.decir("    minutos son enlaces: al pulsarlos, el vídeo salta directo a ese")
    consola.decir("    momento, sin tener que buscarlo a mano.")
    consola.decir("    Ojo: esa guía NO es el acta, es solo la ayuda para comprobarla.")


def reintentar_acta(consola: Consola, resultado, fecha: str):
    """El .docx no se pudo escribir (casi siempre abierto en Word): lo recompone desde
    el informe guardado, sin LLM ni coste. Devuelve el resultado actualizado o el mismo."""
    consola.decir("\n    El acta está redactada, pero el archivo de Word no se ha podido")
    consola.decir("    guardar. Casi siempre es porque el documento de este pleno está")
    consola.decir("    abierto en Word.")
    consola.decir(f"\n    Detalle técnico: {resultado.fallo_acta}")
    while True:
        consola.decir("\n    Ciérralo si lo tienes abierto y lo intento otra vez. Esto es")
        consola.decir("    instantáneo: no vuelve a redactar nada.")
        if not input("\n   ¿Lo intento ahora?  (s/n)  ").strip().lower().startswith("s"):
            return resultado
        if ejecutar_pipeline(consola, lambda: _rehacer_acta(resultado.carpeta.name)) == 0:
            acta = next(iter(sorted(resultado.carpeta.glob(f"{fecha}-acta-*.docx"))), None)
            if acta:
                return resultado._replace(ruta_acta=acta, fallo_acta="")
        consola.decir("\n    Sigue sin poder guardarse.")


def pantalla_final(consola: Consola, resultado, fecha: str, ruta_log: Path) -> None:
    """Lo último que queda en pantalla: si esto se puede sellar o no."""
    raya = "  " + "═" * 56

    # Aquí y no en los flujos, para que valga al crear y al rehacer.
    if resultado.ruta_acta is None and resultado.fallo_acta:
        resultado = reintentar_acta(consola, resultado, fecha)

    consola.decir("\n" + raya)

    if resultado.ruta_acta is None:
        consola.decir("    NO SE HA PODIDO CREAR EL DOCUMENTO")
        consola.decir(raya)
        consola.decir("\n    La transcripción sí se ha guardado: no se ha perdido nada")
        consola.decir("    ni hay que empezar de cero.")
        if resultado.fallo_acta:
            # La opción 2 NO sirve aquí (repetiría el modelo y cobraría): se deriva al responsable.
            consola.decir("\n    Motivo: el archivo de Word no se ha podido guardar, aunque")
            consola.decir("    el acta sí está redactada y guardada por dentro.")
            consola.decir(f"\n    Detalle técnico: {resultado.fallo_acta}")
            consola.decir("\n    Qué puedes hacer:")
            consola.decir("      · El acta no se ha perdido: en cuanto ese documento no")
            consola.decir("        esté abierto, se puede recuperar sin repetir nada.")
            consola.decir(f"      · Avisa a {RESPONSABLE} y envíale este")
            consola.decir(f"        archivo:\n        {ruta_log}")
        else:
            consola.decir("\n    Motivo: en la grabación no se dice si el pleno era ordinario")
            consola.decir("    o extraordinario, y de eso depende el modelo de acta.")
            consola.decir("\n    Qué puedes hacer:")
            consola.decir("      · Usa la opción 2 del menú y aporta el PDF de la convocatoria:")
            consola.decir("        ahí consta el tipo de sesión. Tarda unos 5 minutos.")
            consola.decir(f"      · Si ya lo hiciste con la convocatoria, avisa a {RESPONSABLE}")
            consola.decir(f"        y envíale este archivo:\n        {ruta_log}")
        abrir_carpeta(consola, resultado.carpeta)
        return

    avisos = _avisos_legibles(resultado.pendientes, resultado.objeciones)
    aviso = escribir_comprobaciones(resultado.carpeta, fecha, resultado.pendientes,
                                    resultado.objeciones)
    if aviso is None:
        consola.decir("    EL ACTA ESTÁ LISTA")
        consola.decir(raya)
        consola.decir(f"\n    Pleno del {fecha_en_palabras(fecha)}")
        consola.decir(f"    Documento:  {resultado.ruta_acta.name}")
        consola.decir("\n    El revisor automático no ha marcado ningún punto dudoso.")
    else:
        consola.decir(f"    EL ACTA ESTÁ LISTA, PERO HAY {len(avisos)} PUNTOS QUE COMPROBAR")
        consola.decir(raya)
        consola.decir(f"\n    Pleno del {fecha_en_palabras(fecha)}")
        consola.decir(f"    Documento:  {resultado.ruta_acta.name}")
        consola.decir("\n    El revisor automático no ha podido dar por seguras estas")
        consola.decir(f"    {len(avisos)} frases. Compruébalas escuchando la grabación antes")
        consola.decir("    de sellar el acta:\n")
        for i, av in enumerate(avisos, 1):
            for linea in _lineas_aviso(i, av, con_enlace=False):
                consola.decir(f"    {linea}" if linea else "")
        consola.decir("    Las tienes también en este archivo, por si cierras la ventana:")
        consola.decir(f"       {aviso}")

    _anunciar_guia(consola, resultado)

    consola.decir("\n    RECUERDA: esto es un BORRADOR. Revísalo y complétalo")
    consola.decir("    como haces siempre antes de sellarlo.")
    consola.decir(f"\n    Está aquí:  {resultado.carpeta}")
    abrir_carpeta(consola, resultado.carpeta)


# ── flujo 1: crear el acta de un pleno nuevo ──────────────────────────────────

AVISO_DURACION = """
   ESTO PUEDE TARDAR HASTA UNA HORA, SEGÚN LO QUE DURE EL PLENO.

   Puedes dejar el ordenador trabajando y volver más tarde, pero
   NO cierres esta ventana: si la cierras, se para todo.

   Mientras trabaja irá contando por dónde va. Es normal que aparezca
   algún aviso de que el servicio va lento: el programa lo reintenta
   solo y sigue por su cuenta. No tienes que hacer nada.
"""


def actualizar_descargador(consola: Consola) -> None:
    """Actualiza yt-dlp antes de descargar (YouTube lo rompe cada pocos meses). Si falla, sigue."""
    exe = os.environ.get("YT_DLP_EXE")
    if not exe:
        return
    consola.decir("   Comprobando si hay una versión nueva del descargador...")
    try:
        salida = subprocess.run([exe, "-U"], capture_output=True, text=True, timeout=180)
        consola.anotar(f"yt-dlp -U: {salida.stdout.strip()} {salida.stderr.strip()}")
    except Exception as e:
        consola.anotar(f"no se pudo actualizar yt-dlp: {e}")


def flujo_pleno_nuevo(inst: Instalacion, pantalla) -> None:
    consola_previa = Consola(nuevo_log(inst.registros), pantalla)
    url = preguntar_url(consola_previa)
    local = None if extraer_video_id(url) else url  # archivo en el ordenador, sin YouTube
    titulo = ""
    if not local:
        try:
            titulo = _titulo_de_youtube(url)
            consola_previa.decir(f"\n   He encontrado este vídeo:\n      «{titulo}»")
        except Exception as e:
            consola_previa.anotar(f"no se pudo leer el título del vídeo: {e}")
    fecha = preguntar_fecha(consola_previa, extraer_fecha(titulo, "") or None)
    if not titulo:
        titulo = f"Pleno del {fecha_en_palabras(fecha)}"
    tipo = preguntar_tipo(consola_previa)
    clave = clave_pleno(fecha, tipo)
    consola_previa.cerrar()

    # Nuevo registro con la fecha ya conocida.
    consola = Consola(nuevo_log(inst.registros, clave), pantalla)
    consola.anotar(f"pleno nuevo · url={url} · título={titulo} · fecha={fecha} · tipo={tipo}")

    carpeta = dir_borrador(clave)
    if carpeta.exists():
        consola.decir(f"\n   Ya hay un pleno {'extraordinario' if tipo == 'extraordinaria' else 'ordinario'} guardado con esa fecha.")
        opcion = preguntar_opcion(consola, [
            "Volver a generar solo el documento  (rápido, no vuelve a transcribir)",
            "Empezar de cero y sustituirlo       (hasta 1 hora, según lo que dure el pleno)",
            "Cancelar y volver al menú",
        ])
        if opcion == 1:
            consola.cerrar()
            rehacer_pleno(inst, pantalla, clave)
            return
        if opcion == 3:
            consola.decir("\n   No se ha hecho nada.")
            consola.cerrar()
            return

    pdf = preguntar_convocatoria(consola)
    intervinientes = preguntar_intervinientes(consola)
    consola.decir(AVISO_DURACION)
    if not input("   ¿Empezamos?  (s/n)  ").strip().lower().startswith("s"):
        consola.decir("\n   No se ha hecho nada.")
        consola.cerrar()
        return

    convocatoria = leer_convocatoria(pdf)
    video_id = extraer_video_id(url)
    if not local:
        actualizar_descargador(consola)
    consola.decir("")

    def tarea(fuente=local):
        return procesar_pleno(fuente, video_id, titulo, fecha, None if local else url,
                              convocatoria=convocatoria, intervinientes=intervinientes,
                              tipo=tipo)

    try:
        try:
            resultado = ejecutar_pipeline(consola, tarea)
        except ErrorDeDescarga as e:
            consola.anotar(f"fallo de descarga: {e}")
            consola.decir("\n   No he podido descargar el vídeo de YouTube.")
            grabacion = preguntar_grabacion_local(consola)
            if not grabacion:
                consola.decir(f"\n   Avisa a {RESPONSABLE} y envíale este archivo:")
                consola.decir(f"   {consola.ruta_log}")
                return
            resultado = ejecutar_pipeline(consola, lambda: tarea(grabacion))
        pantalla_final(consola, resultado, fecha, consola.ruta_log)
    except Exception:
        # La traza va al registro; en pantalla solo una frase.
        consola.anotar(traceback.format_exc())
        consola.decir("\n   Ha ocurrido un problema y no he podido terminar el acta.")
        consola.decir("   Si la transcripción llegó a hacerse, está guardada: la opción 2")
        consola.decir("   del menú vuelve a intentarlo sin repetir la transcripción.")
        consola.decir(f"   Avisa a {RESPONSABLE} y envíale este archivo:")
        consola.decir(f"   {consola.ruta_log}")
    finally:
        consola.cerrar()


# ── flujo 2: volver a generar el documento de un pleno ya hecho ───────────────

def plenos_guardados(actas: Path) -> list[tuple[str, str]]:
    """[(clave, título)] de los plenos ya procesados, del más reciente al más antiguo."""
    salida: list[tuple[str, str]] = []
    if not actas.exists():
        return salida
    for carpeta in sorted(actas.iterdir(), reverse=True):
        if not (carpeta.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}(-extraordinario)?", carpeta.name)):
            continue
        titulo = ""
        entrada = carpeta / "entrada.json"
        if entrada.exists():
            try:
                titulo = json.loads(entrada.read_text(encoding="utf-8")).get("titulo", "")
            except (json.JSONDecodeError, OSError):
                pass  # un borrador a medias no puede impedir listar el resto
        salida.append((carpeta.name, titulo))
    return salida


def rehacer_pleno(inst: Instalacion, pantalla, clave: str) -> None:
    """Rehace el documento desde la transcripción guardada, sin descargar ni transcribir."""
    fecha = clave[:10]
    consola = Consola(nuevo_log(inst.registros, clave), pantalla, numerar=False)
    consola.anotar(f"rehacer informe · pleno={clave}")

    # Repetir sin convocatoria da lo mismo (temperatura 0) si faltaba el tipo de sesión.
    pdf = None
    if not (dir_borrador(clave) / f"{fecha}-convocatoria.pdf").exists():
        pdf = preguntar_convocatoria(consola)

    intervinientes = None
    try:
        guardados = json.loads((dir_borrador(clave) / "entrada.json")
                               .read_text(encoding="utf-8")).get("intervinientes")
    except (OSError, json.JSONDecodeError):
        guardados = None
    if not guardados:
        intervinientes = preguntar_intervinientes(consola)

    consola.decir("\n   Vuelvo a redactar el documento a partir de la transcripción")
    consola.decir("   que ya está guardada. No descargo el vídeo ni lo transcribo otra")
    consola.decir("   vez: son unos 5 minutos.\n")

    try:
        resultado = ejecutar_pipeline(consola, lambda: _rehacer_informe(clave, pdf, intervinientes))
        if resultado is None:
            consola.decir("\n   No he podido rehacer ese pleno: le falta la transcripción.")
            consola.decir(f"   Avisa a {RESPONSABLE} y envíale este archivo:")
            consola.decir(f"   {consola.ruta_log}")
            return
        pantalla_final(consola, resultado, fecha, consola.ruta_log)
    except Exception:
        # Igual que en flujo_pleno_nuevo: sin mensaje ni registro cerrado el programa moriría.
        consola.anotar(traceback.format_exc())
        consola.decir("\n   Ha ocurrido un problema y no he podido terminar el documento.")
        consola.decir("   Si la transcripción llegó a hacerse, está guardada: la opción 2")
        consola.decir("   del menú vuelve a intentarlo sin repetir la transcripción.")
        consola.decir(f"   Avisa a {RESPONSABLE} y envíale este archivo:")
        consola.decir(f"   {consola.ruta_log}")
    finally:
        consola.cerrar()


def flujo_rehacer(inst: Instalacion, pantalla) -> None:
    consola = Consola(nuevo_log(inst.registros), pantalla)
    plenos = plenos_guardados(inst.actas)
    if not plenos:
        consola.decir("\n   Todavía no hay ningún pleno guardado en este ordenador.")
        consola.cerrar()
        return
    consola.decir("\n   ¿De qué pleno quieres volver a generar el documento?")
    etiquetas = [f"{fecha_en_palabras(c[:10])}{'  (extraordinario)' if len(c) > 10 else ''}   {t}"
                 for c, t in plenos] + ["Volver al menú"]
    elegido = preguntar_opcion(consola, etiquetas)
    consola.cerrar()
    if elegido <= len(plenos):
        rehacer_pleno(inst, pantalla, plenos[elegido - 1][0])


# ── menú ──────────────────────────────────────────────────────────────────────

def mostrar_instrucciones(inst: Instalacion, consola: Consola) -> None:
    """Muestra el LEEME en pantalla."""
    # .upper() no quita la tilde de "LÉEME", de ahí el replace.
    ruta = next((p for p in inst.base.glob("*.txt")
                 if "EEME" in p.name.upper().replace("É", "E")), None)
    if ruta is None:
        ruta = Path(__file__).resolve().parent / "asistente" / "LEEME.txt"
    if ruta.exists():
        consola.decir("\n" + ruta.read_text(encoding="utf-8"))
    else:
        consola.decir(f"\n   No encuentro el archivo de instrucciones. Avisa a {RESPONSABLE}.")


def main() -> int:
    pantalla = sys.stdout
    inst = preparar_instalacion()
    faltan = [c for c in CLAVES_NECESARIAS if not os.environ.get(c)]
    if faltan:
        print("\n   El programa todavía no está configurado.")
        print(f"   Avisa a {RESPONSABLE}: faltan las claves de acceso a los servicios.")
        print(f"   (detalle técnico: {', '.join(faltan)} en {inst.config / 'configuracion.env'})")
        input("\n   Pulsa Enter para cerrar.  ")
        return 1

    while True:
        consola = Consola(nuevo_log(inst.registros), pantalla)
        consola.decir("\n" + "  " + "═" * 56)
        consola.decir("    ACTAS DE PLENOS · AYUNTAMIENTO DE ENGUÍDANOS")
        consola.decir("  " + "═" * 56)
        opcion = preguntar_opcion(consola, [
            "Crear el acta de un pleno nuevo",
            "Volver a generar el documento de un pleno ya hecho",
            "Ver las instrucciones",
            "Salir",
        ])
        if opcion == 3:
            mostrar_instrucciones(inst, consola)
        consola.cerrar()

        if opcion == 1:
            flujo_pleno_nuevo(inst, pantalla)
        elif opcion == 2:
            flujo_rehacer(inst, pantalla)
        elif opcion == 4:
            return 0
        input("\n   Pulsa Enter para volver al menú.  ")


if __name__ == "__main__":
    try:
        _codigo = main()
    except KeyboardInterrupt:
        print("\n\n   Cancelado.")
        _codigo = 1
    except Exception:
        # Si el fallo original fue en preparar_instalacion, esta llamada también puede
        # fallar: último recurso, traza por pantalla.
        try:
            _inst = preparar_instalacion()
            _ruta = nuevo_log(_inst.registros, "error")
            _ruta.write_text(traceback.format_exc(), encoding="utf-8")
            print("\n   Ha ocurrido un problema y el programa no puede continuar.")
            print(f"   Avisa a {RESPONSABLE} y envíale este archivo:")
            print(f"   {_ruta}")
        except Exception:
            print("\n   Ha ocurrido un problema y el programa no puede continuar.")
            print(f"   Avisa a {RESPONSABLE} y copia el mensaje de abajo:\n")
            print(traceback.format_exc())
        _codigo = 1
    input("\n   Pulsa Enter para cerrar.  ")
    sys.exit(_codigo)
