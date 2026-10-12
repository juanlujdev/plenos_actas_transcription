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
    Votacion, PuntoOrdenDia, BloqueRuegos, InformePleno, Problema, AuditoriaInforme,
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
    "tipo_sesion": "ordinaria",
    "motivo_convocatoria": None,
    "solicitantes": [],
    "fecha_pleno": "2026-06-26",
    "hora_inicio": "12:00",
    "hora_fin": "13:30",
    "presidente": "Sergio de Fez Cerezuela",
    "asistentes": ["Lorena Luján Chujfi", "Mario Cerdán Ochoa"],
    "ausentes": ["Fernando Pons"],
    "declaraciones_apertura": [],
    "orden_del_dia": [
        {"numero": 1, "parte": "resolutiva",
         "titulo": "APROBACIÓN SI PROCEDE DEL ACTA DE LA SESIÓN ANTERIOR",
         "texto": "El Sr. Alcalde da cuenta del acta de la sesión anterior.\n\nNo se formulan observaciones.",
         "acuerdo": "aprobar el acta de la sesión anterior",
         "votacion": {"resultado": "aprobado", "modalidad": "unanimidad",
                      "a_favor": None, "en_contra": None, "abstenciones": None,
                      "voto_de_calidad": False, "timestamp": "00:03:12"}},
        {"numero": 2, "parte": "control",
         "titulo": "DECRETOS DE ALCALDÍA",
         "texto": "El Sr. Alcalde da cuenta de los decretos dictados. La Corporación se da por informada.",
         "acuerdo": None,
         "votacion": None},
    ],
    "ruegos_y_preguntas": [
        {"formulados_por": "D. Joaquín Martínez",
         "puntos": ["Pregunta por el estado del camino de la Fuente."]},
    ],
    "resumen_corto": "Pleno ordinario: acta aprobada por unanimidad e informes de alcaldía.",
}

informe = InformePleno.model_validate(INFORME_MINIMO)
test("informe válido se parsea", informe.resumen_corto, INFORME_MINIMO["resumen_corto"])
test("tipo de sesión", informe.tipo_sesion, "ordinaria")
test("votación unanimidad sin números", informe.orden_del_dia[0].votacion.a_favor, None)
test("punto de control sin votación", informe.orden_del_dia[1].votacion, None)
test("punto clasificado en parte resolutiva", informe.orden_del_dia[0].parte, "resolutiva")
test("punto clasificado en actividad de control", informe.orden_del_dia[1].parte, "control")
test("ruegos agrupados por quien los formula",
     informe.ruegos_y_preguntas[0].formulados_por, "D. Joaquín Martínez")
test("ausentes recogidos", informe.ausentes, ["Fernando Pons"])

# El mapa de voces es nuevo: un informe sin ese campo debe seguir validando (borradores antiguos); lista vacía, no null.
test("mapa de voces: un informe sin el campo sigue validando", informe.identificacion_locutores, [])

from plenos_informe import VozIdentificada

_voz = VozIdentificada(etiqueta="A", persona="Joaquín Martínez Luján",
                       evidencia="[00:01:46] Interviniente B: pues Joaquín, ¿tú tienes algo que decir?",
                       timestamp="00:01:46")
test("mapa de voces: VozIdentificada valida", _voz.persona, "Joaquín Martínez Luján")

_informe_con_mapa = InformePleno.model_validate(dict(
    INFORME_MINIMO,
    identificacion_locutores=[
        {"etiqueta": "A", "persona": "no identificado en la grabación",
         "evidencia": "no hay cita que lo demuestre", "timestamp": None},
        {"etiqueta": "B", "persona": "Lorena Luján Chujfi",
         "evidencia": "[00:00:32] Interviniente B: Damos comienzo al Pleno ordinario...",
         "timestamp": "00:00:32"},
    ]))
test("mapa de voces: un informe con el campo lo conserva",
     len(_informe_con_mapa.identificacion_locutores), 2)
test("mapa de voces: cada entrada guarda su etiqueta, persona y evidencia",
     (_informe_con_mapa.identificacion_locutores[1].etiqueta,
      _informe_con_mapa.identificacion_locutores[1].persona),
     ("B", "Lorena Luján Chujfi"))

# Valor de escape: `persona` es str libre, así que valida sin tocar el esquema.
_voz_mezclada = VozIdentificada(
    etiqueta="B", persona="etiqueta con voces mezcladas",
    evidencia=("[00:00:32] Interviniente B: Damos comienzo al Pleno...; "
              "[03:00:59] Interviniente B: llevo como presidenta de la asociación "
              "de jubilados"),
    timestamp="00:00:32")
test("mapa de voces: 'etiqueta con voces mezcladas' valida como persona",
     _voz_mezclada.persona, "etiqueta con voces mezcladas")
test("mapa de voces: un informe ya guardado sin esa etiqueta sigue validando igual",
     len(_informe_con_mapa.identificacion_locutores), 2)

# Las vías de escape siguen siendo válidas con casi todo vacío.
_MINIMO_VACIO = dict(INFORME_MINIMO, tipo_sesion="no consta", fecha_pleno=None,
                     hora_inicio=None, hora_fin=None, presidente=None,
                     asistentes=[], ausentes=[], declaraciones_apertura=[],
                     ruegos_y_preguntas=[])
_vacio = InformePleno.model_validate(_MINIMO_VACIO)
test("vía de escape: tipo de sesión no consta", _vacio.tipo_sesion, "no consta")
test("vía de escape: sin asistencia registrada", _vacio.asistentes, [])
test("vía de escape: sin turno de ruegos", _vacio.ruegos_y_preguntas, [])

try:
    Votacion.model_validate({"resultado": "empate", "modalidad": "recuento"})
    test("resultado fuera de Literal rechazado", "no lanzó", "ValidationError")
except Exception:
    test("resultado fuera de Literal rechazado", "ValidationError", "ValidationError")

try:
    InformePleno.model_validate({"resumen_corto": "x"})
    test("informe incompleto rechazado", "no lanzó", "ValidationError")
except Exception:
    test("informe incompleto rechazado", "ValidationError", "ValidationError")

# El esquema normaliza los formatos que necesita el documento; no se fía de la descripción del campo.
from plenos_informe import normalizar_fecha, normalizar_hora

test("fecha: ISO se conserva", normalizar_fecha("2026-05-19"), "2026-05-19")
test("fecha: en prosa se normaliza", normalizar_fecha("19 de mayo de 2026"), "2026-05-19")
test("fecha: con barras se normaliza", normalizar_fecha("19/5/2026"), "2026-05-19")
test("fecha: dentro de un título", normalizar_fecha("Pleno ordinario 19-05-2026"), "2026-05-19")
test("fecha: mes imposible se descarta", normalizar_fecha("19/13/2026"), None)
test("fecha: sin fecha", normalizar_fecha("Pleno ordinario"), None)

test("hora: HH:MM se conserva", normalizar_hora("12:02"), "12:02")
test("hora: con coletilla", normalizar_hora("las 12:02 horas"), "12:02")
test("hora: se rellena a dos dígitos", normalizar_hora("9:05"), "09:05")
test("hora: una marca de tiempo no es una hora", normalizar_hora("02:39:28"), None)
test("hora: hora imposible se descarta", normalizar_hora("25:00"), None)

_mal_formateado = InformePleno.model_validate(dict(
    INFORME_MINIMO, fecha_pleno="19 de mayo de 2026", hora_fin="02:39:28"))
test("informe: la fecha en prosa llega normalizada", _mal_formateado.fecha_pleno, "2026-05-19")
test("informe: la marca de tiempo no pasa como hora de cierre", _mal_formateado.hora_fin, None)

# `presidente` pide null si no se identifica, pero el modelo cuela la fórmula de escape de otros campos.
for _escape in ("no identificado en la grabación", "No identificado en la grabacion.",
                "no consta"):
    test(f"informe: '{_escape}' no es un nombre de presidencia",
         InformePleno.model_validate(dict(INFORME_MINIMO, presidente=_escape)).presidente, None)
test("informe: un nombre real de presidencia se conserva",
     InformePleno.model_validate(dict(INFORME_MINIMO,
                                      presidente="Dª Lorena Luján Chujfi")).presidente,
     "Dª Lorena Luján Chujfi")

# El modelo devuelve a veces el acuerdo con la fórmula ya escrita, o lo cuela en puntos sin acuerdo.
_con_formula = PuntoOrdenDia.model_validate(
    {"numero": 1, "parte": "resolutiva", "titulo": "T", "texto": "x",
     "acuerdo": "El Pleno del Ayuntamiento ACUERDA, por unanimidad, aprobar la exención.",
     "votacion": None})
test("acuerdo: la fórmula duplicada se recorta",
     _con_formula.acuerdo, "aprobar la exención.")
_control = PuntoOrdenDia.model_validate(
    {"numero": 3, "parte": "control", "titulo": "DECRETOS", "texto": "Se da cuenta.",
     "acuerdo": "La Corporación se da por informada.", "votacion": None})
test("acuerdo: un punto de control no acuerda nada", _control.acuerdo, None)
test("acuerdo: su cierre no se pierde, pasa al texto",
     _control.texto.endswith("La Corporación se da por informada."), True)

auditoria = AuditoriaInforme.model_validate({"problemas": []})
test("auditoría sin problemas = visto bueno", auditoria.problemas, [])


# ── bucle_informe ─────────────────────────────────────────────────────────────────
print("── bucle_informe ─────────────────────────────────────────────────────")

from plenos_informe import bucle_informe, MAX_VUELTAS

_informe_v1 = InformePleno.model_validate(INFORME_MINIMO)
_problema = Problema(seccion="orden_del_dia", afirmacion_dudosa="aprobado 5-2",
                     motivo="la transcripción dice 4-3", evidencia="[01:02:03] cuatro votos a favor")

test("MAX_VUELTAS es 3", MAX_VUELTAS, 3)

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

estado = {"auditorias": 0, "correcciones": 0}
def _aud_una_vez(t, inf):
    estado["auditorias"] += 1
    if estado["auditorias"] == 1:
        return AuditoriaInforme(problemas=[_problema])
    return AuditoriaInforme(problemas=[])
def _cor(t, inf, probs):
    estado["correcciones"] += 1
    return inf.model_copy(update={"resumen_corto": "corregido"})

informe, pendientes = bucle_informe("t", generar=_gen_ok, auditar=_aud_una_vez, corregir=_cor)
test("corrección resuelve: sin pendientes", pendientes, [])
test("corrección resuelve: 2 auditorías", estado["auditorias"], 2)
test("corrección resuelve: 1 corrección", estado["correcciones"], 1)

# Caso 3: tope de 3 correcciones. El corrector falso cambia algo cada vuelta (si no, el bucle sale antes: caso 5).
contador = {"correcciones": 0}
def _aud_nunca_contento(t, inf):
    return AuditoriaInforme(problemas=[_problema])
def _cor_cuenta(t, inf, probs):
    contador["correcciones"] += 1
    return inf.model_copy(update={"resumen_corto": f"corrección {contador['correcciones']}"})

informe, pendientes = bucle_informe("t", generar=_gen_ok, auditar=_aud_nunca_contento, corregir=_cor_cuenta)
test("tope: exactamente MAX_VUELTAS correcciones", contador["correcciones"], 3)
test("tope: devuelve los problemas pendientes", len(pendientes), 1)


# ── etapa 1 del rediseño del bucle: oscilación, escape y salida temprana ──────
print("── bucle: ping-pong, vía de escape y salida temprana ─────────────────")

from plenos_informe import _aplanar, _fijar, _escape_de

test("aplanar: rutas anidadas con índices",
     dict(_aplanar({"a": [{"b": 1}], "c": None})), {"a[0].b": 1, "c": None})

_d = {"orden_del_dia": [{"votacion": {"resultado": "aprobado"}}]}
_fijar(_d, "orden_del_dia[0].votacion.resultado", "no consta")
test("fijar: escribe en una ruta aplanada",
     _d["orden_del_dia"][0]["votacion"]["resultado"], "no consta")
test("escape: el resultado de una votación tiene vía de escape",
     _escape_de("orden_del_dia[3].votacion.resultado")[0], "no consta")
test("escape: un texto cualquiera no la tiene",
     _escape_de("orden_del_dia[0].texto"), None)


def _con_resultado(valor):
    """Un informe cuyo punto 1 tiene ese resultado de votación."""
    datos = InformePleno.model_validate(INFORME_MINIMO).model_dump()
    datos["orden_del_dia"][0]["votacion"]["resultado"] = valor
    datos["orden_del_dia"][0]["votacion"]["modalidad"] = "recuento"
    return InformePleno.model_validate(datos)


def _resultado_de(inf):
    return inf.orden_del_dia[0].votacion.resultado


_RUTA_VOT = "orden_del_dia[0].votacion.resultado"
_obj_votacion = Problema(seccion=_RUTA_VOT,
                         afirmacion_dudosa="el resultado de la votación del punto 1",
                         motivo="la grabación no lo declara",
                         evidencia="[00:58:04] Aprobada.")

# Caso 4: ping-pong del auditor sobre el mismo campo; el acta no puede afirmar ninguno de los dos.
_vueltas_pp = {"n": 0}
def _gen_aprobado(t):
    return _con_resultado("aprobado")
def _aud_siempre_vot(t, inf):
    return AuditoriaInforme(problemas=[_obj_votacion])
def _cor_flip(t, inf, probs):
    _vueltas_pp["n"] += 1
    return _con_resultado("rechazado" if _vueltas_pp["n"] % 2 else "aprobado")

_inf_pp, _pend_pp = bucle_informe("t", generar=_gen_aprobado, auditar=_aud_siempre_vot,
                                  corregir=_cor_flip)
test("ping-pong: el acta no afirma ninguna de las dos posturas",
     _resultado_de(_inf_pp), "no consta")
test("ping-pong: la objeción sigue viva para que la vea una persona", len(_pend_pp), 1)

# Caso 4b: se acaban las vueltas antes de que el valor vuelva atrás; también tiene que escapar.
def _cor_una_vez(t, inf, probs):
    return _con_resultado("rechazado")

_inf_sv, _pend_sv = bucle_informe("t", generar=_gen_aprobado, auditar=_aud_siempre_vot,
                                  corregir=_cor_una_vez)
test("sin volver atrás: un campo disputado hasta el final también escapa",
     _resultado_de(_inf_sv), "no consta")

# Un campo que nadie discutió NO se toca, aunque queden objeciones de otra cosa.
_obj_otra = Problema(seccion="asistentes", afirmacion_dudosa="falta un concejal",
                     motivo="la lista está incompleta", evidencia="[00:01:00] somos seis")
def _aud_otra_cosa(t, inf):
    return AuditoriaInforme(problemas=[_obj_otra])
def _cor_toca_asistentes(t, inf, probs):
    return inf.model_copy(update={"asistentes": inf.asistentes + ["D. Pedro José Martínez"]})

_inf_ok, _ = bucle_informe("t", generar=_gen_aprobado, auditar=_aud_otra_cosa,
                           corregir=_cor_toca_asistentes)
test("una objeción ajena no borra un resultado que nadie discute",
     _resultado_de(_inf_ok), "aprobado")

# Caso 5: si una corrección no cambia nada, seguir es tirar dinero.
_sin_cambio = {"correcciones": 0, "auditorias": 0}
def _aud_terco(t, inf):
    _sin_cambio["auditorias"] += 1
    return AuditoriaInforme(problemas=[_problema])
def _cor_inmovil(t, inf, probs):
    _sin_cambio["correcciones"] += 1
    return inf

bucle_informe("t", generar=_gen_ok, auditar=_aud_terco, corregir=_cor_inmovil)
test("salida temprana: una corrección sin cambios no gasta las 3 vueltas",
     _sin_cambio["correcciones"], 1)
test("salida temprana: tampoco vuelve a auditar", _sin_cambio["auditorias"], 1)

# Caso 6: el auditor recibe las rutas que el corrector tocó (calculadas en Python; son pista, no recorte).
import contextlib
import io

import plenos_informe as _pi_rutas

_vistas = []
_reales_r = (_pi_rutas.generar_informe, _pi_rutas.auditar_informe, _pi_rutas.corregir_informe)
_atrib_real = _pi_rutas.auditar_atribuciones
_pi_rutas.auditar_atribuciones = lambda t, i, c=None, **k: AuditoriaInforme(problemas=[])
try:
    def _gen_r(t, convocatoria=None):
        return _con_resultado("aprobado")
    def _aud_r(t, i, convocatoria=None, rutas_tocadas=None):
        _vistas.append(list(rutas_tocadas or []))
        return AuditoriaInforme(problemas=[_obj_votacion] if len(_vistas) < 2 else [])
    def _cor_r(t, i, p, convocatoria=None):
        return i.model_copy(update={"resumen_corto": "otro resumen"})
    _pi_rutas.generar_informe, _pi_rutas.auditar_informe, _pi_rutas.corregir_informe = (
        _gen_r, _aud_r, _cor_r)
    with contextlib.redirect_stdout(io.StringIO()):
        _pi_rutas.bucle_informe("t")
finally:
    (_pi_rutas.generar_informe, _pi_rutas.auditar_informe,
     _pi_rutas.corregir_informe) = _reales_r
    _pi_rutas.auditar_atribuciones = _atrib_real

test("rutas: la primera auditoría no recibe ninguna (no ha corregido nadie)", _vistas[0], [])
test("rutas: la auditoría de vuelta recibe el campo que el corrector tocó",
     _vistas[1], ["resumen_corto"])


# ── funciones puras del pipeline ──────────────────────────────────────────────
print("── pipeline: fecha, segmentos, esperas ───────────────────────────────")

from procesar_pleno import (
    extraer_fecha, unir_segmentos, formatear_utterances, extraer_video_id,
    _espera_tras_error, ESPERA_MAXIMA, AAI_SPELLING, AAI_KEYTERMS, AAI_PROMPT,
)

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

# start viene en milisegundos; la etiqueta de locutor va delante del texto.
utts = [{"start": 0, "end": 4000, "speaker": "A", "text": " Buenas tardes. "},
        {"start": 1801200, "end": 1806000, "speaker": "B", "text": "Segundo fragmento."}]
diarizado = formatear_utterances(utts)
test("utterances: locutor y marca de tiempo",
     diarizado.splitlines()[0], "[00:00:00] Interviniente A: Buenas tardes.")
test("utterances: ms a HH:MM:SS",
     diarizado.splitlines()[1], "[00:30:01] Interviniente B: Segundo fragmento.")
test("utterances: sin intervenciones no revienta", formatear_utterances([]), "")

# La API exige que `to` sea UNA sola palabra; `from` sí admite varias.
test("custom_spelling: `to` de una sola palabra",
     [c["to"] for c in AAI_SPELLING if len(c["to"].split()) != 1], [])
# Tope de la API: 1000 términos y 6 palabras por término.
test("keyterms: dentro de los topes de la API",
     (len(AAI_KEYTERMS) <= 1000, max(len(k.split()) for k in AAI_KEYTERMS) <= 6),
     (True, True))

# El contexto debe avisar de que hay público que a veces interviene, no solo la Corporación.
test("AAI_PROMPT: menciona que asiste público", "público" in AAI_PROMPT, True)
test("AAI_PROMPT: menciona que intervienen vecinos",
     "vecinos" in AAI_PROMPT and "ruegos y preguntas" in AAI_PROMPT, True)
# La doc de AssemblyAI pide 5-50 palabras en prosa.
test("AAI_PROMPT: longitud dentro de lo razonable (5-70 palabras)",
     5 <= len(AAI_PROMPT.split()) <= 70, True)

