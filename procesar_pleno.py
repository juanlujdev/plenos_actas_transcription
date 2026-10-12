#!/usr/bin/env python3
"""
procesar_pleno.py - Pipeline del acta de plenos. Ejecución manual desde el PC.

Modos:
    --url <youtube>              descarga el audio del vídeo y lo procesa
    --audio <fichero> --fecha YYYY-MM-DD --titulo "..."   procesa un audio local
    --rehacer-informe <fecha>    (extraordinario: <fecha>-extraordinario) rehace el acta de un pleno ya transcrito (no vuelve a transcribir)
    --rehacer-acta <fecha>       recompone el .docx desde el informe.json guardado (sin LLM)

Opcional en todos los modos de generación:
    --convocatoria <pdf>         el orden del día publicado antes de la sesión
    --intervinientes <txt>       quienes intervienen, una persona por línea:
                                 "Nombre completo = cómo la llaman" (apodo opcional)

Flujo: audio → AssemblyAI universal-3.5-pro (diarizado; Groq whisper-large-v3 como
respaldo) → bucle Gemini (plenos_informe) → acta .docx (plenos_acta) →
uploads/actas/<fecha>/. El acta es un BORRADOR para la secretaria; no se publica nada.

Se ejecuta en local: YouTube bloquea las descargas desde IPs de datacenter.
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

from plenos_informe import (TOPONIMOS, Problema, normalizar_fecha, parsear_intervinientes,
                            verificar_respuesta)

# UTF-8 en Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parent
BORRADOR_DIR = RAIZ / "uploads" / "actas"


def clave_pleno(fecha: str, tipo: str | None = None) -> str:
    """Nombre de la carpeta de un pleno: la fecha más «-ordinario» o «-extraordinario», para
    que se vea cuál es y no se pisen dos plenos del mismo día. Sin tipo (o en las carpetas
    antiguas) es solo la fecha. La fecha se recupera con clave[:10]."""
    sufijo = {"ordinaria": "-ordinario", "extraordinaria": "-extraordinario"}.get(tipo or "", "")
    return fecha + sufijo


def dir_borrador(fecha: str) -> Path:
    """Carpeta de trabajo de un pleno (uploads/ está gitignorado). `fecha` es la clave
    de `clave_pleno`.

    ACTAS_DIR manda si está definida (el .exe corre sin repo); se lee en cada
    llamada, no al importar."""
    raiz = os.environ.get("ACTAS_DIR")
    return (Path(raiz) if raiz else BORRADOR_DIR) / fecha


def leer_convocatoria(ruta: str | None) -> bytes | None:
    """Lee el PDF del orden del día tal cual (son escaneos sin capa de texto: viaja
    entero a Gemini). Un JPEG suelto se envuelve en un PDF de una página para que el
    resto del pipeline siga recibiendo siempre un PDF."""
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
    """Intervenciones diarizadas de AssemblyAI al formato [HH:MM:SS] de unir_segmentos.

    La etiqueta es una voz, no una identidad: se escribe "Interviniente A" para que
    el redactor no la confunda con un nombre."""
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
    """subprocess.run que, al fallar, incluye el final del stderr en el error."""
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        detalle = (e.stderr or e.stdout or "").strip()[-500:]
        raise RuntimeError(f"{os.path.basename(str(cmd[0]))} falló (exit {e.returncode}): {detalle}") from e


class ErrorDeDescarga(RuntimeError):
    """Fallo al bajar el audio de YouTube; el asistente lo distingue porque tiene
    salida propia (usar una grabación local)."""


def _comando_yt_dlp() -> list[str]:
    """Cómo invocar a yt-dlp: YT_DLP_EXE (la define el asistente) o el módulo."""
    exe = os.environ.get("YT_DLP_EXE")
    if exe:
        return [exe]
    if getattr(sys, "frozen", False):
        # Empaquetado, `sys.executable -m yt_dlp` relanzaría el propio asistente.
        raise ErrorDeDescarga("no encuentro el programa que descarga los vídeos (yt-dlp.exe)")
    return [sys.executable, "-m", "yt_dlp"]


def descargar_audio(url: str, destino_dir: str) -> str:
    """Descarga el audio tal cual lo sirve YouTube y devuelve su ruta. No se
    convierte aquí: sería una recodificación de más."""
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
    """Trocea el audio en fragmentos de `segundos`, recodificado a mono 64 kbps
    (30 min ≈ 14 MB, bajo el tope de 25 MB por fichero de Groq)."""
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

# Contexto en prosa (5-50 palabras según la doc); las palabras sueltas van en keyterms.
AAI_PROMPT = (
    "Sesión plenaria del Ayuntamiento de Enguídanos, provincia de Cuenca, España. "
    "Intervienen la Alcaldía, seis concejales, la secretaria municipal y público "
    "asistente; algunos vecinos toman la palabra, sobre todo en ruegos y preguntas. "
    "Se debaten y votan los puntos del orden del día: mociones, ordenanzas fiscales, "
    "presupuesto municipal, subvenciones de la Diputación de Cuenca, expedientes de "
    "contratación, decretos de alcaldía y ruegos y preguntas."
)

# Tope: 1000 términos, 6 palabras por término.
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
    *TOPONIMOS,
]

# `to` admite UNA sola palabra (`from` varias) y distingue mayúsculas.
AAI_SPELLING = [
    {"from": ["chufi", "chufy", "chuji", "chusfi"], "to": "Chujfi"},
    {"from": ["lujan"], "to": "Luján"},
    {"from": ["cerdan"], "to": "Cerdán"},
    {"from": ["cerezuela", "ceresuela"], "to": "Cerezuela"},
    {"from": ["enguidanos", "engidanos"], "to": "Enguídanos"},
]


def _subir_audio(ruta: str, cabeceras: dict, intentos: int = 4) -> str:
    """Sube el audio y devuelve su URL temporal en AssemblyAI. Reintenta porque la
    subida (100-200 MB) se corta a menudo; el fichero se reabre en cada intento."""
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


def keyterms_del_pleno(intervinientes: list[dict] | None) -> list[str]:
    """AAI_KEYTERMS más nombres y apodos de este pleno, sin repetir (máx. 6 palabras por término)."""
    extra = [t for p in intervinientes or [] for t in (p["nombre"], *p.get("apodos", []))
             if 0 < len(t.split()) <= 6]
    vistos, salida = set(), []
    for t in [*AAI_KEYTERMS, *extra]:
        if t.lower() not in vistos:
            vistos.add(t.lower())
            salida.append(t)
    return salida


def transcribir_assemblyai(ruta: str, intervinientes: list[dict] | None = None) -> str:
    """Sube el audio entero (sin trocear ni recodificar) y devuelve la transcripción
    diarizada. `intervinientes`: [{'nombre', 'apodos'}] o None; amplían los keyterms."""
    cabeceras = {"authorization": os.environ["ASSEMBLYAI_API_KEY"]}
    print("  subiendo el audio...")
    url_audio = _subir_audio(ruta, cabeceras)

    cuerpo = {
        "audio_url": url_audio,
        "speech_models": [AAI_MODELO],
        "language_code": "es",           # fijo: no dejamos que lo detecte
        "speaker_labels": True,
        # Rango HOLGADO A PROPÓSITO, y ambos son límites duros (por encima del máximo,
        # AssemblyAI funde voces): partir a una persona en dos etiquetas es recuperable,
        # fundir a dos en una no, porque el generador propaga la etiqueta a un nombre real.
        # Mínimo 6 = suelo de la corporación; máximo 15 = margen sobre las ~12 voces reales.
        "speaker_options": {"min_speakers_expected": 6, "max_speakers_expected": 15},
        "prompt": AAI_PROMPT,
        "keyterms_prompt": keyterms_del_pleno(intervinientes),
        "custom_spelling": AAI_SPELLING,
    }
    r = requests.post(f"{AAI_URL}/v2/transcript", headers=cabeceras, json=cuerpo, timeout=60)
    verificar_respuesta(r)
    transcript_id = r.json()["id"]

    print(f"  transcribiendo (id {transcript_id}); un pleno tarda unos minutos...")
    # Un corte de red al sondear no pierde el trabajo (sigue en AssemblyAI): se
    # reintenta hasta 10 fallos seguidos. status == "error" aborta de inmediato.
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
    """Segundos a esperar: el `retry-after` de Groq o, sin él, backoff de 2/4/8 min."""
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


def transcribir(ruta_audio: str, tmp: str, intervinientes: list[dict] | None = None) -> str:
    """AssemblyAI si hay clave; Groq solo si NO la hay. Si AssemblyAI falla teniendo
    clave se para: degradar en silencio a Groq (sin diarización) no es aceptable."""
    if os.environ.get("ASSEMBLYAI_API_KEY"):
        print(f"transcribiendo con AssemblyAI {AAI_MODELO} (diarizado)...")
        return (transcribir_assemblyai(ruta_audio, intervinientes) if intervinientes
                else transcribir_assemblyai(ruta_audio))
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
    """Persiste las objeciones del auditor junto al informe, para que
    --rehacer-acta las recupere. Se sobrescribe, y se borra si ya no hay ninguna:
    refleja la última corrida."""
    ruta = _ruta_objeciones(carpeta, fecha)
    if not pendientes:
        ruta.unlink(missing_ok=True)
        return
    _guardar_json(ruta, [p.model_dump() for p in pendientes])


def cargar_objeciones(carpeta: Path, fecha: str) -> list:
    """Relee las objeciones de guardar_objeciones; lista vacía si no hay fichero."""
    ruta = _ruta_objeciones(carpeta, fecha)
    if not ruta.exists():
        return []
    return [Problema.model_validate(d) for d in json.loads(ruta.read_text(encoding="utf-8"))]


def _componer_guia(informe, entrada: dict, transcripcion: str, pendientes: list,
                   destino: Path, fecha: str) -> tuple:
    """Compone la guía de verificación HTML y el aviso "COMPROBAR ANTES DE SELLAR.txt"
    (sin LLM), a partir de las mismas objeciones, para que acta, guía y .txt cuenten
    lo mismo. Un try/except por fichero: que falle uno no tumba el otro.

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
            # Guía anterior abierta en el navegador: Windows bloquea el fichero.
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
    """Resultado para el asistente: carpeta, acta, objeciones pendientes y guía.

    `objeciones` son las `pendientes` en forma legible (plenos_guia.objecion_legible).
    `fallo_acta` distingue por qué `ruta_acta` es None: vacío = el tipo de sesión no
    consta (hay que volver al modelo); con texto = el .docx no se escribió (casi
    siempre abierto en Word) y se arregla con --rehacer-acta."""
    carpeta: Path
    ruta_acta: Path | None
    pendientes: list
    ruta_guia: Path | None = None
    objeciones: tuple = ()
    fallo_acta: str = ""


