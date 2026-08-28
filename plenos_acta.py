#!/usr/bin/env python3
"""
plenos_acta.py - Render determinista del acta: InformePleno → .docx.

Sin LLM. Rellena la plantilla Word oficial del Ayuntamiento (una para plenos
ordinarios y otra para extraordinarios) con los datos del informe.

El acta escribe las cifras en palabras, así que este módulo incluye un
conversor de 0 a 99: cubre horas, minutos, días, recuentos de votos y el año.
# ponytail: tabla propia en vez de la dependencia num2words; 0-99 es todo lo
# que un acta necesita. Si algún día hiciera falta más rango, cambiar aquí.
"""

_UNIDADES = [
    "cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve",
    "diez", "once", "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete",
    "dieciocho", "diecinueve", "veinte", "veintiuno", "veintidós", "veintitrés",
    "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho", "veintinueve",
]

_DECENAS = {3: "treinta", 4: "cuarenta", 5: "cincuenta", 6: "sesenta",
            7: "setenta", 8: "ochenta", 9: "noventa"}

_MESES_NOMBRE = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                 "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def letras(n: int) -> str:
    """Número de 0 a 99 en palabras."""
    if not 0 <= n <= 99:
        raise ValueError(f"fuera de rango (0-99): {n}")
    if n < 30:
        return _UNIDADES[n]
    decena, unidad = divmod(n, 10)
    if unidad == 0:
        return _DECENAS[decena]
    return f"{_DECENAS[decena]} y {_UNIDADES[unidad]}"


def anio_en_letra(a: int) -> str:
    if not 2000 <= a <= 2099:
        raise ValueError(f"año fuera de rango (2000-2099): {a}")
    return "dos mil" if a == 2000 else f"dos mil {letras(a - 2000)}"


def hora_en_letra(hhmm: str) -> str:
    """'15:54' → 'las quince horas y cincuenta y cuatro minutos'."""
    h, m = (int(x) for x in hhmm.split(":"))
    texto = f"las {letras(h)} horas"
    if m:
        texto += f" y {letras(m)} minutos"
    return texto


def fecha_en_letra(iso: str) -> str:
    """'2026-02-11' → 'once de febrero del dos mil veintiséis'."""
    a, m, d = (int(x) for x in iso.split("-"))
    return f"{letras(d)} de {_MESES_NOMBRE[m]} del {anio_en_letra(a)}"


def fecha_larga(iso: str) -> str:
    """'2026-02-11' → '11 de febrero de 2026' (la celda Fecha del acta va en dígitos)."""
    a, m, d = (int(x) for x in iso.split("-"))
    return f"{d} de {_MESES_NOMBRE[m]} de {a}"


from pathlib import Path

from plenos_informe import PRESIDENCIA, InformePleno, Votacion

PLANTILLAS_DIR = Path(__file__).resolve().parent / "plantillas"
PLANTILLAS = {"ordinaria": "acta_ordinaria.docx",
              "extraordinaria": "acta_extraordinaria.docx"}

HUECO = "___________"

# Índices de las anclas dentro de la plantilla. Las dos plantillas son
# estructuralmente idénticas (9 tablas), así que sirven para ambas.
_T_EXPEDIENTE, _T_DATOS = 1, 2
# La plantilla reparte los puntos en tres bloques —A) PARTE RESOLUTIVA, B) ACTIVIDAD DE
# CONTROL, C) RUEGOS Y PREGUNTAS—, pero el acta que la secretaría firma no los usa:
# numera los puntos como vienen en el orden del día y los escribe seguidos bajo un único
# encabezado. Se reaprovecha la banda de A) como ese encabezado y se eliminan los otros
# dos bloques y sus tablas de contenido.
_T_ENCABEZADO_ORDEN, _T_ORDEN = 3, 4
_T_SOBRANTES = (8, 7, 6, 5)  # de mayor a menor: borrar por índice no desplaza los previos
_FILA_TIPO, _FILA_FECHA, _FILA_DURACION, _FILA_PRESIDENTE = 1, 2, 3, 5

_RESULTADO = {"aprobado": "queda aprobado", "rechazado": "queda rechazado"}