test("video_id: watch", extraer_video_id("https://www.youtube.com/watch?v=AbC123xyz_9"), "AbC123xyz_9")
test("video_id: youtu.be", extraer_video_id("https://youtu.be/AbC123xyz_9"), "AbC123xyz_9")
test("video_id: live", extraer_video_id("https://www.youtube.com/live/AbC123xyz_9"), "AbC123xyz_9")
test("video_id: basura", extraer_video_id("https://example.com/x"), None)

class _RespuestaFalsa:
    def __init__(self, cabeceras):
        self.headers = cabeceras

# Sin retry-after: backoff exponencial 2/4/8 min
test("espera: backoff 1er intento", _espera_tras_error(_RespuestaFalsa({}), 0), 120)
test("espera: backoff 3er intento", _espera_tras_error(_RespuestaFalsa({}), 2), 480)
test("espera: sin respuesta usa backoff", _espera_tras_error(None, 1), 240)

# Con retry-after: manda el servidor (+5s de margen), topado a ESPERA_MAXIMA
test("espera: respeta retry-after", _espera_tras_error(_RespuestaFalsa({"retry-after": "7.66"}), 0), 12.66)
test("espera: cupo horario supera el backoff",
     _espera_tras_error(_RespuestaFalsa({"retry-after": "3000"}), 0), 3005)
