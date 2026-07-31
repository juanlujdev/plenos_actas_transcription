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


# ── resultado ─────────────────────────────────────────────────────────────────
print()
if _failures:
    print(f"✗ {len(_failures)} tests fallidos")
    sys.exit(1)
print("✓ Todos los tests pasan")
