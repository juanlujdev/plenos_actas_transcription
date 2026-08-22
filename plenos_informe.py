#!/usr/bin/env python3
"""
plenos_informe.py - Esquemas, prompts y bucle LLM del informe de plenos.

El modelo devuelve SIEMPRE JSON contra estos esquemas pydantic.
Principio: la vía de escape está dentro del esquema — todo dato que la
transcripción pueda no contener es Optional o tiene un valor "no consta",
para que el esquema nunca fuerce al modelo a inventar.
"""

from typing import Literal

from pydantic import BaseModel, Field


class Votacion(BaseModel):
    """Resultado de la votación de un punto. Solo datos oídos en la grabación."""
    resultado: Literal["aprobado", "rechazado", "sin votación", "no consta"]
    modalidad: Literal["unanimidad", "recuento", "no consta"]
    a_favor: int | None = Field(None, description="Solo si se dice el número en la grabación; si no, null")
    en_contra: int | None = Field(None, description="Solo si se dice el número en la grabación; si no, null")
    abstenciones: int | None = Field(None, description="Solo si se dice el número en la grabación; si no, null")
    timestamp: str | None = Field(None, description="HH:MM:SS de la transcripción donde se anuncia el resultado")


class PuntoOrdenDia(BaseModel):
    numero: int | None = Field(None, description="Número del punto si se menciona; si no, null")
    parte: Literal["resolutiva", "control"] = Field(description=(
        "'resolutiva' si el punto se somete a acuerdo del Pleno; 'control' para decretos "
        "de alcaldía, daciones de cuenta y todo aquello de lo que la Corporación solo se "
        "da por informada."))
    titulo: str = Field(description="Título del punto EN MAYÚSCULAS, como en un acta municipal")
    texto: str = Field(description=(
        "Redacción del punto en prosa de acta, con las intervenciones incorporadas y el "
        "acuerdo desglosado si lo hay. NO escribas aquí recuentos de votos: van en el "
        "campo `votacion` y el documento los compone a partir de ahí."))
    votacion: Votacion | None = Field(None, description="null si el punto no se sometió a votación")


class BloqueRuegos(BaseModel):
    """El acta agrupa los ruegos y preguntas por quien los formula."""
    formulados_por: str = Field(description=(
        "Quien formula el bloque, con tratamiento ('D. Joaquín Martínez'), SOLO si la "
        "grabación lo identifica; si no, exactamente 'no identificado en la grabación'."))
    puntos: list[str] = Field(description="Un elemento por ruego o pregunta")


class InformePleno(BaseModel):
    """Contenido del acta de un pleno. Lo devuelven el generador y el corrector."""
    tipo_sesion: Literal["ordinaria", "extraordinaria", "no consta"] = Field(description=(
        "Tipo de sesión según lo que se diga en la grabación (la convocatoria suele leerse "
        "al inicio). Si no se dice, 'no consta': no lo deduzcas del contenido."))
    motivo_convocatoria: str | None = Field(None, description=(
        "Solo en sesiones extraordinarias y solo si se lee el motivo de la convocatoria; "
        "si no, null"))
    fecha_pleno: str | None = Field(None, description="YYYY-MM-DD solo si se menciona en la grabación; si no, null")
    hora_inicio: str | None = Field(None, description="HH:MM solo si se dice en la grabación; si no, null")
    hora_fin: str | None = Field(None, description="HH:MM solo si se dice en la grabación; si no, null")
    presidente: str | None = Field(None, description=(
        "Quien preside la sesión, solo si la grabación lo identifica; si no, null"))
    asistentes: list[str] = Field(description=(
        "Miembros de la corporación cuya asistencia consta en la grabación (pase de lista "
        "o identificación explícita). Lista vacía si no consta; nunca deduzcas asistencia."))
    ausentes: list[str] = Field(description=(
        "Miembros cuya ausencia se hace constar expresamente. Lista vacía si no consta."))
    orden_del_dia: list[PuntoOrdenDia]
    ruegos_y_preguntas: list[BloqueRuegos] = Field(description="Lista vacía si no hubo turno")
    resumen_corto: str = Field(description="2-3 frases para la tarjeta de la web")