test("espera: tope de espera", _espera_tras_error(_RespuestaFalsa({"retry-after": "99999"}), 0), ESPERA_MAXIMA)
test("espera: retry-after no numérico cae al backoff",
     _espera_tras_error(_RespuestaFalsa({"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}), 1), 240)


# ── acta: números en letra ────────────────────────────────────────────────────────────────────
print("── acta: números en letra ────────────────────────────────────────────")

from plenos_acta import letras, anio_en_letra, hora_en_letra, fecha_en_letra, fecha_larga

test("letras: cero", letras(0), "cero")
test("letras: unidad", letras(3), "tres")
test("letras: quince", letras(15), "quince")
test("letras: veintitantos van juntos", letras(26), "veintiséis")
test("letras: decena redonda", letras(30), "treinta")
test("letras: decena con unidad", letras(54), "cincuenta y cuatro")
test("letras: noventa y nueve", letras(99), "noventa y nueve")

_fuera_de_rango = None
try:
    letras(100)
except ValueError as e:
    _fuera_de_rango = "rango"
test("letras: fuera de rango avisa", _fuera_de_rango, "rango")

test("año: dos mil redondo", anio_en_letra(2000), "dos mil")
test("año: dos mil veintiséis", anio_en_letra(2026), "dos mil veintiséis")

test("hora: con minutos", hora_en_letra("15:54"), "las quince horas y cincuenta y cuatro minutos")
test("hora: en punto no dice minutos", hora_en_letra("12:00"), "las doce horas")

test("fecha en letra", fecha_en_letra("2026-02-11"), "once de febrero del dos mil veintiséis")
test("fecha larga con dígitos", fecha_larga("2026-02-11"), "11 de febrero de 2026")


# ── acta: render del .docx ────────────────────────────────────────────────────
print("── acta: render del .docx ────────────────────────────────────────────")

import tempfile

from docx import Document as _Document
from plenos_acta import (
    render_acta, frase_votacion, frase_acuerdo, parrafos_apertura, formula_cierre, HUECO,
)
from plenos_informe import PRESIDENCIA

# Frase de votación: los recuentos van en letra y un None nunca se imprime como cero.
test("votación: unanimidad",
     frase_votacion(Votacion(resultado="aprobado", modalidad="unanimidad",
                             a_favor=None, en_contra=None, abstenciones=None, timestamp=None)),
     "Sometido el asunto a votación, queda aprobado por unanimidad de los asistentes.")
test("votación: recuento completo en letra",
     frase_votacion(Votacion(resultado="aprobado", modalidad="recuento",
                             a_favor=3, en_contra=3, abstenciones=None, timestamp=None)),
     "Se producen las votaciones con tres votos a favor y tres en contra. El asunto queda aprobado.")
test("votación: un solo voto va en singular",
     frase_votacion(Votacion(resultado="rechazado", modalidad="recuento",
                             a_favor=1, en_contra=None, abstenciones=None, timestamp=None)),
     "Se producen las votaciones con un voto a favor. El asunto queda rechazado.")
test("votación: recuento sin cifras no inventa ceros",
     frase_votacion(Votacion(resultado="aprobado", modalidad="recuento",
                             a_favor=None, en_contra=None, abstenciones=None, timestamp=None)),
     "Sometido el asunto a votación, queda aprobado.")
test("votación: sin votación no genera frase", frase_votacion(None), "")

# El recuento va dentro de la fórmula del acuerdo, sin frase de votación aparte.
def _punto(**kw):
    return PuntoOrdenDia.model_validate(dict(
        {"numero": 1, "parte": "resolutiva", "titulo": "T", "texto": "x",
         "acuerdo": None, "votacion": None}, **kw))


def _votacion(**kw):
    return dict({"resultado": "aprobado", "modalidad": "recuento", "a_favor": None,
                 "en_contra": None, "abstenciones": None, "voto_de_calidad": False,
                 "timestamp": None}, **kw)


test("acuerdo: recuento dentro de la fórmula ACUERDA, con el voto de calidad",
     frase_acuerdo(_punto(acuerdo="establecer la periodicidad en 40 días",
                          votacion=_votacion(a_favor=3, en_contra=3, voto_de_calidad=True))),
     "El Pleno del Ayuntamiento ACUERDA, establecer la periodicidad en 40 días, por tres "
     "votos a favor y tres en contra. En virtud de su voto de calidad, la Sra. Teniente "
     "de Alcalde resuelve el empate a favor de la propuesta.")
test("acuerdo: unanimidad",
     frase_acuerdo(_punto(acuerdo="aprobar la apertura del patio.",
                          votacion=_votacion(modalidad="unanimidad"))),
     "El Pleno del Ayuntamiento ACUERDA por unanimidad, aprobar la apertura del patio.")
test("acuerdo: sin votación también se acuerda dejar el punto sobre la mesa",
     frase_acuerdo(_punto(acuerdo="dejar el punto sobre la mesa",
                          votacion=_votacion(resultado="sin votación", modalidad="no consta"))),
     "El Pleno del Ayuntamiento ACUERDA, dejar el punto sobre la mesa.")
test("acuerdo: un punto rechazado no lleva fórmula de acuerdo",
     frase_acuerdo(_punto(acuerdo="realizar una auditoría",
                          votacion=_votacion(resultado="rechazado", a_favor=1, en_contra=2))),
     "Se producen las votaciones con un voto a favor y dos en contra. El asunto queda rechazado.")
test("acuerdo: punto de control no genera frase", frase_acuerdo(_punto()), "")

_apertura = "\n".join(parrafos_apertura(informe))
test("apertura: fórmula de constitución con la hora y la fecha",
     "siendo las doce horas del día 26 de junio de 2026" in _apertura, True)
test("apertura: preside por delegación, nunca como alcaldesa",
     "delegación de funciones" in _apertura and "Alcaldesa" not in _apertura, True)
test("apertura: nombra a los asistentes", "Mario Cerdán Ochoa" in _apertura, True)
test("apertura: hace constar la ausencia", "No asiste" in _apertura, True)
test("apertura: constitución verificada por la Secretaria, en femenino",
     "verificada por la Secretaria" in _apertura
     and "la Presidenta abre la sesión" in _apertura, True)
test("apertura: sin datos deja huecos",
     HUECO in "\n".join(parrafos_apertura(_vacio)), True)

# Lo que declara la Presidencia al abrir va en el encabezado, no en el primer punto.
_con_declaraciones = InformePleno.model_validate(dict(
    INFORME_MINIMO, declaraciones_apertura=["La Sesión tiene carácter público."]))
_ap_decl = "\n".join(parrafos_apertura(_con_declaraciones))
test("apertura: recoge las declaraciones de la Presidencia",
     "La Sesión tiene carácter público." in _ap_decl, True)
test("apertura: tras las declaraciones se pasa al orden del día",
     _ap_decl.endswith("Se procede a la deliberación sobre los asuntos incluidos en el "
                       "Orden del Día."), True)

_cierre = formula_cierre(informe)
test("cierre: hora en letra", "las trece horas y treinta minutos" in _cierre, True)
test("cierre: fecha en letra", "veintiséis de junio del dos mil veintiséis" in _cierre, True)
test("cierre: sin datos deja huecos", "___________" in formula_cierre(_vacio), True)
# El acta real firmada lleva raya, no guion: "Secretaria – Interventora".
test("cierre: Secretaria con raya, como en el acta real", "Secretaria – Interventora" in _cierre, True)


def _acta_generada(inf):
    """Genera el .docx y devuelve (texto de las tablas, texto de los párrafos)."""
    ruta = os.path.join(tempfile.gettempdir(), "test_acta.docx")
    render_acta(inf, ruta)
    d = _Document(ruta)
    tablas = ["\n".join(c.text for f in t.rows for c in f.cells) for t in d.tables]
    parrafos = "\n".join(p.text for p in d.paragraphs)
    os.remove(ruta)
    return tablas, parrafos


_tablas, _parrafos = _acta_generada(informe)
test("acta: tipo de convocatoria", "Ordinaria" in _tablas[2], True)
test("acta: fecha en la cabecera", "26 de junio de 2026" in _tablas[2], True)
test("acta: duración rellena", "Desde las 12:00 hasta las 13:30 horas" in _tablas[2], True)
test("acta: presidente de la grabación en mayúsculas, como la celda de la plantilla",
     "SERGIO DE FEZ CEREZUELA" in _tablas[2], True)
test("acta: expediente en blanco", "PLN/2026/" in _tablas[1], False)
test("acta: expediente sustituido por el hueco", HUECO in _tablas[1], True)
# El acta lista los puntos seguidos, sin las bandas A) / B) / C).
test("acta: un único encabezado ORDEN DEL DÍA", _tablas[3].strip(), "ORDEN DEL DÍA")
test("acta: sin las bandas A)/B)/C) de la plantilla",
     any("PARTE RESOLUTIVA" in t or "ACTIVIDAD DE CONTROL" in t for t in _tablas), False)
test("acta: resolutiva y control seguidos bajo el mismo encabezado",
     "APROBACIÓN SI PROCEDE" in _tablas[4] and "DECRETOS DE ALCALDÍA" in _tablas[4], True)
test("acta: los puntos van en el orden de la convocatoria",
     _tablas[4].index("APROBACIÓN SI PROCEDE") < _tablas[4].index("DECRETOS DE ALCALDÍA"), True)
test("acta: numeración del punto", "1º)" in _tablas[4], True)
test("acta: el acuerdo lleva su fórmula y su modalidad de votación",
     "El Pleno del Ayuntamiento ACUERDA por unanimidad" in _tablas[4], True)
test("acta: el debate se parte en párrafos, no en un bloque",
     "El Sr. Alcalde da cuenta del acta de la sesión anterior.\nNo se formulan" in _tablas[4],
     True)
test("acta: el título del punto queda en su propio renglón",
     "1º) APROBACIÓN SI PROCEDE DEL ACTA DE LA SESIÓN ANTERIOR.\nEl Sr. Alcalde" in _tablas[4],
     True)
test("acta: ruegos con quien los formula", "D. Joaquín Martínez" in _tablas[4], True)
test("acta: contenido del ruego", "camino de la Fuente" in _tablas[4], True)
test("acta: sin marcas de tiempo", "00:03:12" in "".join(_tablas), False)
test("acta: fórmula de cierre presente", "no habiendo más asuntos que tratar" in _parrafos, True)
test("acta: asistentes en el párrafo de apertura", "Lorena Luján Chujfi" in _parrafos, True)

# Sin esas bandas no queda ninguna sección vacía.
_sin_ruegos = InformePleno.model_validate(dict(INFORME_MINIMO, ruegos_y_preguntas=[]))
_tablas_sr, _ = _acta_generada(_sin_ruegos)
test("acta: sin ruegos no quedan secciones huérfanas",
     any("No hay asuntos" in t for t in _tablas_sr), False)
test("acta: la plantilla queda en cinco tablas", len(_tablas_sr), 5)

# Decisión de la spec: sin presidente identificado, "Presidida por" conserva el nombre de la plantilla
# (la secretaria revisa el borrador a mano antes de sellarlo).
_sin_presidente = InformePleno.model_validate(dict(INFORME_MINIMO, presidente=None))
_tablas_sp, _ = _acta_generada(_sin_presidente)
test("acta: sin presidente en la grabación conserva el de la plantilla",
     "LORENA LUJÁN CHUJFI" in _tablas_sp[2], True)

# La fórmula de cierre nombra a quien preside desde PRESIDENCIA en vez de dejar un hueco.
_cierre_sp = formula_cierre(_sin_presidente)
test("acta: el cierre nombra a quien preside aunque la grabación no lo diga",
     PRESIDENCIA["tratamiento"] in _cierre_sp, True)
test("acta: el cierre nunca deja el hueco en la presidencia",
     f"acto, {HUECO} levanta" in _cierre_sp, False)
test("acta: la fórmula de escape no llega al cierre como si fuera un nombre",
     "no identificado en la grabación levanta" in
     formula_cierre(InformePleno.model_validate(
         dict(INFORME_MINIMO, presidente="no identificado en la grabación"))), False)

# La extraordinaria usa su plantilla y rellena el motivo, que la ordinaria no tiene.
_extra = InformePleno.model_validate(dict(
    INFORME_MINIMO, tipo_sesion="extraordinaria",
    motivo_convocatoria="Aprobación del presupuesto municipal"))
_tablas_ex, _ = _acta_generada(_extra)
test("acta: plantilla extraordinaria", "Extraordinaria" in _tablas_ex[2], True)
test("acta: motivo de la convocatoria", "Aprobación del presupuesto" in _tablas_ex[2], True)

# tipo_sesion "no consta" no puede elegir plantilla: es un error, no un valor por defecto.
_sin_tipo = None
try:
    _acta_generada(_vacio)
except ValueError:
    _sin_tipo = "error"
test("acta: tipo no consta aborta", _sin_tipo, "error")


# ── forma del documento: comillas, negrita, alineación y sangría ──────────────
print("── forma del acta (comillas, negrita, alineación, sangría) ───────────")

from plenos_acta import SANGRIA, comillas

# Comillas unificadas en código, no pidiéndoselo al modelo (mezclaba tipos en un mismo punto).
test("comillas: las dobles rectas se vuelven tipográficas",
     comillas('la zona conocida como "la playeta".'), "la zona conocida como “la playeta”.")
test("comillas: las simples también",
     comillas("excluir 'la playeta' de las restricciones"),
     "excluir “la playeta” de las restricciones")
test("comillas: dos pares en la misma frase",
     comillas('dijo "sí" y luego "no"'), "dijo “sí” y luego “no”")
test("comillas: una comilla suelta no se toca", comillas('un tubo de 5" de diámetro'),
     'un tubo de 5" de diámetro')
test("comillas: idempotente sobre las ya tipográficas",
     comillas("como “la playeta”."), "como “la playeta”.")


def _parrafos_orden(inf):
    """Los párrafos reales de la celda del orden del día, con su formato."""
    ruta = os.path.join(tempfile.gettempdir(), "test_acta_forma.docx")
    render_acta(inf, ruta)
    d = _Document(ruta)
    parrafos = list(d.tables[4].rows[0].cells[0].paragraphs)
    os.remove(ruta)
    return parrafos


_ps = _parrafos_orden(informe)
_encabezados = [p for p in _ps if p.text.startswith(("1º)", "2º)", "RUEGOS"))]
_cuerpo = [p for p in _ps if p not in _encabezados and p.text.strip()]

# La plantilla trae el párrafo de ejemplo centrado; no debe contagiar al primer punto.
test("acta: ningún párrafo del orden del día queda centrado",
     any(p.paragraph_format.alignment is not None for p in _ps), False)

# Título del punto en negrita y en su propio párrafo; el cuerpo, en el siguiente.
_p1 = _ps[0]
test("acta: el encabezado del punto va en negrita", _p1.runs[0].bold, True)
test("acta: el encabezado es solo el título",
     _p1.text, "1º) APROBACIÓN SI PROCEDE DEL ACTA DE LA SESIÓN ANTERIOR.")
test("acta: el cuerpo empieza en el párrafo siguiente",
     _ps[1].text.startswith("El Sr. Alcalde"), True)
test("acta: el cuerpo no va en negrita", _ps[1].runs[0].bold, None)

test("acta: los encabezados no llevan sangría",
     {p.paragraph_format.first_line_indent for p in _encabezados}, {0})
test("acta: todo párrafo de cuerpo lleva sangría",
     {p.paragraph_format.first_line_indent for p in _cuerpo}, {SANGRIA})

# Los ruegos se anuncian como punto más, sin numerar (el render no conoce el número de la convocatoria).
_ruegos = [p for p in _ps if p.text == "RUEGOS Y PREGUNTAS"]
test("acta: RUEGOS Y PREGUNTAS aparece como encabezado", len(_ruegos), 1)
test("acta: RUEGOS Y PREGUNTAS en negrita", _ruegos[0].runs[0].bold, True)
test("acta: RUEGOS Y PREGUNTAS antes de quién los formula",
     _ps.index(_ruegos[0]) < next(i for i, p in enumerate(_ps)
                                  if p.text.startswith("Ruegos y preguntas formuladas")),
     True)
test("acta: sin ruegos no aparece el encabezado",
     any(p.text == "RUEGOS Y PREGUNTAS" for p in _parrafos_orden(_sin_ruegos)), False)

# Si la convocatoria ya numera RUEGOS Y PREGUNTAS, el encabezado suelto no se duplica.
_con_punto_ruegos = InformePleno.model_validate(dict(
    INFORME_MINIMO,
    orden_del_dia=INFORME_MINIMO["orden_del_dia"] + [
        {"numero": 3, "parte": "control", "titulo": "RUEGOS Y PREGUNTAS",
         "texto": "Se abre el turno de ruegos y preguntas.",
         "acuerdo": None, "votacion": None}]))
_ps_ruegos = [p.text for p in _parrafos_orden(_con_punto_ruegos)]
test("acta: el punto RUEGOS Y PREGUNTAS de la convocatoria se escribe una vez",
     _ps_ruegos.count("3º) RUEGOS Y PREGUNTAS."), 1)
test("acta: sin encabezado suelto que lo duplique",
     "RUEGOS Y PREGUNTAS" in _ps_ruegos, False)


# ── convocatoria ──────────────────────────────────────────────────────────────
print("── convocatoria (orden del día) ──────────────────────────────────────")

from procesar_pleno import leer_convocatoria

test("convocatoria: sin ruta no hay convocatoria", leer_convocatoria(None), None)

with tempfile.TemporaryDirectory() as _tmp:
    # Binario y sin extraer texto: son escaneos y el PDF viaja entero a Gemini.
    _pdf = os.path.join(_tmp, "convocatoria.pdf")
    with open(_pdf, "wb") as _f:
        _f.write(b"%PDF-1.4 fake")
    test("convocatoria: se lee en bytes, sin extraer texto",
         leer_convocatoria(_pdf), b"%PDF-1.4 fake")

    # Un JPEG suelto se envuelve en un PDF para que el resto del pipeline vea siempre un PDF.
    from PIL import Image
    _jpg = os.path.join(_tmp, "convocatoria.jpg")
    Image.new("RGB", (4, 4), color="white").save(_jpg, format="JPEG")
    test("convocatoria: una foto/escaneo en JPEG se envuelve en un PDF",
         leer_convocatoria(_jpg)[:4], b"%PDF")

    _no_pdf = os.path.join(_tmp, "convocatoria.docx")
    with open(_no_pdf, "wb") as _f:
        _f.write(b"x")
    _rechazo = ""
    try:
        leer_convocatoria(_no_pdf)
    except ValueError as e:
        _rechazo = str(e)
    test("convocatoria: un fichero que no es PDF ni JPEG se rechaza",
         "PDF" in _rechazo and "JPEG" in _rechazo, True)

    _falta = None
    try:
        leer_convocatoria(os.path.join(_tmp, "no-existe.pdf"))
    except FileNotFoundError:
        _falta = "no existe"
    test("convocatoria: ruta inexistente avisa", _falta, "no existe")

# El auditor recibe la convocatoria como el generador; si no, marcaría los títulos como no respaldados.
_recibida = {"generar": None, "auditar": None, "corregir": None}
_CONV = b"%PDF-convocatoria"

import plenos_informe as _pi

_reales = (_pi.generar_informe, _pi.auditar_informe, _pi.corregir_informe)
_atrib_real2 = _pi.auditar_atribuciones
_pi.auditar_atribuciones = lambda t, i, c=None, **k: AuditoriaInforme(problemas=[])
try:
    def _gen_espia(t, convocatoria=None):
        _recibida["generar"] = convocatoria
        return _informe_v1
    def _aud_espia(t, i, convocatoria=None, rutas_tocadas=None):
        # El espía sustituye a la función real del módulo, así que sigue su firma.
        _recibida["auditar"] = convocatoria
        return AuditoriaInforme(problemas=[])
    def _cor_espia(t, i, p, convocatoria=None):
        _recibida["corregir"] = convocatoria
        return i
    _pi.generar_informe, _pi.auditar_informe, _pi.corregir_informe = (
        _gen_espia, _aud_espia, _cor_espia)
    # Sin kwargs inyectados el bucle narra su progreso; aquí se descarta.
    import contextlib, io as _io
    with contextlib.redirect_stdout(_io.StringIO()):
        _pi.bucle_informe("transcripción", _CONV)
finally:
    _pi.generar_informe, _pi.auditar_informe, _pi.corregir_informe = _reales
    _pi.auditar_atribuciones = _atrib_real2

test("convocatoria: la recibe el generador", _recibida["generar"], _CONV)
test("convocatoria: la recibe el AUDITOR", _recibida["auditar"], _CONV)

# Los fakes inyectados conservan su firma: el bucle no les pasa la convocatoria.
_arity = {"ok": False}
def _gen_viejo(t):
    _arity["ok"] = True
    return _informe_v1
def _aud_viejo(t, i):
    return AuditoriaInforme(problemas=[])
def _cor_viejo(t, i, p):
    return i
bucle_informe("t", _CONV, generar=_gen_viejo, auditar=_aud_viejo, corregir=_cor_viejo)
test("convocatoria: los fakes inyectados mantienen su firma", _arity["ok"], True)


# ── transcripción con AssemblyAI ──────────────────────────────────────────────
print()
print("── AssemblyAI: cuerpo de la petición y sondeo ────────────────────────")

import procesar_pleno as _pp


class _RequestsFalso:
    """Sustituye a requests: upload → submit → processing → completed."""
    def __init__(self):
        self.cuerpo = None
        self.sondeos = 0

    class _R:
        def __init__(self, datos): self._datos = datos
        def json(self): return self._datos
        def raise_for_status(self): pass

    def post(self, url, **kw):
        if url.endswith("/v2/upload"):
            return self._R({"upload_url": "https://cdn.assemblyai.com/upload/xyz"})
        self.cuerpo = kw["json"]
        return self._R({"id": "tid-1"})

    def get(self, url, **kw):
        self.sondeos += 1
        if self.sondeos < 2:
            return self._R({"status": "processing"})
        return self._R({"status": "completed",
                        "utterances": [{"start": 5000, "speaker": "C", "text": "Se abre la sesión."}]})


class _TimeFalso:
    def __init__(self): self.dormido = 0
    def sleep(self, s): self.dormido += s


_falso, _reloj = _RequestsFalso(), _TimeFalso()
_pp.requests, _pp.time = _falso, _reloj
os.environ["ASSEMBLYAI_API_KEY"] = "clave-de-prueba"
_audio = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_plenos.py")
_texto = _pp.transcribir_assemblyai(_audio)
_pp.requests, _pp.time = __import__("requests"), __import__("time")

test("assemblyai: sondea hasta completed", _falso.sondeos, 2)
test("assemblyai: devuelve la transcripción diarizada",
     _texto, "[00:00:05] Interviniente C: Se abre la sesión.")
test("assemblyai: modelo universal-3.5-pro", _falso.cuerpo["speech_models"], ["universal-3-5-pro"])
test("assemblyai: español fijo, sin detección", _falso.cuerpo["language_code"], "es")
test("assemblyai: diarización activada", _falso.cuerpo["speaker_labels"], True)
# min/max van DENTRO de speaker_options; sueltos la API los ignora.
# Rango 4-15 a propósito: partir a una persona en dos etiquetas es recuperable; fundir a dos, no.
test("assemblyai: rango de locutores anidado en speaker_options",
     _falso.cuerpo["speaker_options"], {"min_speakers_expected": 6, "max_speakers_expected": 15})
test("assemblyai: la corporación viaja en keyterms",
     "Lorena Luján Chujfi" in _falso.cuerpo["keyterms_prompt"], True)


# ── _subir_audio: la subida se corta y se reintenta ───────────────────────────
print()
print("── AssemblyAI: reintento de subida ───────────────────────────────────")

import requests as _requests_real


class _RequestsSubidaFalla:
    """Primer intento: la conexión se corta a mitad de subida. Segundo: sube bien."""
    RequestException = _requests_real.RequestException

    def __init__(self, fallos: int = 1):
        self.fallos = fallos
        self.intentos = 0

    class _R:
        def __init__(self, datos): self._datos = datos
        def json(self): return self._datos
        def raise_for_status(self): pass

    def post(self, url, **kw):
        self.intentos += 1
        # Se consume el cuerpo para simular un corte a mitad de la transferencia.
        kw["data"].read()
        if self.intentos <= self.fallos:
            raise _requests_real.exceptions.ConnectionError("EOF occurred in violation of protocol")
        return self._R({"upload_url": "https://cdn.assemblyai.com/upload/xyz"})


_esperas_subida = []
_pp.requests = _RequestsSubidaFalla(fallos=1)
_pp.time = _TimeFalso()
_pp.time.sleep = lambda s: _esperas_subida.append(s)
try:
    _url = _pp._subir_audio(_audio, {"authorization": "clave-de-prueba"})
    test("subir_audio: reintenta y acaba devolviendo la URL",
         _url, "https://cdn.assemblyai.com/upload/xyz")
    test("subir_audio: reabre el fichero en cada intento", _pp.requests.intentos, 2)
    test("subir_audio: espera entre el primer fallo y el reintento",
         len(_esperas_subida), 1)
finally:
    _pp.requests, _pp.time = _requests_real, __import__("time")

# Agotados los intentos, la excepción se propaga: no hay tercer intento silencioso.
_pp.requests = _RequestsSubidaFalla(fallos=99)
_pp.time = _TimeFalso()
_pp.time.sleep = lambda s: None
try:
    _propago = False
    try:
        _pp._subir_audio(_audio, {"authorization": "clave-de-prueba"}, intentos=3)
    except _requests_real.exceptions.ConnectionError:
        _propago = True
    test("subir_audio: agotados los intentos, propaga el error", _propago, True)
    test("subir_audio: se intentó el número de veces pedido", _pp.requests.intentos, 3)
finally:
    _pp.requests, _pp.time = _requests_real, __import__("time")


# ── transcribir(): sin fallback silencioso a Groq ─────────────────────────────
print()
print("── transcribir(): AssemblyAI no cae a Groq si hay clave ──────────────")

_env_previo = os.environ.get("ASSEMBLYAI_API_KEY")
os.environ["ASSEMBLYAI_API_KEY"] = "clave-de-prueba"


def _aai_que_revienta(ruta):
    raise RuntimeError("EOF occurred in violation of protocol")


_aai_real = _pp.transcribir_assemblyai
_trocear_llamado = {"si": False}


def _trocear_espia(ruta, tmp, segundos=1800):
    _trocear_llamado["si"] = True
    return []


_trocear_real = _pp.trocear_audio
_pp.transcribir_assemblyai = _aai_que_revienta
_pp.trocear_audio = _trocear_espia
try:
    _revento_aai = False
    try:
        _pp.transcribir(_audio, tempfile.mkdtemp())
    except RuntimeError:
        _revento_aai = True
    test("transcribir: si AssemblyAI falla con clave presente, propaga el error",
         _revento_aai, True)
    test("transcribir: NO cae a Groq (no llama a trocear_audio)",
         _trocear_llamado["si"], False)
finally:
    _pp.transcribir_assemblyai = _aai_real
    _pp.trocear_audio = _trocear_real
    if _env_previo is None:
        os.environ.pop("ASSEMBLYAI_API_KEY", None)
    else:
        os.environ["ASSEMBLYAI_API_KEY"] = _env_previo

_env_previo2 = os.environ.pop("ASSEMBLYAI_API_KEY", None)
_trocear_llamado2 = {"si": False}


def _trocear_espia2(ruta, tmp, segundos=1800):
    _trocear_llamado2["si"] = True
    return []


_pi_chunks_real = _pp.transcribir_chunks
_pp.trocear_audio = _trocear_espia2
_pp.transcribir_chunks = lambda chunks: "transcripción de groq"
try:
    _resultado_groq = _pp.transcribir(_audio, tempfile.mkdtemp())
    test("transcribir: sin ASSEMBLYAI_API_KEY usa Groq",
         _trocear_llamado2["si"], True)
    test("transcribir: y devuelve lo que produce Groq",
         _resultado_groq, "transcripción de groq")
finally:
    _pp.trocear_audio = _trocear_real
    _pp.transcribir_chunks = _pi_chunks_real
    if _env_previo2 is not None:
        os.environ["ASSEMBLYAI_API_KEY"] = _env_previo2


# ── esquema strict de OpenRouter ──────────────────────────────────────────────
print()
print("── esquema strict ────────────────────────────────────────────────────")

from plenos_informe import _esquema_estricto

_e = _esquema_estricto(InformePleno.model_json_schema())
test("strict: todas las propiedades son required",
     set(_e["required"]), set(_e["properties"]))
test("strict: sin additionalProperties", _e["additionalProperties"], False)
test("strict: los sub-esquemas también se normalizan",
     [(d["additionalProperties"], set(d["required"]) == set(d["properties"]))
      for d in _e["$defs"].values()],
     [(False, True)] * len(_e["$defs"]))
test("strict: sin `default`, que strict prohíbe",
     "default" in str(_e), False)
test("strict: los opcionales conservan su vía de escape (null)",
     any(_v.get("type") == "null" for _v in _e["properties"]["presidente"]["anyOf"]), True)
test("strict: identificacion_locutores es required pese a tener default",
     "identificacion_locutores" in _e["required"], True)
test("strict: sin `default` tampoco en identificacion_locutores",
     "default" not in _e["properties"]["identificacion_locutores"], True)


# ── la transcripción sobrevive al fallo del LLM ───────────────────────────────
print("── la transcripción sobrevive al fallo del LLM ──────────────────────")

# Si el bucle LLM revienta, la transcripción (cara de repetir) ya debe estar en disco.
import plenos_informe as _pi_rescate
from pathlib import Path as _Path_rescate

with tempfile.TemporaryDirectory() as _tmp_r:
    _tmp_r = _Path_rescate(_tmp_r)
    _bd0 = _pp.BORRADOR_DIR
    _pp.BORRADOR_DIR = _tmp_r / "actas"

    def _bucle_que_revienta(transcripcion, convocatoria=None):
        raise RuntimeError("el modelo devolvió una respuesta sin contenido")

    _bucle0 = _pi_rescate.bucle_informe
    _pi_rescate.bucle_informe = _bucle_que_revienta
    try:
        _revento = False
        try:
            _pp.procesar_pleno(None, "vid123", "PLENO EXTRAORDINARIO", "2026-09-02",
                               "https://youtu.be/vid123",
                               transcripcion="[00:00:01] Interviniente A: buenas tardes.")
        except RuntimeError:
            _revento = True
        _md = _pp.BORRADOR_DIR / "2026-09-02" / "2026-09-02-transcripcion.md"
        test("rescate: el bucle falló (premisa del test)", _revento, True)
        test("rescate: la transcripción queda en disco pese al fallo", _md.exists(), True)
        test("rescate: y con el texto íntegro",
             "buenas tardes" in _md.read_text(encoding="utf-8"), True)
        test("rescate: entrada.json queda escrito para --rehacer-informe",
             (_pp.BORRADOR_DIR / "2026-09-02" / "entrada.json").exists(), True)
    finally:
        _pi_rescate.bucle_informe = _bucle0
        _pp.BORRADOR_DIR = _bd0


# ── respuesta de OpenRouter sin contenido ─────────────────────────────────────
print("── respuesta de OpenRouter sin contenido ────────────────────────────")

# content=None llegaba hasta pydantic con un error mudo sobre la causa.
_peticion0 = _pi_rescate._peticion
_pi_rescate._peticion = lambda cuerpo, intentos=4: {
    "choices": [{"message": {"content": None}, "finish_reason": "length",
                 "native_finish_reason": "MAX_TOKENS"}],
    "usage": {"prompt_tokens": 45000, "completion_tokens": 545,
              "completion_tokens_details": {"reasoning_tokens": 545}},
}
try:
    _msg = ""
    try:
        _pi_rescate._llamar_llm("instrucciones", "contenido",
                                _pi_rescate.AuditoriaInforme, None, "auditor")
    except RuntimeError as e:
        _msg = str(e)
    test("sin contenido: lanza RuntimeError, no ValidationError de pydantic",
         _msg.startswith("auditor: OpenRouter devolvió una respuesta sin contenido"), True)
    test("sin contenido: el mensaje trae el finish_reason",
         "'length'" in _msg and "MAX_TOKENS" in _msg, True)
finally:
    _pi_rescate._peticion = _peticion0


# ── el proveedor corta la respuesta (HTTP 200 con error dentro) ───────────────
print("── el proveedor corta la respuesta ──────────────────────────────────")

# OpenRouter devuelve 200 con {"error": ...} dentro del choice; debe reintentarse.
# La petición va en streaming, así que el falso devuelve líneas SSE.
_corte = ['data: {"choices":[{"finish_reason":"error","delta":{},'
          '"error":{"code":504,"message":"Upstream idle timeout exceeded"}}]}']
_buena = ['data: {"choices":[{"finish_reason":"stop",'
          '"delta":{"content":"{\\"problemas\\": []}"}}]}', 'data: [DONE]']

class _RespuestaFalsa:
    def __init__(self, lineas): self._lineas = lineas
    status_code = 200
    encoding = None
    def raise_for_status(self): pass
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def iter_lines(self, decode_unicode=False): return iter(self._lineas)

_llamadas = {"n": 0}
def _post_falso(url, headers=None, json=None, timeout=None, stream=None):
    _llamadas["n"] += 1
    return _RespuestaFalsa(_corte if _llamadas["n"] == 1 else _buena)

_post0, _sleep0 = _pi_rescate.requests.post, _pi_rescate.time.sleep
_esperas = []
_pi_rescate.requests.post = _post_falso
_pi_rescate.time.sleep = lambda s: _esperas.append(s)
os.environ.setdefault("OPENROUTER_API_KEY", "test")
try:
    import contextlib as _ctx_corte, io as _io_corte
    with _ctx_corte.redirect_stdout(_io_corte.StringIO()):
        _datos = _pi_rescate._peticion({"model": "x"})
    test("corte: reintenta en vez de rendirse", _llamadas["n"], 2)
    test("corte: devuelve la respuesta buena del reintento",
         _datos["choices"][0]["message"]["content"], '{"problemas": []}')
    test("corte: espera antes de reintentar", _esperas, [120])
finally:
    _pi_rescate.requests.post, _pi_rescate.time.sleep = _post0, _sleep0

_llamadas_todas = {"n": 0}
def _post_siempre_roto(url, headers=None, json=None, timeout=None, stream=None):
    _llamadas_todas["n"] += 1
    return _RespuestaFalsa(_corte)

_pi_rescate.requests.post = _post_siempre_roto
_pi_rescate.time.sleep = lambda s: None
try:
    _msg_corte = ""
    with _ctx_corte.redirect_stdout(_io_corte.StringIO()):
        try:
            _pi_rescate._llamar_llm("i", "c", _pi_rescate.AuditoriaInforme, None, "auditor")
        except RuntimeError as e:
            _msg_corte = str(e)
    test("corte: tras agotar los intentos, error legible",
         "sin contenido" in _msg_corte, True)
    test("corte: se agotan los 4 intentos", _llamadas_todas["n"], 4)
finally:
    _pi_rescate.requests.post, _pi_rescate.time.sleep = _post0, _sleep0


# ── el corrector no rellena recuentos ────────────────────────────────────────
print("── el corrector no rellena recuentos ────────────────────────────────")

# El corrector cambiaba 5 por 4 en vez de poner null; la regla debe seguir en el prompt.
_pc = _pi_rescate.PROMPT_CORRECTOR
test("corrector: la regla de recuentos está en el prompt",
     "RECUENTOS DE VOTOS" in _pc, True)
test("corrector: prohíbe cambiar la cifra por otra que encaje",
     "NO es\n   cambiar ese número por otro" in _pc, True)
test("corrector: prohíbe deducir restando de los asistentes",
     "restando del número de asistentes" in _pc, True)
test("corrector: prohíbe el 0 de relleno",
     "va a `null`, nunca a 0" in _pc, True)

# Bloque compartido: el `0` inventado lo escribía el generador, no el corrector.
_pg = _pi_rescate.PROMPT_GENERADOR
test("generador: recibe también la regla de recuentos",
     "RECUENTOS DE VOTOS" in _pg, True)
test("generador: recuento incompleto va entero a null",
     "Un recuento incompleto NO es un recuento" in _pg, True)
test("generador: una abstención verbalizada sí se cuenta",
     "si alguien dice que se abstiene,\n  cuenta esa abstención" in _pg, True)
test("generador: el resultado se conserva aunque los números vayan a null",
     "ese resultado se escribe aunque los números vayan a `null`" in _pg, True)

# Dos concejales comparten apellido: el apellido solo no identifica a ninguno.
test("corporación: avisa de que hay dos Martínez",
     "son DOS personas distintas que comparten apellido" in _pg, True)
test("corporación: el aviso llega también al auditor",
     "son DOS personas distintas que comparten apellido" in _pi_rescate.PROMPT_AUDITOR, True)

# CORPORACION debe dejar claro que el público existe, que no está en ningún listado y cómo se le nombra.
_corp = _pi_rescate.CORPORACION
test("corporación: avisa de que asiste público y algunos vecinos intervienen",
     "PÚBLICO ASISTENTE" in _corp, True)
test("corporación: el público no está en ningún listado (no se identifica por descarte)",
     'no se les puede identificar "por descarte" contra la Corporación' in _corp, True)
test("corporación: el público no vota ni se cuenta, y nunca va en asistentes/ausentes",
     "no se cuentan en ningún recuento" in _corp
     and "nunca van en `asistentes` ni en `ausentes`" in _corp, True)
test("corporación: prohíbe nombre y apellidos de un vecino asistente en el acta",
     "NUNCA con nombre y apellidos" in _corp, True)
test("corporación: una voz no identificada puede ser público, no forzosamente un concejal",
     "puede perfectamente ser público" in _corp, True)
test("corporación: el bloque de público llega también al auditor y al corrector",
     ("PÚBLICO ASISTENTE" in _pg,
      "PÚBLICO ASISTENTE" in _pi_rescate.PROMPT_AUDITOR),
     (True, True))
test("corrector: resultado y modalidad se conservan",
     "`resultado` y `modalidad` se conservan" in _pc, True)
test("corrector: sus reglas siguen numeradas sin saltos",
     [n for n in range(1, 8) if f"\n{n}. " in _pc], list(range(1, 8)))


# ── "sin votación" como cadena en lugar del objeto ───────────────────────────
print("── \"sin votación\" como cadena ─────────────────────────────────────")

# El generador confundía dos vías de escape; la intención es inequívoca, así que se normaliza.
from plenos_informe import PuntoOrdenDia as _POD
_base = {"numero": 2, "parte": "control", "titulo": "X", "texto": "y"}
for _cadena in ("sin votación", "sin votacion", "no consta", "", "  SIN VOTACIÓN  "):
    test(f"cadena {_cadena!r} en `votacion` se normaliza a null",
         _POD.model_validate(dict(_base, votacion=_cadena)).votacion, None)
test("null explícito sigue siendo null",
     _POD.model_validate(dict(_base, votacion=None)).votacion, None)
_obj = _POD.model_validate(dict(_base, votacion={"resultado": "aprobado",
                                                 "modalidad": "unanimidad"}))
test("el objeto de votación sigue validándose", _obj.votacion.resultado, "aprobado")

# Una cadena que no significa ausencia debe seguir fallando.
_fallo = False
try:
    _POD.model_validate(dict(_base, votacion="aprobado por unanimidad"))
except Exception:
    _fallo = True
test("una cadena con contenido sigue siendo un error", _fallo, True)

test("el prompt explica que `votacion` es objeto o null, nunca cadena",
     "nunca una cadena de texto" in _pi_rescate.PROMPT_GENERADOR, True)


# ── reensamblado del stream SSE ───────────────────────────────────────────────
# El streaming evita el 504 por ociosidad; el reensamblado debe dar la forma que espera _llamar_llm.
_sse = _pi_rescate._reensamblar_sse
_ok = _sse([
    ': OPENROUTER PROCESSING',
    'data: {"choices":[{"delta":{"content":"{\\"a\\":"}}]}',
    '',
    ': OPENROUTER PROCESSING',
    'data: {"choices":[{"delta":{"content":"1}"},"finish_reason":"stop"}]}',
    'data: {"choices":[],"usage":{"prompt_tokens":7}}',
    'data: [DONE]',
])
test("los deltas se concatenan en el content", _ok["choices"][0]["message"]["content"], '{"a":1}')
test("el finish_reason se conserva", _ok["choices"][0]["finish_reason"], "stop")
test("el usage del último trozo se conserva", _ok["usage"]["prompt_tokens"], 7)
test("un stream limpio no lleva error", "error" in _ok["choices"][0], False)

# El corte llega como un trozo con el error en el choice; debe propagarse para poder reintentar.
_roto = _sse([
    'data: {"choices":[{"delta":{"content":"{\\"a\\":"}}]}',
    'data: {"choices":[{"error":{"code":504,"message":"Upstream idle timeout exceeded"}}]}',
])
test("el error del proveedor se propaga", _roto["choices"][0]["error"]["code"], 504)

test("el auditor también recibe el bloque de RECUENTOS",
     "RECUENTOS DE VOTOS" in _pi_rescate.PROMPT_AUDITOR, True)


# ── mapa de voces: reglas del bloque DIARIZACION y revisión del auditor ───────
print("── mapa de voces (DIARIZACION + auditor) ─────────────────────────────")

# DIARIZACION debe llevar las reglas de "da la palabra a X" y de la voz que excluye a una persona, y llegar a los tres roles.
_diar = _pi_rescate.DIARIZACION
test("diarización: dar la palabra por su nombre NO identifica a quien habla después",
     "no identifica la voz que\n  habla a continuación" in _diar, True)
test("diarización: regla de exclusión explícita",
     "REGLA DE EXCLUSIÓN" in _diar and "esa etiqueta NO es\n  esa persona" in _diar, True)
test("diarización: la evidencia tiene que ser cita literal, no un resumen",
     "CITA LITERAL de la transcripción" in _diar, True)
test("diarización: primero el mapa, después el acta",
     "PRIMERO EL MAPA, DESPUÉS EL ACTA" in _diar, True)

# Regla de voces mezcladas (DIARIZACION y CORPORACION).
test("diarización: avisa de que una etiqueta puede fusionar a dos personas",
     "haya fusionado dos voces parecidas bajo una sola etiqueta" in _diar, True)
test("diarización: la señal es que la etiqueta afirme identidades incompatibles",
     "afirmando identidades INCOMPATIBLES" in _diar, True)
test("diarización: cita el caso real (presidenta de la asociación de jubilados)",
     "presidenta de la asociación de jubilados" in _diar, True)
test("diarización: ante la contradicción, no se elige entre las dos identidades",
     "NO elijas entre las dos identidades" in _diar, True)
test("diarización: el valor de escape es 'etiqueta con voces mezcladas'",
     '"etiqueta con voces mezcladas"' in _diar, True)
test("diarización: una identificación propia manda sobre la etiqueta contaminada",
     "una intervención que se identifica a sí misma manda sobre lo que diga su\n  etiqueta"
     in _diar, True)

# DIARIZACION es un bloque compartido: el auditor debe verlo para poder objetar.
test("diarización: llega al generador", _diar in _pi_rescate.PROMPT_GENERADOR, True)
test("diarización: llega al auditor", _diar in _pi_rescate.PROMPT_AUDITOR, True)
test("diarización: llega al corrector", _diar in _pi_rescate.PROMPT_CORRECTOR, True)

# El auditor revisa el mapa de voces como tal, no solo las atribuciones sueltas.
_pa = _pi_rescate.PROMPT_AUDITOR
test("auditor: instrucción explícita de revisar identificacion_locutores",
     "identificacion_locutores" in _pa, True)
test("auditor: comprueba que la evidencia del mapa exista y lo sostenga",
     "que su\n`evidencia` es una cita que existe de verdad en la transcripción" in _pa, True)
test("auditor: objeta atribuciones que no estén respaldadas por el mapa",
     "cuya etiqueta\nno esté identificada en el mapa" in _pa, True)

# El auditor busca activamente la etiqueta contaminada, que el generador no ve al redactar.
test("auditor: instrucción explícita de buscar etiquetas contaminadas",
     "BUSCA ACTIVAMENTE LAS ETIQUETAS CONTAMINADAS" in _pa, True)
test("auditor: se le pide leer todas las intervenciones de cada etiqueta, no solo la citada",
     "lee TODAS sus\nintervenciones en la transcripción" in _pa, True)
test("auditor: objeta el patrón aunque la cita del mapa sea literal",
     "la cita\npuede ser literal y aun así la etiqueta seguir mezclando a dos personas."
     in _pa, True)


# ── mapa de voces: los dos huecos nuevos (turnos alternos + jerarquía de pruebas) ─
print("── mapa de voces: turnos alternos y jerarquía de pruebas ─────────────")

# Hueco 1: dos etiquetas que dicen ser la MISMA persona pese a alternarse entre sí.
test("diarización: regla de turnos alternos explícita",
     "REGLA DE TURNOS ALTERNOS" in _diar, True)
test("diarización: dos etiquetas que se alternan son personas distintas",
     "son PERSONAS DISTINTAS" in _diar, True)
test("diarización: si el mapa las funde, se marca conflicto y las dos escapan",
     'manda las dos a "no identificado en la grabación"' in _diar, True)
test("diarización: salvo que una prueba sea claramente más fuerte, que prevalece",
     "salvo que una de las dos pruebas sea\n  claramente más fuerte" in _diar, True)
test("diarización: matiz — si nunca se alternan, sí pueden ser la misma persona partida",
     "si dos etiquetas\n  NUNCA se alternan entre sí, sí pueden ser la misma persona partida"
     in _diar, True)

# Hueco 2: la jerarquía de pruebas decide cuándo una prueba fuerte desplaza a una débil ya anotada.
test("diarización: jerarquía de pruebas explícita", "JERARQUÍA DE PRUEBAS" in _diar, True)
test("diarización: autoidentificación es la prueba más fuerte",
     "SE IDENTIFICA A SÍ MISMA" in _diar, True)
test("diarización: nombrada respondiendo es la segunda",
     "NOMBRA\n  RESPONDIÉNDOLE" in _diar, True)
test("diarización: dirigirse a ella por nombre o cargo es la tercera",
     "SE DIRIGE A ELLA" in _diar, True)
test("diarización: gana la prueba fuerte, no la que llegó primero",
     "gana la prueba fuerte, NO\n  la que llegó primero" in _diar, True)

# Las reglas nuevas siguen llegando a los tres roles vía `_diar`.
test("diarización: turnos alternos llega a los tres roles (vía DIARIZACION completo)",
     ("REGLA DE TURNOS ALTERNOS" in _pg, "REGLA DE TURNOS ALTERNOS" in _pa,
      "REGLA DE TURNOS ALTERNOS" in _pi_rescate.PROMPT_CORRECTOR),
     (True, True, True))
test("diarización: jerarquía de pruebas llega a los tres roles",
     ("JERARQUÍA DE PRUEBAS" in _pg, "JERARQUÍA DE PRUEBAS" in _pa,
      "JERARQUÍA DE PRUEBAS" in _pi_rescate.PROMPT_CORRECTOR),
     (True, True, True))

# El auditor recibe además las dos comprobaciones específicas para estos huecos.
test("auditor: instrucción explícita de comprobar el patrón contrario (dos etiquetas, una persona)",
     "COMPRUEBA TAMBIÉN EL PATRÓN CONTRARIO" in _pa, True)
test("auditor: remite a la regla de turnos alternos para ese patrón contrario",
     "REGLA DE TURNOS\nALTERNOS" in _pa, True)
test("auditor: comprueba que la evidencia sea la prueba de más peso, no una más débil",
     "es la prueba de MÁS PESO" in _pa, True)


# ── asistente: adaptaciones de procesar_pleno ─────────────────────────────────
import json
import tempfile
from pathlib import Path

print()
print("── adaptaciones para el asistente ────────────────────────────────────")

# La carpeta de actas puede vivir fuera del repo (en el PC del Ayuntamiento no hay repo).
_bd_previo = _pp.BORRADOR_DIR
_actas_previo = os.environ.pop("ACTAS_DIR", None)
try:
    test("sin ACTAS_DIR se usa la carpeta del repo",
         _pp.dir_borrador("2026-09-02"), _bd_previo / "2026-09-02")
    os.environ["ACTAS_DIR"] = r"C:\Escritorio\Actas de Plenos\Actas generadas"
    test("con ACTAS_DIR manda la carpeta configurada",
         _pp.dir_borrador("2026-09-02"),
         Path(r"C:\Escritorio\Actas de Plenos\Actas generadas") / "2026-09-02")
finally:
    os.environ.pop("ACTAS_DIR", None)
    if _actas_previo is not None:
        os.environ["ACTAS_DIR"] = _actas_previo

# Un extraordinario y un ordinario del mismo día no pueden compartir carpeta.
test("ordinaria: la carpeta lo dice", _pp.clave_pleno("2026-10-07", "ordinaria"), "2026-10-07-ordinario")
test("sin tipo: la carpeta es la fecha", _pp.clave_pleno("2026-10-07"), "2026-10-07")
test("extraordinaria: carpeta distinta el mismo día",
     _pp.clave_pleno("2026-10-07", "extraordinaria"), "2026-10-07-extraordinario")

# Dentro del .exe, sys.executable es el propio ejecutable: `sys.executable -m yt_dlp`
# se relanzaría a sí mismo en vez de descargar nada.
_yt_previo = os.environ.pop("YT_DLP_EXE", None)
try:
    test("sin YT_DLP_EXE se usa el módulo de Python",
         _pp._comando_yt_dlp(), [sys.executable, "-m", "yt_dlp"])
    os.environ["YT_DLP_EXE"] = r"C:\Actas\yt-dlp.exe"
    test("con YT_DLP_EXE se usa el binario incluido",
         _pp._comando_yt_dlp(), [r"C:\Actas\yt-dlp.exe"])

    # Congelado y sin YT_DLP_EXE: debe avisar, no relanzar el propio asistente.
    os.environ.pop("YT_DLP_EXE", None)
    _frozen_previo = getattr(sys, "frozen", None)
    sys.frozen = True
    try:
        _excepcion_frozen = None
        try:
            _pp._comando_yt_dlp()
        except _pp.ErrorDeDescarga as e:
            _excepcion_frozen = e
        test("congelado y sin YT_DLP_EXE, avisa en vez de relanzarse a sí mismo",
             isinstance(_excepcion_frozen, _pp.ErrorDeDescarga), True)
    finally:
        if _frozen_previo is None:
            del sys.frozen
        else:
            sys.frozen = _frozen_previo
finally:
    os.environ.pop("YT_DLP_EXE", None)
    if _yt_previo is not None:
        os.environ["YT_DLP_EXE"] = _yt_previo

# El asistente necesita distinguir "no se pudo descargar el vídeo" (tiene salida:
# ofrecerle usar un fichero local) de cualquier otro fallo.
test("el error de descarga es distinguible",
     issubclass(_pp.ErrorDeDescarga, RuntimeError), True)


# ── asistente: instalación y configuración ────────────────────────────────────
print()
print("── asistente: instalación ────────────────────────────────────────────")

import asistente_plenos as _ap

_tmp_inst = Path(tempfile.mkdtemp())
(_tmp_inst / "config").mkdir()

# Bloques anteriores dejan las claves en el entorno; se quitan para probar la detección y se devuelven al final.
_claves_previas = {c: os.environ.pop(c, None) for c in _ap.CLAVES_NECESARIAS}
try:
    test("sin claves en el entorno, se listan las que faltan",
         _ap.cargar_configuracion(_tmp_inst / "config"),
         ["ASSEMBLYAI_API_KEY", "OPENROUTER_API_KEY"])

    (_tmp_inst / "config" / "configuracion.env").write_text(
        "ASSEMBLYAI_API_KEY=aaa\nOPENROUTER_API_KEY=bbb\n", encoding="utf-8")
    test("con el fichero relleno, no falta ninguna",
         _ap.cargar_configuracion(_tmp_inst / "config"), [])
    test("las claves quedan en el entorno para el pipeline",
         os.environ["OPENROUTER_API_KEY"], "bbb")
finally:
    for _c, _v in _claves_previas.items():
        if _v is None:
            os.environ.pop(_c, None)
        else:
            os.environ[_c] = _v

_nombre = _ap.nuevo_log(_tmp_inst, "2026-09-02").name
test("el nombre del registro lleva la fecha del pleno",
     _nombre.endswith("_pleno-2026-09-02.log"), True)

# El Bloc de notas guarda con BOM; sin utf-8-sig la primera clave del fichero se pierde en silencio.
_tmp_bom = Path(tempfile.mkdtemp())
(_tmp_bom / "config").mkdir()
_claves_previas_bom = {c: os.environ.pop(c, None) for c in _ap.CLAVES_NECESARIAS}
try:
    (_tmp_bom / "config" / "configuracion.env").write_text(
        "ASSEMBLYAI_API_KEY=ccc\nOPENROUTER_API_KEY=ddd\n", encoding="utf-8-sig")
    test("un configuracion.env guardado con BOM (Bloc de notas) también se lee bien",
         _ap.cargar_configuracion(_tmp_bom / "config"), [])
    test("la primera clave del fichero no arrastra el BOM en el nombre",
         os.environ["ASSEMBLYAI_API_KEY"], "ccc")
finally:
    for _c, _v in _claves_previas_bom.items():
        if _v is None:
            os.environ.pop(_c, None)
        else:
            os.environ[_c] = _v


# ── asistente: la consola amable ──────────────────────────────────────────────
print()
print("── asistente: consola ────────────────────────────────────────────────")

test("la descarga se anuncia como el paso 1",
     _ap.traducir("descargando audio de https://www.youtube.com/watch?v=abc"),
     "Paso 1 de 3 · Descargando la grabación del pleno.")
test("el 504 se convierte en un aviso tranquilizador",
     _ap.traducir("     OpenRouter devolvió 504; esperando 2 min y reintentando..."),
     "   El servicio va lento ahora mismo. Se reintenta solo: NO cierres esta ventana.")
test("la subida cortada se traduce en un aviso de que se reintenta sola",
     _ap.traducir("  se cortó la subida (ConnectionError); reintentando en 1 min..."),
     "   El envío se ha interrumpido. Se reintenta solo: NO cierres esta ventana.")
test("un 429 también",
     _ap.traducir("     OpenRouter devolvió 429; esperando 4 min y reintentando...") is not None,
     True)
test("una línea cualquiera del pipeline no se enseña",
     _ap.traducir("       3º) APROBACIÓN DE LA ORDENANZA FISCAL"), None)
test("al rehacer no se numeran los pasos",
     _ap.traducir("generando acta (bucle generador→auditor→corrector)...", numerar=False),
     "Redactando el acta y revisándola.")

# El registro se lo queda TODO: es lo que ella envía cuando algo falla.
_tmp_log = Path(tempfile.mkdtemp()) / "prueba.log"


class _Pantalla:
    def __init__(self): self.visto = []
    def write(self, t): self.visto.append(t)
    def flush(self): pass


_pantalla = _Pantalla()
_consola = _ap.Consola(_tmp_log, _pantalla)
_consola.write("descargando audio de https://youtu.be/abc\n")
_consola.write("       3º) UN TÍTULO QUE NO DEBE VERSE\n")
_consola.cerrar()
_guardado = _tmp_log.read_text(encoding="utf-8")
test("el registro guarda la línea técnica entera",
     "3º) UN TÍTULO QUE NO DEBE VERSE" in _guardado, True)
test("la pantalla solo recibe la traducida",
     "".join(_pantalla.visto), "Paso 1 de 3 · Descargando la grabación del pleno.\n")
test("la consola dice que no es una terminal (el pipeline no debe pintar colores ANSI)",
     _consola.isatty(), False)

# Camino real: banner y Consola de verdad dentro de ejecutar_pipeline (habría cazado el fallo de isatty).
_tmp_banner_log = Path(tempfile.mkdtemp()) / "banner.log"
_consola_banner = _ap.Consola(_tmp_banner_log, _Pantalla())
_excepcion_banner = None
try:
    _ap.ejecutar_pipeline(_consola_banner,
                          lambda: _pp._banner("SUCCESS", "prueba de banner"))
except Exception as e:
    _excepcion_banner = e
finally:
    _consola_banner.cerrar()
test("el banner final no revienta con una Consola de verdad",
     _excepcion_banner, None)
test("el banner queda en el registro",
     "prueba de banner" in _tmp_banner_log.read_text(encoding="utf-8"), True)

# Sin normalizar la tilde, mostrar_instrucciones caía siempre al LÉEME de repuesto.
_tmp_leeme_dir = Path(tempfile.mkdtemp())
(_tmp_leeme_dir / "LÉEME - Cómo generar un acta.txt").write_text(
    "CONTENIDO DE PRUEBA DEL LEEME REAL", encoding="utf-8")
_inst_leeme = _ap.Instalacion(_tmp_leeme_dir, _tmp_leeme_dir, _tmp_leeme_dir, _tmp_leeme_dir)
_log_leeme = Path(tempfile.mkdtemp()) / "leeme.log"
_consola_leeme = _ap.Consola(_log_leeme, _Pantalla())
_ap.mostrar_instrucciones(_inst_leeme, _consola_leeme)
_consola_leeme.cerrar()
test("la búsqueda del LÉEME encuentra el fichero real aunque lleve la É en mayúscula",
     "CONTENIDO DE PRUEBA DEL LEEME REAL" in _log_leeme.read_text(encoding="utf-8"), True)


# ── asistente: preguntas ──────────────────────────────────────────────────────
print()
print("── asistente: preguntas ──────────────────────────────────────────────")

# Windows envuelve entre comillas la ruta al arrastrar un fichero a la consola.
test("la ruta arrastrada pierde las comillas",
     _ap.limpiar_ruta('"C:\\Users\\Ayto\\Escritorio\\convocatoria.pdf"  '),
     "C:\\Users\\Ayto\\Escritorio\\convocatoria.pdf")
test("una ruta sin comillas se queda igual",
     _ap.limpiar_ruta("C:\\Actas\\pleno.mp4"), "C:\\Actas\\pleno.mp4")
test("una respuesta vacía sigue vacía", _ap.limpiar_ruta("   "), "")

# La fecha se devuelve en palabras para que 02/09 no se confunda con 09/02.
test("la fecha se dice en palabras",
     _ap.fecha_en_palabras("2026-09-02"), "2 de septiembre de 2026")
test("y con el mes correcto en enero",
     _ap.fecha_en_palabras("2026-01-31"), "31 de enero de 2026")


# ── asistente: pantalla final y aviso de comprobaciones ───────────────────────
print()
print("── asistente: pantalla final ─────────────────────────────────────────")

# texto_comprobaciones y escribir_comprobaciones viven en plenos_guia.py (también las usa --rehacer-acta).
from plenos_guia import texto_comprobaciones, escribir_comprobaciones

# `Problema` exige también `evidencia`: los cuatro campos son obligatorios.
_pendientes = [Problema(seccion="Punto 3 — el resultado",
                        afirmacion_dudosa="queda aprobado",
                        motivo="nadie declara el resultado en la grabación",
                        evidencia="[01:12:04] Pues bueno, votos a favor.")]

# Formato antiguo: solo `Problema`, sin objeciones traducidas (compatibilidad).
_aviso = texto_comprobaciones("2026-07-07", _pendientes)
test("el aviso lleva la fecha en palabras", "7 de julio de 2026" in _aviso, True)
test("el aviso recoge la frase dudosa", "queda aprobado" in _aviso, True)
test("y el motivo", "nadie declara el resultado" in _aviso, True)
test("sin objeciones traducidas, no inventa cita ni minuto",
     "Se oye" in _aviso or "Compruébalo en el vídeo" in _aviso, False)

_tmp_pleno = Path(tempfile.mkdtemp())
_ruta_aviso = escribir_comprobaciones(_tmp_pleno, "2026-07-07", _pendientes)
test("el aviso se guarda junto al acta",
     _ruta_aviso.name, "COMPROBAR ANTES DE SELLAR.txt")
test("sin objeciones no se crea ningún aviso",
     escribir_comprobaciones(_tmp_pleno, "2026-07-07", []), None)
test("y borra el aviso de una vez anterior si ya no hay nada que comprobar",
     (_tmp_pleno / "COMPROBAR ANTES DE SELLAR.txt").exists(), False)

# Formato nuevo: objeciones ya traducidas por plenos_guia.objecion_legible, con
# cita y minuto completos.
_objeciones_completas = (
    {"donde": "Punto 3 — APROBACIÓN DE LA ORDENANZA FISCAL",
     "dice": "queda aprobado", "motivo": "nadie declara el resultado en la grabación",
     "se_oye": "Pues bueno, votos a favor.", "hms": "01:12:04",
     "enlace": "https://youtu.be/abc?t=4324s"},
)
_aviso_completo = texto_comprobaciones("2026-07-07", _pendientes, _objeciones_completas)
test("con objeción traducida, aparece la cita entre comillas",
     '"Pues bueno, votos a favor."' in _aviso_completo, True)
test("y el minuto, sin el cero de la hora",
     "minuto 1:12:04" in _aviso_completo, True)
test("y en el fichero, la dirección completa del vídeo (se puede pegar en el navegador)",
     "https://youtu.be/abc?t=4324s" in _aviso_completo, True)

# Objeción traducida sin cita localizada ni minuto: no deja hueco ni texto raro.
_objeciones_sin_cita = (
    {"donde": "Punto 4", "dice": "algo dudoso", "motivo": "motivo cualquiera",
     "se_oye": None, "hms": None, "enlace": None},
)
_aviso_sin_cita = texto_comprobaciones("2026-07-07", _pendientes, _objeciones_sin_cita)
test("sin cita localizada, no aparece la línea 'Se oye'",
     "Se oye" in _aviso_sin_cita, False)
test("sin minuto, no aparece la línea de comprobar en el vídeo",
     "Compruébalo en el vídeo" in _aviso_sin_cita, False)
test("pero sí el resto del aviso", "algo dudoso" in _aviso_sin_cita, True)

# Objeción traducida con minuto pero sin vídeo (audio local, sin enlace posible):
# el minuto se dice, pero no se imprime ninguna URL.
_objeciones_sin_video = (
    {"donde": "Punto 4", "dice": "algo dudoso", "motivo": "motivo cualquiera",
     "se_oye": None, "hms": "00:40:00", "enlace": None},
)
_aviso_sin_video = texto_comprobaciones("2026-07-07", _pendientes, _objeciones_sin_video)
test("con minuto pero sin enlace, se menciona el minuto",
     "minuto 0:40:00" in _aviso_sin_video, True)
test("pero no se imprime ninguna dirección de vídeo",
     "http" in _aviso_sin_video, False)

_ruta_aviso_completo = escribir_comprobaciones(_tmp_pleno, "2026-07-07", _pendientes,
                                               _objeciones_completas)
test("escribir_comprobaciones también pasa las objeciones traducidas al fichero",
     "https://youtu.be/abc?t=4324s" in _ruta_aviso_completo.read_text(encoding="utf-8"),
     True)


# ── asistente: la guía de verificación, anunciada en la pantalla final ────────
print()
print("── asistente: anuncio de la guía en la pantalla final ────────────────")


class _ResultadoFalso:
    """ResultadoPleno de mentira, solo con los campos que lee pantalla_final."""
    def __init__(self, ruta_acta, pendientes, ruta_guia, objeciones=()):
        self.carpeta = Path(tempfile.mkdtemp())
        self.ruta_acta = ruta_acta
        self.pendientes = pendientes
        self.ruta_guia = ruta_guia
        self.objeciones = objeciones


def _pantalla_final_texto(resultado) -> str:
    """Ejecuta pantalla_final sobre una consola de prueba y devuelve lo que vería la funcionaria."""
    _log = Path(tempfile.mkdtemp()) / "prueba.log"
    _pant = _Pantalla()
    _cons = _ap.Consola(_log, _pant)
    _ap.pantalla_final(_cons, resultado, "2026-07-07", _log)
    _cons.cerrar()
    return "".join(_pant.visto)

_falso_acta = Path(tempfile.mkdtemp()) / "2026-07-07-acta-ordinaria.docx"
_falso_acta.write_bytes(b"")
_falso_guia = Path(tempfile.mkdtemp()) / "2026-07-07-guia-de-verificacion.html"
_falso_guia.write_text("<html></html>", encoding="utf-8")

# pantalla_final abre el Explorador (os.startfile): se sustituye por un no-op durante este bloque.
_startfile_real = getattr(os, "startfile", None)
os.startfile = lambda *_a, **_kw: None
try:
    _texto_con_guia = _pantalla_final_texto(
        _ResultadoFalso(_falso_acta, [], _falso_guia))
    test("con ruta_guia, la pantalla final menciona la guía de verificación",
         "guía de verificación" in _texto_con_guia, True)
    test("y deja claro que no es el acta",
         "NO es el acta" in _texto_con_guia, True)

    _texto_sin_guia = _pantalla_final_texto(
        _ResultadoFalso(_falso_acta, [], None))
    test("sin ruta_guia (no se pudo componer), la pantalla final no la menciona",
         "guía de verificación" in _texto_sin_guia, False)

    _texto_con_objeciones_y_guia = _pantalla_final_texto(
        _ResultadoFalso(_falso_acta, _pendientes, _falso_guia, _objeciones_completas))
    test("con objeciones y guía, también se menciona la guía",
         "guía de verificación" in _texto_con_objeciones_y_guia, True)
    test("y la pantalla muestra la cita de la objeción traducida",
         '"Pues bueno, votos a favor."' in _texto_con_objeciones_y_guia, True)
    test("y el minuto, aunque en pantalla sin la URL completa",
         "minuto 1:12:04" in _texto_con_objeciones_y_guia, True)
    test("la pantalla no imprime la URL entera (solo el fichero la necesita)",
         "https://youtu.be/abc" in _texto_con_objeciones_y_guia, False)
finally:
    if _startfile_real is not None:
        os.startfile = _startfile_real
    else:
        del os.startfile


# ── asistente: aviso de duración ──────────────────────────────────────────────
test("se avisa de cuánto puede tardar, y de que depende del pleno",
     "hasta una hora" in _ap.AVISO_DURACION.lower()
     and "dure el pleno" in _ap.AVISO_DURACION.lower(), True)
test("se avisa de que un mensaje de lentitud no detiene nada",
     "NO cierres" in _ap.AVISO_DURACION, True)


# ── asistente: listado de plenos ────────────────────────────────────────────
print()
print("── asistente: listado de plenos ──────────────────────────────────────")

_tmp_actas = Path(tempfile.mkdtemp())
for _f, _t in [("2026-07-07", "PLENO EXTRAORDINARIO 7 DE JULIO"),
               ("2026-09-02", "PLENO ORDINARIO 2 DE SEPTIEMBRE")]:
    (_tmp_actas / _f).mkdir()
    (_tmp_actas / _f / "entrada.json").write_text(
        json.dumps({"fecha": _f, "titulo": _t}), encoding="utf-8")
(_tmp_actas / "no-es-un-pleno").mkdir()
(_tmp_actas / "2026-05-19").mkdir()  # sin entrada.json: no debe reventar

test("los plenos se listan del más reciente al más antiguo",
     [f for f, _ in _ap.plenos_guardados(_tmp_actas)],
     ["2026-09-02", "2026-07-07", "2026-05-19"])
test("cada pleno lleva su título",
     _ap.plenos_guardados(_tmp_actas)[0][1], "PLENO ORDINARIO 2 DE SEPTIEMBRE")
test("un pleno sin entrada.json se lista igual, sin título",
     _ap.plenos_guardados(_tmp_actas)[2][1], "")
test("las carpetas que no son plenos se ignoran",
     any(f == "no-es-un-pleno" for f, _ in _ap.plenos_guardados(_tmp_actas)), False)
test("una carpeta de actas que no existe devuelve lista vacía",
     _ap.plenos_guardados(_tmp_actas / "no-existe"), [])


# ── guía de verificación (plenos_guia) ────────────────────────────────────────
print()
print("── guía de verificación (plenos_guia) ────────────────────────────────")

from plenos_guia import segundos, enlace_video, localizar, objecion_legible, render_guia

test("segundos: hh:mm:ss", segundos("01:12:04"), 4324)
test("segundos: minutos y segundos sueltos", segundos("00:03:12"), 192)
test("segundos: basura no revienta, da 0", segundos("no es una hora"), 0)
test("segundos: cadena vacía da 0", segundos(""), 0)
test("segundos: None da 0", segundos(None), 0)

test("enlace_video: sin url no hay enlace", enlace_video(None, "00:01:00"), None)
test("enlace_video: sin tiempo no hay enlace", enlace_video("https://youtu.be/abc", None), None)
test("enlace_video: url sin query previa, segundo bien calculado",
     enlace_video("https://youtu.be/abc", "00:01:05"), "https://youtu.be/abc?t=65s")
test("enlace_video: url con query previa se concatena con &",
     enlace_video("https://www.youtube.com/watch?v=abc", "00:00:10"),
     "https://www.youtube.com/watch?v=abc&t=10s")

# La transcripción real son líneas "[HH:MM:SS] Interviniente X: texto".
_TRANS_GUIA = (
    "[00:00:01] Interviniente A: Buenas tardes, comienza la sesión.\n"
    "[00:58:04] Interviniente B: Pues bueno, votos a favor.\n"
    "[01:00:14] Interviniente A: Aprobado por unanimidad, “la playeta” queda excluida.\n"
    "[01:05:30] Interviniente C: La Presidenta informó del expediente número 12.\n"
)

test("localizar: cita exacta encontrada",
     localizar("Pues bueno, votos a favor.", _TRANS_GUIA), "00:58:04")
test("localizar: distinta puntuación y sin acentos, encontrada",
     localizar("la presidenta informo del expediente numero 12", _TRANS_GUIA), "01:05:30")
test("localizar: cita inventada no se inventa un tiempo",
     localizar("esto no lo dice nadie en la grabación", _TRANS_GUIA), None)
test("localizar: cita vacía", localizar("", _TRANS_GUIA), None)
test("localizar: recorta la marca de tiempo que el auditor copia junto a la cita",
     localizar("[00:58:04] Pues bueno, votos a favor.", _TRANS_GUIA), "00:58:04")

# Informe de prueba con timestamps por punto y por votación, para fijar la cascada.
_informe_guia = InformePleno.model_validate(dict(
    INFORME_MINIMO,
    orden_del_dia=[
        {"numero": 3, "parte": "resolutiva", "timestamp": "00:20:00",
         "titulo": "APROBACIÓN DE LA ORDENANZA FISCAL", "texto": "x", "acuerdo": None,
         "votacion": {"resultado": "aprobado", "modalidad": "recuento",
                      "a_favor": 3, "en_contra": 2, "abstenciones": None,
                      "voto_de_calidad": False, "timestamp": "00:25:00"}},
        {"numero": 4, "parte": "control", "timestamp": "00:40:00",
         "titulo": "DECRETOS DE ALCALDÍA", "texto": "y", "acuerdo": None,
         "votacion": None},
    ]))

# Caso 1: la cita se localiza en la transcripción → manda sobre lo demás.
_prob_evidencia = Problema(seccion="Punto 3", afirmacion_dudosa="aprobado 5-2",
                           motivo="no se dice el recuento",
                           evidencia="Pues bueno, votos a favor.")
_o1 = objecion_legible(_prob_evidencia, _informe_guia, _TRANS_GUIA, "https://youtu.be/abc")
test("objeción: la cita localizada manda sobre el resto de la cascada", _o1["hms"], "00:58:04")
test("objeción: 'donde' se vuelve legible casando por número",
     _o1["donde"], "Punto 3 — APROBACIÓN DE LA ORDENANZA FISCAL")
test("objeción: el enlace usa el tiempo encontrado",
     _o1["enlace"], "https://youtu.be/abc?t=3484s")

# Caso 2: la cita no se localiza → cae al timestamp de la votación del punto.
_prob_sin_cita = Problema(seccion="APROBACIÓN DE LA ORDENANZA FISCAL",
                          afirmacion_dudosa="aprobado 5-2", motivo="no se dice el recuento",
                          evidencia="esto no está en la transcripción")
_o2 = objecion_legible(_prob_sin_cita, _informe_guia, _TRANS_GUIA, None)
test("objeción: sin cita localizable, usa el timestamp de la votación", _o2["hms"], "00:25:00")
test("objeción: 'donde' se vuelve legible casando por título",
     _o2["donde"], "Punto 3 — APROBACIÓN DE LA ORDENANZA FISCAL")
test("objeción: sin vídeo no hay enlace aunque haya tiempo", _o2["enlace"], None)

# Caso 3: sin votación en el punto → cae al timestamp del propio punto.
_prob_control = Problema(seccion="Punto 4", afirmacion_dudosa="algo dudoso",
                         motivo="motivo cualquiera", evidencia="esto tampoco está")
_o3 = objecion_legible(_prob_control, _informe_guia, _TRANS_GUIA, "https://youtu.be/abc")
test("objeción: sin votación en el punto, usa el timestamp del propio punto",
     _o3["hms"], "00:40:00")

# Caso 4: ningún dato de tiempo disponible → None, nunca se inventa un minuto.
_informe_sin_tiempos = InformePleno.model_validate(dict(
    INFORME_MINIMO,
    orden_del_dia=[{"numero": 9, "parte": "control", "titulo": "OTRO PUNTO",
                    "texto": "z", "acuerdo": None, "votacion": None}]))
_o4 = objecion_legible(Problema(seccion="Punto 9", afirmacion_dudosa="x", motivo="y",
                                evidencia="tampoco está"),
                       _informe_sin_tiempos, _TRANS_GUIA, "https://youtu.be/abc")
test("objeción: sin ningún dato de tiempo, 'hms' queda en None", _o4["hms"], None)
test("objeción: y por tanto tampoco hay enlace", _o4["enlace"], None)

test("objeción: una sección que no casa con ningún punto se deja tal cual",
     objecion_legible(Problema(seccion="algo raro sin numero ni titulo",
                               afirmacion_dudosa="x", motivo="y", evidencia="z"),
                      _informe_guia, _TRANS_GUIA, None)["donde"],
     "algo raro sin numero ni titulo")

# El auditor a veces cita la ruta interna del JSON ('orden_del_dia[2].texto').
# Fixture: 5 puntos (índice 2 -> punto 3, índice 4 -> punto 5) y un turno de ruegos de 3 intervenciones.
_informe_rutas = InformePleno.model_validate(dict(
    INFORME_MINIMO,
    orden_del_dia=[
        {"numero": 1, "parte": "resolutiva", "titulo": "APROBACIÓN DE ACTAS ANTERIORES",
         "texto": "x", "acuerdo": None, "votacion": None},
        {"numero": 2, "parte": "resolutiva", "titulo": "DÍAS FESTIVOS PARA 2027",
         "texto": "x", "acuerdo": None, "votacion": None},
        {"numero": 3, "parte": "resolutiva",
         "titulo": "SOLICITUD ASISTENCIA JURÍDICA A LA EXCMA. DIPUTACIÓN PROVINCIAL",
         "texto": "x", "acuerdo": "solicitar la asistencia jurídica",
         "votacion": {"resultado": "aprobado", "modalidad": "unanimidad",
                      "a_favor": None, "en_contra": None, "abstenciones": None,
                      "voto_de_calidad": False, "timestamp": "00:23:00"}},
        {"numero": 4, "parte": "resolutiva", "titulo": "SOLICITUD ASISTENCIA JURÍDICA CONTENCIOSO",
         "texto": "x", "acuerdo": None, "votacion": None},
        {"numero": 5, "parte": "resolutiva",
         "titulo": "APROBACIÓN SI PROCEDE DE LA SOLICITUD DE SUBVENCIÓN PARA ACONDICIONAMIENTO",
         "texto": "x", "acuerdo": None, "votacion": None},
        {"numero": 10, "parte": "control", "titulo": "RUEGOS Y PREGUNTAS",
         "texto": "x", "acuerdo": None, "votacion": None},
    ],
    ruegos_y_preguntas=[
        {"formulados_por": "D. Joaquín Martínez Luján", "puntos": ["a"]},
        {"formulados_por": "D. Fernando Pons Mayor", "puntos": ["b"]},
        {"formulados_por": "Dª Mª Rosario Cerdán Pérez", "puntos": ["c"]},
    ],
))

def _donde(seccion, evidencia="no está en la transcripción"):
    return objecion_legible(
        Problema(seccion=seccion, afirmacion_dudosa="x", motivo="y", evidencia=evidencia),
        _informe_rutas, _TRANS_GUIA, None)["donde"]

test("ruta orden_del_dia[2].texto -> punto 3 real, en el relato del debate",
     _donde("orden_del_dia[2].texto"),
     "Punto 3º) SOLICITUD ASISTENCIA JURÍDICA A LA EXCMA. DIPUTACIÓN PROVINCIAL — en el relato del debate")
test("ruta orden_del_dia[4].texto -> punto 5 real, en el relato del debate",
     _donde("orden_del_dia[4].texto"),
     "Punto 5º) APROBACIÓN SI PROCEDE DE LA SOLICITUD DE SUBVENCIÓN PARA ACONDICIONAMIENTO — en el relato del debate")
test("ruta ruegos_y_preguntas[2] -> intervención 3, con el número de punto antepuesto",
     _donde("ruegos_y_preguntas[2]"),
     "Punto 10º) RUEGOS Y PREGUNTAS — intervención 3")
test("ruta orden_del_dia[2].acuerdo -> sufijo 'en el acuerdo'",
     _donde("orden_del_dia[2].acuerdo"),
     "Punto 3º) SOLICITUD ASISTENCIA JURÍDICA A LA EXCMA. DIPUTACIÓN PROVINCIAL — en el acuerdo")
test("ruta orden_del_dia[2].votacion.resultado -> sufijo 'en la votación'",
     _donde("orden_del_dia[2].votacion.resultado"),
     "Punto 3º) SOLICITUD ASISTENCIA JURÍDICA A LA EXCMA. DIPUTACIÓN PROVINCIAL — en la votación")
test("ruta orden_del_dia[2].votacion.resultado usa el timestamp de esa votación",
     objecion_legible(Problema(seccion="orden_del_dia[2].votacion.resultado",
                               afirmacion_dudosa="x", motivo="y",
                               evidencia="no está en la transcripción"),
                      _informe_rutas, _TRANS_GUIA, None)["hms"],
     "00:23:00")
test("ruta con índice fuera de rango se deja tal cual (el modelo puede citar mal el suyo)",
     _donde("orden_del_dia[99].texto"), "orden_del_dia[99].texto")
test("ruta con raíz desconocida se deja tal cual",
     _donde("algo_desconocido[0].texto"), "algo_desconocido[0].texto")
test("campo simple del informe: asistentes -> 'Lista de asistentes'",
     _donde("asistentes"), "Lista de asistentes")
test("campo simple del informe: presidente -> 'Quién preside'",
     _donde("presidente"), "Quién preside")
test("campo simple del informe: hora_inicio -> 'Hora de inicio'",
     _donde("hora_inicio"), "Hora de inicio")
test("una sección ya en prosa se sigue respetando (no es una ruta)",
     _donde("Punto 3"), "Punto 3 — SOLICITUD ASISTENCIA JURÍDICA A LA EXCMA. DIPUTACIÓN PROVINCIAL")

# Sin el punto RUEGOS Y PREGUNTAS numerado en el orden del día, la ruta no antepone
# ningún número: el turno de ruegos no tiene número de punto que anteponer.
_informe_sin_ryp_numerado = InformePleno.model_validate(dict(
    INFORME_MINIMO,
    orden_del_dia=[{"numero": 1, "parte": "resolutiva", "titulo": "UN PUNTO CUALQUIERA",
                    "texto": "x", "acuerdo": None, "votacion": None}],
    ruegos_y_preguntas=[{"formulados_por": "D. Joaquín Martínez Luján", "puntos": ["a"]}],
))
test("ruegos_y_preguntas[0] sin punto numerado en el orden del día",
     objecion_legible(Problema(seccion="ruegos_y_preguntas[0]", afirmacion_dudosa="x",
                               motivo="y", evidencia="z"),
                      _informe_sin_ryp_numerado, _TRANS_GUIA, None)["donde"],
     "RUEGOS Y PREGUNTAS — intervención 1")

# se_oye: limpia las marcas de la transcripción, conservando el "[...]" de salto.
_o_marca = objecion_legible(
    Problema(seccion="orden_del_dia[2].texto", afirmacion_dudosa="x", motivo="y",
             evidencia="[00:22:20] Interviniente B: Siempre. No sé si queréis, le doy "
                       "palabra a Joaquín [...] [00:22:39] Interviniente E: Sí, yo, en "
                       "primer lugar..."),
    _informe_rutas, _TRANS_GUIA, None)
test("se_oye: quita las marcas [HH:MM:SS] e 'Interviniente X:', conserva el '[...]'",
     _o_marca["se_oye"],
     "Siempre. No sé si queréis, le doy palabra a Joaquín [...] Sí, yo, en primer lugar...")
test("se_oye: None se queda en None",
     objecion_legible(Problema(seccion="asistentes", afirmacion_dudosa="x", motivo="y",
                               evidencia=""),
                      _informe_rutas, _TRANS_GUIA, None)["se_oye"], None)

# ── buscar_en_acta: la frase literal para el buscador de Word ────────────────
print()
print("── buscar_en_acta: la frase literal para el buscador de Word ─────────")

from plenos_guia import buscar_en_acta

# El auditor cita entre comillas, en `afirmacion_dudosa`, un fragmento literal del campo del informe.
_informe_buscar = InformePleno.model_validate(dict(
    INFORME_MINIMO,
    orden_del_dia=[
        {"numero": 3, "parte": "resolutiva", "titulo": "SOLICITUD ASISTENCIA JURÍDICA",
         "texto": ("La Sra. Teniente de Alcalde da cuenta de la demanda interpuesta.\n\n"
                   "A petición del Pleno, un interviniente no identificado en la "
                   "grabación explica que la queja se fundamenta en la demora en la "
                   "toma de posesión de un concejal."),
         "acuerdo": None, "votacion": None},
        {"numero": 5, "parte": "resolutiva", "titulo": "SOLICITUD DE SUBVENCIÓN",
         "texto": ("La Presidencia informa sobre una convocatoria de ayudas para la "
                   "mejora de caminos rurales.\n\n"
                   "Se abre el debate sobre qué camino incluir en la solicitud. El "
                   "concejal D. Mario Cerdán Ochoa interviene para proponer la "
                   "actuación en el camino de la Rambla, señalando su mal estado."),
         "acuerdo": None, "votacion": None},
    ],
    ruegos_y_preguntas=[
        {"formulados_por": "La Sra. Teniente de Alcalde, Dª Lorena Luján Chujfi",
         "puntos": [
             "Como presidenta de la Asociación de Jubilados, ruega que se limpien "
             "los baños del hogar del jubilado.",
             "Reclama que los ingresos del bar reviertan en la asociación y no en "
             "el Ayuntamiento.",
         ]},
    ],
))

# 1) Fragmento entrecomillado: se queda con el que aparece literalmente en el informe.
test("buscar_en_acta: el fragmento entrecomillado que sí está en el informe",
     buscar_en_acta(
         Problema(seccion="orden_del_dia[0].texto",
                  afirmacion_dudosa='La explicación la da "un interviniente no '
                                    'identificado en la grabación".',
                  motivo="y", evidencia="z"),
         _informe_buscar),
     "un interviniente no identificado en la grabación")

# 2) Sin comillas: la frase con mayor PROPORCIÓN de palabras compartidas, no por recuento bruto.
test("buscar_en_acta: sin comillas, la frase que mejor casa (por proporción, no por "
     "recuento bruto)",
     buscar_en_acta(
         Problema(seccion="orden_del_dia[1].texto",
                  afirmacion_dudosa="La propuesta sobre el camino a incluir en la "
                                    "solicitud la realiza el concejal D. Mario Cerdán "
                                    "Ochoa.",
                  motivo="y", evidencia="z"),
         _informe_buscar),
     "Se abre el debate sobre qué camino incluir en la solicitud.")

# 3) ruegos_y_preguntas[N] es un objeto: si la duda es sobre QUIÉN habla, gana `formulados_por`.
test("buscar_en_acta: en un bloque de ruegos, 'formulados_por' cuando la duda es sobre "
     "quién habla",
     buscar_en_acta(
         Problema(seccion="ruegos_y_preguntas[0]",
                  afirmacion_dudosa="Los ruegos sobre los baños del hogar del jubilado "
                                    "y los ingresos del bar son formulados por la Sra. "
                                    "Teniente de Alcalde, Dª Lorena Luján Chujfi.",
                  motivo="y", evidencia="z"),
         _informe_buscar),
     "La Sra. Teniente de Alcalde, Dª Lorena Luján Chujfi")

# 4) Nada con confianza suficiente (ni comillas válidas ni una frase que comparta lo
# bastante): None, nunca se ofrece una frase al azar.
test("buscar_en_acta: sin nada que ofrecer con confianza, None",
     buscar_en_acta(
         Problema(seccion="orden_del_dia[0].texto",
                  afirmacion_dudosa="Se debatió extensamente sobre presupuestos "
                                    "municipales para el año próximo.",
                  motivo="y", evidencia="z"),
         _informe_buscar),
     None)

test("buscar_en_acta: una sección que no señala ningún campo reconocible, None",
     buscar_en_acta(
         Problema(seccion="algo_desconocido[0].texto", afirmacion_dudosa='"cualquier cosa"',
                  motivo="y", evidencia="z"),
         _informe_buscar),
     None)

# objecion_legible incorpora 'buscar' en el dict que ya usan pantalla/txt/guía.
test("objecion_legible: incluye la clave 'buscar'",
     "buscar" in objecion_legible(
         Problema(seccion="orden_del_dia[0].texto",
                  afirmacion_dudosa='La explicación la da "un interviniente no '
                                    'identificado en la grabación".',
                  motivo="y", evidencia="no está en la transcripción"),
         _informe_buscar, _TRANS_GUIA, None),
     True)


from plenos_guia import _limpiar_evidencia
test("_limpiar_evidencia: cadena sin marcas se deja igual",
     _limpiar_evidencia("Sí, yo, en primer lugar."), "Sí, yo, en primer lugar.")
test("_limpiar_evidencia: None se deja igual", _limpiar_evidencia(None), None)
test("_limpiar_evidencia: cadena vacía se deja igual", _limpiar_evidencia(""), "")

# render_guia: escribe el fichero, con objeciones, vídeo con query vacía (?t=...).
_tmp_guia = os.path.join(tempfile.gettempdir(), "test_guia.html")
_entrada_guia = {"video_id": "abc", "fecha": "2026-05-19",
                 "titulo": "Pleno <ordinario> de mayo", "video_url": "https://youtu.be/abc"}
render_guia(_informe_guia, _entrada_guia, _TRANS_GUIA, [_prob_evidencia], _tmp_guia)
_html_guia = Path(_tmp_guia).read_text(encoding="utf-8")
os.remove(_tmp_guia)

test("render_guia: escribe el fichero", len(_html_guia) > 0, True)
test("render_guia: lleva el título del pleno, con el < escapado",
     "Pleno &lt;ordinario&gt; de mayo" in _html_guia, True)
test("render_guia: no cuela HTML sin escapar de un título con '<'",
     "<ordinario>" in _html_guia, False)
test("render_guia: deja clarísimo que esto NO es el acta",
     "NO es el acta" in _html_guia, True)
test("render_guia: con objeciones, la sección destacada aparece primero",
     "Puntos que conviene comprobar" in _html_guia, True)
test("render_guia: un enlace con ?t= al minuto, cuando hay vídeo",
     "?t=" in _html_guia, True)
test("render_guia: los enlaces abren en pestaña nueva",
     'target="_blank"' in _html_guia, True)

# Sin vídeo (audio local) y sin objeciones: ni enlaces ni la sección destacada.
_tmp_guia2 = os.path.join(tempfile.gettempdir(), "test_guia_sin_video.html")
render_guia(_informe_guia, {"video_id": None, "fecha": "2026-05-19",
                            "titulo": "Pleno de audio local", "video_url": None},
           _TRANS_GUIA, [], _tmp_guia2)
_html_guia2 = Path(_tmp_guia2).read_text(encoding="utf-8")
os.remove(_tmp_guia2)

test("render_guia: sin vídeo no hay enlaces con ?t=", "?t=" in _html_guia2, False)
test("render_guia: sin vídeo, el tiempo se muestra en texto", "Minuto" in _html_guia2, True)
test("render_guia: sin objeciones no aparece la sección destacada",
     "Puntos que conviene comprobar" in _html_guia2, False)

# El mapa de voces va ANTES de las comprobaciones: una voz mal identificada invalida sus intervenciones.
_tmp_guia3 = os.path.join(tempfile.gettempdir(), "test_guia_mapa.html")
render_guia(_informe_con_mapa, _entrada_guia, _TRANS_GUIA, [_prob_evidencia], _tmp_guia3)
_html_guia3 = Path(_tmp_guia3).read_text(encoding="utf-8")
os.remove(_tmp_guia3)

test("render_guia: pinta el mapa de voces cuando el informe lo trae",
     "Quién es quién en la grabación" in _html_guia3, True)
test("render_guia: muestra la persona identificada",
     "Lorena Luján Chujfi" in _html_guia3, True)
test("render_guia: muestra la evidencia que la identifica",
     "Damos comienzo al Pleno ordinario" in _html_guia3, True)
test("render_guia: el mapa lleva enlace al minuto de esa cita",
     f"?t={segundos('00:00:32')}s" in _html_guia3, True)
test("render_guia: el mapa aparece antes que las comprobaciones",
     _html_guia3.index("Quién es quién en la grabación")
     < _html_guia3.index("Puntos que conviene comprobar"), True)

# La voz A (no identificada) debe llevar el aviso de comprobarla en el vídeo.
test("render_guia: una voz no identificada lleva su propio aviso",
     "no ha podido separar bien esta voz" in _html_guia3, True)

# La etiqueta de la evidencia varía: "Se identifica porque:" no vale para voces sin identificar o mezcladas.
test("render_guia: voz identificada con normalidad lleva 'Se identifica porque:'",
     "Se identifica porque:" in _html_guia3, True)
test("render_guia: voz sin identificar lleva su propia etiqueta, no 'Se identifica porque:'",
     "No se ha podido saber quién es:" in _html_guia3, True)
test("render_guia: voz sin identificar lleva la clase de aviso leve, no la de alerta fuerte",
     'class="voz voz-aviso-leve"' in _html_guia3, True)

# Un pleno anterior sin mapa no muestra la sección ni inventa uno.
test("render_guia: sin mapa, la sección no aparece",
     "Quién es quién en la grabación" in _html_guia, False)

# ── mapa de voces: etiqueta con voces mezcladas (fallo real 2026-09-03) ───────
# AssemblyAI fusionó en B a quien presidía y a una vecina; la guía debe dejar claro que es una etiqueta mezclada.
_informe_con_mezcla = InformePleno.model_validate(dict(
    INFORME_MINIMO,
    identificacion_locutores=[
        {"etiqueta": "B", "persona": "etiqueta con voces mezcladas",
         "evidencia": ("[00:00:32] Interviniente B: Damos comienzo al Pleno...; "
                       "[03:00:59] Interviniente B: llevo como presidenta de la "
                       "asociación de jubilados"),
         "timestamp": "00:00:32"},
    ]))
_tmp_guia4 = os.path.join(tempfile.gettempdir(), "test_guia_mezcla.html")
render_guia(_informe_con_mezcla, _entrada_guia, _TRANS_GUIA, [], _tmp_guia4)
_html_guia4 = Path(_tmp_guia4).read_text(encoding="utf-8")
os.remove(_tmp_guia4)

test("render_guia: pinta la etiqueta con voces mezcladas", "voces mezcladas" in _html_guia4, True)
test("render_guia: avisa de que el transcriptor ha mezclado a dos personas",
     "DOS PERSONAS DISTINTAS" in _html_guia4, True)
test("render_guia: la voz mezclada lleva la clase de alerta",
     'class="voz voz-alerta"' in _html_guia4, True)
# "Se identifica porque:" mentiría delante de una etiqueta contaminada.
test("render_guia: la voz mezclada lleva su propia etiqueta, no 'Se identifica porque:'",
     ("Aquí el transcriptor ha mezclado a dos personas:" in _html_guia4,
      "Se identifica porque:" in _html_guia4),
     (True, False))

# Una voz identificada con normalidad no lleva aviso ni clase de alerta.
_informe_voz_limpia = InformePleno.model_validate(dict(
    INFORME_MINIMO,
    identificacion_locutores=[
        {"etiqueta": "B", "persona": "Lorena Luján Chujfi",
         "evidencia": "[00:00:32] Interviniente B: Damos comienzo al Pleno ordinario...",
         "timestamp": "00:00:32"},
    ]))
_tmp_guia5 = os.path.join(tempfile.gettempdir(), "test_guia_voz_limpia.html")
render_guia(_informe_voz_limpia, _entrada_guia, _TRANS_GUIA, [], _tmp_guia5)
_html_guia5 = Path(_tmp_guia5).read_text(encoding="utf-8")
os.remove(_tmp_guia5)

test("render_guia: una voz identificada con normalidad no lleva la clase de alerta",
     'class="voz voz-alerta"' in _html_guia5, False)
test("render_guia: ni la clase de aviso leve tampoco, es una voz limpia",
     'class="voz voz-aviso-leve"' in _html_guia5, False)
test("render_guia: una voz identificada con normalidad sí lleva 'Se identifica porque:'",
     "Se identifica porque:" in _html_guia5, True)
test("render_guia: ni el aviso de la voz mezclada ni el de sin identificar",
     ("DOS PERSONAS DISTINTAS" in _html_guia5, "no ha podido separar bien esta voz" in _html_guia5),
     (False, False))


# ── mapa de voces: turnos alternos (hueco 1, detectado sin LLM contra la transcripción) ─
print()
print("── mapa de voces: conflicto de turnos alternos en la guía ────────────")

from plenos_guia import _secuencia_etiquetas, _se_alternan, conflictos_turnos_alternos

# _TRANS_GUIA es A, B, A, C: A y B se responden (trío A,B,A); C no se cruza con nadie.
test("_secuencia_etiquetas: una entrada por turno, en orden",
     _secuencia_etiquetas(_TRANS_GUIA), ["A", "B", "A", "C"])
test("_se_alternan: A y B se responden (trío A,B,A)",
     _se_alternan("A", "B", _secuencia_etiquetas(_TRANS_GUIA)), True)
test("_se_alternan: A y C nunca se cruzan directamente",
     _se_alternan("A", "C", _secuencia_etiquetas(_TRANS_GUIA)), False)

# Las repeticiones consecutivas de una misma etiqueta cuentan como un solo turno: no
# deben poder simular un trío A,B,A por sí solas.
test("_secuencia_etiquetas: colapsa las repeticiones consecutivas",
     _secuencia_etiquetas(
         "[00:00:01] Interviniente A: primera frase.\n"
         "[00:00:04] Interviniente A: sigue hablando.\n"
         "[00:00:08] Interviniente B: responde.\n"),
     ["A", "B"])

# Hueco 1: dos etiquetas identificadas como la MISMA persona pese a responderse; se detecta en Python contra la transcripción.
_informe_conflicto = InformePleno.model_validate(dict(
    INFORME_MINIMO,
    identificacion_locutores=[
        {"etiqueta": "A", "persona": "Fernando Pons Mayor",
         "evidencia": "[00:00:01] Interviniente A: Buenas tardes, comienza la sesión.",
         "timestamp": "00:00:01"},
        {"etiqueta": "B", "persona": "Fernando Pons Mayor",
         "evidencia": "[00:58:04] Interviniente B: Pues bueno, votos a favor.",
         "timestamp": "00:58:04"},
    ]))
test("conflictos_turnos_alternos: detecta las dos etiquetas que se alternan",
     conflictos_turnos_alternos(_informe_conflicto, _TRANS_GUIA), {"A", "B"})

# Las voces de escape no afirman ser una persona concreta: no hay conflicto de identidad que señalar.
_informe_sin_conflicto = InformePleno.model_validate(dict(
    INFORME_MINIMO,
    identificacion_locutores=[
        {"etiqueta": "A", "persona": "no identificado en la grabación",
         "evidencia": "no hay cita que lo demuestre", "timestamp": None},
        {"etiqueta": "B", "persona": "no identificado en la grabación",
         "evidencia": "no hay cita que lo demuestre", "timestamp": None},
    ]))
test("conflictos_turnos_alternos: los valores de escape no generan conflicto",
     conflictos_turnos_alternos(_informe_sin_conflicto, _TRANS_GUIA), set())

# Sin este caso, el mapa normal se pinta como siempre.
test("conflictos_turnos_alternos: sin personas repetidas, no hay nada que marcar",
     conflictos_turnos_alternos(_informe_con_mapa, _TRANS_GUIA), set())

_tmp_guia6 = os.path.join(tempfile.gettempdir(), "test_guia_conflicto.html")
render_guia(_informe_conflicto, _entrada_guia, _TRANS_GUIA, [], _tmp_guia6)
_html_guia6 = Path(_tmp_guia6).read_text(encoding="utf-8")
os.remove(_tmp_guia6)

# Mismo peso visual que la voz mezclada; las dos etiquetas en conflicto lo llevan.
test("render_guia: el conflicto de turnos alternos lleva la clase de alerta fuerte",
     _html_guia6.count('class="voz voz-alerta"'), 2)
test("render_guia: trae su propia frase, distinta de la de voces mezcladas",
     "se responden entre sí en la grabación" in _html_guia6, True)
test("render_guia: explica que dos voces distintas se han identificado como la misma persona",
     "la misma persona que" in _html_guia6, True)
test("render_guia: sigue reutilizando la cabecera normal de evidencia (_etiqueta_evidencia)",
     _html_guia6.count("Se identifica porque:"), 2)
test("render_guia: no confunde el conflicto con una etiqueta de voces mezcladas",
     "DOS PERSONAS DISTINTAS" in _html_guia6, False)

# Un informe sin ningún caso de este tipo se sigue pintando exactamente como antes.
_tmp_guia7 = os.path.join(tempfile.gettempdir(), "test_guia_sin_conflicto.html")
render_guia(_informe_con_mapa, _entrada_guia, _TRANS_GUIA, [_prob_evidencia], _tmp_guia7)
_html_guia7 = Path(_tmp_guia7).read_text(encoding="utf-8")
os.remove(_tmp_guia7)
test("render_guia: sin conflicto de turnos alternos, ninguna voz lleva esa frase",
     "se responden entre sí en la grabación" in _html_guia7, False)
test("render_guia: sin conflicto, el conteo de voz-alerta es el de siempre (ninguna aquí)",
     _html_guia7.count('class="voz voz-alerta"'), 0)


# ── objeciones persistidas junto al informe ───────────────────────────────────
print()
print("── objeciones persistidas (guardar_objeciones / cargar_objeciones) ──────")

from procesar_pleno import guardar_objeciones, cargar_objeciones

_tmp_obj = Path(tempfile.mkdtemp())
_fecha_obj = "2026-09-06"
_problemas_obj = [
    Problema(seccion="Punto 1", afirmacion_dudosa="aprobado por unanimidad",
            motivo="no se dice el recuento", evidencia="[00:10:00] eso creo"),
    Problema(seccion="Punto 2", afirmacion_dudosa="rechazado",
            motivo="nadie declara el resultado", evidencia="[00:20:00] pues no sé"),
]

guardar_objeciones(_tmp_obj, _fecha_obj, _problemas_obj)
_ruta_obj = _tmp_obj / f"{_fecha_obj}-objeciones.json"
test("guardar_objeciones: crea el fichero", _ruta_obj.exists(), True)

_releidas = cargar_objeciones(_tmp_obj, _fecha_obj)
test("cargar_objeciones: relee el mismo número de objeciones", len(_releidas), 2)
test("cargar_objeciones: se releen como Problema",
     all(isinstance(p, Problema) for p in _releidas), True)
test("cargar_objeciones: conserva el contenido",
     [p.model_dump() for p in _releidas], [p.model_dump() for p in _problemas_obj])

# Una lista vacía borra el fichero para no arrastrar objeciones de una ejecución anterior.
guardar_objeciones(_tmp_obj, _fecha_obj, [])
test("guardar_objeciones: lista vacía borra el fichero (no arrastra lo anterior)",
     _ruta_obj.exists(), False)
test("cargar_objeciones: fichero ausente devuelve lista vacía (plenos anteriores a este cambio)",
     cargar_objeciones(_tmp_obj, _fecha_obj), [])

# Reprocesar con menos objeciones debe dejar el fichero al día, no acumularlas.
guardar_objeciones(_tmp_obj, _fecha_obj, _problemas_obj)
guardar_objeciones(_tmp_obj, _fecha_obj, [_problemas_obj[0]])
test("guardar_objeciones: al reprocesar, el fichero refleja solo la última corrida",
     len(cargar_objeciones(_tmp_obj, _fecha_obj)), 1)


# ── --rehacer-acta reconstruye la guía con sus objeciones ─────────────────────
print()
print("── --rehacer-acta reconstruye la guía con sus objeciones ─────────────")

import contextlib as _ctx_reh
import io as _io_reh

_tmp_reh = Path(tempfile.mkdtemp())
_fecha_reh = "2026-09-06"
_carpeta_reh = _tmp_reh / "actas" / _fecha_reh
_carpeta_reh.mkdir(parents=True)

_informe_reh = InformePleno.model_validate(INFORME_MINIMO)
(_carpeta_reh / f"{_fecha_reh}-informe.json").write_text(
    _informe_reh.model_dump_json(indent=2), encoding="utf-8")
(_carpeta_reh / f"{_fecha_reh}-transcripcion.md").write_text(
    "# Transcripción — prueba\n\n[00:00:01] Interviniente A: Buenas tardes.\n",
    encoding="utf-8")
(_carpeta_reh / "entrada.json").write_text(
    json.dumps({"video_id": None, "fecha": _fecha_reh, "titulo": "Pleno de prueba",
               "video_url": None}), encoding="utf-8")
# Ruta interna a propósito: es como el auditor cita una sección y la que traduce _ruta_legible.
guardar_objeciones(_carpeta_reh, _fecha_reh,
                   [Problema(seccion="orden_del_dia[0].texto", afirmacion_dudosa="x",
                            motivo="y", evidencia="[00:00:01] Buenas tardes.")])

# El .txt de una corrida anterior, desfasado: el aviso no debe seguir citando rutas internas.
_ruta_txt_reh = _carpeta_reh / "COMPROBAR ANTES DE SELLAR.txt"
_ruta_txt_reh.write_text(
    "AVISO DE UNA CORRIDA ANTERIOR YA DESFASADO\norden_del_dia[2].texto\n",
    encoding="utf-8")

_bd_reh = _pp.BORRADOR_DIR
_pp.BORRADOR_DIR = _tmp_reh / "actas"
try:
    with _ctx_reh.redirect_stdout(_io_reh.StringIO()):
        _codigo = _pp._rehacer_acta(_fecha_reh)
    _html_reh = (_carpeta_reh / f"{_fecha_reh}-guia-de-verificacion.html").read_text(encoding="utf-8")
    test("--rehacer-acta: termina bien", _codigo, 0)
    test("--rehacer-acta: la guía recupera la sección de comprobaciones del fichero persistido",
         "Puntos que conviene comprobar" in _html_reh, True)

    # Acta, guía y .txt se regeneran juntos en _componer_guia y deben contar lo mismo.
    _txt_reh = _ruta_txt_reh.read_text(encoding="utf-8")
    test("--rehacer-acta: el .txt de comprobaciones también se regenera",
         "AVISO DE UNA CORRIDA ANTERIOR" in _txt_reh, False)
    test("--rehacer-acta: el .txt no expone rutas internas del JSON",
         "orden_del_dia[" in _txt_reh, False)
    test("--rehacer-acta: el .txt nombra el punto igual que la guía y el acta",
         "Punto 1º)" in _txt_reh, True)

    # Sin fichero de objeciones (plenos antiguos) la guía se genera igual, sin esa sección.
    (_carpeta_reh / f"{_fecha_reh}-objeciones.json").unlink()
    with _ctx_reh.redirect_stdout(_io_reh.StringIO()):
        _codigo2 = _pp._rehacer_acta(_fecha_reh)
    _html_reh2 = (_carpeta_reh / f"{_fecha_reh}-guia-de-verificacion.html").read_text(encoding="utf-8")
    test("--rehacer-acta: sin fichero de objeciones, sigue funcionando sin romperse", _codigo2, 0)
    test("--rehacer-acta: sin fichero de objeciones, no hay sección de comprobaciones",
         "Puntos que conviene comprobar" in _html_reh2, False)
    test("--rehacer-acta: sin objeciones, borra el .txt de la corrida anterior en vez de "
         "dejar un aviso que ya no toca",
         _ruta_txt_reh.exists(), False)

    # Con el .docx bloqueado (Word abierto) _rehacer_acta no debe abortar. Se simula con un render_acta que falla.
    import plenos_acta as _pa_reh

    def _render_bloqueado(*_a, **_k):
        raise PermissionError("[Errno 13] Permission denied: 'acta.docx' (simulado)")

    _render_original = _pa_reh.render_acta
    _pa_reh.render_acta = _render_bloqueado
    try:
        _salida_bloqueo = _io_reh.StringIO()
        with _ctx_reh.redirect_stdout(_salida_bloqueo):
            _codigo3 = _pp._rehacer_acta(_fecha_reh)
    finally:
        _pa_reh.render_acta = _render_original

    # El código de salida habla del .docx (1 = sigue sin escribirse); las aserciones siguientes comprueban que no aborta.
    test("--rehacer-acta: con el .docx bloqueado, el código de salida lo dice",
         _codigo3, 1)
    test("--rehacer-acta: con el .docx bloqueado, avisa de que puede estar abierto en Word",
         "Word" in _salida_bloqueo.getvalue(), True)
    test("--rehacer-acta: con el .docx bloqueado, la guía se regenera igualmente",
         (_carpeta_reh / f"{_fecha_reh}-guia-de-verificacion.html").exists(), True)

    # Caso simétrico: la guía HTML abierta en el navegador (PermissionError) no debe dejar el .txt sin escribir.
    import plenos_guia as _pg_reh

    guardar_objeciones(_carpeta_reh, _fecha_reh,
                       [Problema(seccion="orden_del_dia[0].texto", afirmacion_dudosa="x",
                                motivo="y", evidencia="[00:00:01] Buenas tardes.")])
    _ruta_txt_reh.write_text("AVISO VIEJO\n", encoding="utf-8")
    _render_guia_original = _pg_reh.render_guia
    _intentos_guia = []

    def _guia_bloqueada(*a, **_k):
        _intentos_guia.append(a[-1])
        if len(_intentos_guia) == 1:  # solo el nombre de siempre está bloqueado
            raise PermissionError("[Errno 13] Permission denied: 'guia.html' (simulado)")
        return _render_guia_original(*a, **_k)

    _pg_reh.render_guia = _guia_bloqueada
    try:
        _salida_guia = _io_reh.StringIO()
        with _ctx_reh.redirect_stdout(_salida_guia):
            _codigo4 = _pp._rehacer_acta(_fecha_reh)
    finally:
        _pg_reh.render_guia = _render_guia_original

    _txt_bloqueo = _ruta_txt_reh.read_text(encoding="utf-8")
    test("--rehacer-acta: con la guía bloqueada, no aborta la función", _codigo4, 0)
    test("--rehacer-acta: con la guía bloqueada, el .txt se escribe igual",
         "AVISO VIEJO" in _txt_bloqueo, False)
    test("--rehacer-acta: con la guía bloqueada, el .txt sigue nombrando el punto en cristiano",
         "Punto 1º)" in _txt_bloqueo, True)
    test("--rehacer-acta: con la guía bloqueada, se escribe con otro nombre en vez de perderse",
         len(list(_carpeta_reh.glob(f"{_fecha_reh}-guia-de-verificacion-*.html"))), 1)
finally:
    _pp.BORRADOR_DIR = _bd_reh


# La presidenta de la Asociación de Jubilados es concejala, no público.
test("CORPORACION: dice que la presidenta de los jubilados es la concejala Chari",
     "Asociación de Jubilados" in _pi.CORPORACION
     and "Mª Rosario Cerdán Pérez" in _pi.CORPORACION, True)
test("CORPORACION: el ejemplo de cómo nombrar al público ya no usa ese cargo",
     "de la Asociación de Jubilados\"" in _pi.CORPORACION, False)


# ── asuntos fuera del orden del día (regla 16 ter) ────────────────────────────
# Van solo a la guía, nunca al acta: la secretaria decide si los recoge y dónde.
_informe_asuntos = InformePleno.model_validate(dict(
    INFORME_MINIMO,
    orden_del_dia=[
        {"numero": 1, "parte": "resolutiva", "timestamp": "00:10:00",
         "titulo": "APROBACIÓN DEL ACTA ANTERIOR", "texto": "x", "acuerdo": None,
         "votacion": None},
    ],
    asuntos_no_convocados=[
        {"asunto": "El Sr. Pons plantea el estado del camino de Las Chorreras.",
         "surge_en": "APROBACIÓN DEL ACTA ANTERIOR", "timestamp": "00:15:30"},
    ]))

_tmp_asuntos = os.path.join(tempfile.gettempdir(), "test_guia_asuntos.html")
render_guia(_informe_asuntos, _entrada_guia, _TRANS_GUIA, [], _tmp_asuntos)
_html_asuntos = Path(_tmp_asuntos).read_text(encoding="utf-8")
os.remove(_tmp_asuntos)

test("asuntos fuera del orden del día: la guía los pinta",
     "camino de Las Chorreras" in _html_asuntos, True)
test("asuntos fuera del orden del día: dicen en qué punto surgen",
     "En el debate de: APROBACIÓN DEL ACTA ANTERIOR" in _html_asuntos, True)
test("asuntos fuera del orden del día: llevan enlace al minuto",
     "?t=930" in _html_asuntos, True)
test("asuntos fuera del orden del día: la guía avisa de que NO están en el acta",
     "no está en ella" in _html_asuntos, True)
test("asuntos fuera del orden del día: sin ninguno, la sección no aparece",
     "Asuntos tratados fuera del orden del día" in _html_guia, False)

# El campo tiene default: un informe.json viejo (--rehacer-acta) sigue cargando.
test("asuntos fuera del orden del día: campo opcional, informes viejos siguen validando",
     InformePleno.model_validate(INFORME_MINIMO).asuntos_no_convocados, [])


# ── las dos causas de «no hay acta» no se confunden ───────────────────────────
print("── las dos causas de «no hay acta» ──────────────────────────────────")

# El .docx abierto en Word no es "tipo de sesión no consta": fallo_acta las separa y --rehacer-acta devuelve 1 si no se escribió.
import plenos_acta as _pa_fallo

def _render_bloqueado(informe, ruta):
    raise PermissionError(f"[Errno 13] Permission denied: '{ruta}'")

with tempfile.TemporaryDirectory() as _tmp_f:
    _bd_f = _pp.BORRADOR_DIR
    _pp.BORRADOR_DIR = Path(_tmp_f) / "actas"
    _bucle_f = _pi_rescate.bucle_informe
    _pi_rescate.bucle_informe = lambda t, c=None: (
        InformePleno.model_validate(INFORME_MINIMO), [])
    _render_f = _pa_fallo.render_acta
    _pa_fallo.render_acta = _render_bloqueado
    try:
        _res_f = _pp.procesar_pleno(None, "vid", "PLENO ORDINARIO", "2026-06-26", None,
                                    transcripcion="[00:00:01] Interviniente A: hola.")
        test("dos causas: con el .docx bloqueado no hay acta", _res_f.ruta_acta, None)
        test("dos causas: pero el motivo real queda registrado",
             _res_f.fallo_acta.startswith("PermissionError"), True)
        test("dos causas: --rehacer-acta avisa de que sigue sin escribirse",
             _pp._rehacer_acta("2026-06-26"), 1)

        _pa_fallo.render_acta = _render_f
        test("dos causas: al liberarse, --rehacer-acta lo compone",
             _pp._rehacer_acta("2026-06-26"), 0)
        _res_ok = _pp.procesar_pleno(None, "vid", "PLENO ORDINARIO", "2026-06-26", None,
                                     transcripcion="[00:00:01] Interviniente A: hola.")
        test("dos causas: con acta compuesta, fallo_acta vacío", _res_ok.fallo_acta, "")
        test("dos causas: y con su .docx", _res_ok.ruta_acta.exists(), True)
    finally:
        _pi_rescate.bucle_informe = _bucle_f
        _pa_fallo.render_acta = _render_f
        _pp.BORRADOR_DIR = _bd_f


# ── verificar_respuesta ───────────────────────────────────────────────────────
print("── verificar_respuesta ───────────────────────────────────────────────")

import requests as _rq
from plenos_informe import verificar_respuesta as _verificar


def _respuesta_http(codigo, cuerpo, razon):
    r = _rq.Response()
    r.status_code, r.reason, r.url = codigo, razon, "https://ejemplo/api"
    r._content = cuerpo.encode("utf-8")
    return r


def _mensaje_de(r):
    try:
        _verificar(r)
    except _rq.HTTPError as e:
        return str(e)
    return "no lanzó"


# Sin el cuerpo de la respuesta, el registro solo diría "402 Client Error".
_m402 = _mensaje_de(_respuesta_http(
    402, '{"error":{"code":402,"message":"Insufficient credits"}}', "Payment Required"))
test("verificar_respuesta: el motivo del 402 llega al mensaje",
     "402" in _m402 and "Insufficient credits" in _m402, True)
test("verificar_respuesta: sin cuerpo, el mensaje de requests queda intacto",
     _mensaje_de(_respuesta_http(400, "", "Bad Request")),
     "400 Client Error: Bad Request for url: https://ejemplo/api")
test("verificar_respuesta: una respuesta correcta pasa y se devuelve",
     _verificar(_respuesta_http(200, "ok", "OK")).status_code, 200)


# ── intervinientes, topónimos y reglas nuevas de los prompts ──────────────────
print("── intervinientes y prompts ──────────────────────────────────────────")
import plenos_informe as _pi_iv
import procesar_pleno as _pp_iv

_iv = _pi_iv.parsear_intervinientes(
    "- Fernando Pons Mayor = Nando, Pons\nMª Rosario Cerdán Pérez = Chari\n  \nMario Cerdán Ochoa")
test("intervinientes: una persona por línea, apodos separados por coma, apodo opcional",
     _iv, [{"nombre": "Fernando Pons Mayor", "apodos": ["Nando", "Pons"]},
           {"nombre": "Mª Rosario Cerdán Pérez", "apodos": ["Chari"]},
           {"nombre": "Mario Cerdán Ochoa", "apodos": []}])
test("intervinientes: sin lista no hay bloque", _pi_iv.bloque_intervinientes(None), "")
_b = _pi_iv.bloque_intervinientes(_iv)
test("intervinientes: el bloque lleva nombre y apodos",
     "Fernando Pons Mayor — en la sesión le llaman: «Nando», «Pons»" in _b
     and "- Mario Cerdán Ochoa\n" in _b, True)

_enviados = []
_llamar_orig = _pi_iv._llamar_llm
_pi_iv._llamar_llm = lambda sistema, contenido, *a, **k: (_enviados.append(contenido),
                                                            (_ for _ in ()).throw(StopIteration))[1]
for _fn, _args in ((_pi_iv.generar_informe, ("T",)),
                   (_pi_iv.auditar_informe, ("T", _pi_iv.InformePleno.model_construct())),
                   (_pi_iv.corregir_informe, ("T", _pi_iv.InformePleno.model_construct(), []))):
    for _iv_arg in (_iv, None):
        try:
            _fn(*_args, intervinientes=_iv_arg) if _iv_arg else _fn(*_args)
        except (StopIteration, RuntimeError):
            pass
_pi_iv._llamar_llm = _llamar_orig
test("intervinientes: generador, auditor y corrector reciben el bloque antes de la transcripción",
     [c.startswith("INTERVINIENTES DE ESTA SESIÓN") for c in _enviados],
     [True, False, True, False, True, False])

for _rol in ("PROMPT_GENERADOR", "PROMPT_AUDITOR", "PROMPT_CORRECTOR"):
    _t = getattr(_pi_iv, _rol)
    test(f"{_rol}: lleva las reglas de intervinientes y el listado de la Corporación",
         "INTERVINIENTES DE LA SESIÓN" in _t and "CORPORACIÓN MUNICIPAL" in _t, True)
for _t in (_pi_iv.PROMPT_GENERADOR, _pi_iv.PROMPT_CORRECTOR):
    test("topónimos: generador y corrector los listan todos",
         all(x in _t for x in _pi_iv.TOPONIMOS), True)
test("generador: reglas 6 bis, 14 bis y 16 quater presentes",
     all(r in _pi_iv.PROMPT_GENERADOR for r in ("6 bis. NO RECONSTRUYAS", "14 bis. LAS RESPUESTAS",
                                                "16 quater. INSULTOS")), True)
test("auditor: revisa datos sin frase clara y reproches personales",
     "DATOS SIN UNA FRASE CLARA" in _pi_iv.PROMPT_AUDITOR
     and "REPROCHES PERSONALES" in _pi_iv.PROMPT_AUDITOR, True)
test("corrector: no deshace las reglas nuevas", "6 bis" in _pi_iv.PROMPT_CORRECTOR
     and "16 quater" in _pi_iv.PROMPT_CORRECTOR, True)
test("la 16 no contradice la 16 quater: remite a ella para el reproche personal",
     "16 quater" in _pi_iv.PROMPT_GENERADOR.split("16 bis.")[0], True)

_kt = _pp_iv.keyterms_del_pleno(_iv)
test("keyterms: toponimos fijos + nombres y apodos del pleno, sin duplicados",
     all(t in _kt for t in ("Pesquera", "Las Chorreras", "Playeta", "Keltiber", "PR-53",
                            "GR-64", "GR-66", "Nando", "Chari", "Fernando Pons Mayor"))
     and len(_kt) == len({t.lower() for t in _kt}), True)
test("keyterms: sin intervinientes quedan los fijos", _pp_iv.keyterms_del_pleno(None),
     list(dict.fromkeys(_pp_iv.AAI_KEYTERMS)))


from plenos_acta import normalizar_cargos as _nc, tipografia as _tip
test("cargos: «la Sra. Alcaldesa» pasa a la Teniente de Alcalde",
     _nc("La Sra. Alcaldesa da cuenta del decreto."), "La Sra. Teniente de Alcalde da cuenta del decreto.")
test("cargos: «en funciones» y minúsculas también",
     _nc("Responde la alcaldesa en funciones que sí."), "Responde la Sra. Teniente de Alcalde que sí.")
test("cargos: una cita entre comillas se respeta",
     _nc("lamenta el uso de términos como “alcaldesa accidental” para referirse a ella."),
     "lamenta el uso de términos como “alcaldesa accidental” para referirse a ella.")
test("cargos: lo que ya está bien no cambia",
     _nc("La Sra. Teniente de Alcalde propone."), "La Sra. Teniente de Alcalde propone.")
test("tipografía: comillas rectas y cargos a la vez",
     _tip('La alcaldesa dice "sí"'), "La Sra. Teniente de Alcalde dice “sí”")


# ── votaciones coherentes, calificaciones vetadas y fecha (acta del 3-IX, 2.ª vuelta) ──
print("── coherencia de votaciones y fecha ──────────────────────────────────")
from plenos_informe import Votacion as _V, PuntoOrdenDia as _P, InformePleno as _IP, incoherencias as _inc
test("recuento completo + 'no consta' → se deduce aprobado (3-2-2)",
     _V(resultado="no consta", modalidad="recuento", a_favor=3, en_contra=2, abstenciones=2).resultado,
     "aprobado")
test("recuento completo + 'no consta' → se deduce rechazado (3-4)",
     _V(resultado="no consta", modalidad="recuento", a_favor=3, en_contra=4).resultado, "rechazado")
test("empate: no se deduce, depende del voto de calidad",
     _V(resultado="no consta", modalidad="recuento", a_favor=3, en_contra=3).resultado, "no consta")
test("recuento incompleto: no se deduce",
     _V(resultado="no consta", modalidad="recuento", a_favor=3).resultado, "no consta")

def _informe_con(punto_kw, ruegos=()):
    base = dict(tipo_sesion="ordinaria", solicitantes=[], asistentes=[], ausentes=[],
                declaraciones_apertura=[], ruegos_y_preguntas=list(ruegos), resumen_corto="r")
    punto = {"numero": 1, "parte": "resolutiva", "titulo": "T", "texto": "Debate.", **punto_kw}
    return _IP(orden_del_dia=[_P(**punto)], **base)

_acta7 = _informe_con(dict(acuerdo="rechazar la aprobación del acta del 7 de julio",
                           votacion=_V(resultado="no consta", modalidad="recuento",
                                       a_favor=3, en_contra=2, abstenciones=2)))
test("incoherencia: acuerdo que rechaza lo que el recuento aprueba",
     [p.seccion for p in _inc(_acta7)], ["orden_del_dia[0].acuerdo"])
_ok = _informe_con(dict(acuerdo="aprobar el acta del 7 de julio",
                        votacion=_V(resultado="aprobado", modalidad="recuento", a_favor=3, en_contra=2)))
test("coherente: sin problemas", _inc(_ok), [])
_rech = _informe_con(dict(acuerdo="rechazar la solicitud de asistencia jurídica",
                          votacion=_V(resultado="rechazado", modalidad="recuento", a_favor=3, en_contra=4)))
test("rechazo coherente: sin problemas", _inc(_rech), [])
_mal = _informe_con(dict(acuerdo="aprobar la solicitud",
                         votacion=_V(resultado="rechazado", modalidad="recuento", a_favor=5, en_contra=2)))
test("incoherencia: resultado contrario al recuento, y acuerdo que no dice rechazar",
     sorted(p.seccion for p in _inc(_mal)), ["orden_del_dia[0].acuerdo", "orden_del_dia[0].votacion"])
_tenso = _informe_con(dict(texto="Se produce un tenso enfrentamiento entre ambos."))
test("16 quater: «tenso enfrentamiento» se marca para el corrector",
     [p.seccion for p in _inc(_tenso)], ["orden_del_dia[0].texto"])

from procesar_pleno import fijar_fecha as _ff
test("fecha: manda la indicada al procesar, aunque el modelo oyera otra",
     _ff(_informe_con(dict()).model_copy(update={"fecha_pleno": "2026-09-30"}), "2026-09-03").fecha_pleno,
     "2026-09-03")
test("fecha: también rellena el null", _ff(_informe_con(dict()), "2026-09-03").fecha_pleno, "2026-09-03")
test("topónimos: Hoya de las Abejas", "Hoya de las Abejas" in _pi_iv.TOPONIMOS, True)


# ── citas literales, topónimos parecidos, auditor con otro modelo y atribuciones ─────
print("── citas, topónimos, modelo del auditor, atribuciones ────────────────")
import plenos_informe as _pj
from plenos_informe import citas_no_halladas as _citas, toponimos_parecidos as _topos

_TR = ("[00:10:00] Interviniente A: Yo lo que digo es que usted nos ha mentido a todos los "
       "vecinos en este asunto y no pienso callarme\n"
       "[00:10:20] Interviniente B: Eso no es cierto, Chari, y lo sabes perfectamente bien")
_c_ok = _informe_con(dict(texto='Dª Rosario afirma: “usted nos ha mentido a todos los vecinos en este asunto”.'))
test("citas: una cita que está en la transcripción no se marca", _citas(_c_ok, _TR), [])
_c_mal = _informe_con(dict(texto='Dª Rosario amenaza: “voy a promover su expulsión del grupo por traidor”.'))
test("citas: una cita inventada se marca", [p.seccion for p in _citas(_c_mal, _TR)],
     ["orden_del_dia[0].texto"])
_c_nombre = _informe_con(dict(texto='Responde: “Eso no es cierto, Dª Rosario, y lo sabes perfectamente bien”.'))
test("citas: un nombre sustituido dentro de la cita no dispara", _citas(_c_nombre, _TR), [])
_c_corta = _informe_con(dict(texto='Lamenta el uso de “alcaldesa accidental” en la prensa.'))
test("citas: las muy cortas se saltan", _citas(_c_corta, _TR), [])
_c_elip = _informe_con(dict(texto='Dice: “usted nos ha mentido a todos los vecinos … y no pienso callarme”.'))
test("citas: los puntos suspensivos parten la cita", _citas(_c_elip, _TR), [])
test("citas: sin transcripción, incoherencias no las comprueba", _inc(_c_mal), [])
test("citas: con transcripción, incoherencias sí las comprueba",
     [p.seccion for p in _inc(_c_mal, _TR)], ["orden_del_dia[0].texto"])

test("topónimos: «Hoya de las Vejas» se marca",
     [p.evidencia for p in _topos(_informe_con(dict(texto="Se arregla el camino de la Hoya de las Vejas.")))],
     ["(comprobación automática de topónimos)"])
test("topónimos: el nombre exacto no se marca",
     _topos(_informe_con(dict(texto="Se arregla el camino de la Hoya de las Abejas y Las Chorreras."))), [])
test("topónimos: un lugar que no está en la lista no se detecta ni molesta",
     _topos(_informe_con(dict(texto="Se arregla el camino del Cerro Gordo."))), [])
test("topónimos: el gentilicio «Enguídano» no se marca",
     _topos(_informe_con(dict(texto="Un vecino enguidano pregunta."))), [])
test("topónimos: GR-65 es casi GR-64 y se marca",
     len(_topos(_informe_con(dict(texto="Por el GR-65 hay un desprendimiento.")))), 1)

_cuerpos = []
_peticion_real = _pj._peticion
try:
    def _peticion_espia(cuerpo, intentos=4):
        _cuerpos.append(cuerpo)
        return {"choices": [{"finish_reason": "stop", "message": {"content": '{"problemas": []}'}}],
                "usage": {}}
    _pj._peticion = _peticion_espia
    with contextlib.redirect_stdout(io.StringIO()):
        _pj._llamar_llm("i", "c", AuditoriaInforme, None, "x")
        _pj._llamar_llm("i", "c", AuditoriaInforme, None, "auditor", _pj.MODELO_AUDITOR)
finally:
    _pj._peticion = _peticion_real
test("auditor: el redactor sigue en Gemini con temperatura 0",
     (_cuerpos[0]["model"], _cuerpos[0].get("temperature"), "reasoning" in _cuerpos[0]),
     ("google/gemini-2.5-pro", 0, False))
test("auditor: otro modelo, sin temperatura y con razonamiento",
     (_cuerpos[1]["model"], "temperature" in _cuerpos[1], _cuerpos[1].get("reasoning")),
     ("anthropic/claude-opus-5.5", False, {"enabled": True}))
test("auditor: no es el mismo modelo que el redactor", _pj.MODELO_AUDITOR != _pj.MODELO, True)

_atrib_llamadas, _vistos_corrector = [], []
def _atrib_fake(t, i):
    _atrib_llamadas.append(1)
    return AuditoriaInforme(problemas=[Problema(seccion="ruegos_y_preguntas[0]",
        afirmacion_dudosa="Pregunta atribuida a D. Joaquín", motivo="la hizo un vecino",
        evidencia="usted se puede enterar")])
_auds = iter([AuditoriaInforme(problemas=[]), AuditoriaInforme(problemas=[])])
def _cor_atrib(t, i, p):
    _vistos_corrector.append([x.seccion for x in p])
    return i.model_copy(update={"resumen_corto": "corregido"})
bucle_informe("t", generar=lambda t: _informe_v1, auditar=lambda t, i: next(_auds),
              corregir=_cor_atrib, atribuciones=_atrib_fake)
test("atribuciones: se ejecuta una sola vez", len(_atrib_llamadas), 1)
test("atribuciones: sus objeciones llegan al corrector", _vistos_corrector[0], ["ruegos_y_preguntas[0]"])
test("atribuciones: con fakes y sin inyectarla no se llama a ningún modelo",
     bucle_informe("t", generar=lambda t: _informe_v1,
                   auditar=lambda t, i: AuditoriaInforme(problemas=[]),
                   corregir=lambda t, i, p: i)[1], [])
test("atribuciones: el prompt pregunta quién lo dijo y pide citar el turno",
     all(x in _pj.PROMPT_ATRIBUCIONES for x in ("UNA sola comprobación", "SEÑALES DE PÚBLICO",
                                                 "NO señales")), True)

import quejas_pleno as _qp
_malo = _informe_con(dict(texto="Se produce un tenso enfrentamiento en Pesquera."))
test("quejas: un informe con la queja en pie la detecta",
     [c[0] for c in _qp.CASOS["2026-09-03"] if not c[2](_malo)][:3], ["fecha", "punto1-votacion", "punto3-votacion"])
test("quejas: fuera_de_citas respeta las citas",
     "alcaldesa" in _qp.fuera_de_citas("la alcaldesa dice “alcaldesa accidental”").lower(), True)
test("quejas: texto entre citas no cuenta", _qp.fuera_de_citas("dice “alcaldesa accidental” fin").count("alcaldesa"), 0)


# ── recuentos protegidos y auditor Opus ───────────────────────────────────────────────
print("── recuentos protegidos ──────────────────────────────────────────────")
from plenos_informe import restaurar_recuentos as _rr
_con34 = _informe_con(dict(acuerdo="rechazar la solicitud",
                           votacion=_V(resultado="rechazado", modalidad="recuento", a_favor=3, en_contra=4)))
_sin34 = _informe_con(dict(acuerdo="rechazar la solicitud",
                           votacion=_V(resultado="rechazado", modalidad="recuento")))
_r, _av = _rr(_con34, _sin34)
test("recuento: el que el corrector borra se restaura",
     (_r.orden_del_dia[0].votacion.a_favor, _r.orden_del_dia[0].votacion.en_contra), (3, 4))
test("recuento: el resultado del corrector se respeta", _r.orden_del_dia[0].votacion.resultado, "rechazado")
test("recuento: queda un aviso para quien revisa", [a.seccion for a in _av], ["orden_del_dia[0].votacion"])
_r2, _av2 = _rr(_con34, _informe_con(dict(acuerdo="rechazar la solicitud")))
test("recuento: también si el corrector deja la votación en null",
     (_r2.orden_del_dia[0].votacion.a_favor, len(_av2)), (3, 1))
_r3, _av3 = _rr(_sin34, _con34)
test("recuento: añadir uno no genera aviso", _av3, [])
_r4, _av4 = _rr(_con34, _con34.model_copy(update={"resumen_corto": "otro"}))
test("recuento: si no se toca no hay aviso", _av4, [])
_c_otro = _informe_con(dict(acuerdo="x", votacion=_V(resultado="rechazado", modalidad="recuento",
                                                     a_favor=5, en_contra=1)))
_r5, _av5 = _rr(_con34, _c_otro)
test("recuento: un recuento distinto (no borrado) lo decide el corrector", _av5, [])
test("auditor: Opus 5.5", _pj.MODELO_AUDITOR, "anthropic/claude-opus-5.5")
test("recuento: el auditor y el de atribuciones saben que la etiqueta mezclada no lo invalida",
     ("NO INVALIDA UN RECUENTO" in _pj.PROMPT_AUDITOR, "no los invalida" in _pj.PROMPT_ATRIBUCIONES),
     (True, True))

_g34 = _con34
_n = iter([AuditoriaInforme(problemas=[Problema(seccion="orden_del_dia[0].votacion",
            afirmacion_dudosa="3-4", motivo="etiqueta mezclada", evidencia="e")]),
           AuditoriaInforme(problemas=[])])
_inf_f, _pend_f = bucle_informe("t", generar=lambda t: _g34, auditar=lambda t, i: next(_n),
                                corregir=lambda t, i, p: _sin34)
test("bucle: el recuento borrado por el corrector se restaura",
     (_inf_f.orden_del_dia[0].votacion.a_favor, _inf_f.orden_del_dia[0].votacion.en_contra), (3, 4))
test("bucle: el aviso llega a los pendientes",
     _pend_f[-1].evidencia, "(comprobación automática de recuentos)")


print()
print("── voces confirmadas por la secretaría ───────────────────────────────")
from plenos_informe import (VOZ_MEZCLADA, VOZ_PUBLICO, aplicar_voces, bloque_voces,
                            muestras_por_etiqueta)

_t_voces = "\n".join(
    f"[00:{i:02d}:00] Interviniente {'A' if i % 2 else 'B'}: " + " ".join(["palabra"] * 10) + f" {i}"
    for i in range(1, 21)) + "\n[00:30:00] Interviniente C: sí\n"
_m = muestras_por_etiqueta(_t_voces, n=4)
test("muestras: una entrada por etiqueta", sorted(_m), ["A", "B", "C"])
test("muestras: cuenta las intervenciones", _m["A"][0], 10)
test("muestras: n frases", len(_m["A"][1]), 4)
test("muestras: repartidas, no las primeras",
     (_m["A"][1][0][0], _m["A"][1][-1][0]), ("00:01:00", "00:19:00"))
test("muestras: una etiqueta de una sola frase corta aún sale", _m["C"][1], [("00:30:00", "sí")])

test("sin voces no hay bloque", bloque_voces(None), "")
_bv = bloque_voces({"B": "Dª Lorena Luján Chujfi", "F": VOZ_PUBLICO, "C": VOZ_MEZCLADA})
test("bloque: nombre de la persona", "Interviniente B: Dª Lorena Luján Chujfi" in _bv, True)
test("bloque: público", "Interviniente F: público asistente" in _bv, True)
test("bloque: mezclada no atribuye identidad", "ninguna identidad" in _bv, True)

_inf_v = aplicar_voces(_informe_v1, {"B": "Dª Lorena Luján Chujfi", "C": VOZ_MEZCLADA})
_mapa = {v.etiqueta: v for v in _inf_v.identificacion_locutores}
test("aplicar: la confirmada entra en el mapa", _mapa["B"].persona, "Dª Lorena Luján Chujfi")
test("aplicar: con su evidencia", "Confirmada por la secretaría" in _mapa["B"].evidencia, True)
test("aplicar: mezclada", _mapa["C"].persona, VOZ_MEZCLADA)
test("aplicar sin voces no toca nada", aplicar_voces(_informe_v1, None), _informe_v1)


# ── resultado ─────────────────────────────────────────────────────────────────
print()
if _failures:
    print(f"✗ {len(_failures)} tests fallidos")
    sys.exit(1)
print("✓ Todos los tests pasan")
