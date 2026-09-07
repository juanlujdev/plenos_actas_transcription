#!/usr/bin/env python3
"""
plenos_guia.py - Guía de verificación en HTML: InformePleno + transcripción → .html.

Resuelve un problema muy concreto: la funcionaria del Ayuntamiento tiene que contrastar
el acta contra una grabación de tres horas y media antes de sellarla, y hoy no tiene
forma de saber en qué minuto del vídeo está cada cosa. Verificar una frase dudosa
significa rebuscar por horas — y lo que pasa en la práctica es que no se verifica.

Los datos ya existen: la transcripción lleva marcas [HH:MM:SS], cada votación y cada
punto del orden del día guardan su propio `timestamp`, y cada objeción del auditor trae
una cita literal de la grabación (`Problema.evidencia`). Esta guía solo los compone en
una página. Sin LLM, igual que plenos_acta.py: recibe un InformePleno ya generado y
escribe un documento — coste cero.
"""

import html
import re
import unicodedata
from pathlib import Path

from plenos_acta import fecha_larga

# ══════════════════════════════════════════════════════════════════════════════
# Tiempo y enlaces
# ══════════════════════════════════════════════════════════════════════════════

def segundos(hms: str) -> int:
    """'01:12:04' -> 4324. Devuelve 0 si no parsea.

    Quien llama a esto decide qué hacer con un 0 (normalmente, no generar enlace):
    esta función nunca inventa un tiempo, que en un documento de verificación es peor
    que no tener ninguno."""
    m = re.fullmatch(r"(\d{1,2}):(\d{2}):(\d{2})", (hms or "").strip())
    if not m:
        return 0
    h, minutos, s = (int(x) for x in m.groups())
    return h * 3600 + minutos * 60 + s


def _hms_legible(hms: str) -> str:
    """'01:12:04' -> '1:12:04': sin el cero de relleno de la hora, como se lee un
    minuto de vídeo y no una hora de reloj."""
    try:
        h, m, s = hms.split(":")
        return f"{int(h)}:{m}:{s}"
    except (ValueError, AttributeError):
        return hms


def enlace_video(video_url: str | None, hms: str | None) -> str | None:
    """URL de YouTube que salta a ese segundo, o None si falta alguno de los dos.

    Sin vídeo (el pleno se procesó desde un audio local con --audio) no hay nada a lo
    que enlazar, y sin tiempo tampoco: un enlace al minuto 0 sería peor que ninguno,
    porque parece un dato y no lo es."""
    if not video_url or not hms:
        return None
    separador = "&" if "?" in video_url else "?"
    return f"{video_url}{separador}t={segundos(hms)}s"


# ══════════════════════════════════════════════════════════════════════════════
# Localizar una cita en la transcripción
# ══════════════════════════════════════════════════════════════════════════════

_LINEA = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s*(.*)$")
# El auditor a veces copia la cita con su propia marca de tiempo delante
# ("[01:12:04] Pues bueno, votos a favor."): es ruido para la comparación, no parte
# de lo dicho, así que se recorta antes de buscar.
_PREFIJO_CITA = re.compile(r"^\[\d{2}:\d{2}:\d{2}\]\s*(?:Interviniente\s+\S+:\s*)?")