class Problema(BaseModel):
    seccion: str = Field(description="Sección del informe donde está la afirmación dudosa")
    afirmacion_dudosa: str
    motivo: str
    evidencia: str = Field(description="Cita literal de la transcripción que contradice o no respalda la afirmación")


class AuditoriaInforme(BaseModel):
    """Resultado del auditor. Lista vacía = visto bueno."""
    problemas: list[Problema]


# ══════════════════════════════════════════════════════════════════════════════
# Prompts de los tres roles
# ══════════════════════════════════════════════════════════════════════════════

CORPORACION = """CORPORACIÓN MUNICIPAL (solo para escribir bien los nombres, ver regla 4):
- Sergio de Fez Cerezuela — Alcalde-Presidente (PSOE), de baja médica
- Lorena Luján Chujfi — Concejala, equipo de gobierno (PSOE); ejerce la Alcaldía en
  funciones durante esa baja y es quien preside las sesiones
- Mª Rosario Cerdán Pérez — Concejala, equipo de gobierno (PSOE). En la sesión se
  dirigen a ella como "Chari": es la misma persona.
- Mario Cerdán Ochoa — Concejal, equipo de gobierno (PSOE)
- Joaquín Martínez — Concejal, oposición (PP)
- Pedro José Martínez — Concejal, oposición (PP)
- Fernando Pons — Concejal, oposición (AIE)
- Elena — Secretaria del Ayuntamiento. NO es miembro de la Corporación y no vota: da fe
  de la sesión, lee acuerdos e informa cuando se le pide. Su voz sale en la grabación,
  pero nunca va en `asistentes` ni en `ausentes`.

Quién preside se te dice para acertar el TRATAMIENTO al redactar ("la Sra. Alcaldesa"),
NO para rellenar el campo `presidente` ni para atribuir intervenciones: eso sigue
exigiendo que la grabación lo diga (reglas 1, 4 y 5)."""


DIARIZACION = """ETIQUETAS DE LOCUTOR:
La transcripción viene diarizada: cada línea es [HH:MM:SS] seguido de "Interviniente A:",
"Interviniente B:"... Esas etiquetas las pone el transcriptor separando VOCES, no
identidades: sabe que dos intervenciones son de la misma persona, no de quién son.
- La misma etiqueta es la misma persona durante toda la sesión.
- Si en cualquier momento la grabación identifica a quien lleva una etiqueta (se
  presenta, la Presidencia le da la palabra por su nombre o su cargo, alguien le
  responde nombrándole), atribúyele TODAS las intervenciones de esa etiqueta, también
  las anteriores. Una sola identificación vale para toda la sesión.
- Si una etiqueta no se identifica nunca, sus intervenciones siguen siendo "no
  identificado en la grabación". No adivines por el orden de palabra, por el tema del
  que habla, por cuánto habla ni por el reparto de la corporación.
- Las etiquetas no se escriben en el acta: son andamiaje de la transcripción."""


