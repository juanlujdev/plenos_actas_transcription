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

from plenos_informe import InformePleno, Votacion

PLANTILLAS_DIR = Path(__file__).resolve().parent / "plantillas"
PLANTILLAS = {"ordinaria": "acta_ordinaria.docx",
              "extraordinaria": "acta_extraordinaria.docx"}

HUECO = "___________"

# Índices de las anclas dentro de la plantilla. Las dos plantillas son
# estructuralmente idénticas (9 tablas), así que sirven para ambas.
_T_EXPEDIENTE, _T_DATOS = 1, 2
_T_RESOLUTIVA, _T_CONTROL, _T_RUEGOS = 4, 6, 8
_FILA_TIPO, _FILA_FECHA, _FILA_DURACION, _FILA_PRESIDENTE = 1, 2, 3, 5

_RESULTADO = {"aprobado": "queda aprobado", "rechazado": "queda rechazado"}


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


def parrafo_apertura(informe: InformePleno) -> str:
    """Narrativa de asistencia. Solo nombra a quien la grabación identifica."""
    partes = []
    if informe.asistentes:
        partes.append(f"Asisten {_enumerar(informe.asistentes)}.")
    if informe.ausentes:
        verbo = "No asisten" if len(informe.ausentes) > 1 else "No asiste"
        partes.append(f"{verbo} {_enumerar(informe.ausentes)}.")
    return " ".join(partes) if partes else HUECO


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
    """Un punto del orden del día como lista de párrafos."""
    numero = f"{punto.numero}º) " if punto.numero is not None else ""
    parrafos = [f"{numero}{punto.titulo}.- {punto.texto}"]
    frase = frase_votacion(punto.votacion)
    if frase:
        parrafos.append(frase)
    return parrafos


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

    _escribir(_parrafo_con_texto(doc, HUECO), parrafo_apertura(informe))

    for indice, parte in ((_T_RESOLUTIVA, "resolutiva"), (_T_CONTROL, "control")):
        puntos = [p for p in informe.orden_del_dia if p.parte == parte]
        if puntos:
            parrafos = [linea for p in puntos for linea in _texto_punto(p)]
            _poner_parrafos(doc.tables[indice].rows[0].cells[0], parrafos)

    if informe.ruegos_y_preguntas:
        parrafos = []
        for bloque in informe.ruegos_y_preguntas:
            parrafos.append(f"Ruegos y preguntas formuladas por {bloque.formulados_por}:")
            parrafos.extend(f"- {p}" for p in bloque.puntos)
        _poner_parrafos(doc.tables[_T_RUEGOS].rows[0].cells[0], parrafos)

    firma = _parrafo_con_texto(doc, "DOCUMENTO FIRMADO ELECTRÓNICAMENTE")
    firma.insert_paragraph_before(formula_cierre(informe), style=firma.style)

    doc.save(ruta_salida)
