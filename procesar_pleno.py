#!/usr/bin/env python3
"""
procesar_pleno.py - Pipeline del acta de plenos. Ejecución manual desde el PC.

Modos:
    --url <youtube>              descarga el audio del vídeo y lo procesa
    --audio <fichero> --fecha YYYY-MM-DD --titulo "..."   procesa un audio local
    --rehacer-informe <fecha>    rehace el acta de un pleno ya transcrito (no vuelve a transcribir)
    --rehacer-acta <fecha>       recompone el .docx desde el informe.json guardado (sin LLM)

Opcional en todos los modos de generación:
    --convocatoria <pdf>         el orden del día publicado antes de la sesión

Flujo: audio → AssemblyAI universal-3.5-pro (diarizado; Groq whisper-large-v3 como
respaldo) → bucle Gemini (plenos_informe) → acta .docx (plenos_acta) →
uploads/actas/<fecha>/.

El acta generada es un BORRADOR: se envía por email a la secretaria del
Ayuntamiento, que la revisa, la completa y la sella. El pipeline termina ahí:
nada de lo que genera se publica en ninguna web.

Se ejecuta en local a propósito: YouTube bloquea las descargas desde IPs de
datacenter (GitHub Actions) con "confirm you're not a bot", y los plenos son
mensuales, así que no compensa la infraestructura de sondeo automático.
"""

import argparse
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import NamedTuple

import requests

from plenos_informe import Problema, normalizar_fecha, verificar_respuesta

# UTF-8 en Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parent
BORRADOR_DIR = RAIZ / "uploads" / "actas"


def dir_borrador(fecha: str) -> Path:
    """Carpeta de trabajo de un pleno. uploads/ está gitignorado: el borrador de
    un acta no revisada no tiene por qué acabar versionado en el repositorio.

    ACTAS_DIR manda cuando está definida: el ejecutable que usa la funcionaria vive
    en el PC del Ayuntamiento, donde no hay repo y por tanto no hay uploads/actas.
    Se lee en cada llamada, no al importar, para que quien la defina no tenga que
    hacerlo antes del import."""
    raiz = os.environ.get("ACTAS_DIR")
    return (Path(raiz) if raiz else BORRADOR_DIR) / fecha


def leer_convocatoria(ruta: str | None) -> bytes | None:
    """Lee el PDF del orden del día tal cual, sin extraer texto.

    Las convocatorias del Ayuntamiento son escaneos: un JPEG dentro de un PDF, sin
    capa de texto. Extraerlas exigiría OCR; en su lugar el PDF viaja entero a Gemini,
    que lee escaneos y además conserva la maquetación (numeración, expedientes).

    También admite la convocatoria como imagen JPEG suelta —lo normal cuando alguien
    la fotografía o escanea sin pasarla por PDF—, envuelta aquí mismo en un PDF de una
    sola página. Así el resto del pipeline no se entera: al modelo le sigue viajando un
    PDF por el plugin file-parser, y la copia que se guarda en el borrador para
    --rehacer-informe también es un PDF válido.
    """
    if ruta is None:
        return None
    origen = Path(ruta)
    if not origen.exists():
        raise FileNotFoundError(f"no existe la convocatoria: {origen}")
    sufijo = origen.suffix.lower()
    if sufijo == ".pdf":
        return origen.read_bytes()
    if sufijo in (".jpg", ".jpeg"):
        from PIL import Image
        buffer = io.BytesIO()
        Image.open(origen).convert("RGB").save(buffer, format="PDF")
        return buffer.getvalue()
    raise ValueError(
        f"la convocatoria debe ser un PDF o una imagen JPEG, no {origen.suffix!r}: {origen}")

# ══════════════════════════════════════════════════════════════════════════════
# Funciones puras (cubiertas por test_plenos.py)
# ══════════════════════════════════════════════════════════════════════════════

def extraer_fecha(titulo: str, fallback: str) -> str:
    """Busca una fecha en el título (26/06/2026, 5-3-2026, '3 de mayo de 2026');
    si no hay, devuelve el fallback."""
    return normalizar_fecha(titulo) or fallback


def _hms(segundos: float) -> str:
    t = int(segundos)
    return f"[{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}]"


def unir_segmentos(respuestas: list[tuple[float, dict]]) -> str:
    """Une respuestas verbose_json de whisper (una por chunk, con su offset en
    segundos) en una transcripción con marcas [HH:MM:SS] absolutas."""
    lineas = []
    for offset, resp in respuestas:
        for seg in resp.get("segments", []):
            lineas.append(f"{_hms(offset + seg['start'])} {seg['text'].strip()}")
    return "\n".join(lineas)


def formatear_utterances(utterances: list[dict]) -> str:
    """Convierte las intervenciones diarizadas de AssemblyAI al mismo formato
    [HH:MM:SS] que produce unir_segmentos, anteponiendo la etiqueta de locutor.

    La etiqueta ("A", "B"...) la asigna el modelo por voz, no por identidad: dice
    que dos intervenciones son de la misma persona, no de quién. Se escribe como
    "Interviniente A" para que el redactor no la confunda con un nombre; quién es
    cada etiqueta solo lo puede decir la propia grabación."""
    return "\n".join(
        f"{_hms(u['start'] / 1000)} Interviniente {u['speaker']}: {u['text'].strip()}"
        for u in utterances)


