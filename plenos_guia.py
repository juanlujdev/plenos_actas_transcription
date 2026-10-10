#!/usr/bin/env python3
"""Guía HTML para verificar el acta contra la grabación: enlaza cada punto, votación y
objeción del auditor con su minuto en el vídeo. Sin LLM."""

import html
import re
import unicodedata
from pathlib import Path

from plenos_acta import fecha_larga


def segundos(hms: str) -> int:
    """'01:12:04' -> 4324. Devuelve 0 si no parsea (nunca inventa un tiempo)."""
    m = re.fullmatch(r"(\d{1,2}):(\d{2}):(\d{2})", (hms or "").strip())
    if not m:
        return 0
    h, minutos, s = (int(x) for x in m.groups())
    return h * 3600 + minutos * 60 + s


def _hms_legible(hms: str) -> str:
    """'01:12:04' -> '1:12:04', sin el cero de relleno de la hora."""
    try:
        h, m, s = hms.split(":")
        return f"{int(h)}:{m}:{s}"
    except (ValueError, AttributeError):
        return hms


def enlace_video(video_url: str | None, hms: str | None) -> str | None:
    """URL de YouTube que salta a ese segundo, o None si falta el vídeo o el tiempo."""
    if not video_url or not hms:
        return None
    separador = "&" if "?" in video_url else "?"
    return f"{video_url}{separador}t={segundos(hms)}s"



_LINEA = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s*(.*)$")
# El auditor a veces antepone a la cita su marca de tiempo; se recorta antes de buscar.
_PREFIJO_CITA = re.compile(r"^\[\d{2}:\d{2}:\d{2}\]\s*(?:Interviniente\s+\S+:\s*)?")


def _normalizar(texto: str) -> str:
    """Minúsculas, sin acentos ni puntuación, espacios colapsados (para casar citas)."""
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


# Turnos alternos: comprobación en Python de la regla DIARIZACION, sin fiarse del LLM.

_ETIQUETA_LOCUTOR = re.compile(r"Interviniente\s+(\S+?):")


def _secuencia_etiquetas(transcripcion: str) -> list[str]:
    """Etiquetas de locutor en orden de intervención, colapsando repeticiones consecutivas."""
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
    """True si las etiquetas se responden directamente (A, B, A o B, A, B) en `secuencia`.

    Dos etiquetas que nunca se alternan pueden ser una misma persona partida en dos voces;
    dos que se responden, no (ver REGLA DE TURNOS ALTERNOS en plenos_informe.DIARIZACION)."""
    pares = ([etiqueta_a, etiqueta_b, etiqueta_a], [etiqueta_b, etiqueta_a, etiqueta_b])
    return any(secuencia[i:i + 3] in pares for i in range(len(secuencia) - 2))


def conflictos_turnos_alternos(informe, transcripcion: str) -> set[str]:
    """Etiquetas que el mapa asigna a la MISMA persona pese a alternar turnos entre sí.

    Ignora las de escape (voces mezcladas / no identificado). Devuelve etiquetas, no pares."""
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
    """'HH:MM:SS' de la intervención que contiene `cita`, o None (nunca inventa un tiempo).

    Cascada: subcadena exacta; cita normalizada; ventanas de 6 a 8 palabras (las más largas
    primero)."""
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



def _numero_citado(seccion: str) -> int | None:
    """Número de punto citado en `seccion` ('Punto 3', '3º'), o None.

    Ignora '[2]': es el índice en el JSON, no el número del punto."""
    sin_indices = re.sub(r"\[\d+\]", "", seccion or "")
    m = re.search(r"\d+", sin_indices)
    return int(m.group()) if m else None


def _punto_de(seccion: str, informe):
    """PuntoOrdenDia que casa con `seccion` (en prosa) por número o título; None si ninguno."""
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
    """'Punto 3º) TÍTULO', como en el acta; sin número, un guion."""
    numero = f"{punto.numero}º" if punto.numero is not None else "—"
    return f"Punto {numero}) {punto.titulo}"


def _punto_ruegos_y_preguntas(informe):
    """El punto 'RUEGOS Y PREGUNTAS' si el orden del día lo trae numerado; None si no."""
    for punto in informe.orden_del_dia:
        if _normalizar(punto.titulo) == "ruegos y preguntas":
            return punto
    return None


# Sufijo según la parte del punto señalada por el auditor ('numero' no: ya va en "Punto Nº)").
_SUFIJOS_CAMPO = {
    "texto": "en el relato del debate",
    "acuerdo": "en el acuerdo",
    "titulo": "en el título",
}