PROMPT_GENERADOR = f"""Eres el redactor de informes de los plenos del Ayuntamiento de
Enguídanos (Cuenca). Recibes la transcripción literal de un pleno, con marcas de tiempo
[HH:MM:SS] al inicio de cada segmento, y produces un informe estructurado en el JSON
que se te pide.

{CORPORACION}

{DIARIZACION}

REGLAS INNEGOCIABLES:
1. Usa ÚNICAMENTE información presente en la transcripción. Prohibido inferir,
   completar huecos o usar conocimiento externo.
2. Si un dato no consta o no se entiende, usa la vía de escape del esquema:
   null, "no consta", "sin votación" o "no identificado en la grabación", según el campo.
3. Cada votación debe llevar el timestamp donde se anuncia su resultado. Los números
   de votos solo si se dicen en voz alta; si se aprueba "por unanimidad" sin contar,
   modalidad="unanimidad" y los números en null.
4. La transcripción es automática y deforma los nombres propios. Cuando aparezca un
   nombre que se corresponda claramente por sonido con uno de la corporación (p. ej.
   "Féceres Zuela" → "Sergio de Fez Cerezuela"; "Zatanochoa" → "Mario Cerdán Ochoa"),
   escríbelo en su forma correcta. Esa lista sirve SOLO para escribir bien un nombre que
   la grabación pronuncia: nunca para deducir quién habla ni para atribuir intervenciones
   que la grabación no atribuye.
5. Atribuye una intervención a una persona SOLO si la propia grabación la identifica
   ("tiene la palabra el concejal de...", "responde la alcaldesa..."), directamente o a
   través de su etiqueta de locutor según las reglas de arriba. Nunca por deducción.
6. Si un fragmento es incoherente por errores de transcripción, no lo interpretes
   creativamente: descártalo o marca "no consta".

REDACCIÓN — ESTILO DE ACTA MUNICIPAL:
7. Escribe en PRESENTE de indicativo, con el registro impersonal y formal propio de un
   acta: "La Sra. Alcaldesa da cuenta...", "Se acuerda...". Nunca en pasado.
8. Usa el tratamiento formal del acta: D., Dª, Sr. concejal, Sra. concejala, seguidos del
   nombre completo. A quien preside la sesión trátalo por el cargo y en su género: hoy
   preside Dª Lorena Luján Chujfi como Alcaldesa en funciones, así que es "la Sra.
   Alcaldesa", nunca "el Sr. Alcalde". Introduce las intervenciones con la fórmula
   habitual: "Toma la palabra el Sr. concejal D. Fernando Pons para decir que...", "Le
   responde la Sra. Alcaldesa que...".
9. Los títulos de los puntos van EN MAYÚSCULAS, como en las actas.
10. Las intervenciones van DENTRO del texto del punto al que corresponden, en el orden en
    que se producen. No hay una sección separada de intervenciones.
11. Los puntos de la parte resolutiva terminan con el acuerdo desglosado cuando lo hay:
    "el Pleno del Ayuntamiento ACUERDA: PRIMERO. ... SEGUNDO. ...".
12. Los puntos de actividad de control terminan con "La Corporación se da por informada."
    cuando así ocurre en la grabación.
13. Cuando una frase sea textual de un concejal y valga la pena recogerla tal cual,
    entrecomíllala.
14. Sé extenso y concreto: recoge los argumentos de cada postura, las cifras, plazos,
    importes y expedientes que se citen. Varios párrafos si el punto lo merece.
15. No cites marcas de tiempo dentro de los textos redactados, ni escribas recuentos de
    votos en el texto: los recuentos van en el campo `votacion`.
16. Español claro y neutro.

LA CONVOCATORIA OFICIAL:
Puede que junto a la transcripción recibas la CONVOCATORIA del pleno: el documento con el
orden del día que el Ayuntamiento publica ANTES de la sesión, a menudo escaneado. Si la
recibes, mándate por estas cuatro reglas. Si no, ignóralas.
17. La convocatoria manda en la FORMA. Los títulos exactos de los puntos, su numeración,
    los números de expediente y el tipo de sesión (ordinaria o extraordinaria, y el motivo
    si es extraordinaria) se toman de ella, no de lo que se entienda en el audio. Copia los
    títulos literalmente, en mayúsculas.
18. La grabación manda en el FONDO. Qué se debate, qué se acuerda, qué se vota y quién
    interviene sale SOLO de la transcripción. La convocatoria dice lo previsto; el acta
    recoge lo ocurrido, y no siempre coinciden.
19. Un punto que figura en la convocatoria pero del que la grabación no dice nada NO se
    redacta como si se hubiera tratado. Si en la grabación se retira, se aplaza o se deja
    sobre la mesa, hazlo constar así; si sencillamente no aparece, omítelo.
20. Un punto que se trata en la grabación y no está en la convocatoria SÍ va al acta —
    suele ser un asunto de urgencia —, con `numero` en null si no se le da número.
"""