def extraer_video_id(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|/live/|/shorts/)([\w-]{11})", url)
    return m.group(1) if m else None


# ══════════════════════════════════════════════════════════════════════════════
# Audio: descarga y troceado
# ══════════════════════════════════════════════════════════════════════════════

def _ejecutar(cmd: list[str]) -> None:
    """subprocess.run con captura; si falla, re-lanza incluyendo el final del
    stderr — sin esto el CalledProcessError solo enseña el comando y el error
    real (p. ej. el "confirm you're not a bot" de YouTube) queda invisible."""
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        detalle = (e.stderr or e.stdout or "").strip()[-500:]
        raise RuntimeError(f"{os.path.basename(str(cmd[0]))} falló (exit {e.returncode}): {detalle}") from e


class ErrorDeDescarga(RuntimeError):
    """Fallo al bajar el audio de YouTube. Tiene una salida propia —usar una
    grabación que ya esté en el ordenador—, así que el asistente necesita
    distinguirlo de cualquier otro fallo del pipeline."""


def _comando_yt_dlp() -> list[str]:
    """Cómo invocar a yt-dlp. Dentro del ejecutable empaquetado no hay intérprete
    de Python suelto —`sys.executable` es el propio .exe y `-m yt_dlp` se
    relanzaría a sí mismo—, así que ahí se usa el yt-dlp.exe oficial que viaja en
    la carpeta y se autoactualiza. YT_DLP_EXE la define el asistente."""
    exe = os.environ.get("YT_DLP_EXE")
    if exe:
        return [exe]
    if getattr(sys, "frozen", False):
        # Empaquetado no hay intérprete suelto: `sys.executable -m yt_dlp` relanzaría el
        # propio asistente, con la salida capturada y sin timeout, y quedaría una ventana
        # muerta. Si el binario no está —antivirus, borrado—, hay que decirlo.
        raise ErrorDeDescarga("no encuentro el programa que descarga los vídeos (yt-dlp.exe)")
    return [sys.executable, "-m", "yt_dlp"]


def descargar_audio(url: str, destino_dir: str) -> str:
    """Descarga la pista de audio tal cual la sirve YouTube (suele ser webm/opus)
    y devuelve su ruta, sin convertir nada: de eso ya se encarga trocear_audio en
    una sola pasada. Pedirle a yt-dlp que convierta a m4a aquí sería una
    recodificación de más — más lenta y con una generación extra de pérdida
    (opus→aac→aac en vez de opus→aac)."""
    try:
        _ejecutar(_comando_yt_dlp() + ["-f", "bestaudio/best",
                                       "-o", os.path.join(destino_dir, "pleno.%(ext)s"),
                                       "--no-progress", url])
    except RuntimeError as e:
        raise ErrorDeDescarga(str(e)) from e
    descargados = sorted(Path(destino_dir).glob("pleno.*"))
    if not descargados:
        raise ErrorDeDescarga("yt-dlp terminó sin dejar ningún fichero de audio")
    return str(descargados[0])


def trocear_audio(ruta: str, destino_dir: str, segundos: int = 1800) -> list[str]:
    """Trocea el audio en fragmentos de `segundos`, recodificando a mono 64 kbps
    (30 min ≈ 14 MB, holgado frente al tope de 25 MB por fichero del plan
    gratuito de Groq). Recodificar cuesta un par de minutos de CPU, pero es lo
    único que garantiza el tamaño sea cual sea el original de YouTube.
    Mono porque whisper convierte a mono 16 kHz igualmente; 64k en vez de los
    32k de la spec para dar margen de calidad en salas con eco y micro lejano."""
    patron = os.path.join(destino_dir, "chunk_%03d.m4a")
    _ejecutar(["ffmpeg", "-y", "-i", ruta, "-vn", "-ac", "1", "-b:a", "64k",
               "-f", "segment", "-segment_time", str(segundos), patron])
    return sorted(str(p) for p in Path(destino_dir).glob("chunk_*.m4a"))


# ══════════════════════════════════════════════════════════════════════════════
# Transcripción con AssemblyAI universal-3.5-pro (principal)
# ══════════════════════════════════════════════════════════════════════════════

AAI_URL = "https://api.assemblyai.com"
AAI_MODELO = "universal-3-5-pro"
AAI_SONDEO = 20  # s entre sondeos; no hay webhook porque esto corre en tu PC

# Contexto en prosa para el modelo (5-50 palabras según la doc; frases completas,
# no una lista de palabras sueltas — para eso está keyterms).
AAI_PROMPT = (
    "Sesión plenaria del Ayuntamiento de Enguídanos, provincia de Cuenca, España. "
    "Intervienen la Alcaldía, seis concejales, la secretaria municipal y público "
    "asistente; algunos vecinos toman la palabra, sobre todo en ruegos y preguntas. "
    "Se debaten y votan los puntos del orden del día: mociones, ordenanzas fiscales, "
    "presupuesto municipal, subvenciones de la Diputación de Cuenca, expedientes de "
    "contratación, decretos de alcaldía y ruegos y preguntas."
)

