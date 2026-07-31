#!/usr/bin/env python3
"""
test_plenos.py - Tests de funciones puras del pipeline de plenos.

Uso:
    python scripts/test_plenos.py
"""

import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from plenos_informe import (
    Votacion, PuntoOrdenDia, Intervencion, InformePleno, Problema, AuditoriaInforme,
)

_failures = []


def test(name: str, got, expected) -> None:
    if got != expected:
        _failures.append(name)
        print(f"  ✗ FAIL: {name}")
        print(f"      got:      {got!r}")
        print(f"      expected: {expected!r}")
    else:
        print(f"  ✓ {name}")


# ── esquemas ──────────────────────────────────────────────────────────────────
print("── esquemas pydantic ─────────────────────────────────────────────────")

INFORME_MINIMO = {
    "fecha_pleno": None,
    "resumen_ejecutivo": "Pleno ordinario sin acuerdos relevantes.",
    "orden_del_dia": [
        {"numero": 1, "titulo": "Aprobación del acta anterior",
         "debate": "Sin debate.",
         "votacion": {"resultado": "aprobado", "modalidad": "unanimidad",
                      "a_favor": None, "en_contra": None, "abstenciones": None,
                      "timestamp": "00:03:12"}},
        {"numero": None, "titulo": "Informes de alcaldía", "debate": "Se informa de las obras.",
         "votacion": None},
    ],
    "intervenciones": [
        {"interviniente": "no identificado en la grabación", "resumen": "Pregunta por las obras."},
    ],
    "ruegos_y_preguntas": ["Se pregunta por el estado del camino de la Fuente."],
    "resumen_corto": "Pleno ordinario: acta aprobada por unanimidad e informes de alcaldía.",
}

informe = InformePleno.model_validate(INFORME_MINIMO)
test("informe válido se parsea", informe.resumen_corto, INFORME_MINIMO["resumen_corto"])
test("votación unanimidad sin números", informe.orden_del_dia[0].votacion.a_favor, None)
test("punto sin votación", informe.orden_del_dia[1].votacion, None)
test("interviniente vía de escape", informe.intervenciones[0].interviniente,
     "no identificado en la grabación")

try:
    Votacion.model_validate({"resultado": "empate", "modalidad": "recuento"})
    test("resultado fuera de Literal rechazado", "no lanzó", "ValidationError")
except Exception:
    test("resultado fuera de Literal rechazado", "ValidationError", "ValidationError")

try:
    InformePleno.model_validate({"resumen_ejecutivo": "x"})
    test("informe incompleto rechazado", "no lanzó", "ValidationError")
except Exception:
    test("informe incompleto rechazado", "ValidationError", "ValidationError")

auditoria = AuditoriaInforme.model_validate({"problemas": []})
test("auditoría sin problemas = visto bueno", auditoria.problemas, [])


# ── bucle_informe ─────────────────────────────────────────────────────────────────
print("── bucle_informe ─────────────────────────────────────────────────────")

from plenos_informe import bucle_informe, MAX_VUELTAS

_informe_v1 = InformePleno.model_validate(INFORME_MINIMO)
_problema = Problema(seccion="orden_del_dia", afirmacion_dudosa="aprobado 5-2",
                     motivo="la transcripción dice 4-3", evidencia="[01:02:03] cuatro votos a favor")

test("MAX_VUELTAS es 3", MAX_VUELTAS, 3)

# Caso 1: el auditor da el visto bueno a la primera → 1 auditoría, 0 correcciones
llamadas = {"generar": 0, "auditar": 0, "corregir": 0}
def _gen_ok(t):
    llamadas["generar"] += 1
    return _informe_v1
def _aud_ok(t, inf):
    llamadas["auditar"] += 1
    return AuditoriaInforme(problemas=[])
def _cor_nunca(t, inf, probs):
    llamadas["corregir"] += 1
    return inf

informe, pendientes = bucle_informe("transcripcion", generar=_gen_ok, auditar=_aud_ok, corregir=_cor_nunca)
test("visto bueno directo: sin problemas pendientes", pendientes, [])
test("visto bueno directo: 1 generación", llamadas["generar"], 1)
test("visto bueno directo: 1 auditoría", llamadas["auditar"], 1)
test("visto bueno directo: 0 correcciones", llamadas["corregir"], 0)

# Caso 2: 1 problema que la corrección resuelve → 2 auditorías, 1 corrección
estado = {"auditorias": 0, "correcciones": 0}
def _aud_una_vez(t, inf):
    estado["auditorias"] += 1
    if estado["auditorias"] == 1:
        return AuditoriaInforme(problemas=[_problema])
    return AuditoriaInforme(problemas=[])
def _cor(t, inf, probs):
    estado["correcciones"] += 1
    return inf