PROMPT_AUDITOR = f"""Eres el auditor de calidad de informes de plenos del Ayuntamiento de
Enguídanos. Recibes la transcripción literal de un pleno (con marcas [HH:MM:SS]) y un
informe en JSON generado a partir de ella. Tu único trabajo: encontrar afirmaciones del
informe que la transcripción NO respalde.

Comprueba una a una las afirmaciones verificables: resultados y números de votaciones,
nombres y cargos, importes, fechas, acuerdos adoptados y atribuciones de intervenciones.

{CORPORACION}

{DIARIZACION}

El redactor tiene esas mismas instrucciones. Que atribuya a una persona TODAS las
intervenciones de una etiqueta que la grabación identifica una sola vez es la conducta
esperada, no una invención: NO lo señales, aunque el fragmento concreto que estás
comprobando no repita el nombre. Lo que sí debes señalar es que ponga nombre a una
etiqueta que la grabación no identifica en ningún momento, o que mezcle en una misma
persona intervenciones de etiquetas distintas.

La transcripción es automática y deforma los nombres propios, así que el redactor tiene
instrucciones de corregirlos contra esa lista. NO señales como problema que el informe
escriba "Sergio de Fez Cerezuela" donde la transcripción dice "Féceres Zuela", ni casos
equivalentes: es la corrección esperada. Sí debes señalar que se atribuya una
intervención a una persona concreta cuando la grabación no la identifique.

Tampoco es un problema el tiempo verbal ni el estilo: el informe se redacta en presente
a propósito.

Tampoco son problema las fórmulas y el tratamiento propios de un acta municipal: que el
informe escriba "la Sra. Alcaldesa", "D. Joaquín Martínez", "Toma la palabra...", "La
Corporación se da por informada" o los títulos en mayúsculas es la redacción esperada, no
una afirmación inventada, aunque la transcripción no contenga esas palabras literales. Sí
debes señalar que se atribuya una intervención a una persona que la grabación no identifica.

Comprueba también que cada punto está en la parte correcta: 'resolutiva' si se somete a
acuerdo del Pleno, 'control' si es un decreto de alcaldía o una dación de cuenta de la que
la Corporación solo se da por informada. Y que `asistentes` y `ausentes` solo afirman lo
que la grabación dice expresamente.

Puede que recibas también la CONVOCATORIA oficial del pleno (el orden del día que el
Ayuntamiento publica antes de la sesión, a menudo escaneado). Si está, es una fuente
LEGÍTIMA, igual que el listado de la corporación: que un título, una numeración, un número
de expediente o el tipo de sesión salgan de ella y no aparezcan en la transcripción NO es
una afirmación inventada, y no debes señalarlo.

Lo que sí debes señalar es lo contrario, y es tu comprobación más importante cuando hay
convocatoria: **un punto redactado como si se hubiera debatido, acordado o votado cuando
la transcripción no lo respalda, aunque figure en la convocatoria.** La convocatoria dice
lo que estaba previsto tratar, no lo que se trató. Un punto convocado que se retira, se
aplaza o del que no se habla en la grabación no puede aparecer en el acta con contenido.

Para cada problema devuelve: la sección, la afirmación dudosa, el motivo y una cita
literal de la transcripción como evidencia. Si el informe es fiel a la transcripción,
devuelve la lista de problemas VACÍA. No inventes problemas menores de estilo: solo
faltas de fidelidad a la fuente."""

PROMPT_CORRECTOR = f"""Eres el corrector de informes de plenos del Ayuntamiento de
Enguídanos. Recibes: la transcripción literal (con marcas [HH:MM:SS]), el informe completo
en JSON, y la lista de problemas detectados por un auditor (cada uno con su evidencia).

{DIARIZACION}

Devuelve el informe COMPLETO corregido, en el mismo esquema JSON:
1. Corrige exclusivamente lo señalado en los problemas, apoyándote en la transcripción.
2. Si la transcripción no permite resolver un problema, aplica la vía de escape del
   esquema (null, "no consta", "no identificado en la grabación") en ese dato.
3. RECUENTOS DE VOTOS. Si el auditor objeta un número de votos, la corrección NO es
   cambiar ese número por otro que encaje mejor: es poner `null` en el campo objetado.
   Un recuento solo lleva número si ese número se oye en la grabación.
   - Si el recuento se verbaliza de forma ininteligible, todos sus campos van a `null`.
   - Si solo consta una parte (se oye "uno a favor" pero no el resto), pon número SOLO
     en lo que se oye y `null` en los demás campos.
   - Deducir los votos que faltan restando del número de asistentes, del reparto de la
     corporación o del sentido del debate es inventar: prohibido.
   - Nunca pongas 0 para rellenar: un 0 afirma que nadie votó así, y eso hay que oírlo
     igual que cualquier otra cifra.
   `resultado` y `modalidad` se conservan si sí constan: que no se sepa el recuento no
   significa que no se sepa si el punto se aprobó o se rechazó.
4. No toques el resto del informe.
5. Mismas reglas que el redactor: nada que no esté en la transcripción.
6. Conserva la redacción en presente de indicativo, el registro y las fórmulas de acta
   municipal (tratamiento D./Dª/Sr./Sra., "Toma la palabra...", títulos en mayúsculas,
   acuerdos desglosados en PRIMERO./SEGUNDO.) y el nivel de detalle del texto original;
   no lo resumas ni lo pases a pasado.
7. Si recibes la CONVOCATORIA oficial del pleno, sigue mandando en la forma (títulos
   literales, numeración, expedientes, tipo de sesión) mientras la grabación manda en el
   fondo. No añadas contenido a un punto convocado del que la transcripción no habla:
   eso es justo lo que el auditor señala."""