# Campos de InformePleno (salvo orden del día y ruegos) en lenguaje llano.
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

# Ruta interna tipo 'orden_del_dia[2].texto': raíz, índice opcional, resto opcional.
# Una sección en prosa no casa entera.
_RUTA_CAMPO = re.compile(r"^(\w+)(?:\[(\d+)\])?(?:\.(.+))?$")


def _sufijo_campo(resto: str | None) -> str | None:
    """Parte del punto donde está la duda ('.texto', '.votacion'...) en cristiano, o None."""
    if not resto:
        return None
    raiz = re.sub(r"\[\d+\]$", "", resto.split(".")[0])
    if raiz == "votacion":
        return "en la votación"
    return _SUFIJOS_CAMPO.get(raiz)


def _ruta_legible(seccion: str, informe) -> tuple[str | None, object | None]:
    """Traduce una ruta interna ('orden_del_dia[2].texto') al lenguaje del acta.

    Devuelve (texto, punto). (None, None) si no es una ruta, el índice está fuera de rango o
    la raíz no se reconoce: ante la duda no se inventa nada."""
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
        # Se nombra por la etiqueta (lo que ve la funcionaria en la guía), no por el índice.
        if indice is None:
            return "Mapa de voces", None
        idx = int(indice)
        if not (0 <= idx < len(informe.identificacion_locutores)):
            return None, None
        return f"Mapa de voces — etiqueta {informe.identificacion_locutores[idx].etiqueta}", None

    if raiz in _CAMPOS_INFORME and indice is None and resto is None:
        return _CAMPOS_INFORME[raiz], None

    return None, None


# Marca "[HH:MM:SS] Interviniente X: " (ruido: el tiempo se muestra aparte). El "[...]" del
# auditor no lleva dígitos y se conserva.
_MARCA_TIEMPO_LOCUTOR = re.compile(r"\[\d{2}:\d{2}:\d{2}\]\s*(?:Interviniente\s+\S+:\s*)?")


def _limpiar_evidencia(texto: str | None) -> str | None:
    """La cita sin marcas [HH:MM:SS] ni 'Interviniente X:'; conserva los '[...]'."""
    if not texto:
        return texto
    limpio = _MARCA_TIEMPO_LOCUTOR.sub("", texto)
    return re.sub(r"[ \t]+", " ", limpio).strip()


# buscar_en_acta: `afirmacion_dudosa` es una descripción del auditor, no la frase del acta;
# se reconstruye la frase literal verificándola contra el informe.

_COMILLAS = re.compile(r'[«"“]([^»"”]+)[»"”]')


def _fragmentos_citados(texto: str) -> list[str]:
    """Fragmentos entre comillas (rectas, angulares o tipográficas) de `texto`, en orden."""
    return [f.strip() for f in _COMILLAS.findall(texto or "") if f.strip()]


def _palabras_significativas(texto: str) -> set[str]:
    """Palabras normalizadas de cinco letras o más (las que distinguen una frase de otra)."""
    return {w for w in _normalizar(texto).split() if len(w) >= 5}


_FIN_FRASE = re.compile(r"(?<=[.!?])\s+")

# Tratamientos abreviados con punto que no deben tomarse por fin de frase.
# Una abreviatura nueva se añade aquí.
_ABREVIATURAS = re.compile(r"\b(D|Dª|Dna|Sr|Sra|Srta|Excmo|Excma|Ilmo|Ilma)\.",
                           re.IGNORECASE)
_MARCA_PUNTO_PROTEGIDO = "￼"  # carácter que no aparece en prosa real


def _frases(texto: str) -> list[str]:
    """Trocea en frases; ingenuo a propósito (solo protege `_ABREVIATURAS`): basta como ayuda de búsqueda."""
    frases = []
    for parrafo in (texto or "").split("\n"):
        protegido = _ABREVIATURAS.sub(lambda m: m.group(1) + _MARCA_PUNTO_PROTEGIDO, parrafo)
        for f in _FIN_FRASE.split(protegido):
            f = f.replace(_MARCA_PUNTO_PROTEGIDO, ".").strip()
            if f:
                frases.append(f)
    return frases


