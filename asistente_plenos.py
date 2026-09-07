#!/usr/bin/env python3
"""
asistente_plenos.py - Asistente guiado para generar el acta de un pleno.

Es el punto de entrada del ejecutable que usa la funcionaria del Ayuntamiento:
pregunta, valida y llama al pipeline de procesar_pleno.py. No duplica nada de la
lógica del pipeline; solo la expone sin terminal y sin jerga.

Se ejecuta de dos formas:
  · empaquetado con PyInstaller — lo normal en el PC del Ayuntamiento
  · python scripts/asistente_plenos.py — para desarrollar y probar
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

# Windows abre la consola con su codepage regional (cp1252 en España) y ahí los acentos
# de nuestros mensajes salen como "todavÃ­a". Reconfigurar sys.stdout a UTF-8 no basta:
# hay que decírselo también a la consola. Sin esto, la funcionaria ve rota cada frase.
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass  # sin consola propia (salida redirigida a fichero): nada que ajustar

# UTF-8 en Windows: sin esto, un acento en un mensaje aborta la ejecución.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Al ejecutarse desde el repo, los módulos del pipeline están en esta misma carpeta.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from procesar_pleno import (ErrorDeDescarga, dir_borrador, extraer_fecha,
                            extraer_video_id, leer_convocatoria, procesar_pleno,
                            _rehacer_informe, _titulo_de_youtube)
from plenos_informe import normalizar_fecha
# El aviso "COMPROBAR ANTES DE SELLAR.txt" vive en plenos_guia.py, no aquí: depende
# del mismo formato de objeción que objecion_legible, y procesar_pleno lo escribe
# también en --rehacer-acta, sin pasar por este asistente.
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
    """La carpeta de la instalación: la del .exe si está empaquetado, la raíz del
    repo si no. Dentro del .exe no vale __file__: apunta a una carpeta temporal
    que Windows borra al salir, así que nada de lo que se guarde ahí sobrevive."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def cargar_configuracion(config: Path) -> list[str]:
    """Lee configuracion.env y devuelve las claves de API que falten.

    Las claves viven en un fichero de texto y no en variables de entorno del
    sistema porque el día que se pasen a las cuentas del Ayuntamiento hay que
    poder cambiarlas con el Bloc de notas, sin reconstruir el ejecutable."""
    ruta = config / "configuracion.env"
    if ruta.exists():
        from dotenv import load_dotenv
        # El Bloc de notas de Windows guarda con BOM, y así es como se va a editar
        # este fichero en el Ayuntamiento cuando lleguen las claves. Sin
        # utf-8-sig, el BOM se pega a la primera clave del fichero
        # ("﻿ASSEMBLYAI_API_KEY" en vez de "ASSEMBLYAI_API_KEY") y esa clave se
        # pierde en silencio: el programa diría "todavía no está configurado"
        # aunque la clave estuviera bien escrita.
        load_dotenv(ruta, override=True, encoding="utf-8-sig")
    return [c for c in CLAVES_NECESARIAS if not os.environ.get(c)]


def preparar_instalacion() -> Instalacion:
    """Resuelve las carpetas, crea las que falten y deja el entorno listo para
    que el pipeline escriba donde toca."""
    base = carpeta_base()
    config = base / DIR_CONFIG
    config.mkdir(parents=True, exist_ok=True)
    cargar_configuracion(config)

    if os.environ.get("ACTAS_DIR"):
        actas = Path(os.environ["ACTAS_DIR"])
    elif getattr(sys, "frozen", False):
        actas = base / DIR_ACTAS
    else:
        # Desde el repo se respeta la carpeta de siempre del desarrollador.
        actas = base / "uploads" / "actas"
    actas.mkdir(parents=True, exist_ok=True)
    os.environ["ACTAS_DIR"] = str(actas)  # lo lee procesar_pleno.dir_borrador

    registros = config / "registros"
    registros.mkdir(parents=True, exist_ok=True)

    # El yt-dlp.exe incluido solo existe en la instalación empaquetada; desde el
    # repo se usa el de pip, que es el que el desarrollador ya mantiene.
    descargador = config / "yt-dlp.exe"
    if descargador.exists():
        os.environ["YT_DLP_EXE"] = str(descargador)

    return Instalacion(base, config, registros, actas)