# Vocabulario que Whisper deformaba sistemáticamente. Tope: 1000 términos, 6 palabras
# por término. Se escriben tal cual deben salir en la transcripción.
AAI_KEYTERMS = [
    "Sergio de Fez Cerezuela", "Lorena Luján Chujfi", "María Rosario Cerdán Pérez",
    "Mario Cerdán Ochoa", "Joaquín Martínez", "Pedro José Martínez Martínez",
    "Fernando Pons Mayor", "Chari",  # se dirigen a Mª Rosario por el apodo
    "moción de censura", "delegación de funciones",
    "Enguídanos", "Ayuntamiento de Enguídanos", "Diputación de Cuenca",
    "Sra. Alcaldesa", "Sr. Alcalde", "secretaria", "orden del día",
    "ordenanza fiscal", "presupuesto municipal", "moción", "dación de cuenta",
    "decreto de alcaldía", "ruegos y preguntas", "por unanimidad", "abstención",
    "sesión ordinaria", "sesión extraordinaria", "expediente",
]

# Red de seguridad determinista sobre keyterms. `to` admite UNA sola palabra (`from`
# sí varias) y distingue mayúsculas, así que aquí solo caben apellidos sueltos.
AAI_SPELLING = [
    {"from": ["chufi", "chufy", "chuji", "chusfi"], "to": "Chujfi"},
    {"from": ["lujan"], "to": "Luján"},
    {"from": ["cerdan"], "to": "Cerdán"},
    {"from": ["cerezuela", "ceresuela"], "to": "Cerezuela"},
    {"from": ["enguidanos", "engidanos"], "to": "Enguídanos"},
]


def _subir_audio(ruta: str, cabeceras: dict, intentos: int = 4) -> str:
    """Sube el audio y devuelve su URL temporal en AssemblyAI.

    Un pleno son 100-200 MB y la subida dura minutos por una línea doméstica: que la
    conexión se parta a mitad no es excepcional, es lo normal cada tantas ejecuciones
    (`SSLEOFError`, `ConnectionError`). Sin reintento, ese corte tira por la borda la
    descarga y obliga a repetirlo todo. El fichero se reabre en cada intento porque el
    cuerpo ya consumido no se puede reenviar.
    """
    for intento in range(intentos):
        try:
            with open(ruta, "rb") as f:
                r = requests.post(f"{AAI_URL}/v2/upload", headers=cabeceras,
                                  data=f, timeout=3600)
            verificar_respuesta(r)
            return r.json()["upload_url"]
        except (requests.RequestException, OSError) as e:
            if intento == intentos - 1:
                raise
            espera = 30 * 2 ** intento
            print(f"  se cortó la subida ({type(e).__name__}); reintentando en "
                  f"{espera // 60 or 1} min...")
            time.sleep(espera)


def transcribir_assemblyai(ruta: str) -> str:
    """Sube el audio entero y devuelve la transcripción diarizada.

    Sin trocear: el tope es 5 GB / 10 h por petición, no los 25 MB por fichero de
    Groq. El pleno viaja tal cual lo deja yt-dlp, sin recodificar.
    """
    cabeceras = {"authorization": os.environ["ASSEMBLYAI_API_KEY"]}
    print("  subiendo el audio...")
    url_audio = _subir_audio(ruta, cabeceras)

    cuerpo = {
        "audio_url": url_audio,
        "speech_models": [AAI_MODELO],
        "language_code": "es",           # fijo: no dejamos que lo detecte
        "speaker_labels": True,
        # Rango en vez de `speakers_expected`: no todos hablan en todas las sesiones (puede
        # haber un pleno corto con solo 4 concejales) y además hay público, que sí interviene
        # —sobre todo en ruegos y preguntas—, en número variable de un pleno a otro.
        # El máximo va HOLGADO A PROPÓSITO, por encima de lo que se necesita casi nunca:
        # partir a una persona en dos etiquetas es un fallo recuperable (esa voz queda "no
        # identificada", molesto pero honesto); fundir a dos personas en una etiqueta no lo
        # es, porque el generador propaga esa etiqueta a un nombre real (ver DIARIZACION en
        # plenos_informe.py). Es justo lo que pasó en el pleno del 3 de septiembre de 2026:
        # AssemblyAI fusionó en una sola etiqueta a quien presidía y a una vecina —la
        # presidenta de la Asociación de Jubilados— que intervino tres horas después, y el
        # acta acabó atribuyéndole a la Teniente de Alcalde unos ruegos que formuló la
        # vecina. En un documento que se sella ese riesgo no es aceptable, así que aquí se
        # paga con margen: 4-7 concejales + secretaria + 3-4 vecinos son unas 12 voces
        # reales como mucho; 15 deja hueco de sobra sin que "más etiquetas de las que hay"
        # tenga coste real (una etiqueta de más simplemente no se usa).
        # Los dos son LÍMITES DUROS, no pistas (doc de AssemblyAI): por debajo del mínimo
        # el modelo parte voces hasta alcanzarlo, y por encima del máximo "the additional
        # speakers are merged into existing labels". Por eso el mínimo NO se baja a la
        # ligera: empuja a separar, que es el lado seguro. Los números salen de la
        # corporación real: seis concejales, la delegada y quien preside son ocho, y
        # aunque falte alguno NUNCA bajan de seis; con los vecinos que asisten e
        # intervienen, nunca pasan de doce. De ahí el mínimo en ese suelo de seis, y el
        # máximo con margen por encima del techo de doce: pasarse de máximo no cuesta
        # nada (una etiqueta de más no se usa) y quedarse corto fusiona dos personas en
        # una etiqueta, que es el fallo del pleno del 3 de septiembre de 2026.
        "speaker_options": {"min_speakers_expected": 6, "max_speakers_expected": 15},
        "prompt": AAI_PROMPT,
        "keyterms_prompt": AAI_KEYTERMS,
        "custom_spelling": AAI_SPELLING,
        # disfluencies se queda en false (por defecto): un acta no recoge los "eh".
    }
    r = requests.post(f"{AAI_URL}/v2/transcript", headers=cabeceras, json=cuerpo, timeout=60)
    verificar_respuesta(r)
    transcript_id = r.json()["id"]

    print(f"  transcribiendo (id {transcript_id}); un pleno tarda unos minutos...")
    # Un fallo de RED al sondear no significa que la transcripción se haya perdido:
    # el trabajo sigue corriendo en AssemblyAI (y ya se ha pagado), así que un corte
    # aquí solo debe anotarse y reintentar el sondeo, no abortar el pipeline entero.
    # Un tope de fallos consecutivos evita quedarse sondeando para siempre si la
    # conexión se ha caído de verdad; los errores que SÍ devuelve la propia API
    # (status == "error") siguen abortando de inmediato, como antes.
    fallos_seguidos = 0
    while True:
        time.sleep(AAI_SONDEO)
        try:
            r = requests.get(f"{AAI_URL}/v2/transcript/{transcript_id}",
                             headers=cabeceras, timeout=60)
            verificar_respuesta(r)
            estado = r.json()
        except requests.RequestException as e:
            fallos_seguidos += 1
            if fallos_seguidos >= 10:
                raise
            print(f"  se cortó el sondeo ({type(e).__name__}); reintentando...")
            continue
        fallos_seguidos = 0
        if estado["status"] == "completed":
            return formatear_utterances(estado["utterances"])
        if estado["status"] == "error":
            raise RuntimeError(f"AssemblyAI: {estado.get('error')}")