# ══════════════════════════════════════════════════════════════════════════════
# Llamadas al LLM (OpenRouter) y bucle de fiabilidad
# ══════════════════════════════════════════════════════════════════════════════

import base64
import json
import os
import tempfile
import time
from pathlib import Path

import requests

MAX_VUELTAS = 3
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
MODELO = "google/gemini-2.5-pro"


def _plural(n: int, singular: str, plural: str) -> str:
    """'1 objeción' / '3 objeciones'. El log lo lee una persona, no un parser."""
    return f"{n} {singular if n == 1 else plural}"


def _log(texto: str) -> None:
    """Progreso por consola. Estas llamadas tardan minutos y el bucle puede dar tres
    vueltas: sin rastro no se sabe si avanza, en qué rol está ni qué ha objetado el
    auditor. flush porque la salida suele ir a un fichero con `| tee`."""
    print(texto, flush=True)


def _esquema_estricto(schema):
    """Adapta el JSON Schema de pydantic al modo `strict` de OpenRouter, que exige
    todas las propiedades en `required` y prohíbe `default`. No pierde vías de
    escape: los campos opcionales ya admiten null en el propio esquema."""
    if isinstance(schema, dict):
        schema.pop("default", None)
        if "properties" in schema:
            schema["required"] = list(schema["properties"])
            schema["additionalProperties"] = False
        for valor in schema.values():
            _esquema_estricto(valor)
    elif isinstance(schema, list):
        for valor in schema:
            _esquema_estricto(valor)
    return schema


def _peticion(cuerpo: dict, intentos: int = 4) -> dict:
    """POST a OpenRouter; ante 429 o error de servidor reintenta con el mismo backoff
    exponencial que _reintentar() en procesar_pleno.py (2, 4, 8 min)."""
    for i in range(intentos):
        r = requests.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
            json=cuerpo,
            timeout=900,
        )
        if (r.status_code == 429 or r.status_code >= 500) and i < intentos - 1:
            espera = 120 * 2 ** i
            _log(f"     OpenRouter devolvió {r.status_code}; esperando {espera // 60} min y reintentando...")
            time.sleep(espera)
            continue
        r.raise_for_status()
        datos = r.json()
        if "choices" not in datos:  # OpenRouter devuelve algunos errores con HTTP 200
            raise RuntimeError(f"OpenRouter no devolvió respuesta: {datos}")
        # Un fallo del proveedor a mitad de generación también llega con HTTP 200, pero
        # con el error DENTRO del choice: el modelo se atasca razonando en círculos,
        # Google deja de emitir tokens y OpenRouter corta ("Upstream idle timeout
        # exceeded", 504). Es transitorio y le pasa sobre todo al auditor, que es la
        # llamada más larga, así que se reintenta igual que un 5xx de transporte.
        fallo = (datos["choices"][0] or {}).get("error")
        if fallo and i < intentos - 1:
            espera = 120 * 2 ** i
            _log(f"     el proveedor cortó la respuesta ({fallo.get('code')}: "
                 f"{fallo.get('message')}); esperando {espera // 60} min y reintentando...")
            time.sleep(espera)
            continue
        return datos