def nuevo_log(registros: Path, etiqueta: str = "") -> Path:
    """Un fichero de registro por ejecución. Es lo que la funcionaria envía
    cuando algo falla, así que el nombre tiene que decir de qué pleno es."""
    sello = datetime.now().strftime("%Y-%m-%d_%H%M")
    sufijo = f"_pleno-{etiqueta}" if etiqueta else ""
    return registros / f"{sello}{sufijo}.log"


# ── la consola: el registro se lo queda todo, la pantalla solo lo legible ──────
# El pipeline imprime cientos de líneas pensadas para el desarrollador. Enseñárselas
# a la funcionaria sería ruido; ocultarlas sin guardarlas dejaría sin diagnóstico el
# día que algo falle. Así que van enteras al registro y traducidas a la pantalla.

_TRADUCCIONES = [
    (re.compile(r"^descargando audio"), "Paso 1 de 3 · Descargando la grabación del pleno."),
    (re.compile(r"^transcribiendo con AssemblyAI"),
     "Paso 2 de 3 · Transcribiendo la grabación. Es la parte más larga."),
    (re.compile(r"^\s*subiendo el audio"), "   Enviando la grabación al servicio de transcripción."),
    # El envío de un pleno entero (100-200 MB) puede cortarse a mitad; _subir_audio
    # ya lo reintenta solo. Tiene que ir ANTES de la entrada genérica de "va lento"
    # porque ambas podrían casar con líneas parecidas de reintento.
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
    # El 504 "Upstream idle timeout" ya lo reintenta solo _peticion: lo único que
    # falta es que ella no lo lea como un error suyo ni cierre la ventana.
    (re.compile(r"devolvió (429|5\d\d)|el proveedor cortó la respuesta"),
     "   El servicio va lento ahora mismo. Se reintenta solo: NO cierres esta ventana."),
]


def traducir(linea: str, numerar: bool = True) -> str | None:
    """Línea del pipeline → frase para la funcionaria, o None si no debe verla.
    Lo que no se traduce no se pierde: va entero al registro.

    numerar=False al rehacer el documento: ahí no hay descarga ni transcripción, y
    un "paso 3 de 3" como paso único sería desconcertante."""
    for patron, amable in _TRADUCCIONES:
        if patron.search(linea):
            return amable if numerar else re.sub(r"^Paso \d de 3 · ", "", amable)
    return None


class Consola:
    """Sustituye a sys.stdout mientras corre el pipeline. El pipeline es código
    ajeno que puede tocar cualquier miembro del contrato habitual de un fichero de
    texto (isatty, encoding, writelines...), no solo write/flush: el fallo de
    isatty no fue mala suerte, fue que esta clase no lo cumplía del todo."""

    encoding = "utf-8"

    def __init__(self, ruta_log: Path, pantalla, numerar: bool = True):
        self.pantalla = pantalla
        self.numerar = numerar
        self.ruta_log = ruta_log
        self.fichero = open(ruta_log, "a", encoding="utf-8")
        self._resto = ""
        self._candado = threading.Lock()

    def write(self, texto: str) -> int:
        # El pipeline escribe por trozos, no por líneas: hay que reensamblarlas o
        # el traductor no reconocería ningún patrón.
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
        """El pipeline pregunta esto para decidir si pinta colores ANSI. Aquí la
        respuesta es no: lo que sale por pantalla ya viene filtrado y traducido, y
        en el registro los códigos de color solo ensuciarían el fichero que la
        funcionaria nos acaba enviando. Sin este método, `_hay_color()` revienta al
        final de cada ejecución, con el acta ya escrita."""
        return False

    def cerrar(self) -> None:
        if self._resto:
            self._linea(self._resto)
            self._resto = ""
        self.fichero.close()