# ══════════════════════════════════════════════════════════════════════════════
# Transcripción con Groq whisper-large-v3 (respaldo)
# ══════════════════════════════════════════════════════════════════════════════

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL = "whisper-large-v3"
ESPERA_MAXIMA = 3900  # 65 min: cubre la ventana horaria del plan gratuito


def _espera_tras_error(respuesta, intento: int) -> float:
    """Segundos a esperar antes de reintentar. Groq manda `retry-after` cuando
    se agota el cupo (el horario del plan gratuito pide ~1h, mucho más que el
    backoff); si no viene la cabecera, backoff exponencial de 2/4/8 min."""
    cabecera = respuesta.headers.get("retry-after") if respuesta is not None else None
    if cabecera:
        try:
            return min(float(cabecera) + 5, ESPERA_MAXIMA)
        except ValueError:
            pass
    return 120 * 2 ** intento


def _reintentar(fn, intentos: int = 4):
    """Ejecuta fn(); ante 429/5xx reintenta esperando lo que pida el servidor."""
    for i in range(intentos):
        try:
            return fn()
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status not in (429, 500, 502, 503) or i == intentos - 1:
                raise
            espera = _espera_tras_error(e.response, i)
            print(f"  Groq devolvió {status}; esperando {espera / 60:.0f} min y reintentando...")
            time.sleep(espera)


def _transcribir_chunk(ruta: str) -> dict:
    def llamada():
        with open(ruta, "rb") as f:
            r = requests.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
                files={"file": (os.path.basename(ruta), f, "audio/mp4")},
                data={"model": GROQ_MODEL, "language": "es",
                      "response_format": "verbose_json"},
                timeout=600,
            )
        verificar_respuesta(r)
        return r.json()
    return _reintentar(llamada)


def transcribir_chunks(chunks: list[str], segundos_chunk: int = 1800) -> str:
    """Transcribe cada chunk en secuencia y une los segmentos con offsets absolutos."""
    respuestas = []
    for i, ruta in enumerate(chunks):
        print(f"  transcribiendo chunk {i + 1}/{len(chunks)}...")
        respuestas.append((i * float(segundos_chunk), _transcribir_chunk(ruta)))
    return unir_segmentos(respuestas)


def transcribir(ruta_audio: str, tmp: str) -> str:
    """AssemblyAI si hay clave; Groq solo si NO la hay.

    Groq no diariza —el acta necesita saber quién interviene— y exige trocear con
    ffmpeg, que no está en el PC donde corre el ejecutable. Degradar en silencio a
    ese camino en un documento que se sella es peor que parar: si AssemblyAI falla
    teniendo clave, se para y se dice, y la transcripción se reintenta luego sin
    volver a descargar nada.
    """
    if os.environ.get("ASSEMBLYAI_API_KEY"):
        print(f"transcribiendo con AssemblyAI {AAI_MODELO} (diarizado)...")
        return transcribir_assemblyai(ruta_audio)
    print("troceando audio...")
    chunks = trocear_audio(ruta_audio, tmp)
    print(f"transcribiendo {len(chunks)} fragmentos con Groq...")
    return transcribir_chunks(chunks)


# ══════════════════════════════════════════════════════════════════════════════
# Orquestación
# ══════════════════════════════════════════════════════════════════════════════

def _cargar_json(path: Path, defecto: dict) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return defecto