# El párrafo fijo que trae la plantilla, en masculino genérico. Se sustituye por la
# fórmula con el género de quien preside y de quien da fe (ver PRESIDENCIA).
_FORMULA_PLANTILLA = ("Una vez verificada por el Secretario la válida constitución del "
                      "órgano, el Presidente abre sesión, procediendo a la deliberación "
                      "sobre los asuntos incluidos en el Orden del Día")


# ── composición de textos ─────────────────────────────────────────────────────

def _enumerar(elementos: list[str]) -> str:
    """['a', 'b', 'c'] → 'a, b y c'."""
    if len(elementos) == 1:
        return elementos[0]
    return ", ".join(elementos[:-1]) + " y " + elementos[-1]


def _recuento_en_letra(v: Votacion) -> str:
    """Solo los recuentos que constan. Un None es 'no se dijo': darlo por cero
    inventaría un dato (llegó a publicarse 'rechazado, 0 en contra')."""
    partes = []
    if v.a_favor is not None:
        # "uno" se apocopa a "un" delante de un nombre masculino ("un voto",
        # no "uno voto"); letras() no lo sabe porque es un conversor genérico.
        cantidad = "un" if v.a_favor == 1 else letras(v.a_favor)
        partes.append(f"{cantidad} {'voto' if v.a_favor == 1 else 'votos'} a favor")
    if v.en_contra is not None:
        partes.append(f"{letras(v.en_contra)} en contra")
    if v.abstenciones is not None:
        if v.abstenciones == 1:
            partes.append("una abstención")
        else:
            partes.append(f"{letras(v.abstenciones)} abstenciones")
    return _enumerar(partes) if partes else ""


def frase_votacion(v: Votacion | None) -> str:
    """Frase de votación en estilo de acta, con las cifras en letra."""
    if v is None or v.resultado == "sin votación":
        return ""
    if v.resultado == "no consta":
        return "El resultado de la votación no consta en la grabación."
    if v.modalidad == "unanimidad":
        return f"Sometido el asunto a votación, {_RESULTADO[v.resultado]} por unanimidad de los asistentes."
    recuento = _recuento_en_letra(v)
    if recuento:
        return f"Se producen las votaciones con {recuento}. El asunto {_RESULTADO[v.resultado]}."
    return f"Sometido el asunto a votación, {_RESULTADO[v.resultado]}."


def frase_acuerdo(punto) -> str:
    """Cierre de un punto resolutivo. El acta integra el recuento en la propia fórmula
    del acuerdo —"ACUERDA: ..., por tres votos a favor, tres en contra"— en vez de
    añadir una frase de votación aparte, que sonaba a repetición."""
    v = punto.votacion
    acuerdo = (punto.acuerdo or "").strip().rstrip(".")
    if not acuerdo or (v is not None and v.resultado == "rechazado"):
        return frase_votacion(v)
    cabeza = "El Pleno del Ayuntamiento ACUERDA"
    if v is None or v.resultado in ("sin votación", "no consta"):
        return f"{cabeza}, {acuerdo}."
    if v.modalidad == "unanimidad":
        return f"{cabeza} por unanimidad, {acuerdo}."
    recuento = _recuento_en_letra(v)
    frase = f"{cabeza}, {acuerdo}, por {recuento}." if recuento else f"{cabeza}, {acuerdo}."
    if v.voto_de_calidad:
        frase += (f" En virtud de su voto de calidad, {PRESIDENCIA['tratamiento']} "
                  f"resuelve el empate a favor de la propuesta.")
    return frase