class Latido:
    """Da señales de vida mientras el pipeline trabaja. Veinte minutos de consola
    muda parecen un programa colgado, y lo que hace alguien ante un programa
    colgado es cerrarlo."""

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
    """Ejecuta la tarea con la salida del pipeline redirigida a la consola amable.
    El sys.stdout original se restaura pase lo que pase: sin eso, un fallo dejaría
    a las preguntas siguientes escribiendo en el registro en vez de en pantalla."""
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
    """Arrastrar un fichero a la consola pega su ruta, y Windows la envuelve entre
    comillas. Es la forma menos técnica de pedir un archivo a alguien que no
    sabría escribir una ruta a mano."""
    return texto.strip().strip('"').strip("'").strip()


def fecha_en_palabras(iso: str) -> str:
    """'2026-09-02' → '2 de septiembre de 2026'. A mano y no con locale: en Windows
    el locale español no está garantizado y el mes saldría en inglés."""
    anyo, mes, dia = (int(x) for x in iso.split("-"))
    return f"{dia} de {_MESES[mes - 1]} de {anyo}"


def preguntar_url(consola: Consola) -> str:
    while True:
        consola.decir("\n   Pega aquí la dirección del vídeo del pleno en YouTube.")
        consola.decir("   (cópiala del navegador con Ctrl+C y pégala aquí con Ctrl+V)")
        url = input("\n>  ").strip()
        if extraer_video_id(url):
            return url
        consola.decir("\n   Eso no parece una dirección de YouTube. Tiene que empezar")
        consola.decir("   por https://www.youtube.com/...  o por https://youtu.be/...")


def preguntar_fecha(consola: Consola, sugerida: str | None) -> str:
    """La escribe ella. Deducirla del título del vídeo es lo frágil del proceso, y
    un error de un dedo acabaría en el nombre de la carpeta y en el encabezado de
    un documento que se sella."""
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


def preguntar_convocatoria(consola: Consola) -> str | None:
    """El orden del día. Manda en la forma —títulos, numeración, expedientes y tipo
    de sesión— mientras la grabación manda en el fondo."""
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
            leer_convocatoria(ruta)  # valida que existe y que es un PDF o una imagen JPEG
            return ruta
        except (FileNotFoundError, ValueError) as e:
            consola.anotar(f"convocatoria rechazada: {e}")
            consola.decir("\n   Ese archivo no me vale: tiene que ser un PDF o una imagen")
            consola.decir("   JPEG guardada en este ordenador.")


def preguntar_grabacion_local(consola: Consola) -> str | None:
    """Salida cuando YouTube no deja descargar el vídeo. AssemblyAI acepta vídeo
    además de audio, así que sirve el fichero tal cual, sin convertir nada."""
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
# texto_comprobaciones, escribir_comprobaciones y sus dos ayudantes (_avisos_legibles,
# _lineas_aviso) viven en plenos_guia.py (importados arriba): ver el comentario junto
# a ese import.

def abrir_carpeta(consola: Consola, carpeta: Path) -> None:
    """Le abre la carpeta del pleno para que no tenga que ir a buscarla."""
    try:
        os.startfile(str(carpeta))  # solo Windows, que es donde se usa esto
    except Exception as e:
        consola.anotar(f"no se pudo abrir la carpeta {carpeta}: {e}")


def _anunciar_guia(consola: Consola, resultado) -> None:
    """La guía de verificación HTML, si se pudo componer. Explica para qué sirve,
    no solo que existe: sin eso, "hay un archivo más" no le dice a la funcionaria
    por qué merece abrirlo antes de escuchar tres horas de grabación a ciegas."""
    if resultado.ruta_guia is None:
        return
    consola.decir("\n    También se ha creado una guía de verificación, en un")
    consola.decir(f"    archivo aparte:  {resultado.ruta_guia.name}")
    consola.decir("    Ábrela con doble clic (se abre en el navegador). Dice en qué")
    consola.decir("    minuto de la grabación está cada punto del orden del día, y esos")
    consola.decir("    minutos son enlaces: al pulsarlos, el vídeo salta directo a ese")
    consola.decir("    momento, sin tener que buscarlo a mano.")
    consola.decir("    Ojo: esa guía NO es el acta, es solo la ayuda para comprobarla.")