def fijar_fecha(informe, fecha: str):
    """La fecha del pleno es la de quien lo procesa, no la que el modelo entienda de la grabación."""
    if informe.fecha_pleno and informe.fecha_pleno != fecha:
        print(f"  ⚠ el modelo fechó el pleno el {informe.fecha_pleno}; "
              f"se usa la fecha indicada al procesarlo, {fecha}")
    return informe.model_copy(update={"fecha_pleno": fecha})


def procesar_pleno(fuente_audio: str | None, video_id: str | None, titulo: str,
                   fecha: str, video_url: str | None,
                   transcripcion: str | None = None,
                   convocatoria: bytes | None = None,
                   intervinientes: list[dict] | None = None,
                   tipo: str | None = None,
                   voces: dict[str, str] | None = None,
                   elegir_voces=None) -> ResultadoPleno:
    """Pipeline completo de un pleno: audio → transcripción → acta → ficheros.

    fuente_audio: ruta a un audio local, o None para descargar de video_url.
    transcripcion: si se pasa, se salta el audio y la transcripción (--rehacer-informe).
    convocatoria: bytes del PDF del orden del día, o None.
    intervinientes: [{'nombre', 'apodos'}] o None; se guarda en entrada.json para --rehacer-informe.
    tipo: 'ordinaria' | 'extraordinaria' | None. Solo decide la carpeta (ver clave_pleno).
    voces: {etiqueta: persona} confirmadas por la secretaría (se guardan en entrada.json).
    elegir_voces: función(transcripcion) -> dict | None que las pregunta a una persona,
        solo si `voces` es None; devolver {} es «no quiero confirmar ninguna».
    """
    from plenos_informe import MAX_VUELTAS, _plural, aplicar_voces, bucle_informe
    from plenos_acta import render_acta

    if transcripcion is None:
        with tempfile.TemporaryDirectory() as tmp:
            if fuente_audio is None:
                print(f"descargando audio de {video_url}...")
                fuente_audio = descargar_audio(video_url, tmp)
            transcripcion = (transcribir(fuente_audio, tmp, intervinientes) if intervinientes
                             else transcribir(fuente_audio, tmp))

    destino = dir_borrador(clave_pleno(fecha, tipo))
    destino.mkdir(parents=True, exist_ok=True)
    ruta_md = destino / f"{fecha}-transcripcion.md"
    ruta_json = destino / f"{fecha}-informe.json"
    ruta_entrada = destino / "entrada.json"
    entrada = {"video_id": video_id, "fecha": fecha, "titulo": titulo,
               "video_url": video_url}
    if intervinientes:
        entrada["intervinientes"] = intervinientes
    if tipo:
        entrada["tipo"] = tipo

    # La transcripción se guarda ANTES del bucle LLM para que --rehacer-informe la
    # reutilice si el bucle falla.
    if convocatoria:
        # Para que --rehacer-informe la reutilice.
        (destino / f"{fecha}-convocatoria.pdf").write_bytes(convocatoria)
    ruta_md.write_text(f"# Transcripción — {titulo}\n\n{transcripcion}\n", encoding="utf-8")
    _guardar_json(ruta_entrada, entrada)
    print(f"transcripción guardada en {ruta_md}")

    # Después de guardar lo caro, y antes del bucle: es quien decide quién es cada voz.
    if voces is None and elegir_voces:
        voces = elegir_voces(transcripcion)
    if voces is not None:
        entrada["voces"] = voces
        _guardar_json(ruta_entrada, entrada)
    voces = voces or None

    print("generando acta (bucle generador→auditor→corrector)...")
    # Solo los kwargs que haya, para no cambiar la firma que esperan los tests.
    extra = {k: v for k, v in (("intervinientes", intervinientes), ("voces", voces)) if v}
    informe, pendientes = bucle_informe(transcripcion, convocatoria, **extra)
    informe = aplicar_voces(informe, voces)

    informe = fijar_fecha(informe, fecha)
    if tipo and informe.tipo_sesion in ("ordinaria", "extraordinaria") and informe.tipo_sesion != tipo:
        print(f"  ⚠ se indicó una sesión {tipo}, pero la grabación parece {informe.tipo_sesion}: "
              f"revisa el encabezado del acta")

    ruta_json.write_text(informe.model_dump_json(indent=2), encoding="utf-8")
    _guardar_json(ruta_entrada, dict(entrada, resumen_corto=informe.resumen_corto))
    # Antes de componer nada: es trabajo de LLM ya pagado.
    guardar_objeciones(destino, fecha, pendientes)

    ruta_acta = None
    fallo_acta = ""
    if informe.tipo_sesion in ("ordinaria", "extraordinaria"):
        ruta_acta = destino / f"{fecha}-acta-{informe.tipo_sesion}.docx"
        try:
            render_acta(informe, str(ruta_acta))
        except Exception as e:
            # El JSON ya está en disco: --rehacer-acta lo recompone gratis.
            ruta_acta = None
            fallo_acta = f"{type(e).__name__}: {e}"
            print(f"\nEl informe está guardado, pero el acta no se ha podido componer:"
                  f"\n  {type(e).__name__}: {e}"
                  f"\nCorrige el JSON si hace falta y vuelve a intentarlo SIN coste:"
                  f"\n  python scripts/procesar_pleno.py --rehacer-acta {fecha}")

    # La guía no depende del acta: se compone aunque el .docx haya fallado.
    ruta_guia, objeciones = _componer_guia(informe, entrada, transcripcion, pendientes,
                                           destino, fecha)

    print(f"\nTranscripción:  {ruta_md}")
    print(f"Informe JSON:   {ruta_json}")
    if ruta_acta:
        print(f"Acta:           {ruta_acta}")
    else:
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

    # Lo último en pantalla: debe decir en una línea si se puede enviar o no.
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
# Color solo si la salida es una terminal (con `| tee` los códigos ANSI ensucian el
# fichero). NO_COLOR: https://no-color.org.

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


