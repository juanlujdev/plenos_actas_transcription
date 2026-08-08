#!/usr/bin/env python3
"""
procesar_pleno.py - Pipeline de informes de plenos desde YouTube o audio local.

Modos:
    --mode scan                  cron: sondea el feed RSS y procesa vídeos nuevos
    --url <youtube>              procesa un vídeo concreto (backfill / reintento)
    --audio <fichero> --fecha YYYY-MM-DD --titulo "..."   procesa un audio local

Flujo: audio → troceado ffmpeg → Groq whisper-large-v3 → bucle Gemini
(plenos_informe) → render MD/PDF (plenos_render) → public/plenos/ +
public/data/plenos.json → aviso Telegram.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

# UTF-8 en Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
STATE_PATH = RAIZ / "scripts" / "plenos_state.json"
INDICE_PATH = RAIZ / "public" / "data" / "plenos.json"
SALIDA_DIR = RAIZ / "public" / "plenos"

CHANNEL_ID = "UCJ7hictYSiPLcDrPfJJUm-g"
FEED_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
MAX_INTENTOS = 3

_NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}

_MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
          "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10,
          "noviembre": 11, "diciembre": 12}


# ══════════════════════════════════════════════════════════════════════════════
# Funciones puras (cubiertas por test_plenos.py)
# ══════════════════════════════════════════════════════════════════════════════

def parsear_feed(xml_text: str) -> list[dict]:
    """Extrae {video_id, titulo, publicado} de cada entry del feed Atom de YouTube."""
    root = ET.fromstring(xml_text)
    videos = []
    for entry in root.findall("a:entry", _NS):
        videos.append({
            "video_id": entry.find("yt:videoId", _NS).text,
            "titulo": entry.find("a:title", _NS).text or "",
            "publicado": (entry.find("a:published", _NS).text or "")[:10],
        })
    return videos


def extraer_fecha(titulo: str, fallback: str) -> str:
    """Busca una fecha en el título (26/06/2026, 5-3-2026, '3 de mayo de 2026');
    si no hay, devuelve el fallback (fecha de publicación)."""
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", titulo)
    if m:
        d, mes, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{a:04d}-{mes:02d}-{d:02d}"
    m = re.search(r"(\d{1,2})\s+de\s+(" + "|".join(_MESES) + r")\s+(?:de\s+)?(\d{4})",
                  titulo, re.IGNORECASE)
    if m:
        return f"{int(m.group(3)):04d}-{_MESES[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    return fallback


def unir_segmentos(respuestas: list[tuple[float, dict]]) -> str:
    """Une respuestas verbose_json de whisper (una por chunk, con su offset en
    segundos) en una transcripción con marcas [HH:MM:SS] absolutas."""
    lineas = []
    for offset, resp in respuestas:
        for seg in resp.get("segments", []):
            t = int(offset + seg["start"])
            lineas.append(f"[{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}] {seg['text'].strip()}")
    return "\n".join(lineas)


def extraer_video_id(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|/live/|/shorts/)([\w-]{11})", url)
    return m.group(1) if m else None


def es_nuevo(state: dict, video_id: str) -> bool:
    return video_id not in state["procesados"] and video_id not in state["fallidos"]


def registrar_fallo(state: dict, video_id: str) -> dict:
    intentos = state["pendientes"].get(video_id, 0) + 1
    if intentos >= MAX_INTENTOS:
        state["pendientes"].pop(video_id, None)
        state["fallidos"].append(video_id)
    else:
        state["pendientes"][video_id] = intentos
    return state


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
    """Descarga solo el audio del vídeo con yt-dlp, convertido a m4a mono 32k
    (4h ≈ 55 MB). Si YouTube bloquea la IP del runner ("confirm you're not a
    bot"), el error llega al aviso de Telegram; plan B documentado en la spec:
    secret YT_COOKIES."""
    salida = os.path.join(destino_dir, "pleno.m4a")
    cmd = [sys.executable, "-m", "yt_dlp",
           "-f", "bestaudio/best", "-x", "--audio-format", "m4a",
           "--postprocessor-args", "ffmpeg:-ac 1 -b:a 32k",
           "-o", salida, "--no-progress", url]
    cookies = os.environ.get("YT_COOKIES_FILE")
    if cookies:
        cmd += ["--cookies", cookies]
    _ejecutar(cmd)
    return salida


def trocear_audio(ruta: str, destino_dir: str, segundos: int = 1800) -> list[str]:
    """Trocea el audio en fragmentos de `segundos` con ffmpeg (límite de fichero
    de la API de Groq). Corte sin re-codificar: la pérdida máxima es ~1 palabra
    por frontera de fragmento."""
    patron = os.path.join(destino_dir, "chunk_%03d.m4a")
    _ejecutar(["ffmpeg", "-y", "-i", ruta, "-f", "segment",
               "-segment_time", str(segundos), "-c", "copy", patron])
    return sorted(str(p) for p in Path(destino_dir).glob("chunk_*.m4a"))


# ══════════════════════════════════════════════════════════════════════════════
# Transcripción con Groq whisper-large-v3
# ══════════════════════════════════════════════════════════════════════════════

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL = "whisper-large-v3"


def _reintentar(fn, intentos: int = 4):
    """Ejecuta fn(); ante 429/5xx reintenta con backoff exponencial (2,4,8 min)."""
    import time
    for i in range(intentos):
        try:
            return fn()
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status not in (429, 500, 502, 503) or i == intentos - 1:
                raise
            time.sleep(120 * 2 ** i)


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


# ══════════════════════════════════════════════════════════════════════════════
# Índice web, Telegram y orquestación
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


def avisar_telegram(texto: str) -> None:
    """Aviso al propietario. Sin token configurado (ejecución local) no hace nada."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_OWNER_ID")
    if not token or not chat:
        print(f"[aviso telegram omitido] {texto}")
        return
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": texto, "parse_mode": "Markdown"},
                      timeout=15).raise_for_status()
    except requests.RequestException as e:
        print(f"[aviso telegram falló] {e}")