informe, pendientes = bucle_informe("t", generar=_gen_ok, auditar=_aud_una_vez, corregir=_cor)
test("corrección resuelve: sin pendientes", pendientes, [])
test("corrección resuelve: 2 auditorías", estado["auditorias"], 2)
test("corrección resuelve: 1 corrección", estado["correcciones"], 1)

# Caso 3: el auditor nunca queda contento → tope de 3 correcciones y devuelve pendientes
contador = {"correcciones": 0}
def _aud_nunca_contento(t, inf):
    return AuditoriaInforme(problemas=[_problema])
def _cor_cuenta(t, inf, probs):
    contador["correcciones"] += 1
    return inf

informe, pendientes = bucle_informe("t", generar=_gen_ok, auditar=_aud_nunca_contento, corregir=_cor_cuenta)
test("tope: exactamente MAX_VUELTAS correcciones", contador["correcciones"], 3)
test("tope: devuelve los problemas pendientes", len(pendientes), 1)


# ── render ────────────────────────────────────────────────────────────────────
print("── render ────────────────────────────────────────────────────────────")

from plenos_render import render_markdown, render_pdf, _latin

md = render_markdown(_informe_v1, "Pleno ordinario — 26 de junio de 2026",
                     "https://www.youtube.com/watch?v=abc123", [])
test("md: título", md.startswith("# Pleno ordinario — 26 de junio de 2026"), True)
test("md: sección resumen", "## Resumen ejecutivo" in md, True)
test("md: sección orden del día", "## Orden del día y votaciones" in md, True)
test("md: sección intervenciones", "## Principales intervenciones" in md, True)
test("md: sección ruegos", "## Ruegos y preguntas" in md, True)
test("md: enlace al vídeo", "https://www.youtube.com/watch?v=abc123" in md, True)
test("md: votación unanimidad", "por unanimidad" in md, True)
test("md: timestamp de votación", "00:03:12" in md, True)
test("md: sin bloque no verificado", "no verificado" in md.lower(), False)

md_sin_video = render_markdown(_informe_v1, "Pleno", None, [])
test("md: sin vídeo no hay enlace", "youtube.com" in md_sin_video, False)

md_con_problemas = render_markdown(_informe_v1, "Pleno", None, [_problema])
test("md: bloque no verificado presente", "no verificado" in md_con_problemas.lower(), True)
test("md: detalle del problema", "aprobado 5-2" in md_con_problemas, True)

test("latin: em-dash", _latin("a — b"), "a - b")
test("latin: comillas tipográficas", _latin("“hola”"), '"hola"')
test("latin: texto español intacto", _latin("Enguídanos, sesión ¿qué? ¡sí!"),
     "Enguídanos, sesión ¿qué? ¡sí!")

import tempfile
_tmp_pdf = os.path.join(tempfile.gettempdir(), "test_pleno.pdf")
render_pdf(_informe_v1, "Pleno ordinario — 26 de junio de 2026", None, [], _tmp_pdf)
with open(_tmp_pdf, "rb") as f:
    cabecera = f.read(5)
test("pdf: se genera y es un PDF", cabecera, b"%PDF-")

# Test de contenido: verifica que el texto se renderiza sin cortarse
from pypdf import PdfReader
reader = PdfReader(_tmp_pdf)
texto_pdf = "".join([page.extract_text() for page in reader.pages])
test("pdf: contiene debate completo", "Se informa de las obras." in texto_pdf, True)

os.remove(_tmp_pdf)


# ── funciones puras del pipeline ──────────────────────────────────────────────
print("── pipeline: RSS, fecha, segmentos, state ────────────────────────────")

from procesar_pleno import (
    parsear_feed, extraer_fecha, unir_segmentos, extraer_video_id,
    es_nuevo, registrar_fallo, MAX_INTENTOS,
)

FEED_EJEMPLO = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>yt:video:AbC123xyz_9</id>
    <yt:videoId>AbC123xyz_9</yt:videoId>
    <title>Pleno ordinario 26/06/2026</title>
    <published>2026-06-27T10:00:00+00:00</published>
  </entry>
  <entry>
    <id>yt:video:Def456uvw_8</id>
    <yt:videoId>Def456uvw_8</yt:videoId>
    <title>Pleno extraordinario 3 de mayo de 2026</title>
    <published>2026-05-04T09:30:00+00:00</published>
  </entry>
