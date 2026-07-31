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
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return salida


def trocear_audio(ruta: str, destino_dir: str, segundos: int = 1800) -> list[str]:
    """Trocea el audio en fragmentos de `segundos` con ffmpeg (límite de fichero
    de la API de Groq). Corte sin re-codificar: la pérdida máxima es ~1 palabra
    por frontera de fragmento."""
    patron = os.path.join(destino_dir, "chunk_%03d.m4a")
    subprocess.run(["ffmpeg", "-y", "-i", ruta, "-f", "segment",
                    "-segment_time", str(segundos), "-c", "copy", patron],
                   check=True, capture_output=True, text=True)
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