def _cargar_json(path: Path, defecto: dict) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return defecto


def _guardar_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def procesar_pleno(fuente_audio: str | None, video_id: str | None, titulo: str,
                   fecha: str, video_url: str | None) -> None:
    """Pipeline completo de un pleno: audio → transcripción → informe → publicación.

    fuente_audio: ruta a un audio local, o None para descargar de video_url.
    """
    from plenos_informe import bucle_informe
    from plenos_render import render_markdown, render_pdf

    with tempfile.TemporaryDirectory() as tmp:
        if fuente_audio is None:
            print(f"descargando audio de {video_url}...")
            fuente_audio = descargar_audio(video_url, tmp)
        print("troceando audio...")
        chunks = trocear_audio(fuente_audio, tmp)
        print(f"transcribiendo {len(chunks)} fragmentos con Groq...")
        transcripcion = transcribir_chunks(chunks)

    print("generando informe (bucle generador→auditor→corrector)...")
    informe, pendientes = bucle_informe(transcripcion)

    SALIDA_DIR.mkdir(parents=True, exist_ok=True)
    base = f"{fecha}-pleno"
    ruta_pdf = SALIDA_DIR / f"{base}.pdf"
    ruta_md = SALIDA_DIR / f"{fecha}-transcripcion.md"
    ruta_json = SALIDA_DIR / f"{fecha}-informe.json"

    render_pdf(informe, titulo, video_url, pendientes, str(ruta_pdf))
    ruta_md.write_text(f"# Transcripción — {titulo}\n\n{transcripcion}\n", encoding="utf-8")
    ruta_json.write_text(informe.model_dump_json(indent=2), encoding="utf-8")

    indice = _cargar_json(INDICE_PATH, {"plenos": []})
    entrada = {"video_id": video_id, "fecha": fecha, "titulo": titulo,
               "video_url": video_url, "pdf": f"plenos/{base}.pdf",
               "transcripcion": f"plenos/{fecha}-transcripcion.md",
               "resumen_corto": informe.resumen_corto}
    _guardar_json(INDICE_PATH, nueva_entrada_indice(indice, entrada))

    aviso = f"📋 *Informe de pleno publicado*\n{titulo}\nhttps://enguidanos.es/plenos/{base}.pdf"
    if pendientes:
        detalle = "\n".join(f"• {p.afirmacion_dudosa} ({p.motivo})" for p in pendientes)
        aviso += f"\n\n⚠️ *{len(pendientes)} puntos sin verificar tras {3} vueltas:*\n{detalle}"
    avisar_telegram(aviso)


