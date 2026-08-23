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
    "fecha_pleno": "2026-06-26",
    "hora_inicio": "12:00",
    "hora_fin": "13:30",
    "presidente": "Sergio de Fez Cerezuela",
    "asistentes": ["Lorena Luján Chujfi", "Mario Cerdán Ochoa"],
    "ausentes": ["Fernando Pons"],
    "orden_del_dia": [
        {"numero": 1, "parte": "resolutiva",
         "titulo": "APROBACIÓN SI PROCEDE DEL ACTA DE LA SESIÓN ANTERIOR",
         "texto": "El Sr. Alcalde da cuenta del acta de la sesión anterior. No se formulan observaciones.",
         "votacion": {"resultado": "aprobado", "modalidad": "unanimidad",
                      "a_favor": None, "en_contra": None, "abstenciones": None,
                      "timestamp": "00:03:12"}},
        {"numero": 2, "parte": "control",
         "titulo": "DECRETOS DE ALCALDÍA",
         "texto": "El Sr. Alcalde da cuenta de los decretos dictados. La Corporación se da por informada.",
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

# Las vías de escape tienen que seguir siendo válidas: un pleno del que no se
# sabe casi nada debe parsear igual, sin forzar al modelo a rellenar huecos.
_MINIMO_VACIO = dict(INFORME_MINIMO, tipo_sesion="no consta", fecha_pleno=None,
                     hora_inicio=None, hora_fin=None, presidente=None,
                     asistentes=[], ausentes=[], ruegos_y_preguntas=[])
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


# ── funciones puras del pipeline ──────────────────────────────────────────────
print("── pipeline: fecha, segmentos, esperas ───────────────────────────────")

from procesar_pleno import (
    extraer_fecha, unir_segmentos, formatear_utterances, extraer_video_id,
    _espera_tras_error, ESPERA_MAXIMA, AAI_SPELLING, AAI_KEYTERMS,
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

# AssemblyAI: start viene en milisegundos, y la etiqueta de locutor va delante del texto
# para que el redactor pueda agrupar intervenciones sin confundirla con un nombre.
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

from procesar_pleno import entrada_publicada

_generada = {"video_id": "v9", "fecha": "2026-07-07", "titulo": "Pleno extraordinario",
             "video_url": "https://youtu.be/v9", "resumen_corto": "..."}
_publicada = entrada_publicada(_generada, "2026-07-07")
test("publicar: ruta del pdf", _publicada["pdf"], "plenos/2026-07-07-pleno.pdf")
test("publicar: ruta de la transcripción",
     _publicada["transcripcion"], "plenos/2026-07-07-transcripcion.md")
test("publicar: conserva el resumen corto", _publicada["resumen_corto"], "...")
test("publicar: no muta la entrada original", "pdf" in _generada, False)

# Publicar dos veces el mismo pleno actualiza la fila, no la duplica.
_idx = nueva_entrada_indice({"plenos": []}, _publicada)
_idx = nueva_entrada_indice(_idx, entrada_publicada(dict(_generada, resumen_corto="revisado"),
                                                    "2026-07-07"))
test("publicar: republicar no duplica", len(_idx["plenos"]), 1)
test("publicar: republicar actualiza", _idx["plenos"][0]["resumen_corto"], "revisado")

# publicar() debe leer todo lo que pueda fallar ANTES de escribir en public/:
# si entrada.json está corrupto, no puede quedar un PDF copiado sin su fila en
# el índice. Se usa un directorio temporal del sistema (nunca uploads/ ni
# public/ del repo) y se restauran las rutas del módulo al terminar.
import json as _json_publicar
import tempfile as _tempfile_publicar
from pathlib import Path as _Path_publicar
import procesar_pleno as _pp

with _tempfile_publicar.TemporaryDirectory() as _tmp_pub:
    _tmp_pub = _Path_publicar(_tmp_pub)
    _borrador_falso = _tmp_pub / "borrador" / "2026-09-01"
    _borrador_falso.mkdir(parents=True)
    (_borrador_falso / "entrada.json").write_text("{esto no es json", encoding="utf-8")
    (_borrador_falso / "2026-09-01-transcripcion.md").write_text("texto", encoding="utf-8")
    _pdf_sellado_falso = _tmp_pub / "sellado.pdf"
    _pdf_sellado_falso.write_bytes(b"%PDF-fake")
    _salida_falsa = _tmp_pub / "public_plenos"

    _bd0, _sd0, _ip0 = _pp.BORRADOR_DIR, _pp.SALIDA_DIR, _pp.INDICE_PATH
    _pp.BORRADOR_DIR = _tmp_pub / "borrador"
    _pp.SALIDA_DIR = _salida_falsa
    _pp.INDICE_PATH = _tmp_pub / "public_data" / "plenos.json"
    try:
        _lanzo_decode_error = False
        try:
            _pp.publicar("2026-09-01", str(_pdf_sellado_falso))
        except _json_publicar.JSONDecodeError:
            _lanzo_decode_error = True
        test("publicar: entrada.json corrupto aborta antes de escribir",
             _lanzo_decode_error, True)
        test("publicar: no deja el pdf publicado a medias",
             (_salida_falsa / "2026-09-01-pleno.pdf").exists(), False)
    finally:
        _pp.BORRADOR_DIR, _pp.SALIDA_DIR, _pp.INDICE_PATH = _bd0, _sd0, _ip0


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
from plenos_acta import render_acta, frase_votacion, parrafo_apertura, formula_cierre, HUECO

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

_apertura = parrafo_apertura(informe)
test("apertura: nombra a los asistentes", "Mario Cerdán Ochoa" in _apertura, True)
test("apertura: hace constar la ausencia", "No asiste" in _apertura, True)
test("apertura: sin datos deja el hueco", parrafo_apertura(_vacio), "___________")

_cierre = formula_cierre(informe)
test("cierre: hora en letra", "las trece horas y treinta minutos" in _cierre, True)
test("cierre: fecha en letra", "veintiséis de junio del dos mil veintiséis" in _cierre, True)
test("cierre: sin datos deja huecos", "___________" in formula_cierre(_vacio), True)
# El acta real firmada lleva raya, no guion: "Secretaria – Interventora".
test("cierre: Secretaria con raya, como en el acta real", "Secretaria – Interventora" in _cierre, True)


def _acta_generada(inf):
    """Genera el .docx y devuelve (texto de las tablas, texto de los párrafos).
    Se comprueba el documento real, no una representación intermedia."""
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
test("acta: punto resolutivo en la parte A", "APROBACIÓN SI PROCEDE" in _tablas[4], True)
test("acta: punto de control en la parte B", "DECRETOS DE ALCALDÍA" in _tablas[6], True)
test("acta: el punto de control no está en la parte A", "DECRETOS DE ALCALDÍA" in _tablas[4], False)
test("acta: numeración del punto", "1º)" in _tablas[4], True)
test("acta: frase de votación en la parte A", "por unanimidad de los asistentes" in _tablas[4], True)
test("acta: ruegos con quien los formula", "D. Joaquín Martínez" in _tablas[8], True)
test("acta: contenido del ruego", "camino de la Fuente" in _tablas[8], True)
test("acta: sin marcas de tiempo", "00:03:12" in "".join(_tablas), False)
test("acta: fórmula de cierre presente", "no habiendo más asuntos que tratar" in _parrafos, True)
test("acta: asistentes en el párrafo de apertura", "Lorena Luján Chujfi" in _parrafos, True)

# Un pleno sin ruegos conserva el "No hay asuntos" de la plantilla en esa sección.
_sin_ruegos = InformePleno.model_validate(dict(INFORME_MINIMO, ruegos_y_preguntas=[]))
_tablas_sr, _ = _acta_generada(_sin_ruegos)
test("acta: sección vacía conserva 'No hay asuntos'", "No hay asuntos" in _tablas_sr[8], True)

# Decisión deliberada de la spec: si la grabación no identifica quién preside,
# la celda "Presidida por" conserva el nombre de la plantilla del Ayuntamiento
# (LORENA LUJÁN CHUJFI) en vez de vaciarse a HUECO. No es un descuido: la
# plantilla es la oficial del Ayuntamiento y la secretaria revisa y corrige el
# borrador a mano antes de sellarlo, así que dejar el valor de la plantilla es
# más seguro que forzar un hueco que igualmente habría que rellenar a mano.
_sin_presidente = InformePleno.model_validate(dict(INFORME_MINIMO, presidente=None))
_tablas_sp, _ = _acta_generada(_sin_presidente)
test("acta: sin presidente en la grabación conserva el de la plantilla",
     "LORENA LUJÁN CHUJFI" in _tablas_sp[2], True)

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


# ── convocatoria ──────────────────────────────────────────────────────────────
print("── convocatoria (orden del día) ──────────────────────────────────────")

from procesar_pleno import leer_convocatoria

test("convocatoria: sin ruta no hay convocatoria", leer_convocatoria(None), None)

with tempfile.TemporaryDirectory() as _tmp:
    # Se lee en BINARIO y sin extraer texto: las convocatorias del Ayuntamiento son
    # escaneos (un JPEG dentro del PDF) y el PDF entero viaja a Gemini tal cual.
    _pdf = os.path.join(_tmp, "convocatoria.pdf")
    with open(_pdf, "wb") as _f:
        _f.write(b"%PDF-1.4 fake")
    test("convocatoria: se lee en bytes, sin extraer texto",
         leer_convocatoria(_pdf), b"%PDF-1.4 fake")

    _no_pdf = os.path.join(_tmp, "convocatoria.docx")
    with open(_no_pdf, "wb") as _f:
        _f.write(b"x")
    _rechazo = None
    try:
        leer_convocatoria(_no_pdf)
    except ValueError:
        _rechazo = "no es pdf"
    test("convocatoria: un fichero que no es PDF se rechaza", _rechazo, "no es pdf")

    _falta = None
    try:
        leer_convocatoria(os.path.join(_tmp, "no-existe.pdf"))
    except FileNotFoundError:
        _falta = "no existe"
    test("convocatoria: ruta inexistente avisa", _falta, "no existe")

# El auditor tiene que recibir la convocatoria igual que el generador: sin ella
# marcaría cada título del orden del día como afirmación no respaldada (Whisper
# destroza los nombres) y quemaría las tres vueltas sin arreglar nada.
_recibida = {"generar": None, "auditar": None, "corregir": None}
_CONV = b"%PDF-convocatoria"

import plenos_informe as _pi

_reales = (_pi.generar_informe, _pi.auditar_informe, _pi.corregir_informe)
try:
    def _gen_espia(t, convocatoria=None):
        _recibida["generar"] = convocatoria
        return _informe_v1
    def _aud_espia(t, i, convocatoria=None):
        _recibida["auditar"] = convocatoria
        return AuditoriaInforme(problemas=[])
    def _cor_espia(t, i, p, convocatoria=None):
        _recibida["corregir"] = convocatoria
        return i
    _pi.generar_informe, _pi.auditar_informe, _pi.corregir_informe = (
        _gen_espia, _aud_espia, _cor_espia)
    # Sin kwargs inyectados, el bucle toma la ruta real y narra su progreso; aquí
    # solo interesa qué recibe cada rol, así que su salida se descarta.
    import contextlib, io as _io
    with contextlib.redirect_stdout(_io.StringIO()):
        _pi.bucle_informe("transcripción", _CONV)
finally:
    _pi.generar_informe, _pi.auditar_informe, _pi.corregir_informe = _reales

test("convocatoria: la recibe el generador", _recibida["generar"], _CONV)
test("convocatoria: la recibe el AUDITOR", _recibida["auditar"], _CONV)

# Los fakes inyectados por los tests conservan su firma de siempre: el bucle no les
# pasa la convocatoria, así que añadirla no obliga a tocar los tests del bucle.
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
    """Sustituye a requests: registra lo que se le pide y devuelve la secuencia
    upload → submit → processing → completed."""
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
test("assemblyai: rango de locutores anidado en speaker_options",
     _falso.cuerpo["speaker_options"], {"min_speakers_expected": 6, "max_speakers_expected": 10})
test("assemblyai: la corporación viaja en keyterms",
     "Lorena Luján Chujfi" in _falso.cuerpo["keyterms_prompt"], True)


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


# ── la transcripción sobrevive al fallo del LLM ───────────────────────────────
print("── la transcripción sobrevive al fallo del LLM ──────────────────────")

# Costó 0,48 $ y no se puede repetir gratis: si el bucle LLM revienta, el .md tiene
# que estar ya en disco para que --rehacer-informe lo reutilice.
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

# El fallo real del 2026-08-22: el auditor devolvió content=None y el None viajaba
# hasta pydantic, que reventaba con un error de tipos mudo sobre la causa.
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

# El fallo real del 2026-08-22: el auditor se atascó razonando, Google dejó de emitir
# y OpenRouter devolvió 200 con {"error": {"code": 504, ...}} dentro del choice. Sin
# reintento, eso tiraba tres vueltas de corrector ya pagadas.
# Ahora la petición va en streaming, así que el falso devuelve líneas SSE, que es lo que
# _peticion consume de verdad.
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

# Agotados los intentos, el corte se convierte en el error legible de siempre.
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

# El bucle del 2026-08-22 quemó sus tres vueltas en el punto 5: el auditor rechazaba
# el recuento ("la frase es ininteligible") y el corrector respondía cambiando 5 por 4
# en vez de poner null. La regla que lo prohíbe tiene que seguir en el prompt.
_pc = _pi_rescate.PROMPT_CORRECTOR
test("corrector: la regla de recuentos está en el prompt",
     "RECUENTOS DE VOTOS" in _pc, True)
test("corrector: prohíbe cambiar la cifra por otra que encaje",
     "NO es\n   cambiar ese número por otro" in _pc, True)
test("corrector: prohíbe deducir restando de los asistentes",
     "restando del número de asistentes" in _pc, True)
test("corrector: prohíbe el 0 de relleno",
     "va a `null`, nunca a 0" in _pc, True)

# La regla vive en un bloque compartido: el generador la necesita porque el `0` inventado
# que la incumplía lo escribió él, no el corrector.
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
test("corrector: resultado y modalidad se conservan",
     "`resultado` y `modalidad` se conservan" in _pc, True)
test("corrector: sus reglas siguen numeradas sin saltos",
     [n for n in range(1, 8) if f"\n{n}. " in _pc], list(range(1, 8)))


# ── "sin votación" como cadena en lugar del objeto ───────────────────────────
print("── \"sin votación\" como cadena ─────────────────────────────────────")

# Fallo real del 2026-08-23: el generador puso la cadena "sin votación" en `votacion`,
# que es objeto o null. Hay dos vías de escape parecidas y las confundió; la intención
# es inequívoca, así que se normaliza en vez de tirar la generación entera.
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

# Una cadena que NO significa ausencia debe seguir fallando: normalizarla a null diría
# que no hubo votación cuando sí la hubo.
_fallo = False
try:
    _POD.model_validate(dict(_base, votacion="aprobado por unanimidad"))
except Exception:
    _fallo = True
test("una cadena con contenido sigue siendo un error", _fallo, True)

test("el prompt explica que `votacion` es objeto o null, nunca cadena",
     "nunca una cadena de texto" in _pi_rescate.PROMPT_GENERADOR, True)


# ── reensamblado del stream SSE ───────────────────────────────────────────────
# El streaming existe para que el proveedor no corte la petición por ociosa mientras
# gemini-2.5-pro razona (504 "Upstream idle timeout exceeded"). Lo que hay que fijar es
# que reensamblar los trozos devuelva exactamente la forma que espera _llamar_llm.
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

# El corte del proveedor llega como un trozo más, con el error dentro del choice: si no
# se propaga, _peticion no lo reintentaría y el JSON truncado llegaría a pydantic.
_roto = _sse([
    'data: {"choices":[{"delta":{"content":"{\\"a\\":"}}]}',
    'data: {"choices":[{"error":{"code":504,"message":"Upstream idle timeout exceeded"}}]}',
])
test("el error del proveedor se propaga", _roto["choices"][0]["error"]["code"], 504)

test("el auditor también recibe el bloque de RECUENTOS",
     "RECUENTOS DE VOTOS" in _pi_rescate.PROMPT_AUDITOR, True)


# ── resultado ─────────────────────────────────────────────────────────────────
print()
if _failures:
    print(f"✗ {len(_failures)} tests fallidos")
    sys.exit(1)
print("✓ Todos los tests pasan")
