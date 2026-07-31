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


# ── resultado ─────────────────────────────────────────────────────────────────
print()
if _failures:
    print(f"✗ {len(_failures)} tests fallidos")
    sys.exit(1)
print("✓ Todos los tests pasan")