def _guardar_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ruta_objeciones(carpeta: Path, fecha: str) -> Path:
    return carpeta / f"{fecha}-objeciones.json"


def guardar_objeciones(carpeta: Path, fecha: str, pendientes: list) -> None:
    """Persiste las objeciones del auditor junto al informe: son parte de lo caro del
    pipeline —hasta tres vueltas de LLM— y hasta ahora vivían solo en la consola
    (ver wiki/concepts/persistir-lo-caro-antes-de-lo-fragil.md). Sin esto, un fallo al
    componer el .docx después del bucle se las llevaba por delante para siempre, y
    --rehacer-acta generaba la guía sin su sección más valiosa.

    Se sobrescribe siempre y se borra si ya no queda ninguna objeción, con el mismo
    criterio que escribir_comprobaciones() en plenos_guia.py: el fichero tiene que
    reflejar la última corrida, nunca arrastrar las objeciones de la anterior."""
    ruta = _ruta_objeciones(carpeta, fecha)
    if not pendientes:
        ruta.unlink(missing_ok=True)
        return
    _guardar_json(ruta, [p.model_dump() for p in pendientes])


def cargar_objeciones(carpeta: Path, fecha: str) -> list:
    """Relee las objeciones que guardó guardar_objeciones, como `Problema`. Lista
    vacía si el fichero no existe: plenos generados antes de este cambio, o plenos
    que ya no tienen ninguna objeción pendiente — en los dos casos la guía se compone
    igual, solo que sin la sección de comprobaciones."""
    ruta = _ruta_objeciones(carpeta, fecha)
    if not ruta.exists():
        return []
    return [Problema.model_validate(d) for d in json.loads(ruta.read_text(encoding="utf-8"))]


def _componer_guia(informe, entrada: dict, transcripcion: str, pendientes: list,
                   destino: Path, fecha: str) -> tuple:
    """Compone la guía de verificación HTML y el aviso "COMPROBAR ANTES DE SELLAR.txt"
    junto al acta, a partir de las mismas objeciones ya traducidas a términos legibles.
    Sin LLM y sin coste, como plenos_guia entero.

    Los dos ficheros se generan juntos y a partir de los mismos datos a propósito: antes,
    el .txt lo escribía solo asistente_plenos.py (y solo cuando la funcionaria usaba el
    menú), así que --rehacer-acta dejaba el acta y la guía al día pero el .txt se quedaba
    con la corrida anterior —pudiendo llegar a citar una ruta interna ("orden_del_dia[2].
    texto") que ya no existía—. Generarlo aquí garantiza que los tres ficheros cuenten
    siempre lo mismo, se ejecute desde donde se ejecute.

    Un try/except por fichero, no uno para los dos. El 2026-09-03 la guía HTML de la
    corrida anterior estaba abierta y Windows dio PermissionError al reescribirla; con un
    único try eso se llevó por delante también el .txt, que el asistente reescribió luego
    por su cuenta sin las objeciones legibles. La funcionaria acabó leyendo
    "orden_del_dia[0]" sin frase que buscar ni minuto que oír — justo lo que este módulo
    existe para evitar. El .txt va primero porque no depende de la guía para nada.

    Devuelve (ruta_guia, objeciones); ruta_guia es None si la guía no se pudo escribir."""
    from plenos_guia import escribir_comprobaciones, objecion_legible, render_guia
    objeciones = ()
    try:
        objeciones = tuple(objecion_legible(p, informe, transcripcion, entrada.get("video_url"))
                           for p in pendientes)
        escribir_comprobaciones(destino, fecha, pendientes, objeciones)
    except Exception as e:
        print(f"\nEl aviso \"COMPROBAR ANTES DE SELLAR.txt\" no se ha podido escribir: "
              f"{type(e).__name__}: {e}\nLas objeciones salen igual por pantalla.")
    try:
        ruta_guia = destino / f"{fecha}-guia-de-verificacion.html"
        try:
            render_guia(informe, entrada, transcripcion, pendientes, str(ruta_guia))
        except PermissionError:
            # La guía de la corrida anterior abierta en el navegador bloquea el fichero en
            # Windows. Escribir al lado es mejor que quedarse sin guía por eso.
            ruta_guia = destino / f"{fecha}-guia-de-verificacion-{time.strftime('%H%M')}.html"
            render_guia(informe, entrada, transcripcion, pendientes, str(ruta_guia))
            print(f"\nLa guía anterior estaba abierta y no se ha podido sobrescribir; "
                  f"la nueva se ha guardado como {ruta_guia.name}.")
        return ruta_guia, objeciones
    except Exception as e:
        print(f"\nLa guía de verificación no se ha podido componer: "
              f"{type(e).__name__}: {e}\nEl acta y el informe no se ven afectados.")
        return None, objeciones


