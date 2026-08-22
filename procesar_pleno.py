#!/usr/bin/env python3
"""
procesar_pleno.py - Pipeline del acta de plenos. Ejecución manual desde el PC.

Modos:
    --url <youtube>              descarga el audio del vídeo y lo procesa
    --audio <fichero> --fecha YYYY-MM-DD --titulo "..."   procesa un audio local
    --rehacer-informe <fecha>    rehace el acta de un pleno ya transcrito (no vuelve a transcribir)
    --publicar <fecha> --pdf <ruta>   publica en la web el acta ya sellada

Opcional en todos los modos de generación:
    --convocatoria <pdf>         el orden del día publicado antes de la sesión

Flujo: audio → AssemblyAI universal-3.5-pro (diarizado; Groq whisper-large-v3 como
respaldo) → bucle Gemini (plenos_informe) → acta .docx (plenos_acta) →
uploads/actas/<fecha>/.

El acta generada es un BORRADOR: se envía por email a la secretaria del
Ayuntamiento, que la revisa, la completa y la sella. Solo cuando devuelve el PDF
sellado se ejecuta --publicar, que es lo único que escribe en public/.

Se ejecuta en local a propósito: YouTube bloquea las descargas desde IPs de
datacenter (GitHub Actions) con "confirm you're not a bot", y los plenos son
mensuales, así que no compensa la infraestructura de sondeo automático.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

# UTF-8 en Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
INDICE_PATH = RAIZ / "public" / "data" / "plenos.json"
SALIDA_DIR = RAIZ / "public" / "plenos"
BORRADOR_DIR = RAIZ / "uploads" / "actas"


def dir_borrador(fecha: str) -> Path:
    """Carpeta de trabajo de un pleno. uploads/ está gitignorado: lo que se
    genera automáticamente no puede caer en public/, que se publica al commitear."""
    return BORRADOR_DIR / fecha


def leer_convocatoria(ruta: str | None) -> bytes | None:
    """Lee el PDF del orden del día tal cual, sin extraer texto.

    Las convocatorias del Ayuntamiento son escaneos: un JPEG dentro de un PDF, sin
    capa de texto. Extraerlas exigiría OCR; en su lugar el PDF viaja entero a Gemini,
    que lee escaneos y además conserva la maquetación (numeración, expedientes).
    """
    if ruta is None:
        return None
    origen = Path(ruta)
    if not origen.exists():
        raise FileNotFoundError(f"no existe la convocatoria: {origen}")
    if origen.suffix.lower() != ".pdf":
        raise ValueError(f"la convocatoria debe ser un PDF, no {origen.suffix!r}: {origen}")
    return origen.read_bytes()

_MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
          "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10,
          "noviembre": 11, "diciembre": 12}


# ══════════════════════════════════════════════════════════════════════════════
# Funciones puras (cubiertas por test_plenos.py)
# ══════════════════════════════════════════════════════════════════════════════

def extraer_fecha(titulo: str, fallback: str) -> str:
    """Busca una fecha en el título (26/06/2026, 5-3-2026, '3 de mayo de 2026');
    si no hay, devuelve el fallback."""
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", titulo)
    if m:
        d, mes, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{a:04d}-{mes:02d}-{d:02d}"
    m = re.search(r"(\d{1,2})\s+de\s+(" + "|".join(_MESES) + r")\s+(?:de\s+)?(\d{4})",
                  titulo, re.IGNORECASE)
    if m:
        return f"{int(m.group(3)):04d}-{_MESES[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    return fallback


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


def descargar_audio(url: str, destino_dir: str) -> str:
    """Descarga la pista de audio tal cual la sirve YouTube (suele ser webm/opus)
    y devuelve su ruta, sin convertir nada: de eso ya se encarga trocear_audio en
    una sola pasada. Pedirle a yt-dlp que convierta a m4a aquí sería una
    recodificación de más — más lenta y con una generación extra de pérdida
    (opus→aac→aac en vez de opus→aac)."""
    _ejecutar([sys.executable, "-m", "yt_dlp", "-f", "bestaudio/best",
               "-o", os.path.join(destino_dir, "pleno.%(ext)s"),
               "--no-progress", url])
    descargados = sorted(Path(destino_dir).glob("pleno.*"))
    if not descargados:
        raise RuntimeError("yt-dlp terminó sin dejar ningún fichero de audio")
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
    "Intervienen la Alcaldía, seis concejales y la secretaria municipal en el salón "
    "de plenos, con micrófono ambiente. Se debaten y se votan los puntos del orden "
    "del día: mociones, ordenanzas fiscales, presupuesto municipal, subvenciones de "
    "la Diputación de Cuenca, expedientes de contratación, decretos de alcaldía y "
    "ruegos y preguntas."
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


def transcribir_assemblyai(ruta: str) -> str:
    """Sube el audio entero y devuelve la transcripción diarizada.

    Sin trocear: el tope es 5 GB / 10 h por petición, no los 25 MB por fichero de
    Groq. El pleno viaja tal cual lo deja yt-dlp, sin recodificar.
    """
    cabeceras = {"authorization": os.environ["ASSEMBLYAI_API_KEY"]}
    print("  subiendo el audio...")
    with open(ruta, "rb") as f:
        r = requests.post(f"{AAI_URL}/v2/upload", headers=cabeceras, data=f, timeout=3600)
    r.raise_for_status()

    cuerpo = {
        "audio_url": r.json()["upload_url"],
        "speech_models": [AAI_MODELO],
        "language_code": "es",           # fijo: no dejamos que lo detecte
        "speaker_labels": True,
        # La corporación son 7 miembros más la secretaria; el público no interviene.
        # Rango en vez de `speakers_expected`: no todos hablan en todas las sesiones.
        "speaker_options": {"min_speakers_expected": 6, "max_speakers_expected": 10},
        "prompt": AAI_PROMPT,
        "keyterms_prompt": AAI_KEYTERMS,
        "custom_spelling": AAI_SPELLING,
        # disfluencies se queda en false (por defecto): un acta no recoge los "eh".
    }
    r = requests.post(f"{AAI_URL}/v2/transcript", headers=cabeceras, json=cuerpo, timeout=60)
    r.raise_for_status()
    transcript_id = r.json()["id"]

    print(f"  transcribiendo (id {transcript_id}); un pleno tarda unos minutos...")
    while True:
        time.sleep(AAI_SONDEO)
        r = requests.get(f"{AAI_URL}/v2/transcript/{transcript_id}",
                         headers=cabeceras, timeout=60)
        r.raise_for_status()
        estado = r.json()
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
        r.raise_for_status()
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
    """AssemblyAI si hay clave; Groq si no la hay o si AssemblyAI falla.

    AssemblyAI cuesta 0,21 $/h (~0,48 $ por pleno de 2h17; no hay capa gratuita,
    sí 50 $ de crédito inicial) y a cambio diariza —el acta necesita saber quién
    interviene— y se traga el audio entero. Groq es gratis pero obliga a trocear,
    se topa con el cupo horario y devuelve un muro de texto sin locutores; se queda
    como red de seguridad para no perder una grabación.
    """
    if os.environ.get("ASSEMBLYAI_API_KEY"):
        try:
            print(f"transcribiendo con AssemblyAI {AAI_MODELO} (diarizado)...")
            return transcribir_assemblyai(ruta_audio)
        except Exception as e:
            print(f"  AssemblyAI falló ({e}); se recurre a Groq {GROQ_MODEL}")
    print("troceando audio...")
    chunks = trocear_audio(ruta_audio, tmp)
    print(f"transcribiendo {len(chunks)} fragmentos con Groq...")
    return transcribir_chunks(chunks)


# ══════════════════════════════════════════════════════════════════════════════
# Índice web y orquestación
# ══════════════════════════════════════════════════════════════════════════════

def nueva_entrada_indice(indice: dict, entrada: dict) -> dict:
    """Inserta la entrada en el índice (reemplaza si ya existe ese pleno) y
    ordena por fecha descendente. Pura: no toca disco."""
    plenos = [p for p in indice["plenos"]
              if not (p.get("video_id") == entrada.get("video_id")
                      and p["fecha"] == entrada["fecha"])]
    plenos.append(entrada)
    plenos.sort(key=lambda p: p["fecha"], reverse=True)
    return {"plenos": plenos}


def entrada_publicada(entrada: dict, fecha: str) -> dict:
    """Añade a la entrada generada las rutas públicas del acta y la transcripción.
    Pura: no toca disco y no muta la entrada recibida."""
    return dict(entrada,
                pdf=f"plenos/{fecha}-pleno.pdf",
                transcripcion=f"plenos/{fecha}-transcripcion.md")


def _cargar_json(path: Path, defecto: dict) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return defecto


def _guardar_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def procesar_pleno(fuente_audio: str | None, video_id: str | None, titulo: str,
                   fecha: str, video_url: str | None,
                   transcripcion: str | None = None,
                   convocatoria: bytes | None = None) -> None:
    """Pipeline completo de un pleno: audio → transcripción → acta → ficheros.

    fuente_audio: ruta a un audio local, o None para descargar de video_url.
    transcripcion: si se pasa, se salta el audio y la transcripción (--rehacer-informe).
    convocatoria: bytes del PDF del orden del día, o None.
    """
    from plenos_informe import MAX_VUELTAS, bucle_informe
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

    ruta_acta = None
    if informe.tipo_sesion in ("ordinaria", "extraordinaria"):
        ruta_acta = destino / f"{fecha}-acta-{informe.tipo_sesion}.docx"
        render_acta(informe, str(ruta_acta))

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

    if pendientes:
        print(f"\n{len(pendientes)} puntos SIN VERIFICAR tras {MAX_VUELTAS} vueltas del auditor:")
        for p in pendientes:
            print(f"  • [{p.seccion}] {p.afirmacion_dudosa} — {p.motivo}")

    print("\nRevisa el acta contra la grabación y envíala a la secretaria.")
    print(f"Cuando devuelva el PDF sellado:\n"
          f'  python scripts/procesar_pleno.py --publicar {fecha} --pdf "<ruta del PDF>"')


def _titulo_de_youtube(url: str) -> str:
    """Título vía oEmbed (sin API key)."""
    r = requests.get("https://www.youtube.com/oembed",
                     params={"url": url, "format": "json"}, timeout=15)
    r.raise_for_status()
    return r.json()["title"]


def _rehacer_informe(fecha: str, convocatoria_pdf: str | None = None) -> int:
    """Regenera el acta de un pleno ya transcrito, reutilizando su transcripción.
    Solo pasa por Gemini: no descarga el audio ni vuelve a transcribirlo. Sirve
    para reprocesar tras ajustar los prompts."""
    borrador = dir_borrador(fecha)
    entrada = _cargar_json(borrador / "entrada.json", {})
    if not entrada:
        # Plenos anteriores a los dos pasos: su entrada vive en el índice publicado.
        entrada = next((p for p in _cargar_json(INDICE_PATH, {"plenos": []})["plenos"]
                        if p["fecha"] == fecha), None)
    if not entrada:
        print(f"No hay ningún pleno con fecha {fecha} en {borrador} ni en {INDICE_PATH}")
        return 1

    ruta = borrador / f"{fecha}-transcripcion.md"
    if not ruta.exists():
        ruta = SALIDA_DIR / f"{fecha}-transcripcion.md"
    if not ruta.exists():
        print(f"Falta la transcripción de {fecha}")
        return 1

    # La convocatoria que se pase manda; si no se pasa ninguna, se reutiliza la que
    # quedó guardada en el borrador, para poder iterar prompts sin volver a buscarla.
    guardada = borrador / f"{fecha}-convocatoria.pdf"
    convocatoria = leer_convocatoria(
        convocatoria_pdf or (str(guardada) if guardada.exists() else None))

    texto = ruta.read_text(encoding="utf-8")
    if texto.startswith("# Transcripción"):
        texto = texto.split("\n\n", 1)[-1]  # quitar el encabezado del fichero
    procesar_pleno(None, entrada.get("video_id"), entrada["titulo"], fecha,
                   entrada.get("video_url"), transcripcion=texto,
                   convocatoria=convocatoria)
    return 0


def publicar(fecha: str, ruta_pdf: str) -> int:
    """Publica en la web el acta ya revisada y sellada por la secretaria.
    Es el único punto del pipeline que escribe en public/."""
    origen_pdf = Path(ruta_pdf)
    if not origen_pdf.exists():
        print(f"No existe el PDF sellado: {origen_pdf}")
        return 1

    borrador = dir_borrador(fecha)
    ruta_entrada = borrador / "entrada.json"
    if not ruta_entrada.exists():
        print(f"Falta {ruta_entrada}: genera primero el pleno de esa fecha.")
        return 1

    ruta_md = borrador / f"{fecha}-transcripcion.md"
    if not ruta_md.exists():
        print(f"Falta la transcripción {ruta_md}: genera primero el pleno de esa fecha.")
        return 1

    # Todo lo que puede fallar leyendo va antes de tocar public/: si entrada.json
    # está corrupto, JSONDecodeError debe abortar sin haber copiado nada, para no
    # dejar el PDF publicado sin su fila en el índice.
    entrada = entrada_publicada(_cargar_json(ruta_entrada, {}), fecha)
    indice = nueva_entrada_indice(_cargar_json(INDICE_PATH, {"plenos": []}), entrada)

    SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origen_pdf, SALIDA_DIR / f"{fecha}-pleno.pdf")
    shutil.copy2(ruta_md, SALIDA_DIR / f"{fecha}-transcripcion.md")
    _guardar_json(INDICE_PATH, indice)

    print(f"Acta publicada:  {SALIDA_DIR / f'{fecha}-pleno.pdf'}")
    print(f"Transcripción:   {SALIDA_DIR / f'{fecha}-transcripcion.md'}")
    print(f"Índice:          {INDICE_PATH}")
    print("\nHaz commit de public/ para que el deploy lo suba.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline del acta de plenos")
    parser.add_argument("--url", help="URL de un vídeo de YouTube")
    parser.add_argument("--audio", help="Ruta a un fichero de audio local")
    parser.add_argument("--fecha", help="YYYY-MM-DD (con --audio; opcional con --url)")
    parser.add_argument("--titulo", help="Título del pleno (con --audio; opcional con --url)")
    parser.add_argument("--rehacer-informe", metavar="YYYY-MM-DD",
                        help="Rehace el acta de un pleno ya transcrito (no vuelve a transcribir)")
    parser.add_argument("--publicar", metavar="YYYY-MM-DD",
                        help="Publica en la web el acta sellada de ese pleno")
    parser.add_argument("--pdf", help="Ruta del PDF sellado (con --publicar)")
    parser.add_argument("--convocatoria", metavar="PDF",
                        help="PDF del orden del día publicado antes de la sesión: "
                             "de ahí salen los títulos exactos, la numeración y los "
                             "expedientes. Puede ser un escaneo")
    args = parser.parse_args()

    if args.publicar:
        if not args.pdf:
            print("--publicar requiere --pdf con la ruta del PDF sellado")
            return 1
        return publicar(args.publicar, args.pdf)

    if args.rehacer_informe:
        return _rehacer_informe(args.rehacer_informe, args.convocatoria)

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