def pantalla_final(consola: Consola, resultado, fecha: str, ruta_log: Path) -> None:
    """Lo último que queda en pantalla: si esto se puede sellar o no."""
    raya = "  " + "═" * 56
    consola.decir("\n" + raya)

    if resultado.ruta_acta is None:
        # Sin tipo de sesión no hay plantilla que elegir, y elegirla a ciegas daría
        # un encabezado equivocado en un documento que se sella.
        consola.decir("    NO SE HA PODIDO CREAR EL DOCUMENTO")
        consola.decir(raya)
        consola.decir("\n    La transcripción sí se ha guardado: no se ha perdido nada")
        consola.decir("    ni hay que empezar de cero.")
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

    # Hasta en el mejor caso: lo que se genera es un borrador, nunca el documento
    # oficial. Lo oficial es lo que ella revisa, completa y sella.
    consola.decir("\n    RECUERDA: esto es un BORRADOR. Revísalo y complétalo")
    consola.decir("    como haces siempre antes de sellarlo.")
    consola.decir(f"\n    Está aquí:  {resultado.carpeta}")
    abrir_carpeta(consola, resultado.carpeta)


# ── flujo 1: crear el acta de un pleno nuevo ──────────────────────────────────

AVISO_DURACION = """
   ESTO VA A TARDAR UNOS 20 MINUTOS.

   Puedes dejar el ordenador trabajando y volver más tarde, pero
   NO cierres esta ventana: si la cierras, se para todo.

   Mientras trabaja irá contando por dónde va. Es normal que aparezca
   algún aviso de que el servicio va lento: el programa lo reintenta
   solo y sigue por su cuenta. No tienes que hacer nada.
"""


def actualizar_descargador(consola: Consola) -> None:
    """yt-dlp deja de funcionar cada pocos meses, cuando YouTube cambia algo. El
    binario oficial sabe actualizarse solo, así que se le pide antes de cada
    descarga: unos segundos una vez al mes, y nadie se queda tirado esperando a
    que le manden un ejecutable nuevo. Si falla, seguimos con lo que haya."""
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
    try:
        titulo = _titulo_de_youtube(url)
        consola_previa.decir(f"\n   He encontrado este vídeo:\n      «{titulo}»")
    except Exception as e:
        consola_previa.anotar(f"no se pudo leer el título del vídeo: {e}")
        titulo = ""
    fecha = preguntar_fecha(consola_previa, extraer_fecha(titulo, "") or None)
    if not titulo:
        titulo = f"Pleno del {fecha_en_palabras(fecha)}"
    consola_previa.cerrar()

    # El registro se renombra por pleno una vez que sabemos la fecha: es lo que
    # ella envía si algo falla, y tiene que decir de qué pleno es.
    consola = Consola(nuevo_log(inst.registros, fecha), pantalla)
    consola.anotar(f"pleno nuevo · url={url} · título={titulo} · fecha={fecha}")

    carpeta = dir_borrador(fecha)
    if carpeta.exists():
        consola.decir("\n   Ya hay un pleno guardado con esa fecha.")
        opcion = preguntar_opcion(consola, [
            "Volver a generar solo el documento  (rápido, no vuelve a transcribir)",
            "Empezar de cero y sustituirlo       (tarda 20 minutos)",
            "Cancelar y volver al menú",
        ])
        if opcion == 1:
            consola.cerrar()
            rehacer_pleno(inst, pantalla, fecha)
            return
        if opcion == 3:
            consola.decir("\n   No se ha hecho nada.")
            consola.cerrar()
            return

    pdf = preguntar_convocatoria(consola)
    consola.decir(AVISO_DURACION)
    if not input("   ¿Empezamos?  (s/n)  ").strip().lower().startswith("s"):
        consola.decir("\n   No se ha hecho nada.")
        consola.cerrar()
        return

    convocatoria = leer_convocatoria(pdf)
    video_id = extraer_video_id(url)
    actualizar_descargador(consola)
    consola.decir("")

    def tarea(fuente=None):
        return procesar_pleno(fuente, video_id, titulo, fecha, url,
                              convocatoria=convocatoria)

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
        # Ella no puede acabar viendo una traza de Python: el detalle entero va al
        # registro, que es lo que nos enviará, y en pantalla queda una frase y a
        # quién avisar.
        consola.anotar(traceback.format_exc())
        consola.decir("\n   Ha ocurrido un problema y no he podido terminar el acta.")
        consola.decir("   Si la transcripción llegó a hacerse, está guardada: la opción 2")
        consola.decir("   del menú vuelve a intentarlo sin repetir los 20 minutos.")
        consola.decir(f"   Avisa a {RESPONSABLE} y envíale este archivo:")
        consola.decir(f"   {consola.ruta_log}")
    finally:
        consola.cerrar()