def _titulo_de_youtube(url: str) -> str:
    """Título vía oEmbed (sin API key)."""
    r = requests.get("https://www.youtube.com/oembed",
                     params={"url": url, "format": "json"}, timeout=15)
    r.raise_for_status()
    return r.json()["title"]


def _scan() -> int:
    """Modo cron: procesa los vídeos del feed no procesados. Devuelve exit code."""
    try:
        state = _cargar_json(STATE_PATH, {"procesados": [], "pendientes": {}, "fallidos": []})
        xml = requests.get(FEED_URL, timeout=30).text
    except Exception as e:
        avisar_telegram(f"❌ *Error al sondear el feed de plenos*\n`{str(e)[:500]}`")
        return 1
    fallo = False
    for v in parsear_feed(xml):
        if not es_nuevo(state, v["video_id"]):
            continue
        url = f"https://www.youtube.com/watch?v={v['video_id']}"
        fecha = extraer_fecha(v["titulo"], v["publicado"])
        try:
            procesar_pleno(None, v["video_id"], v["titulo"], fecha, url)
            state["procesados"].append(v["video_id"])
            state["pendientes"].pop(v["video_id"], None)
        except Exception as e:
            fallo = True
            state = registrar_fallo(state, v["video_id"])
            agotado = v["video_id"] in state["fallidos"]
            avisar_telegram(
                f"❌ *Error procesando pleno* `{v['video_id']}`\n{v['titulo']}\n"
                f"`{str(e)[:500]}`\n"
                + ("Reintentos agotados: requiere reproceso manual (workflow dispatch)."
                   if agotado else "Se reintentará en el siguiente ciclo."))
        _guardar_json(STATE_PATH, state)
    return 1 if fallo else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline de informes de plenos")
    parser.add_argument("--mode", choices=["scan"], help="scan: sondear feed RSS")
    parser.add_argument("--url", help="URL de un vídeo de YouTube concreto")
    parser.add_argument("--audio", help="Ruta a un fichero de audio local")
    parser.add_argument("--fecha", help="YYYY-MM-DD (con --audio; opcional con --url)")
    parser.add_argument("--titulo", help="Título del pleno (con --audio; opcional con --url)")
    args = parser.parse_args()

    if args.mode == "scan":
        return _scan()

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
                       f"https://www.youtube.com/watch?v={video_id}")
        # registrar en state para que el scan no lo reprocese
        state = _cargar_json(STATE_PATH, {"procesados": [], "pendientes": {}, "fallidos": []})
        if video_id not in state["procesados"]:
            state["procesados"].append(video_id)
        state["pendientes"].pop(video_id, None)
        if video_id in state["fallidos"]:
            state["fallidos"].remove(video_id)
        _guardar_json(STATE_PATH, state)
        return 0

    if args.audio:
        if not args.fecha or not args.titulo:
            print("--audio requiere --fecha YYYY-MM-DD y --titulo")
            return 1
        procesar_pleno(args.audio, None, args.titulo, args.fecha, None)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