</feed>"""

videos = parsear_feed(FEED_EJEMPLO)
test("feed: dos entradas", len(videos), 2)
test("feed: video_id", videos[0]["video_id"], "AbC123xyz_9")
test("feed: titulo", videos[0]["titulo"], "Pleno ordinario 26/06/2026")
test("feed: publicado recortado a fecha", videos[0]["publicado"], "2026-06-27")

test("fecha: dd/mm/yyyy", extraer_fecha("Pleno ordinario 26/06/2026", "2026-01-01"), "2026-06-26")
test("fecha: dd-mm-yyyy", extraer_fecha("Pleno 5-3-2026", "2026-01-01"), "2026-03-05")
test("fecha: texto español", extraer_fecha("Pleno extraordinario 3 de mayo de 2026", "2026-01-01"), "2026-05-03")
test("fecha: sin fecha usa fallback", extraer_fecha("Pleno ordinario", "2026-06-27"), "2026-06-27")

resp_a = {"segments": [{"start": 0.0, "end": 4.0, "text": " Buenas tardes."},
                        {"start": 4.0, "end": 9.5, "text": " Comienza la sesión."}]}
resp_b = {"segments": [{"start": 1.2, "end": 6.0, "text": " Segundo fragmento."}]}
texto = unir_segmentos([(0.0, resp_a), (1800.0, resp_b)])
test("segmentos: primera línea", texto.splitlines()[0], "[00:00:00] Buenas tardes.")
test("segmentos: offset del segundo chunk", texto.splitlines()[2], "[00:30:01] Segundo fragmento.")

test("video_id: watch", extraer_video_id("https://www.youtube.com/watch?v=AbC123xyz_9"), "AbC123xyz_9")
test("video_id: youtu.be", extraer_video_id("https://youtu.be/AbC123xyz_9"), "AbC123xyz_9")
test("video_id: live", extraer_video_id("https://www.youtube.com/live/AbC123xyz_9"), "AbC123xyz_9")
test("video_id: basura", extraer_video_id("https://example.com/x"), None)

state = {"procesados": [], "pendientes": {}, "fallidos": []}
test("state: vídeo nuevo", es_nuevo(state, "v1"), True)
state["procesados"].append("v1")
test("state: procesado no es nuevo", es_nuevo(state, "v1"), False)
state = {"procesados": [], "pendientes": {}, "fallidos": []}
state = registrar_fallo(state, "v2")
test("state: primer fallo cuenta 1", state["pendientes"]["v2"], 1)
test("state: pendiente sigue siendo nuevo (se reintenta)", es_nuevo(state, "v2"), True)
state = registrar_fallo(registrar_fallo(state, "v2"), "v2")
test("state: al tercer fallo pasa a fallidos", "v2" in state["fallidos"], True)
test("state: fallido sale de pendientes", "v2" in state["pendientes"], False)
test("state: fallido ya no es nuevo", es_nuevo(state, "v2"), False)
test("state: MAX_INTENTOS es 3", MAX_INTENTOS, 3)


# ── índice web ────────────────────────────────────────────────────────────────
print("── índice plenos.json ────────────────────────────────────────────────")

from procesar_pleno import nueva_entrada_indice

_e1 = {"video_id": "v1", "fecha": "2026-05-03", "titulo": "Pleno mayo",
       "video_url": "https://youtu.be/v1", "pdf": "plenos/2026-05-03-pleno.pdf",
       "transcripcion": "plenos/2026-05-03-transcripcion.md", "resumen_corto": "..."}
_e2 = {"video_id": "v2", "fecha": "2026-06-26", "titulo": "Pleno junio",
       "video_url": "https://youtu.be/v2", "pdf": "plenos/2026-06-26-pleno.pdf",
       "transcripcion": "plenos/2026-06-26-transcripcion.md", "resumen_corto": "..."}

idx = nueva_entrada_indice({"plenos": []}, _e1)
idx = nueva_entrada_indice(idx, _e2)
test("índice: dos entradas", len(idx["plenos"]), 2)
test("índice: ordenado fecha desc", idx["plenos"][0]["fecha"], "2026-06-26")

_e2bis = dict(_e2, resumen_corto="corregido")
idx = nueva_entrada_indice(idx, _e2bis)
test("índice: reprocesar reemplaza, no duplica", len(idx["plenos"]), 2)
test("índice: entrada reemplazada", idx["plenos"][0]["resumen_corto"], "corregido")

_e3 = {"video_id": None, "fecha": "2026-04-01", "titulo": "Pleno audio", "video_url": None,
       "pdf": "plenos/2026-04-01-pleno.pdf", "transcripcion": "plenos/2026-04-01-transcripcion.md",
       "resumen_corto": "..."}
idx = nueva_entrada_indice(idx, _e3)
test("índice: entrada sin vídeo admitida", idx["plenos"][2]["video_id"], None)


# ── resultado ─────────────────────────────────────────────────────────────────
print()
if _failures:
    print(f"✗ {len(_failures)} tests fallidos")
    sys.exit(1)
print("✓ Todos los tests pasan")