def _mejor_frase(afirmacion: str, candidatas: list[str]) -> str | None:
    """Frase candidata que más comparte con la duda, puntuando por PROPORCIÓN de palabras
    significativas (el recuento bruto premia frases largas que coinciden por casualidad).

    El umbral (3+ palabras comunes y >= 50%) se aplica ANTES de comparar, para que una frase
    corta con una sola palabra común no desplace a una válida."""
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
    """Textos reales del informe a los que puede apuntar `seccion` (fuente de verdad de
    `buscar_en_acta`). Nunca devuelve nada que no esté en el informe."""
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
                # 'texto', 'votacion' u otro sufijo: solo la prosa del debate tiene frases que pegar.
                return [punto.texto] if punto.texto else []
        if raiz == "ruegos_y_preguntas" and indice is not None:
            idx = int(indice)
            if 0 <= idx < len(informe.ruegos_y_preguntas):
                bloque = informe.ruegos_y_preguntas[idx]
                # `formulados_por` primero: si la duda es sobre QUIÉN habla, gana por proporción
                # de palabras; el orden solo importa a _fragmentos_citados.
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
    """Frase LITERAL del acta para pegar en el buscador de Word, verificada contra el informe.

    Cascada: fragmento entre comillas de `afirmacion_dudosa`; si no, la frase más parecida
    (`_mejor_frase`); None si ninguna da confianza."""
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
    """Una objeción del auditor en términos de la funcionaria, con el minuto para comprobarla.

    `seccion` puede ser ruta interna o prosa. Tiempo: cita localizada, timestamp de la votación
    del punto o del punto; si ninguno, None. `buscar` es la frase literal del informe (a
    diferencia de `dice`, la descripción del auditor)."""
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


# Aviso "COMPROBAR ANTES DE SELLAR.txt": vive aquí porque procesar_pleno._componer_guia
# (también en --rehacer-acta) lo escribe junto a la guía.

def _avisos_legibles(pendientes: list, objeciones: tuple) -> list[dict]:
    """`objeciones` si las hay; si no, las reconstruye desde `pendientes` sin cita ni minuto.

    Puede venir vacía con pendientes (datos antiguos o guía no compuesta) y el aviso no debe perderse."""
    if objeciones:
        return list(objeciones)
    return [{"donde": p.seccion, "dice": p.afirmacion_dudosa, "motivo": p.motivo,
             "se_oye": None, "hms": None, "enlace": None, "buscar": None} for p in pendientes]