def leer_intervinientes(ruta: str | None) -> list[dict] | None:
    """Lee el fichero de intervinientes (ver plenos_informe.parsear_intervinientes)."""
    if not ruta:
        return None
    origen = Path(ruta)
    if not origen.exists():
        raise FileNotFoundError(f"no existe el fichero de intervinientes: {origen}")
    return parsear_intervinientes(origen.read_text(encoding="utf-8")) or None


def _rehacer_informe(clave: str, convocatoria_pdf: str | None = None,
                     intervinientes: list[dict] | None = None,
                     elegir_voces=None) -> "ResultadoPleno | None":
    """Regenera el acta reutilizando la transcripción guardada (solo pasa por Gemini).
    `clave`: la carpeta del pleno (ver clave_pleno)."""
    fecha = clave[:10]
    borrador = dir_borrador(clave)
    entrada = _cargar_json(borrador / "entrada.json", {})
    if not entrada:
        print(f"No hay ningún pleno con fecha {fecha} en {borrador}")
        return None

    ruta = borrador / f"{fecha}-transcripcion.md"
    if not ruta.exists():
        print(f"Falta la transcripción de {fecha}")
        return None

    # La que se pase manda; si no, la guardada en el borrador.
    guardada = borrador / f"{fecha}-convocatoria.pdf"
    convocatoria = leer_convocatoria(
        convocatoria_pdf or (str(guardada) if guardada.exists() else None))

    texto = ruta.read_text(encoding="utf-8")
    if texto.startswith("# Transcripción"):
        texto = texto.split("\n\n", 1)[-1]  # quitar el encabezado del fichero
    return procesar_pleno(None, entrada.get("video_id"), entrada["titulo"], fecha,
                          entrada.get("video_url"), transcripcion=texto,
                          convocatoria=convocatoria,
                          # La que se pase manda; si no, la guardada.
                          intervinientes=intervinientes or entrada.get("intervinientes"),
                          tipo=entrada.get("tipo"),
                          # Las guardadas no se vuelven a preguntar; si no confirmó ninguna ({}), sí.
                          voces=entrada.get("voces") or None, elegir_voces=elegir_voces)