def parrafos_apertura(informe: InformePleno) -> list[str]:
    """Encabezado narrativo del acta: dónde y cuándo se reúne el Pleno, quién preside y
    en virtud de qué, quién asiste, y las declaraciones que la Presidencia pronuncia al
    abrir la sesión. Solo nombra a quien la grabación identifica."""
    hora = hora_en_letra(informe.hora_inicio) if informe.hora_inicio else HUECO
    fecha = fecha_larga(informe.fecha_pleno) if informe.fecha_pleno else HUECO
    tipo = informe.tipo_sesion if informe.tipo_sesion != "no consta" else HUECO
    solicitud = (f", a solicitud de los Sres. Concejales {_enumerar(informe.solicitantes)}"
                 if informe.solicitantes else "")
    parrafos = [
        f"En la localidad de Enguídanos siendo {hora} del día {fecha}, se reúnen en el "
        f"Salón de Actos de la Casa Consistorial el Pleno de este Ayuntamiento en sesión "
        f"{tipo}, previamente convocada{solicitud}, bajo la Presidencia de "
        f"{PRESIDENCIA['formula']}.",
    ]

    asistencia = []
    if informe.asistentes:
        asistencia.append(f"Asisten {_enumerar(informe.asistentes)}.")
    if informe.ausentes:
        verbo = "No asisten" if len(informe.ausentes) > 1 else "No asiste"
        asistencia.append(f"{verbo} {_enumerar(informe.ausentes)}, "
                          f"que justifica{'n' if len(informe.ausentes) > 1 else ''} su ausencia.")
    parrafos.append(" ".join(asistencia) if asistencia else HUECO)

    verificacion = (f"Una vez verificada por {PRESIDENCIA['secretaria']} la válida "
                    f"constitución del órgano, {PRESIDENCIA['abre_la_sesion']}")
    if informe.declaraciones_apertura:
        parrafos.append(f"{verificacion} y pronuncia las siguientes palabras:")
        parrafos.extend(informe.declaraciones_apertura)
        parrafos.append("Se procede a la deliberación sobre los asuntos incluidos en el "
                        "Orden del Día.")
    else:
        parrafos.append(f"{verificacion}, procediendo a la deliberación sobre los asuntos "
                        f"incluidos en el Orden del Día.")
    return parrafos


def formula_cierre(informe: InformePleno) -> str:
    """Fórmula final del acta. La plantilla no la trae; el acta real sí."""
    presidente = informe.presidente or HUECO
    hora = hora_en_letra(informe.hora_fin) if informe.hora_fin else HUECO
    fecha = fecha_en_letra(informe.fecha_pleno) if informe.fecha_pleno else HUECO
    # "Secretaria – Interventora" lleva raya (–), no guion, tal como en el acta
    # real firmada: "...lo cual como Secretaria – Interventora, doy fe."
    return (f"Y no habiendo más asuntos que tratar y cumpliendo con el objeto del acto, "
            f"{presidente} levanta la sesión a {hora} del día de hoy, {fecha}, lo cual "
            f"como Secretaria – Interventora, doy fe.")


def _texto_punto(punto) -> list[str]:
    """Un punto del orden del día como lista de párrafos. El modelo separa los bloques
    de debate con una línea en blanco; aquí se convierten en párrafos del documento."""
    numero = f"{punto.numero}º) " if punto.numero is not None else ""
    parrafos = [p.strip() for p in punto.texto.split("\n\n") if p.strip()] or [""]
    parrafos[0] = f"{numero}{punto.titulo}.- {parrafos[0]}"
    frase = frase_acuerdo(punto)
    if frase:
        parrafos.append(frase)
    return parrafos


def _por_orden_del_dia(puntos):
    """Los puntos van como los numera la convocatoria, no agrupados por parte. Los que
    no llevan número (asuntos de urgencia) cierran, en el orden en que se trataron."""
    return sorted(puntos, key=lambda p: (p.numero is None, p.numero or 0))


# ── manipulación del .docx ────────────────────────────────────────────────────

def _escribir(parrafo, texto: str) -> None:
    """Sustituye el texto conservando el formato del primer run."""
    if parrafo.runs:
        parrafo.runs[0].text = texto
        for run in parrafo.runs[1:]:
            run.text = ""
    else:
        parrafo.add_run(texto)


def _poner_celda(celda, texto: str) -> None:
    """Escribe una celda de un solo párrafo, borrando los sobrantes."""
    _escribir(celda.paragraphs[0], texto)
    for extra in celda.paragraphs[1:]:
        extra._element.getparent().remove(extra._element)


def _poner_parrafos(celda, parrafos: list[str]) -> None:
    """Escribe varios párrafos en una celda, tomando el primero como modelo de estilo."""
    modelo = celda.paragraphs[0]
    _escribir(modelo, parrafos[0])
    for extra in celda.paragraphs[1:]:
        extra._element.getparent().remove(extra._element)
    for texto in parrafos[1:]:
        celda.add_paragraph(texto, style=modelo.style)