def _llamar_llm(instrucciones: str, contenido: str, schema: type[BaseModel],
                convocatoria: bytes | None = None, etiqueta: str = "llm") -> BaseModel:
    """Una llamada al modelo con salida estructurada validada contra `schema`.

    `convocatoria` son los bytes del PDF del orden del día, que viaja como parte
    multimodal junto al texto. Va en crudo a propósito: las convocatorias del
    Ayuntamiento son escaneos sin capa de texto, así que extraerlas exigiría OCR;
    el modelo las lee directamente, y además conserva la maquetación (lista
    numerada, expedientes) que un texto aplanado pierde.
    """
    partes = [{"type": "text", "text": contenido}]
    cuerpo = {
        "model": MODELO,
        "messages": [
            {"role": "system", "content": instrucciones},
            {"role": "user", "content": partes},
        ],
        "temperature": 0,
        "response_format": {"type": "json_schema", "json_schema": {
            "name": schema.__name__.lower(),
            "strict": True,
            "schema": _esquema_estricto(schema.model_json_schema()),
        }},
    }
    if convocatoria is not None:
        partes.insert(0, {"type": "file", "file": {
            "filename": "convocatoria.pdf",
            "file_data": "data:application/pdf;base64," + base64.b64encode(convocatoria).decode(),
        }})
        # engine "native": el PDF le llega al modelo tal cual. El extractor por
        # defecto de OpenRouter es OCR de pago y devolvería texto plano.
        cuerpo["plugins"] = [{"id": "file-parser", "pdf": {"engine": "native"}}]

    inicio = time.perf_counter()
    datos = _peticion(cuerpo)
    uso = datos.get("usage") or {}
    razonamiento = (uso.get("completion_tokens_details") or {}).get("reasoning_tokens")
    detalle = f"{uso.get('prompt_tokens', 0):,} entrada + {uso.get('completion_tokens', 0):,} salida"
    if razonamiento:
        detalle += f" (de ellos {razonamiento:,} de razonamiento)"
    _log(f"     {etiqueta} responde en {time.perf_counter() - inicio:.0f}s, {detalle}")

    eleccion = datos["choices"][0]
    contenido = (eleccion.get("message") or {}).get("content")
    if not contenido:
        # El modelo puede devolver 200 con content vacío: se le acaba el presupuesto
        # de salida razonando (finish_reason "length"), o el proveedor corta. Sin este
        # aviso el None viajaba hasta pydantic y reventaba con un error de tipos que
        # no dice nada de la causa. El volcado guarda la respuesta para diagnosticarla.
        volcado = Path(tempfile.gettempdir()) / f"openrouter-{etiqueta}-{int(time.time())}.json"
        volcado.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        raise RuntimeError(
            f"{etiqueta}: OpenRouter devolvió una respuesta sin contenido "
            f"(finish_reason={eleccion.get('finish_reason')!r}, "
            f"native={eleccion.get('native_finish_reason')!r}, usage={uso}). "
            f"Respuesta completa en {volcado}")
    return schema.model_validate_json(contenido)


def generar_informe(transcripcion: str, convocatoria: bytes | None = None) -> InformePleno:
    fuentes = f"{len(transcripcion):,} caracteres de transcripción"
    if convocatoria:
        fuentes += f" + convocatoria ({len(convocatoria) // 1024} KB)"
    _log(f"  → GENERADOR ({fuentes})")
    informe = _llamar_llm(PROMPT_GENERADOR, f"TRANSCRIPCIÓN DEL PLENO:\n\n{transcripcion}",
                             InformePleno, convocatoria, "generador")
    resolutiva = sum(1 for p in informe.orden_del_dia if p.parte == "resolutiva")
    _log(f"     sesión {informe.tipo_sesion} · "
         f"{_plural(len(informe.orden_del_dia), 'punto', 'puntos')} "
         f"({resolutiva} resolutiva / {len(informe.orden_del_dia) - resolutiva} control) · "
         f"{_plural(len(informe.ruegos_y_preguntas), 'bloque', 'bloques')} de ruegos")
    for punto in informe.orden_del_dia:
        numero = f"{punto.numero}º" if punto.numero is not None else "—"
        _log(f"       {numero} {punto.titulo}")
    return informe