class ResultadoPleno(NamedTuple):
    """Lo que el asistente necesita saber al terminar: dónde ha quedado todo, si
    hay acta y qué objeciones sostuvo el auditor hasta el final.

    `ruta_guia` y `objeciones` van al final y con valor por defecto para no romper a
    quien ya desempaqueta este NamedTuple por posición. `objeciones` son las mismas
    `pendientes` del auditor, pero legibles (ver plenos_guia.objecion_legible): dónde,
    qué dice el acta, qué se oye en la grabación y el enlace al minuto.

    `fallo_acta` distingue las DOS causas de que `ruta_acta` sea None, que no se
    arreglan igual: vacío = el tipo de sesión no consta (hace falta la convocatoria y
    volver a pasar por el modelo); con texto = el .docx no se pudo escribir aunque el
    informe está bien (casi siempre el documento abierto en Word), y eso se recompone
    gratis con --rehacer-acta. Sin este campo el asistente daba siempre el primer
    motivo, que en el segundo caso es falso y mandaba a la funcionaria a pagar otro
    bucle de LLM para arreglar algo que se arregla cerrando Word."""
    carpeta: Path
    ruta_acta: Path | None
    pendientes: list
    ruta_guia: Path | None = None
    objeciones: tuple = ()
    fallo_acta: str = ""


def procesar_pleno(fuente_audio: str | None, video_id: str | None, titulo: str,
                   fecha: str, video_url: str | None,
                   transcripcion: str | None = None,
                   convocatoria: bytes | None = None) -> ResultadoPleno:
    """Pipeline completo de un pleno: audio → transcripción → acta → ficheros.

    fuente_audio: ruta a un audio local, o None para descargar de video_url.
    transcripcion: si se pasa, se salta el audio y la transcripción (--rehacer-informe).
    convocatoria: bytes del PDF del orden del día, o None.
    """
    from plenos_informe import MAX_VUELTAS, _plural, bucle_informe
    from plenos_acta import render_acta

    if transcripcion is None:
        with tempfile.TemporaryDirectory() as tmp:
            if fuente_audio is None:
                print(f"descargando audio de {video_url}...")
                fuente_audio = descargar_audio(video_url, tmp)
            transcripcion = transcribir(fuente_audio, tmp)

    destino = dir_borrador(fecha)
    destino.mkdir(parents=True, exist_ok=True)
    ruta_md = destino / f"{fecha}-transcripcion.md"
    ruta_json = destino / f"{fecha}-informe.json"
    ruta_entrada = destino / "entrada.json"
    entrada = {"video_id": video_id, "fecha": fecha, "titulo": titulo,
               "video_url": video_url}

    # La transcripción se guarda ANTES del bucle LLM, no después: es la única parte
    # del pipeline que cuesta dinero y no se puede repetir gratis. Si el bucle falla
    # —el modelo devuelve basura, se corta la luz—, --rehacer-informe la reutiliza en
    # vez de obligar a pagar otra transcripción entera.
    if convocatoria:
        # Se guarda junto al resto para que --rehacer-informe la reutilice sin
        # obligarte a volver a localizar el PDF cada vez que ajustas los prompts.
        (destino / f"{fecha}-convocatoria.pdf").write_bytes(convocatoria)
    ruta_md.write_text(f"# Transcripción — {titulo}\n\n{transcripcion}\n", encoding="utf-8")
    _guardar_json(ruta_entrada, entrada)
    print(f"transcripción guardada en {ruta_md}")

    print("generando acta (bucle generador→auditor→corrector)...")
    informe, pendientes = bucle_informe(transcripcion, convocatoria)

    # `fecha` viene de --fecha o del título del vídeo, no del modelo: es un dato que
    # la herramienta conoce con certeza. Si en la grabación no se dice, no tiene
    # sentido dejarle a la secretaria un hueco que podemos rellenar. Solo rellena el
    # null; nunca pisa una fecha que sí conste en la grabación.
    if not informe.fecha_pleno:
        informe = informe.model_copy(update={"fecha_pleno": fecha})

    ruta_json.write_text(informe.model_dump_json(indent=2), encoding="utf-8")
    _guardar_json(ruta_entrada, dict(entrada, resumen_corto=informe.resumen_corto))
    # Se guarda YA, antes de componer nada: son las mismas tres vueltas de LLM que el
    # informe, y hasta ahora solo vivían en la consola (ver guardar_objeciones).
    guardar_objeciones(destino, fecha, pendientes)

    ruta_acta = None
    fallo_acta = ""
    if informe.tipo_sesion in ("ordinaria", "extraordinaria"):
        ruta_acta = destino / f"{fecha}-acta-{informe.tipo_sesion}.docx"
        try:
            render_acta(informe, str(ruta_acta))
        except Exception as e:
            # Llegar hasta aquí cuesta la transcripción y hasta tres vueltas de LLM. Que
            # un fallo al componer el documento se lleve todo eso por delante no es
            # aceptable: el JSON ya está en disco y --rehacer-acta lo recompone gratis.
            ruta_acta = None
            fallo_acta = f"{type(e).__name__}: {e}"
            print(f"\nEl informe está guardado, pero el acta no se ha podido componer:"
                  f"\n  {type(e).__name__}: {e}"
                  f"\nCorrige el JSON si hace falta y vuelve a intentarlo SIN coste:"
                  f"\n  python scripts/procesar_pleno.py --rehacer-acta {fecha}")

    # La guía es independiente del acta: no necesita plantilla ni tipo de sesión, así
    # que se compone aunque el .docx haya fallado arriba. Mismo criterio que ese
    # try/except — si esto falla, ni el acta ni el informe se pierden por ello.
    ruta_guia, objeciones = _componer_guia(informe, entrada, transcripcion, pendientes,
                                           destino, fecha)

    print(f"\nTranscripción:  {ruta_md}")
    print(f"Informe JSON:   {ruta_json}")
    if ruta_acta:
        print(f"Acta:           {ruta_acta}")
    else:
        # Sin tipo de sesión no se puede elegir plantilla, y elegirla a ciegas
        # produciría un acta con el encabezado equivocado.
        print("\nNO se ha generado el acta: el tipo de sesión (ordinaria o "
              "extraordinaria) no consta en la grabación.\nCorrige `tipo_sesion` en el "
              f"JSON o vuelve a intentarlo con --rehacer-informe {fecha}.")
    if ruta_guia:
        print(f"Guía de verificación: {ruta_guia}")

    if pendientes:
        print(f"\n{_pinta('AMARILLO', '⚠ ' + _plural(len(pendientes), 'AFIRMACIÓN', 'AFIRMACIONES') + ' SIN VERIFICAR')}"
              f" tras {MAX_VUELTAS} vueltas del auditor."
              "\n  El auditor las sostuvo hasta el final: contrástalas con la grabación.")
        for p in pendientes:
            print(f"  • [{p.seccion}] {p.afirmacion_dudosa}\n    motivo: {p.motivo}")

    print("\nRevisa el acta contra la grabación y envíala a la secretaria.")

    # El cierre es lo último que queda en pantalla tras 20 minutos de log: tiene que
    # decir en una línea si esto se puede enviar a la secretaria o no.
    if not ruta_acta:
        _banner("ERROR", f"no hay acta: el .docx no se pudo escribir ({fallo_acta})."
                if fallo_acta else
                "no hay acta: el tipo de sesión no consta en la grabación.")
    elif pendientes:
        _banner("WARNING", f"acta generada, pero con "
                           f"{_plural(len(pendientes), 'objeción', 'objeciones')} sin "
                           f"resolver. NO la envíes sin comprobarla contra la grabación.")
    else:
        _banner("SUCCESS", "acta generada y sin objeciones del auditor.")

    return ResultadoPleno(destino, ruta_acta, pendientes, ruta_guia, objeciones,
                          fallo_acta)


