#!/usr/bin/env python3
"""
procesar_pleno.py - Pipeline de informes de plenos. Ejecución manual desde el PC.

Modos:
    --url <youtube>              descarga el audio del vídeo y lo procesa
    --audio <fichero> --fecha YYYY-MM-DD --titulo "..."   procesa un audio local

Flujo: audio → troceado ffmpeg → Groq whisper-large-v3 → bucle Gemini
(plenos_informe) → render PDF (plenos_render) → public/plenos/ +
public/data/plenos.json. Después se revisa el PDF y se hace commit a mano.

Se ejecuta en local a propósito: YouTube bloquea las descargas desde IPs de
datacenter (GitHub Actions) con "confirm you're not a bot", y los plenos son
mensuales, así que no compensa la infraestructura de sondeo automático.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

# UTF-8 en Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
INDICE_PATH = RAIZ / "public" / "data" / "plenos.json"
SALIDA_DIR = RAIZ / "public" / "plenos"

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
    """Descarga solo la pista de audio del vídeo con yt-dlp, tal cual venga de
    YouTube. La compresión se hace al trocear: pedírsela aquí a yt-dlp no es
    fiable, porque si el original ya es m4a copia el flujo sin recodificar e
    ignora el bitrate (así llegaban fragmentos de 25 MB y Groq daba 413)."""
    salida = os.path.join(destino_dir, "pleno.m4a")
    _ejecutar([sys.executable, "-m", "yt_dlp",
               "-f", "bestaudio/best", "-x", "--audio-format", "m4a",
               "-o", salida, "--no-progress", url])
    return salida


def trocear_audio(ruta: str, destino_dir: str, segundos: int = 1800) -> list[str]:
    """Trocea el audio en fragmentos de `segundos`, recodificando a mono 32 kbps
    (30 min ≈ 7 MB, muy por debajo del tope de 25 MB por fichero del plan
    gratuito de Groq). Recodificar cuesta un par de minutos de CPU, pero es lo
    único que garantiza el tamaño sea cual sea el original de YouTube."""
    patron = os.path.join(destino_dir, "chunk_%03d.m4a")
    _ejecutar(["ffmpeg", "-y", "-i", ruta, "-ac", "1", "-b:a", "32k",
               "-f", "segment", "-segment_time", str(segundos), patron])
    return sorted(str(p) for p in Path(destino_dir).glob("chunk_*.m4a"))


# ══════════════════════════════════════════════════════════════════════════════
# Transcripción con Groq whisper-large-v3
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
    import time
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


def _cargar_json(path: Path, defecto: dict) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return defecto


def _guardar_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def procesar_pleno(fuente_audio: str | None, video_id: str | None, titulo: str,
                   fecha: str, video_url: str | None) -> None:
    """Pipeline completo de un pleno: audio → transcripción → informe → ficheros.

    fuente_audio: ruta a un audio local, o None para descargar de video_url.
    """
    from plenos_informe import MAX_VUELTAS, bucle_informe
    from plenos_render import render_pdf

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

    print(f"\nInforme generado: {ruta_pdf}")
    print(f"Transcripción:    {ruta_md}")
    print(f"Índice:           {INDICE_PATH}")
    if pendientes:
        print(f"\n{len(pendientes)} puntos SIN VERIFICAR tras {MAX_VUELTAS} vueltas del auditor:")
        for p in pendientes:
            print(f"  • [{p.seccion}] {p.afirmacion_dudosa} — {p.motivo}")
    print("\nRevisa el PDF contra la grabación antes de hacer commit.")


def _titulo_de_youtube(url: str) -> str:
    """Título vía oEmbed (sin API key)."""
    r = requests.get("https://www.youtube.com/oembed",
                     params={"url": url, "format": "json"}, timeout=15)
    r.raise_for_status()
    return r.json()["title"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline de informes de plenos")
    parser.add_argument("--url", help="URL de un vídeo de YouTube")
    parser.add_argument("--audio", help="Ruta a un fichero de audio local")
    parser.add_argument("--fecha", help="YYYY-MM-DD (con --audio; opcional con --url)")
    parser.add_argument("--titulo", help="Título del pleno (con --audio; opcional con --url)")
    args = parser.parse_args()

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