# ── flujo 2: volver a generar el documento de un pleno ya hecho ───────────────

def plenos_guardados(actas: Path) -> list[tuple[str, str]]:
    """[(fecha, título)] de los plenos ya procesados, del más reciente al más
    antiguo. Así elige por número y no tiene que teclear fechas."""
    salida: list[tuple[str, str]] = []
    if not actas.exists():
        return salida
    for carpeta in sorted(actas.iterdir(), reverse=True):
        if not (carpeta.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", carpeta.name)):
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


def rehacer_pleno(inst: Instalacion, pantalla, fecha: str) -> None:
    """Vuelve a redactar el documento desde la transcripción ya guardada. No
    descarga ni transcribe otra vez: es la parte cara y ya está pagada."""
    consola = Consola(nuevo_log(inst.registros, fecha), pantalla, numerar=False)
    consola.anotar(f"rehacer informe · fecha={fecha}")

    # Si el modelo no pudo determinar el tipo de sesión, repetir sin más devuelve
    # exactamente lo mismo (temperatura 0, misma transcripción). La convocatoria es
    # lo único que aporta el dato que falta.
    pdf = None
    if not (dir_borrador(fecha) / f"{fecha}-convocatoria.pdf").exists():
        pdf = preguntar_convocatoria(consola)

    consola.decir("\n   Vuelvo a redactar el documento a partir de la transcripción")
    consola.decir("   que ya está guardada. No descargo el vídeo ni lo transcribo otra")
    consola.decir("   vez: son unos 5 minutos.\n")

    try:
        resultado = ejecutar_pipeline(consola, lambda: _rehacer_informe(fecha, pdf))
        if resultado is None:
            consola.decir("\n   No he podido rehacer ese pleno: le falta la transcripción.")
            consola.decir(f"   Avisa a {RESPONSABLE} y envíale este archivo:")
            consola.decir(f"   {consola.ruta_log}")
            return
        pantalla_final(consola, resultado, fecha, consola.ruta_log)
    except Exception:
        # Mismo tratamiento que flujo_pleno_nuevo: sin esto, un fallo aquí (el mismo
        # de isatty, un corte de red, una clave caducada) cerraría el programa entero
        # delante de ella, sin mensaje y sin cerrar el registro.
        consola.anotar(traceback.format_exc())
        consola.decir("\n   Ha ocurrido un problema y no he podido terminar el documento.")
        consola.decir("   Si la transcripción llegó a hacerse, está guardada: la opción 2")
        consola.decir("   del menú vuelve a intentarlo sin repetir los 20 minutos.")
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
    etiquetas = [f"{fecha_en_palabras(f)}   {t}" for f, t in plenos] + ["Volver al menú"]
    elegido = preguntar_opcion(consola, etiquetas)
    consola.cerrar()
    if elegido <= len(plenos):
        rehacer_pleno(inst, pantalla, plenos[elegido - 1][0])


# ── menú ──────────────────────────────────────────────────────────────────────

def mostrar_instrucciones(inst: Instalacion, consola: Consola) -> None:
    """Quien no encuentra un archivo sí encuentra una opción en pantalla."""
    # .upper() no basta: "É" en mayúsculas sigue siendo "É", así que
    # "LÉEME - Cómo generar un acta.txt" nunca casaría con "EEME" sin normalizar la tilde.
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
        # La ventana se cierra al terminar: sin esto, el fallo desaparecería con ella.
        # preparar_instalacion() se vuelve a llamar para localizar la carpeta de
        # registros; si el fallo original fue precisamente ahí (p.ej. permisos al
        # crear carpetas), esta segunda llamada fallaría también, y un manejador de
        # errores que revienta es peor que no tener manejador. Por eso va envuelta:
        # si no consigue ni eso, al menos deja la traza por pantalla como último
        # recurso, en vez de morir con un error dentro del propio manejador.
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