def _lineas_aviso(numero: int, aviso: dict, con_enlace: bool) -> list[str]:
    """Líneas de un aviso; omite los datos que faltan. `con_enlace` escribe la URL completa
    (fichero) o solo el minuto (pantalla)."""
    lineas = [f" {numero}. {aviso['donde']}",
              f"    El acta dice:   \"{aviso['dice']}\""]
    if aviso.get("buscar"):
        # Frase literal del informe, a diferencia de "El acta dice" (descripción del auditor).
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
    """Lista de objeciones del auditor en cristiano, con cita y minuto si constan."""
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
    """Guarda la lista junto al acta. Sin objeciones no se crea (y se borra la anterior)."""
    ruta = carpeta / "COMPROBAR ANTES DE SELLAR.txt"
    if not pendientes:
        # Al reprocesar, el aviso anterior contradiría a la pantalla.
        ruta.unlink(missing_ok=True)
        return None
    ruta.write_text(texto_comprobaciones(fecha, pendientes, objeciones), encoding="utf-8")
    return ruta



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
section.asuntos {
  background: #eef6ec; border: 1px solid #b3d3ac; border-radius: 6px;
  padding: 8px 20px 16px; margin-bottom: 32px;
}
section.asuntos h2 { color: #2c6e2c; }
.asunto { border-top: 1px solid #cfe3ca; padding: 12px 0; }
.asunto:first-of-type { border-top: none; }
.asunto p { margin: 4px 0; }
.asunto-donde { font-weight: bold; }
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
  section.asuntos { background: #16301a; border-color: #3a6b3a; }
  section.asuntos h2 { color: #9fd89f; }
  .asunto { border-color: #2c5230; }
  .punto { border-color: #444; }
  .enlace { background: #4a90d9; }
  .tiempo { color: #aaa; }
  .objecion code { background: rgba(255,255,255,.12); }
}
"""


def _html_tiempo(hms: str | None, video_url: str | None,
                 prefijo: str = "▶ Ver en el vídeo") -> str:
    """Enlace al minuto si hay vídeo y tiempo; solo el tiempo si no hay URL; nada si no consta."""
    if not hms:
        return ""
    legible = _hms_legible(hms)
    url = enlace_video(video_url, hms)
    if url:
        return (f'<a class="enlace" href="{html.escape(url)}" target="_blank" '
                f'rel="noopener">{html.escape(prefijo)} ({html.escape(legible)})</a>')
    return f'<span class="tiempo">Minuto {html.escape(legible)} de la grabación</span>'


def _resultado_legible(v) -> str | None:
    """Frase corta del resultado de la votación; None si no se votó."""
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
    # Frase literal del informe en <code>, seleccionable de un clic para el buscador de Word.
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


def _bloque_asunto(asunto, video_url: str | None) -> str:
    """Tema fuera del orden del día: solo síntesis, dónde surge y minuto (con acuerdo o
    votación sería un punto del acta, regla 16 ter)."""
    donde = (f'<p class="asunto-donde">En el debate de: {html.escape(asunto.surge_en)}</p>'
             if asunto.surge_en else "")
    tiempo = _html_tiempo(asunto.timestamp, video_url)
    return f"""    <li class="asunto">
      {donde}
      <p>{html.escape(asunto.asunto)}</p>
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


# Valores de escape de `VozIdentificada.persona` que no son un nombre; se traducen a una frase.
_VOZ_MEZCLADA = "etiqueta con voces mezcladas"
_VOZ_NO_IDENTIFICADA = "no identificado en la grabación"


def _aviso_voz(persona: str) -> str | None:
    """Aviso de por qué una voz debe comprobarse en el vídeo, o None si es un nombre normal.

    Mezclada (dos personas bajo una etiqueta) y no identificada son problemas distintos y se
    avisan distinto."""
    if persona == _VOZ_MEZCLADA:
        return ("⚠ El transcriptor ha mezclado aquí a DOS PERSONAS DISTINTAS bajo la "
                "misma voz: no te fíes de lo que el acta le atribuya sin comprobarlo en "
                "el vídeo, porque puede que la intervención sea de otra persona.")
    if persona == _VOZ_NO_IDENTIFICADA:
        return ("El transcriptor no ha podido separar bien esta voz de las demás: "
                "conviene comprobar sus intervenciones en el vídeo.")
    return None


def _etiqueta_evidencia(persona: str) -> str:
    """Frase que antecede a la cita de `evidencia`, según el tipo de voz."""
    if persona == _VOZ_MEZCLADA:
        return "Aquí el transcriptor ha mezclado a dos personas:"
    if persona == _VOZ_NO_IDENTIFICADA:
        return "No se ha podido saber quién es:"
    return "Se identifica porque:"


def _aviso_conflicto(persona: str) -> str:
    """Aviso para una etiqueta con nombre que alterna turnos con otra identificada como la
    misma persona. Mismo peso visual que la voz mezclada: es un error de identidad."""
    return (f"⚠ Esta etiqueta se identifica aquí como {persona}, la misma persona que "
            "otra etiqueta distinta del mapa — pero las dos se responden entre sí en la "
            "grabación, y dos voces que se alternan no pueden ser la misma persona. "
            "Comprueba estas intervenciones en el vídeo antes de dar la identificación "
            "por buena.")


def _bloque_voz(voz, video_url: str | None, conflicto: bool = False) -> str:
    tiempo = _html_tiempo(voz.timestamp, video_url)
    # `conflicto` solo es True para etiquetas con nombre (ya excluye los valores de escape),
    # así que no compite con los otros avisos.
    aviso = _aviso_conflicto(voz.persona) if conflicto else _aviso_voz(voz.persona)
    etiqueta_evidencia = _etiqueta_evidencia(voz.persona)
    # Voz mezclada y conflicto son lo más grave (atribución errónea); la no identificada es
    # un hueco honesto.
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
    """Sección del mapa de voces; vacía si el informe no lo trae (borradores antiguos).

    Va antes que las objeciones: una voz mal identificada contamina todas sus intervenciones.
    Comprueba además los turnos alternos en Python (`conflictos_turnos_alternos`)."""
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
    """Escribe la guía HTML autocontenida en `destino`; `entrada` aporta título y URL del vídeo."""
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

    # Informes antiguos no traen el campo: se omite la sección.
    asuntos = getattr(informe, "asuntos_no_convocados", None) or []
    bloque_asuntos = ""
    if asuntos:
        items = "\n".join(_bloque_asunto(a, video_url) for a in asuntos)
        bloque_asuntos = f"""  <section class="asuntos">
    <h2>Asuntos tratados fuera del orden del día</h2>
    <p>El acta recoge los puntos convocados, así que esto <strong>no está en ella</strong>.
       Aquí tienes de qué más se habló y en qué minuto, por si quieres recogerlo dentro del
       punto en el que surge.</p>
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
{bloque_asuntos}
  <section class="orden-del-dia">
    <h2>Orden del día</h2>
{bloque_puntos}
  </section>
</body>
</html>
"""
    Path(destino).write_text(documento, encoding="utf-8")