def _normalizar(texto: str) -> str:
    """Minúsculas, sin acentos, sin signos de puntuación, espacios colapsados. Para
    casar una cita del auditor con la transcripción aunque cambien las comillas, las
    tildes o la puntuación exacta entre una y otra."""
    texto = unicodedata.normalize("NFKD", (texto or "").lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^\w\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _lineas(transcripcion: str) -> list[tuple[str, str]]:
    """[(HH:MM:SS, texto de la línea)] de cada intervención de la transcripción."""
    salida = []
    for linea in transcripcion.splitlines():
        m = _LINEA.match(linea.strip())
        if m:
            salida.append((m.group(1), m.group(2)))
    return salida


# ══════════════════════════════════════════════════════════════════════════════
# Turnos alternos: el mismo chequeo que DIARIZACION le pide al modelo, hecho en
# Python contra la transcripción entera. Es la misma red de seguridad que ya usan
# localizar()/buscar_en_acta() para lo que dice el auditor: no confiar en que el LLM
# aplicó bien su propia regla, comprobarlo contra la fuente.
# ══════════════════════════════════════════════════════════════════════════════

_ETIQUETA_LOCUTOR = re.compile(r"Interviniente\s+(\S+?):")


def _secuencia_etiquetas(transcripcion: str) -> list[str]:
    """Las etiquetas de locutor en el orden en que hablan, colapsando las repeticiones
    consecutivas (la misma etiqueta interviniendo varias veces seguidas cuenta como un
    solo turno): lo que importa para detectar un intercambio es quién toma la palabra
    después de quién, no cuántas líneas ocupa cada intervención."""
    secuencia = []
    for _, texto in _lineas(transcripcion):
        m = _ETIQUETA_LOCUTOR.match(texto.strip())
        if not m:
            continue
        etiqueta = m.group(1)
        if not secuencia or secuencia[-1] != etiqueta:
            secuencia.append(etiqueta)
    return secuencia


def _se_alternan(etiqueta_a: str, etiqueta_b: str, secuencia: list[str]) -> bool:
    """True si `etiqueta_a` y `etiqueta_b` se responden DIRECTAMENTE en algún momento:
    tres turnos seguidos de la forma A, B, A (o B, A, B), sin ningún otro locutor entre
    medias. Se exige la adyacencia real en `secuencia` —no basta con que las dos
    aparezcan en cualquier orden a lo largo de la sesión— para no confundir un
    intercambio de verdad con dos etiquetas que sencillamente hablan cada una en su
    momento, sin relación entre sí, con una tercera intercalada.

    Dos etiquetas que jamás vuelven la una sobre la otra así pueden ser la misma persona
    partida en dos voces por el transcriptor; dos que se responden, no (ver REGLA DE
    TURNOS ALTERNOS en plenos_informe.DIARIZACION — validado contra el pleno del
    2026-09-03, donde las seis etiquetas de la sesión se alternaban entre sí, en tríos
    como este, cientos de veces)."""
    pares = ([etiqueta_a, etiqueta_b, etiqueta_a], [etiqueta_b, etiqueta_a, etiqueta_b])
    return any(secuencia[i:i + 3] in pares for i in range(len(secuencia) - 2))


def conflictos_turnos_alternos(informe, transcripcion: str) -> set[str]:
    """Las etiquetas de `identificacion_locutores` que el mapa identifica como la MISMA
    persona pese a alternar turnos entre sí en la transcripción.

    Se ignoran las que ya llevan uno de los dos valores de escape (`etiqueta con voces
    mezcladas`, `no identificado en la grabación`): esas no afirman ser una persona
    concreta, así que no hay conflicto de identidad que detectar en ellas. Devuelve el
    conjunto de etiquetas implicadas, no pares, porque una misma etiqueta puede
    alternar con más de una."""
    voces = [v for v in informe.identificacion_locutores
             if v.persona not in (_VOZ_MEZCLADA, _VOZ_NO_IDENTIFICADA)]
    secuencia = _secuencia_etiquetas(transcripcion)
    conflictivas: set[str] = set()
    for i, v1 in enumerate(voces):
        for v2 in voces[i + 1:]:
            if v1.persona == v2.persona and _se_alternan(v1.etiqueta, v2.etiqueta, secuencia):
                conflictivas.add(v1.etiqueta)
                conflictivas.add(v2.etiqueta)
    return conflictivas


def localizar(cita: str, transcripcion: str) -> str | None:
    """Busca `cita` en la transcripción y devuelve el 'HH:MM:SS' de la intervención
    donde aparece, o None si no la encuentra. Nunca inventa un tiempo: en un
    documento de verificación, un minuto equivocado es peor que ninguno.

    Cascada, de más a menos exigente:
    1. la cita tal cual, como subcadena de la línea;
    2. la cita normalizada (minúsculas, sin acentos, sin puntuación, espacios
       colapsados), para sobrevivir a los cambios de forma que introducen el modelo
       o la propia transcripción automática;
    3. un fragmento de 6 a 8 palabras seguidas de la cita (probando primero el más
       largo en caracteres, que es el que menos probablemente case por casualidad),
       para cuando el modelo parafrasea ligeramente al citar.
    """
    cita = _PREFIJO_CITA.sub("", (cita or "").strip()).strip()
    if not cita or not transcripcion:
        return None
    lineas = _lineas(transcripcion)
    if not lineas:
        return None

    for hms, texto in lineas:
        if cita in texto:
            return hms

    cita_norm = _normalizar(cita)
    if not cita_norm:
        return None
    lineas_norm = [(hms, _normalizar(texto)) for hms, texto in lineas]
    for hms, texto in lineas_norm:
        if cita_norm in texto:
            return hms

    palabras = cita_norm.split()
    for ancho in (8, 7, 6):
        if len(palabras) < ancho:
            continue
        ventanas = (" ".join(palabras[i:i + ancho])
                    for i in range(len(palabras) - ancho + 1))
        for frag in sorted(ventanas, key=len, reverse=True):
            for hms, texto in lineas_norm:
                if frag in texto:
                    return hms
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Objeciones del auditor, en términos que entienda la funcionaria
# ══════════════════════════════════════════════════════════════════════════════

def _numero_citado(seccion: str) -> int | None:
    """El número de punto que menciona `seccion` ('Punto 3', '3º'...), o None.

    Los números entre corchetes ('orden_del_dia[2]') se ignoran a propósito: son el
    índice de la lista en el JSON, no el número del punto en el acta, y confundirlos
    apuntaría al punto equivocado."""
    sin_indices = re.sub(r"\[\d+\]", "", seccion or "")
    m = re.search(r"\d+", sin_indices)
    return int(m.group()) if m else None


def _punto_de(seccion: str, informe):
    """El PuntoOrdenDia cuya sección casa con `seccion`, por número o por título; None
    si no se puede identificar ninguno.

    Es la vía de siempre, para cuando el auditor ya escribe la sección en prosa
    ("Punto 3", un título literal). Las rutas internas del programa
    ("orden_del_dia[2].texto") las traduce `_ruta_legible`, más abajo."""
    numero = _numero_citado(seccion)
    if numero is not None:
        for punto in informe.orden_del_dia:
            if punto.numero == numero:
                return punto
    seccion_norm = _normalizar(seccion or "")
    if seccion_norm:
        for punto in informe.orden_del_dia:
            titulo_norm = _normalizar(punto.titulo)
            if titulo_norm and titulo_norm in seccion_norm:
                return punto
    return None


def _titulo_punto(punto) -> str:
    """'Punto 3º) TÍTULO', con el mismo formato que usa el documento
    (`plenos_acta.render_acta` numera igual: '2º) TÍTULO.'). Sin número, un guion en su
    lugar: no se inventa uno."""
    numero = f"{punto.numero}º" if punto.numero is not None else "—"
    return f"Punto {numero}) {punto.titulo}"


def _punto_ruegos_y_preguntas(informe):
    """El PuntoOrdenDia 'RUEGOS Y PREGUNTAS' si el orden del día lo trae numerado como
    punto propio (lo habitual: suele ser el último); None si no aparece así, en cuyo
    caso el turno de ruegos no tiene número de punto que anteponer."""
    for punto in informe.orden_del_dia:
        if _normalizar(punto.titulo) == "ruegos y preguntas":
            return punto
    return None


# Sufijo en cristiano según en qué parte del punto está la afirmación dudosa. Solo
# cubre lo que puede señalar el auditor dentro de un PuntoOrdenDia: no hay sufijo para
# 'numero' porque ya va dentro del propio "Punto Nº)".
_SUFIJOS_CAMPO = {
    "texto": "en el relato del debate",
    "acuerdo": "en el acuerdo",
    "titulo": "en el título",
}

# Campos de InformePleno que no son el orden del día ni los ruegos, traducidos a
# lenguaje llano. Si el auditor señala uno de estos a secas (sin índice ni sufijo), esto
# basta; si viene con algo más raro detrás, `_ruta_legible` prefiere no inventar.
_CAMPOS_INFORME = {
    "asistentes": "Lista de asistentes",
    "ausentes": "Lista de ausentes",
    "presidente": "Quién preside",
    "hora_inicio": "Hora de inicio",
    "hora_fin": "Hora de fin",
    "fecha_pleno": "Fecha del pleno",
    "tipo_sesion": "Tipo de sesión",
    "declaraciones_apertura": "Declaraciones de apertura",
    "motivo_convocatoria": "Motivo de la convocatoria",
    "solicitantes": "Solicitantes de la convocatoria",
    "resumen_corto": "Resumen para la web",
}

# Ruta interna tipo 'orden_del_dia[2].texto' o 'ruegos_y_preguntas[2]': raíz, índice
# opcional entre corchetes, resto opcional tras un punto. Una sección que ya viene en
# prosa ("Punto 3", un título) nunca casa entera con esto, así que sigue la vía antigua
# de _punto_de sin que este patrón interfiera.
_RUTA_CAMPO = re.compile(r"^(\w+)(?:\[(\d+)\])?(?:\.(.+))?$")


def _sufijo_campo(resto: str | None) -> str | None:
    """La parte del punto donde está la afirmación dudosa, en cristiano: '.texto' es el
    relato del debate, '.votacion' o '.votacion.algo-mas' es la votación. None si el
    resto no dice nada traducible (o no hay resto)."""
    if not resto:
        return None
    raiz = re.sub(r"\[\d+\]$", "", resto.split(".")[0])
    if raiz == "votacion":
        return "en la votación"
    return _SUFIJOS_CAMPO.get(raiz)


def _ruta_legible(seccion: str, informe) -> tuple[str | None, object | None]:
    """Traduce una ruta interna del programa ('orden_del_dia[2].texto',
    'ruegos_y_preguntas[2]', 'asistentes'...) al lenguaje del acta, para que la
    funcionaria pueda buscarlo tal cual. Devuelve (texto, punto): `punto` es el
    PuntoOrdenDia asociado si lo hay, para que la cascada de tiempos de
    `objecion_legible` lo siga aprovechando.

    (None, None) si `seccion` no tiene forma de ruta (es prosa — la resuelve
    `_punto_de`, no esta función) o si la traducción no es segura: un índice fuera de
    rango (el modelo puede citar mal el suyo) o una raíz que no se reconoce. Perder la
    ruta cruda sería peor que no traducirla, así que ante la duda no se inventa nada y
    quien llama la deja tal cual."""
    m = _RUTA_CAMPO.match((seccion or "").strip())
    if not m:
        return None, None
    raiz, indice, resto = m.groups()

    if raiz == "orden_del_dia":
        if indice is None:
            return None, None
        idx = int(indice)
        if not (0 <= idx < len(informe.orden_del_dia)):
            return None, None
        punto = informe.orden_del_dia[idx]
        base = _titulo_punto(punto)
        sufijo = _sufijo_campo(resto)
        return (f"{base} — {sufijo}" if sufijo else base), punto

    if raiz == "ruegos_y_preguntas":
        punto_ryp = _punto_ruegos_y_preguntas(informe)
        base = _titulo_punto(punto_ryp) if punto_ryp is not None else "RUEGOS Y PREGUNTAS"
        if indice is None:
            return base, punto_ryp
        idx = int(indice)
        if not (0 <= idx < len(informe.ruegos_y_preguntas)):
            return None, None
        return f"{base} — intervención {idx + 1}", punto_ryp

    if raiz == "identificacion_locutores":
        # El auditor revisa el mapa de voces (ver DIARIZACION en plenos_informe), así que
        # objeta aquí a menudo. Se nombra por la etiqueta, que es lo que la funcionaria ve
        # en la primera sección de esta misma guía, no por el índice de la lista.
        if indice is None:
            return "Mapa de voces", None
        idx = int(indice)
        if not (0 <= idx < len(informe.identificacion_locutores)):
            return None, None
        return f"Mapa de voces — etiqueta {informe.identificacion_locutores[idx].etiqueta}", None

    if raiz in _CAMPOS_INFORME and indice is None and resto is None:
        return _CAMPOS_INFORME[raiz], None

    return None, None


# Marca "[HH:MM:SS] Interviniente X: " de la transcripción automática: es ruido para la
# funcionaria (el tiempo ya se muestra aparte, en su propia línea con el enlace). El
# separador "[...]" que el auditor mete para indicar un salto entre dos citas no lleva
# dígitos y este patrón no lo toca, así que se conserva.
_MARCA_TIEMPO_LOCUTOR = re.compile(r"\[\d{2}:\d{2}:\d{2}\]\s*(?:Interviniente\s+\S+:\s*)?")


def _limpiar_evidencia(texto: str | None) -> str | None:
    """La cita de la transcripción sin las marcas [HH:MM:SS] ni 'Interviniente X:',
    dejando solo lo que se dijo. Los '[...]' que marcan un salto entre citas se
    conservan tal cual."""
    if not texto:
        return texto
    limpio = _MARCA_TIEMPO_LOCUTOR.sub("", texto)
    return re.sub(r"[ \t]+", " ", limpio).strip()


# ══════════════════════════════════════════════════════════════════════════════
# La frase literal que pegar en el buscador de Word (buscar_en_acta)
# ══════════════════════════════════════════════════════════════════════════════
# `afirmacion_dudosa` es la DESCRIPCIÓN que hace el auditor de lo que dice el acta, no
# la frase tal cual: una funcionaria que la pega en el buscador de Word no encuentra
# nada. `buscar_en_acta` reconstruye, verificando siempre contra el texto real del
# informe, la frase que sí puede pegar.

_COMILLAS = re.compile(r'[«"“]([^»"”]+)[»"”]')


def _fragmentos_citados(texto: str) -> list[str]:
    """Los fragmentos entre comillas (rectas, angulares o tipográficas) de `texto`, en
    el orden en que aparecen. El auditor suele citar así, dentro de `afirmacion_dudosa`,
    el trozo literal del acta que respalda su duda."""
    return [f.strip() for f in _COMILLAS.findall(texto or "") if f.strip()]


def _palabras_significativas(texto: str) -> set[str]:
    """Palabras de cinco letras o más, normalizadas (ver `_normalizar`): las que de
    verdad distinguen una frase de otra. Las cortas (artículos, preposiciones) sobran
    para decidir cuál es 'la misma frase que la duda' y solo añaden ruido."""
    return {w for w in _normalizar(texto).split() if len(w) >= 5}


_FIN_FRASE = re.compile(r"(?<=[.!?])\s+")

# Tratamientos que un acta municipal abrevia con punto y que, sin protegerlos, se
# confunden con un punto y final ("La Sra. Teniente de Alcalde..." se trocearía en "La
# Sra." + "Teniente de Alcalde..."): son justo los que más aparecen en este dominio
# (ver CORPORACION y PRESIDENCIA en plenos_informe.py). Ceiling reconocido: una
# abreviatura nueva que no esté en esta lista se sigue troceando mal; se añade aquí si
# aparece.
_ABREVIATURAS = re.compile(r"\b(D|Dª|Dna|Sr|Sra|Srta|Excmo|Excma|Ilmo|Ilma)\.",
                           re.IGNORECASE)
_MARCA_PUNTO_PROTEGIDO = "￼"  # carácter que no aparece en prosa real


def _frases(texto: str) -> list[str]:
    """Trocea un texto del informe en frases. Naive a propósito más allá de las
    abreviaturas de tratamiento que protege `_ABREVIATURAS` (no distingue, por ejemplo,
    un número decimal de un punto y final): esto es una ayuda para buscar, no un
    analizador lingüístico, y una frase de más o de menos no rompe nada — el resultado
    sigue siendo un fragmento literal del informe."""
    frases = []
    for parrafo in (texto or "").split("\n"):
        protegido = _ABREVIATURAS.sub(lambda m: m.group(1) + _MARCA_PUNTO_PROTEGIDO, parrafo)
        for f in _FIN_FRASE.split(protegido):
            f = f.replace(_MARCA_PUNTO_PROTEGIDO, ".").strip()
            if f:
                frases.append(f)
    return frases


def _mejor_frase(afirmacion: str, candidatas: list[str]) -> str | None:
    """La frase que más comparte con `afirmacion_dudosa`, puntuando por la PROPORCIÓN de
    palabras significativas de la frase candidata que aparecen en la duda — no el
    recuento bruto. El recuento bruto premia frases largas que solo comparten un par de
    palabras por casualidad (p.ej. el nombre de alguien que también sale, sin relación,
    en otra frase) por encima de la frase corta que trata exactamente lo mismo.

    El umbral (al menos tres palabras comunes y la mitad o más de las de la candidata)
    se aplica ANTES de comparar, no después sobre la mejor puntuación global: si no, una
    frase corta y de puntuación perfecta pero con una sola palabra en común (p.ej. "El
    concejal D.", tras el troceo) gana la comparación y luego la descarta el umbral,
    dejando sin ofrecer una frase más larga que sí lo cumplía de sobra."""
    objetivo = _palabras_significativas(afirmacion)
    if not objetivo:
        return None
    mejor, mejor_puntuacion = None, (0.0, 0)
    for candidata in candidatas:
        palabras = _palabras_significativas(candidata)
        if not palabras:
            continue
        comunes = len(palabras & objetivo)
        if comunes < 3:
            continue
        ratio = comunes / len(palabras)
        if ratio < 0.5:
            continue
        puntuacion = (ratio, comunes)
        if puntuacion > mejor_puntuacion:
            mejor, mejor_puntuacion = candidata, puntuacion
    return mejor


def _textos_candidatos(seccion: str, informe) -> list[str]:
    """Los textos reales del informe a los que `seccion` puede estar apuntando: la
    fuente de verdad de `buscar_en_acta`. Nunca se devuelve nada que no esté aquí tal
    cual — ofrecerle a la funcionaria una frase que no existe en el informe sería el
    mismo fallo que se quiere arreglar, solo que con una frase inventada en vez de con
    una ruta interna.

    Mismo parseo de `seccion` que `_ruta_legible`, pero en vez del texto para pantalla
    devuelve el contenido real del campo."""
    m = _RUTA_CAMPO.match((seccion or "").strip())
    if m:
        raiz, indice, resto = m.groups()
        if raiz == "orden_del_dia" and indice is not None:
            idx = int(indice)
            if 0 <= idx < len(informe.orden_del_dia):
                punto = informe.orden_del_dia[idx]
                campo = re.sub(r"\[\d+\]$", "", resto.split(".")[0]) if resto else "texto"
                if campo == "titulo":
                    return [punto.titulo] if punto.titulo else []
                if campo == "acuerdo":
                    return [punto.acuerdo] if punto.acuerdo else []
                # 'texto', 'votacion' (que no tiene texto libre propio) o cualquier otro
                # sufijo: la prosa del debate es lo único con frases literales que pegar.
                return [punto.texto] if punto.texto else []
        if raiz == "ruegos_y_preguntas" and indice is not None:
            idx = int(indice)
            if 0 <= idx < len(informe.ruegos_y_preguntas):
                bloque = informe.ruegos_y_preguntas[idx]
                # `formulados_por` primero: cuando la duda es sobre QUIÉN habla (el caso
                # real que motivó esto), es la candidata que gana por proporción de
                # palabras compartidas, no por ir primera — el orden aquí solo importa
                # para _fragmentos_citados, que se queda con la primera que case.
                return [bloque.formulados_por, *bloque.puntos]
        if raiz in _CAMPOS_INFORME and indice is None and resto is None:
            valor = getattr(informe, raiz, None)
            if isinstance(valor, list):
                return [v for v in valor if v]
            return [valor] if valor else []
    punto = _punto_de(seccion, informe)
    if punto is not None and punto.texto:
        return [punto.texto]
    return []


def buscar_en_acta(problema, informe) -> str | None:
    """La frase LITERAL del acta que la funcionaria puede pegar en el buscador de Word
    para localizar la duda del auditor. Cascada, verificando siempre contra el texto
    real del informe:

    1. Un fragmento citado entre comillas en `afirmacion_dudosa` (el auditor suele citar
       así el trozo literal): el primero que aparezca tal cual en el informe.
    2. Si no hay ninguno así, la frase del informe que más comparte con la duda
       (`_mejor_frase`).
    3. `None` si ninguna de las dos da algo con confianza: no se inventa una frase."""
    textos = _textos_candidatos(problema.seccion, informe)
    if not textos:
        return None
    for fragmento in _fragmentos_citados(problema.afirmacion_dudosa):
        for texto in textos:
            if fragmento in texto:
                return fragmento
    frases = [f for texto in textos for f in _frases(texto)]
    return _mejor_frase(problema.afirmacion_dudosa, frases)


def objecion_legible(problema, informe, transcripcion: str, video_url: str | None) -> dict:
    """Una objeción del auditor (`Problema`) en términos que entienda la funcionaria,
    con el minuto de la grabación en el que comprobarla.

    `problema.seccion` puede llegar como una ruta interna del JSON ('orden_del_dia[2].
    texto') o ya en prosa ('Punto 3', un título): `_ruta_legible` prueba primero la
    ruta, y solo si no la reconoce se prueba el casado en prosa de siempre.

    Cascada de tiempos, de más a menos preciso: la cita literal localizada en la
    transcripción, luego el timestamp de la votación del punto identificado, luego el
    del propio punto. `hms` (y por tanto `enlace`) quedan en None si ninguno de los
    tres da un dato: no se inventa un minuto.

    `buscar` (ver `buscar_en_acta`) es la frase literal del INFORME que se puede pegar
    en el buscador de Word — a diferencia de `dice` (`afirmacion_dudosa`), que es la
    descripción que hace el auditor y casi nunca aparece tal cual en el documento."""
    donde, punto = _ruta_legible(problema.seccion, informe)
    if donde is None:
        punto = _punto_de(problema.seccion, informe)
        if punto is not None:
            donde = (f"Punto {punto.numero} — {punto.titulo}" if punto.numero is not None
                     else f"Punto — {punto.titulo}")
        else:
            donde = problema.seccion

    hms = localizar(problema.evidencia, transcripcion)
    if hms is None and punto is not None and getattr(punto, "votacion", None) is not None:
        hms = punto.votacion.timestamp
    if hms is None and punto is not None:
        hms = punto.timestamp

    return {
        "donde": donde,
        "dice": problema.afirmacion_dudosa,
        "motivo": problema.motivo,
        "se_oye": _limpiar_evidencia(problema.evidencia) or None,
        "hms": hms,
        "enlace": enlace_video(video_url, hms),
        "buscar": buscar_en_acta(problema, informe),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Aviso "COMPROBAR ANTES DE SELLAR.txt"
# ══════════════════════════════════════════════════════════════════════════════
# Vive aquí y no en asistente_plenos.py porque depende del mismo formato de objeción
# que produce objecion_legible (donde/dice/motivo/se_oye/hms/enlace), y porque
# procesar_pleno._componer_guia —que corre también en --rehacer-acta, sin pasar por
# el asistente— necesita poder escribirlo junto con la guía HTML para que los dos
# ficheros (y el acta) cuenten siempre lo mismo.

def _avisos_legibles(pendientes: list, objeciones: tuple) -> list[dict]:
    """`objeciones` (de objecion_legible: donde/dice/motivo/se_oye/hms/enlace/buscar) si
    las hay; si no, las reconstruye a partir de `pendientes` con los tres datos de
    siempre y sin cita, minuto ni frase para buscar.

    Hace falta el segundo camino porque `objeciones` puede venir vacía aunque
    `pendientes` no: un pleno regenerado con datos de antes de que existiera la
    guía, o una corrida donde la guía no se pudo componer. En los dos casos hay
    algo que avisar, y perder el aviso por un cambio de formato sería peor que
    mostrarlo sin cita ni minuto."""
    if objeciones:
        return list(objeciones)
    return [{"donde": p.seccion, "dice": p.afirmacion_dudosa, "motivo": p.motivo,
             "se_oye": None, "hms": None, "enlace": None, "buscar": None} for p in pendientes]


def _lineas_aviso(numero: int, aviso: dict, con_enlace: bool) -> list[str]:
    """Las líneas de un aviso, para la pantalla o para el fichero.

    `se_oye`, el minuto y `buscar` solo se imprimen si el dato existe: no se inventa
    nada, y dejar una línea a medias sería peor que no ponerla. `con_enlace` decide si
    se escribe la dirección completa del vídeo (el fichero, que se lee en el
    ordenador y esa dirección se puede pegar en el navegador) o solo el minuto en
    texto (la pantalla, donde un enlace no se puede pulsar de todos modos)."""
    lineas = [f" {numero}. {aviso['donde']}",
              f"    El acta dice:   \"{aviso['dice']}\""]
    if aviso.get("buscar"):
        # La frase LITERAL del informe, para pegar en el buscador de Word: a diferencia
        # de la línea de arriba (la descripción del auditor), esta sí se encuentra tal
        # cual en el documento.
        lineas.append(f"    Búscalo en el acta:  «{aviso['buscar']}»")
    lineas.append(f"    Por qué dudo:   {aviso['motivo']}")
    if aviso.get("se_oye"):
        lineas.append(f"    Se oye:         \"{aviso['se_oye']}\"")
    if aviso.get("hms"):
        minuto = _hms_legible(aviso["hms"])
        lineas.append(f"    Compruébalo en el vídeo, minuto {minuto}")
        if con_enlace and aviso.get("enlace"):
            lineas.append(f"    {aviso['enlace']}")
    lineas.append("")
    return lineas


def texto_comprobaciones(fecha: str, pendientes: list, objeciones: tuple = ()) -> str:
    """La lista de objeciones del auditor, en cristiano, con la cita literal y el
    minuto de la grabación cuando se conocen (ver _avisos_legibles)."""
    avisos = _avisos_legibles(pendientes, objeciones)
    lineas = [
        "PUNTOS QUE CONVIENE COMPROBAR CONTRA LA GRABACIÓN",
        f"Pleno del {fecha_larga(fecha)}",
        "",
        f"El programa ha redactado el acta, pero estas {len(avisos)} frases no ha",
        "podido confirmarlas del todo. Escucha esos momentos de la grabación",
        "y corrígelas en el documento si hace falta.",
        "",
    ]
    for i, aviso in enumerate(avisos, 1):
        lineas += _lineas_aviso(i, aviso, con_enlace=True)
    return "\n".join(lineas)


def escribir_comprobaciones(carpeta: Path, fecha: str, pendientes: list,
                            objeciones: tuple = ()) -> Path | None:
    """Guarda esa lista junto al acta. Sin esto vive solo en una consola que ella
    va a cerrar, y la necesita justo después, con el documento abierto en Word.
    Si no hay objeciones no se crea: su ausencia ya dice que no hay nada pendiente."""
    ruta = carpeta / "COMPROBAR ANTES DE SELLAR.txt"
    if not pendientes:
        # Al reprocesar una fecha, el aviso de la vez anterior seguiría ahí contradiciendo
        # a la pantalla, que acaba de decir que no hay nada que comprobar.
        ruta.unlink(missing_ok=True)
        return None
    ruta.write_text(texto_comprobaciones(fecha, pendientes, objeciones), encoding="utf-8")
    return ruta


# ══════════════════════════════════════════════════════════════════════════════
# HTML
# ══════════════════════════════════════════════════════════════════════════════

_CSS = """
:root { color-scheme: light dark; }
body {
  font-family: system-ui, -apple-system, "Segoe UI", Arial, sans-serif;
  line-height: 1.5; max-width: 860px; margin: 0 auto; padding: 24px 20px 60px;
  color: #1a1a1a; background: #fff;
}
h1 { font-size: 1.5rem; margin: 0 0 4px; }
h2 { font-size: 1.15rem; }
.fecha { color: #555; margin-top: 0; margin-bottom: 24px; }
header.aviso {
  background: #fff3cd; border: 1px solid #e0a800; border-radius: 6px;
  padding: 12px 16px; margin-bottom: 24px;
}
header.aviso p { margin: 0; }
section.objeciones {
  background: #fdecea; border: 1px solid #e2a3a0; border-radius: 6px;
  padding: 8px 20px 16px; margin-bottom: 32px;
}
section.objeciones h2 { color: #a02622; }
.objecion { border-top: 1px solid #f0c4c0; padding: 12px 0; }
.objecion:first-of-type { border-top: none; }
.objecion p { margin: 4px 0; }
.objecion-donde { font-weight: bold; }
section.mapa-voces {
  background: #e8f0fe; border: 1px solid #a9c6f5; border-radius: 6px;
  padding: 8px 20px 16px; margin-bottom: 32px;
}
section.mapa-voces h2 { color: #1a4fa0; }
.voz { border-top: 1px solid #cfe0fb; padding: 12px 0; }
.voz:first-of-type { border-top: none; }
.voz p { margin: 4px 0; }
.voz-etiqueta { font-weight: bold; }
/* Voz mezclada: la más grave de las tres — puede haber puesto palabras de un vecino en
   boca de una concejala —, con borde de acento para que resalte incluso en un vistazo
   rápido a la lista. Voz sin identificar: un hueco honesto, aviso más discreto. */
.voz-alerta {
  background: #fdecea; border-left: 4px solid #a02622; border-radius: 4px;
  padding: 8px 10px 8px 14px; margin: 6px 0;
}
.voz-alerta .voz-aviso { color: #a02622; font-weight: bold; }
.voz-aviso-leve { background: #fff8e1; border-radius: 4px; padding: 8px 10px; margin: 6px 0; }
.voz-aviso-leve .voz-aviso { color: #8a6d1a; font-weight: normal; }
.objecion code {
  background: rgba(0,0,0,.06); padding: 1px 5px; border-radius: 3px;
  user-select: all;
}
.punto { border-top: 1px solid #ddd; padding: 16px 0; }
.punto h3 { margin: 0 0 6px; }
.punto p { margin: 4px 0; }
.acuerdo { font-style: italic; }
.enlace {
  display: inline-block; background: #1565c0; color: #fff; text-decoration: none;
  padding: 4px 10px; border-radius: 4px; font-size: .9rem;
}
.enlace:hover { background: #0d47a1; }
.tiempo { color: #555; font-size: .9rem; }
@media print {
  header.aviso { background: none; border: 2px solid #000; }
  section.objeciones { background: none; border: 2px solid #a02622; }
  .enlace { background: none; color: #1565c0; padding: 0; text-decoration: underline; }
}
@media (prefers-color-scheme: dark) {
  body { background: #1b1b1b; color: #eee; }
  header.aviso { background: #3a2f00; border-color: #a97400; }
  section.objeciones { background: #3a1a1a; border-color: #8a3a3a; }
  section.objeciones h2 { color: #ff8a80; }
  section.mapa-voces { background: #10233d; border-color: #2d5a94; }
  section.mapa-voces h2 { color: #8ab4f8; }
  .voz { border-color: #24406b; }
  .voz-alerta { background: #3a1a1a; border-left-color: #ff8a80; }
  .voz-alerta .voz-aviso { color: #ff8a80; }
  .voz-aviso-leve { background: #3a2f00; }
  .voz-aviso-leve .voz-aviso { color: #e0c46a; }
  .punto { border-color: #444; }
  .enlace { background: #4a90d9; }
  .tiempo { color: #aaa; }
  .objecion code { background: rgba(255,255,255,.12); }
}
"""


def _html_tiempo(hms: str | None, video_url: str | None,
                 prefijo: str = "▶ Ver en el vídeo") -> str:
    """Un enlace al minuto si hay vídeo y tiempo; el tiempo en texto si solo hay
    tiempo (audio local, sin URL); nada si ni siquiera eso consta."""
    if not hms:
        return ""
    legible = _hms_legible(hms)
    url = enlace_video(video_url, hms)
    if url:
        return (f'<a class="enlace" href="{html.escape(url)}" target="_blank" '
                f'rel="noopener">{html.escape(prefijo)} ({html.escape(legible)})</a>')
    return f'<span class="tiempo">Minuto {html.escape(legible)} de la grabación</span>'


def _resultado_legible(v) -> str | None:
    """Frase corta del resultado de la votación de un punto, con el recuento si
    consta. None si el punto no llegó a votarse (o no se sometió a votación)."""
    if v is None or v.resultado == "sin votación":
        return None
    if v.resultado == "no consta":
        return "El resultado de la votación no consta en la grabación."
    texto = "Aprobado" if v.resultado == "aprobado" else "Rechazado"
    if v.modalidad == "unanimidad":
        return f"{texto} por unanimidad."
    recuento = []
    if v.a_favor is not None:
        recuento.append(f"{v.a_favor} a favor")
    if v.en_contra is not None:
        recuento.append(f"{v.en_contra} en contra")
    if v.abstenciones is not None:
        recuento.append(f"{v.abstenciones} abstenciones")
    return f"{texto} ({', '.join(recuento)})." if recuento else f"{texto}."


def _bloque_objecion(o: dict, video_url: str | None) -> str:
    tiempo = _html_tiempo(o["hms"], video_url)
    se_oye = (f'<p><strong>Se oye en la grabación:</strong> «{html.escape(o["se_oye"])}»</p>'
              if o["se_oye"] else "")
    # La frase LITERAL del informe (a diferencia de "Dice el acta", que es la
    # descripción del auditor): en <code>, seleccionable de un clic (user-select:all)
    # para pegarla directa en el buscador de Word.
    buscar = (f'<p><strong>Búscalo en el acta:</strong> <code>{html.escape(o["buscar"])}</code></p>'
              if o.get("buscar") else "")
    return f"""    <li class="objecion">
      <p class="objecion-donde">{html.escape(o["donde"])}</p>
      <p><strong>Dice el acta:</strong> {html.escape(o["dice"])}</p>
      {buscar}
      <p><strong>Por qué se duda:</strong> {html.escape(o["motivo"])}</p>
      {se_oye}
      {f'<p>{tiempo}</p>' if tiempo else ""}
    </li>"""


def _bloque_punto(punto, video_url: str | None) -> str:
    numero = f"{punto.numero}º" if punto.numero is not None else "—"
    acuerdo = (f'<p class="acuerdo"><strong>Acuerdo:</strong> {html.escape(punto.acuerdo)}</p>'
               if punto.acuerdo else "")
    resultado = _resultado_legible(punto.votacion)
    resultado_html = f'<p class="resultado">{html.escape(resultado)}</p>' if resultado else ""
    tiempo = _html_tiempo(punto.timestamp, video_url)
    return f"""  <div class="punto">
    <h3>{html.escape(numero)}) {html.escape(punto.titulo)}</h3>
    {acuerdo}
    {resultado_html}
    {f'<p>{tiempo}</p>' if tiempo else ""}
  </div>"""


# Los dos valores de escape de `VozIdentificada.persona` que NO son un nombre (ver
# DIARIZACION y VozIdentificada en plenos_informe.py). La funcionaria no tiene por qué
# saber qué significan tal cual salen del JSON, así que se traducen a una frase.
_VOZ_MEZCLADA = "etiqueta con voces mezcladas"
_VOZ_NO_IDENTIFICADA = "no identificado en la grabación"


def _aviso_voz(persona: str) -> str | None:
    """La frase que le explica a la funcionaria por qué esta voz necesita comprobarse
    en el vídeo, o None si `persona` es un nombre identificado con normalidad y no hace
    falta ningún aviso.

    Los dos casos no son el mismo problema: una etiqueta "no identificada" es una voz
    que nunca se identificó (recuperable: sencillamente no se le pone nombre); una
    etiqueta "con voces mezcladas" es el transcriptor fusionando a DOS personas
    distintas bajo la misma etiqueta — el fallo real del pleno del 3 de septiembre de
    2026, en el que unos ruegos de una vecina acabaron atribuidos a la Teniente de
    Alcalde. Se avisa distinto para que la funcionaria sepa qué está comprobando."""
    if persona == _VOZ_MEZCLADA:
        return ("⚠ El transcriptor ha mezclado aquí a DOS PERSONAS DISTINTAS bajo la "
                "misma voz: no te fíes de lo que el acta le atribuya sin comprobarlo en "
                "el vídeo, porque puede que la intervención sea de otra persona.")
    if persona == _VOZ_NO_IDENTIFICADA:
        return ("El transcriptor no ha podido separar bien esta voz de las demás: "
                "conviene comprobar sus intervenciones en el vídeo.")
    return None


def _etiqueta_evidencia(persona: str) -> str:
    """La frase que antecede a la cita de `evidencia`. "Se identifica porque:" no tiene
    sentido delante de una voz que no se ha identificado, y menos delante de una que
    mezcla a dos personas — son problemas distintos, no la misma frase con otro nombre
    detrás, y la funcionaria necesita saber cuál de los tres está leyendo antes de leer
    la cita."""
    if persona == _VOZ_MEZCLADA:
        return "Aquí el transcriptor ha mezclado a dos personas:"
    if persona == _VOZ_NO_IDENTIFICADA:
        return "No se ha podido saber quién es:"
    return "Se identifica porque:"


def _aviso_conflicto(persona: str) -> str:
    """La frase para una etiqueta identificada con normalidad (un nombre, no uno de los
    valores de escape) que además figura en `conflictos_turnos_alternos`: el mapa le da
    la misma persona que a otra etiqueta con la que se alterna en la grabación, y la
    REGLA DE TURNOS ALTERNOS dice que dos etiquetas que se responden no pueden ser la
    misma persona. Mismo peso visual que la voz mezclada (`voz-alerta`): las dos son un
    error de identidad en el mapa, no un hueco honesto sin identificar."""
    return (f"⚠ Esta etiqueta se identifica aquí como {persona}, la misma persona que "
            "otra etiqueta distinta del mapa — pero las dos se responden entre sí en la "
            "grabación, y dos voces que se alternan no pueden ser la misma persona. "
            "Comprueba estas intervenciones en el vídeo antes de dar la identificación "
            "por buena.")


def _bloque_voz(voz, video_url: str | None, conflicto: bool = False) -> str:
    tiempo = _html_tiempo(voz.timestamp, video_url)
    # `conflicto` solo llega True para una etiqueta identificada con normalidad (ver
    # conflictos_turnos_alternos: excluye ya los dos valores de escape), así que aquí
    # nunca compite con el aviso de voz mezclada o sin identificar — son excluyentes.
    aviso = _aviso_conflicto(voz.persona) if conflicto else _aviso_voz(voz.persona)
    etiqueta_evidencia = _etiqueta_evidencia(voz.persona)
    # Tres pesos visuales, no dos: la voz mezclada y el conflicto de turnos alternos son
    # los dos más graves —pueden haber puesto en boca de una persona lo que dijo otra—
    # y tienen que distinguirse de un vistazo de una voz simplemente sin identificar,
    # que es un hueco honesto y no un error de atribución.
    if voz.persona == _VOZ_MEZCLADA or conflicto:
        clase = "voz voz-alerta"
    elif voz.persona == _VOZ_NO_IDENTIFICADA:
        clase = "voz voz-aviso-leve"
    else:
        clase = "voz"
    aviso_html = f'<p class="voz-aviso">{html.escape(aviso)}</p>' if aviso else ""
    return f"""    <li class="{clase}">
      <p class="voz-etiqueta">Interviniente {html.escape(voz.etiqueta)} — {html.escape(voz.persona)}</p>
      <p><strong>{html.escape(etiqueta_evidencia)}</strong> «{html.escape(voz.evidencia)}»</p>
      {aviso_html}
      {f'<p>{tiempo}</p>' if tiempo else ""}
    </li>"""


def _bloque_mapa_voces(informe, video_url: str | None, transcripcion: str) -> str:
    """Sección con el mapa de voces (`identificacion_locutores`), si el informe lo
    trae. Los borradores generados antes de que este campo existiera no lo traen
    (lista vacía por compatibilidad — ver `InformePleno` en plenos_informe.py): en ese
    caso la sección simplemente no aparece, no se inventa un mapa que no existe.

    Va ANTES que las comprobaciones del auditor (ver `render_guia`): si una voz está
    mal identificada, TODAS sus intervenciones a lo largo del pleno están mal
    atribuidas en el acta, no solo la que el auditor haya podido objetar.

    Antes de pintarlo, comprueba en la transcripción si dos etiquetas identificadas
    como la misma persona se alternan hablando (`conflictos_turnos_alternos`): es la
    misma verificación que se le pide al modelo en DIARIZACION, hecha aquí en Python
    contra la sesión entera, por si no se aplicó."""
    if not informe.identificacion_locutores:
        return ""
    conflictivas = conflictos_turnos_alternos(informe, transcripcion)
    items = "\n".join(
        _bloque_voz(v, video_url, conflicto=v.etiqueta in conflictivas)
        for v in informe.identificacion_locutores)
    return f"""  <section class="mapa-voces">
    <h2>🎙 Quién es quién en la grabación</h2>
    <p>Comprueba esto antes que nada: si una de estas identificaciones está mal, TODAS
       las intervenciones de esa voz están mal atribuidas en el acta, no solo una.</p>
    <ul>
{items}
    </ul>
  </section>"""


def render_guia(informe, entrada: dict, transcripcion: str, pendientes: list,
                destino: str) -> None:
    """Escribe la guía de verificación HTML en `destino`.

    Autocontenida (CSS embebido, sin librerías ni conexión a internet) para que se
    pueda abrir con un doble clic. `entrada` es el `entrada.json` del borrador: de ahí
    salen el título y la URL del vídeo, que no vive en el InformePleno."""
    video_url = entrada.get("video_url")
    titulo = entrada.get("titulo") or "Pleno del Ayuntamiento de Enguídanos"
    fecha = informe.fecha_pleno or entrada.get("fecha")
    fecha_txt = fecha_larga(fecha) if fecha else "fecha no determinada en la grabación"

    bloque_mapa = _bloque_mapa_voces(informe, video_url, transcripcion)

    objeciones = [objecion_legible(p, informe, transcripcion, video_url) for p in pendientes]
    bloque_objeciones = ""
    if objeciones:
        items = "\n".join(_bloque_objecion(o, video_url) for o in objeciones)
        bloque_objeciones = f"""  <section class="objeciones">
    <h2>⚠ Puntos que conviene comprobar</h2>
    <p>El auditor automático no pudo confirmar estas afirmaciones contra la
       grabación. Revísalas antes de sellar el acta.</p>
    <ul>
{items}
    </ul>
  </section>"""

    puntos_ordenados = sorted(informe.orden_del_dia,
                              key=lambda p: (p.numero is None, p.numero or 0))
    bloque_puntos = "\n".join(_bloque_punto(p, video_url) for p in puntos_ordenados)

    documento = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Guía de verificación — {html.escape(titulo)}</title>
<style>{_CSS}</style>
</head>
<body>
  <header class="aviso">
    <p><strong>Esto NO es el acta.</strong> Es una ayuda para comprobarla contra el
       vídeo antes de sellarla: dice en qué minuto de la grabación está cada punto,
       para no tener que rebuscar por toda la sesión.</p>
  </header>
  <h1>{html.escape(titulo)}</h1>
  <p class="fecha">{html.escape(fecha_txt)}</p>
{bloque_mapa}
{bloque_objeciones}
  <section class="orden-del-dia">
    <h2>Orden del día</h2>
{bloque_puntos}
  </section>
</body>
</html>
"""
    Path(destino).write_text(documento, encoding="utf-8")