def _rehacer_acta(clave: str) -> int:
    """Recompone el .docx desde el informe.json guardado, sin LLM ni coste. Rehace
    también la guía y el .txt, releyendo las objeciones de guardar_objeciones()."""
    from plenos_acta import render_acta
    from plenos_informe import InformePleno

    fecha = clave[:10]
    carpeta = dir_borrador(clave)
    ruta_json = carpeta / f"{fecha}-informe.json"
    if not ruta_json.exists():
        print(f"No hay informe guardado en {ruta_json}")
        return 1
    informe = InformePleno.model_validate_json(ruta_json.read_text(encoding="utf-8"))
    informe = fijar_fecha(informe, _cargar_json(carpeta / "entrada.json", {}).get("fecha", fecha))
    if informe.tipo_sesion not in ("ordinaria", "extraordinaria"):
        print("El tipo de sesión no consta en el informe: no se puede elegir plantilla.")
        return 1
    # Se reescribe porque los validadores del esquema normalizan al cargar.
    ruta_json.write_text(informe.model_dump_json(indent=2), encoding="utf-8")
    ruta_acta = carpeta / f"{fecha}-acta-{informe.tipo_sesion}.docx"
    fallo = ""
    try:
        render_acta(informe, str(ruta_acta))
        print(f"Acta: {ruta_acta}")
    except Exception as e:
        # Se avisa y se sigue con la guía y el .txt. Causa habitual: .docx abierto en Word.
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
    # El código de salida habla solo del .docx.
    return 1 if fallo else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pipeline del acta de plenos")
    parser.add_argument("--url", help="URL de un vídeo de YouTube")
    parser.add_argument("--audio", help="Ruta a un fichero de audio local")
    parser.add_argument("--fecha", help="YYYY-MM-DD (con --audio; opcional con --url)")
    parser.add_argument("--extraordinario", action="store_true",
                        help="El pleno es extraordinario: va a su propia carpeta "
                             "(<fecha>-extraordinario) y no pisa un ordinario del mismo día")
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
    parser.add_argument("--intervinientes", metavar="TXT",
                        help="Fichero de texto con quienes intervienen en el pleno, una "
                             "persona por línea: 'Nombre completo = cómo la llaman'. Ayuda "
                             "al transcriptor y al redactor a reconocer nombres y apodos")
    args = parser.parse_args()
    intervinientes = leer_intervinientes(args.intervinientes)
    tipo = "extraordinaria" if args.extraordinario else "ordinaria"

    if args.rehacer_acta:
        return _rehacer_acta(args.rehacer_acta)

    if args.rehacer_informe:
        return 0 if _rehacer_informe(args.rehacer_informe, args.convocatoria, intervinientes) else 1

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
                       convocatoria=leer_convocatoria(args.convocatoria),
                       intervinientes=intervinientes, tipo=tipo)
        return 0

    if args.audio:
        if not args.fecha or not args.titulo:
            print("--audio requiere --fecha YYYY-MM-DD y --titulo")
            return 1
        procesar_pleno(args.audio, None, args.titulo, args.fecha, None,
                       convocatoria=leer_convocatoria(args.convocatoria),
                       intervinientes=intervinientes, tipo=tipo)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