# ── cierre de la ejecución ────────────────────────────────────────────────────
# El pipeline tarda 20 minutos y escupe cientos de líneas; el resultado tiene que
# leerse de un vistazo. Color solo si la salida es una terminal: esto se ejecuta a
# menudo con `| tee ~/pleno.log` y ahí los códigos ANSI solo ensucian el fichero.
# NO_COLOR es la convención de https://no-color.org.

_ANSI = {"VERDE": "42;30", "AMARILLO": "43;30", "ROJO": "41;97"}
_NIVELES = {"SUCCESS": "VERDE", "WARNING": "AMARILLO", "ERROR": "ROJO"}


def _hay_color() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _pinta(color: str, texto: str) -> str:
    return f"\033[1;{_ANSI[color]}m {texto} \033[0m" if _hay_color() else texto


def _banner(nivel: str, mensaje: str) -> None:
    """Última línea de la ejecución: SUCCESS / WARNING / ERROR y qué hacer."""
    print(f"\n{_pinta(_NIVELES[nivel], nivel)} {mensaje}", flush=True)


def _titulo_de_youtube(url: str) -> str:
    """Título vía oEmbed (sin API key)."""
    r = requests.get("https://www.youtube.com/oembed",
                     params={"url": url, "format": "json"}, timeout=15)
    r.raise_for_status()
    return r.json()["title"]


def _rehacer_informe(fecha: str, convocatoria_pdf: str | None = None) -> "ResultadoPleno | None":
    """Regenera el acta de un pleno ya transcrito, reutilizando su transcripción.
    Solo pasa por Gemini: no descarga el audio ni vuelve a transcribirlo. Sirve
    para reprocesar tras ajustar los prompts."""
    borrador = dir_borrador(fecha)
    entrada = _cargar_json(borrador / "entrada.json", {})
    if not entrada:
        print(f"No hay ningún pleno con fecha {fecha} en {borrador}")
        return None

    ruta = borrador / f"{fecha}-transcripcion.md"
    if not ruta.exists():
        print(f"Falta la transcripción de {fecha}")
        return None

    # La convocatoria que se pase manda; si no se pasa ninguna, se reutiliza la que
    # quedó guardada en el borrador, para poder iterar prompts sin volver a buscarla.
    guardada = borrador / f"{fecha}-convocatoria.pdf"
    convocatoria = leer_convocatoria(
        convocatoria_pdf or (str(guardada) if guardada.exists() else None))

    texto = ruta.read_text(encoding="utf-8")
    if texto.startswith("# Transcripción"):
        texto = texto.split("\n\n", 1)[-1]  # quitar el encabezado del fichero
    return procesar_pleno(None, entrada.get("video_id"), entrada["titulo"], fecha,
                          entrada.get("video_url"), transcripcion=texto,
                          convocatoria=convocatoria)