def _parrafo_con_texto(doc, texto: str):
    """Localiza un párrafo del cuerpo por su contenido. Más robusto que el
    índice: si la plantilla gana un salto de línea, el índice se desplaza."""
    for parrafo in doc.paragraphs:
        if parrafo.text.strip() == texto:
            return parrafo
    raise ValueError(f"la plantilla no contiene el párrafo {texto!r}")


# ── render ────────────────────────────────────────────────────────────────────

def render_acta(informe: InformePleno, ruta_salida: str) -> None:
    """Rellena la plantilla oficial con los datos del informe."""
    from docx import Document

    if informe.tipo_sesion not in PLANTILLAS:
        raise ValueError(
            "no se puede elegir plantilla: el tipo de sesión no consta en la grabación")

    doc = Document(str(PLANTILLAS_DIR / PLANTILLAS[informe.tipo_sesion]))

    # El PLN/2026/N de la plantilla es un número de ejemplo: copiarlo publicaría
    # un expediente falso. Lo rellena la secretaria.
    _poner_celda(doc.tables[_T_EXPEDIENTE].rows[1].cells[0], HUECO)

    datos = doc.tables[_T_DATOS]
    if informe.tipo_sesion == "extraordinaria":
        # Esta celda tiene dos párrafos: 'Extraordinaria' y 'Motivo:'.
        celda = datos.rows[_FILA_TIPO].cells[1]
        motivo = informe.motivo_convocatoria or HUECO
        _escribir(celda.paragraphs[1], f"Motivo: {motivo}")

    if informe.fecha_pleno:
        _poner_celda(datos.rows[_FILA_FECHA].cells[1], fecha_larga(informe.fecha_pleno))
    if informe.hora_inicio and informe.hora_fin:
        _poner_celda(datos.rows[_FILA_DURACION].cells[1],
                     f"Desde las {informe.hora_inicio} hasta las {informe.hora_fin} horas")
    if informe.presidente:
        # La plantilla trae su propio valor de ejemplo en mayúsculas
        # ("LORENA LUJÁN CHUJFI"); el acta real firmada también lo hace
        # ("SERGIO DE FEZ CEREZUELA"). Uniformar el caso del dato del informe
        # con la convención de la celda.
        _poner_celda(datos.rows[_FILA_PRESIDENTE].cells[1], informe.presidente.upper())

    # El hueco de la plantilla es un solo párrafo; el encabezado del acta son varios.
    # El primero reaprovecha ese párrafo (y su estilo) y el resto se inserta detrás,
    # antes de la fórmula fija, que también se reescribe con el género de la Presidencia.
    apertura = parrafos_apertura(informe)
    hueco = _parrafo_con_texto(doc, HUECO)
    _escribir(hueco, apertura[0])
    formula = _parrafo_con_texto(doc, _FORMULA_PLANTILLA)
    for texto in apertura[1:]:
        formula.insert_paragraph_before(texto, style=hueco.style)
    formula._element.getparent().remove(formula._element)

    _poner_celda(doc.tables[_T_ENCABEZADO_ORDEN].rows[0].cells[0], "ORDEN DEL DÍA")
    parrafos = [linea for p in _por_orden_del_dia(informe.orden_del_dia)
                for linea in _texto_punto(p)]
    for bloque in informe.ruegos_y_preguntas:
        parrafos.append(f"Ruegos y preguntas formuladas por {bloque.formulados_por}:")
        parrafos.extend(f"- {p}" for p in bloque.puntos)
    if parrafos:
        _poner_parrafos(doc.tables[_T_ORDEN].rows[0].cells[0], parrafos)
    for indice in _T_SOBRANTES:
        tabla = doc.tables[indice]._element
        tabla.getparent().remove(tabla)

    firma = _parrafo_con_texto(doc, "DOCUMENTO FIRMADO ELECTRÓNICAMENTE")
    firma.insert_paragraph_before(formula_cierre(informe), style=firma.style)

    doc.save(ruta_salida)