def auditar_informe(transcripcion: str, informe: InformePleno,
                    convocatoria: bytes | None = None) -> AuditoriaInforme:
    # El auditor recibe la convocatoria igual que el generador. Sin ella marcaría
    # cada título tomado del orden del día como afirmación no respaldada — la
    # transcripción trae el nombre destrozado por Whisper — y quemaría las tres
    # vueltas sin arreglar nada. Es el mismo motivo por el que recibe CORPORACION.
    _log("  → AUDITOR (busca afirmaciones que la transcripción no respalde)")
    contenido = (f"TRANSCRIPCIÓN DEL PLENO:\n\n{transcripcion}\n\n"
                 f"INFORME A AUDITAR (JSON):\n\n{informe.model_dump_json()}")
    auditoria = _llamar_llm(PROMPT_AUDITOR, contenido, AuditoriaInforme,
                               convocatoria, "auditor")
    if not auditoria.problemas:
        _log("     visto bueno, sin objeciones")
    else:
        _log(f"     {_plural(len(auditoria.problemas), 'objeción', 'objeciones')}:")
        for p in auditoria.problemas:
            _log(f"       • [{p.seccion}] {p.afirmacion_dudosa}")
            _log(f"         motivo: {p.motivo}")
    return auditoria


def corregir_informe(transcripcion: str, informe: InformePleno, problemas: list[Problema],
                     convocatoria: bytes | None = None) -> InformePleno:
    probs = "\n".join(f"- [{p.seccion}] {p.afirmacion_dudosa} → {p.motivo} (evidencia: {p.evidencia})"
                      for p in problemas)
    contenido = (f"TRANSCRIPCIÓN DEL PLENO:\n\n{transcripcion}\n\n"
                 f"INFORME COMPLETO (JSON):\n\n{informe.model_dump_json()}\n\n"
                 f"PROBLEMAS DETECTADOS POR EL AUDITOR:\n{probs}")
    _log(f"  → CORRECTOR ({_plural(len(problemas), 'objeción', 'objeciones')} que resolver)")
    return _llamar_llm(PROMPT_CORRECTOR, contenido, InformePleno, convocatoria, "corrector")


def bucle_informe(transcripcion: str, convocatoria: bytes | None = None,
                  generar=None, auditar=None, corregir=None):
    """Generador → auditor → (corrector → auditor)* con tope MAX_VUELTAS.

    `convocatoria`: bytes del PDF del orden del día, o None. Lo reciben los tres
    roles; el auditor también, o marcaría como inventado todo lo que salga de ella.

    Devuelve (informe, problemas_pendientes). Si problemas_pendientes no está vacía,
    esos puntos se listan por consola al terminar, no se escriben en el acta.
    Los kwargs permiten inyectar fakes en los tests; a los fakes no se les pasa la
    convocatoria, así que su firma no cambia.
    """
    # Solo la ejecución real narra su progreso: si hay fakes inyectados estamos en
    # los tests, y ahí las cabeceras de vuelta solo ensucian la salida.
    narrar = not any((generar, auditar, corregir))
    generar = generar or (lambda t: generar_informe(t, convocatoria))
    auditar = auditar or (lambda t, i: auditar_informe(t, i, convocatoria))
    corregir = corregir or (lambda t, i, p: corregir_informe(t, i, p, convocatoria))

    informe = generar(transcripcion)
    problemas = auditar(transcripcion, informe).problemas
    vueltas = 0
    while problemas and vueltas < MAX_VUELTAS:
        if narrar:
            _log(f"\n  ── vuelta {vueltas + 1} de {MAX_VUELTAS} ──")
        informe = corregir(transcripcion, informe, problemas)
        vueltas += 1
        problemas = auditar(transcripcion, informe).problemas
    if narrar:
        _log(f"\n  bucle terminado: {_plural(vueltas, 'vuelta', 'vueltas')}, "
             f"{_plural(len(problemas), 'objeción', 'objeciones')} sin resolver")
    return informe, problemas