def _rehacer_acta(fecha: str) -> int:
    """Vuelve a componer el .docx desde el informe.json ya guardado. No llama a ningún
    LLM ni transcribe: coste cero. Es la forma de iterar el formato del acta —plantilla,
    encabezado, fórmulas— sin volver a pagar lo que ya está pagado, y de recuperar el
    documento cuando el render falla después de un bucle de LLM que sí costó dinero.

    Rehace también la guía de verificación y el aviso "COMPROBAR ANTES DE SELLAR.txt":
    es igual de gratis, y así se puede iterar su formato sin pagar nada. Las objeciones
    del auditor se releen del fichero que guardar_objeciones() escribió junto al
    informe, así que los dos salen con su sección de «puntos que conviene comprobar»
    igual que en la corrida original —y el .txt nunca se queda desfasado respecto al
    acta y la guía que sí se acaban de recomponer—. Un pleno anterior a este cambio
    (sin ese fichero) sigue funcionando: salen sin esa sección, no revienta."""
    from plenos_acta import render_acta
    from plenos_informe import InformePleno

    carpeta = dir_borrador(fecha)
    ruta_json = carpeta / f"{fecha}-informe.json"
    if not ruta_json.exists():
        print(f"No hay informe guardado en {ruta_json}")
        return 1
    informe = InformePleno.model_validate_json(ruta_json.read_text(encoding="utf-8"))
    if informe.tipo_sesion not in ("ordinaria", "extraordinaria"):
        print("El tipo de sesión no consta en el informe: no se puede elegir plantilla.")
        return 1
    # El JSON se reescribe porque los validadores del esquema normalizan al cargarlo
    # (fechas, horas, la fórmula del acuerdo): así el fichero refleja lo que se compuso.
    ruta_json.write_text(informe.model_dump_json(indent=2), encoding="utf-8")
    ruta_acta = carpeta / f"{fecha}-acta-{informe.tipo_sesion}.docx"
    fallo = ""
    try:
        render_acta(informe, str(ruta_acta))
        print(f"Acta: {ruta_acta}")
    except Exception as e:
        # Mismo criterio que procesar_pleno(): la guía y el .txt no tienen ninguna culpa
        # de que el .docx no se haya podido escribir, y son justo lo que se estaba
        # regenerando, así que se avisa y se sigue con ellos en vez de abortar la función
        # entera. En la práctica, la causa más frecuente es el propio .docx abierto en
        # Word, que lo bloquea para escritura (PermissionError) — nos ha pasado de verdad.
        print(f"\nEl acta no se ha podido componer: {type(e).__name__}: {e}"
              f"\nSi el mensaje habla de permisos, seguramente el documento esté abierto "
              f"en Word: ciérralo y vuelve a lanzar --rehacer-acta {fecha}.")
        fallo = f"{type(e).__name__}: {e}"

    entrada = _cargar_json(carpeta / "entrada.json", {})
    ruta_md = carpeta / f"{fecha}-transcripcion.md"
    if ruta_md.exists():
        transcripcion = ruta_md.read_text(encoding="utf-8")
        if transcripcion.startswith("# Transcripción"):
            transcripcion = transcripcion.split("\n\n", 1)[-1]
        pendientes = cargar_objeciones(carpeta, fecha)
        ruta_guia, _ = _componer_guia(informe, entrada, transcripcion, pendientes, carpeta, fecha)
        if ruta_guia:
            print(f"Guía de verificación: {ruta_guia}")
    else:
        print(f"(sin transcripción en {ruta_md}: no se ha podido rehacer la guía)")
    # La guía y el .txt se rehacen igual, pero el código de salida habla del .docx:
    # es lo que el asistente necesita para saber si el reintento sirvió de algo.
    return 1 if fallo else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline del acta de plenos")
    parser.add_argument("--url", help="URL de un vídeo de YouTube")
    parser.add_argument("--audio", help="Ruta a un fichero de audio local")
    parser.add_argument("--fecha", help="YYYY-MM-DD (con --audio; opcional con --url)")
    parser.add_argument("--titulo", help="Título del pleno (con --audio; opcional con --url)")
    parser.add_argument("--rehacer-informe", metavar="YYYY-MM-DD",
                        help="Rehace el acta de un pleno ya transcrito (no vuelve a transcribir)")
    parser.add_argument("--rehacer-acta", metavar="YYYY-MM-DD",
                        help="Vuelve a componer el .docx desde el informe.json guardado: "
                             "sin LLM y sin coste. Para iterar el formato del acta")
    parser.add_argument("--convocatoria", metavar="PDF",
                        help="PDF del orden del día publicado antes de la sesión: "
                             "de ahí salen los títulos exactos, la numeración y los "
                             "expedientes. Puede ser un escaneo")
    args = parser.parse_args()

    if args.rehacer_acta:
        return _rehacer_acta(args.rehacer_acta)

    if args.rehacer_informe:
        return 0 if _rehacer_informe(args.rehacer_informe, args.convocatoria) else 1

    if args.url:
        video_id = extraer_video_id(args.url)
        if not video_id:
            print(f"URL no reconocida: {args.url}")
            return 1
        titulo = args.titulo or _titulo_de_youtube(args.url)
        fecha = args.fecha or extraer_fecha(titulo, "")
        if not fecha:
            print("No se pudo deducir la fecha del título; usa --fecha YYYY-MM-DD")
            return 1
        procesar_pleno(None, video_id, titulo, fecha,
                       f"https://www.youtube.com/watch?v={video_id}",
                       convocatoria=leer_convocatoria(args.convocatoria))
        return 0

    if args.audio:
        if not args.fecha or not args.titulo:
            print("--audio requiere --fecha YYYY-MM-DD y --titulo")
            return 1
        procesar_pleno(args.audio, None, args.titulo, args.fecha, None,
                       convocatoria=leer_convocatoria(args.convocatoria))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
