#!/usr/bin/env python3
"""
plenos_informe.py - Esquemas, prompts y bucle LLM del informe de plenos.

El modelo (Gemini) devuelve SIEMPRE JSON contra estos esquemas pydantic.
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
    titulo: str
    debate: str = Field(description="Resumen fiel del debate de este punto, sin añadir nada no dicho")
    votacion: Votacion | None = Field(None, description="null si el punto no se sometió a votación")


class Intervencion(BaseModel):
    interviniente: str = Field(description=(
        "Nombre o cargo SOLO si la grabación lo hace explícito (p. ej. 'tiene la palabra "
        "la concejala de cultura'); si no, exactamente 'no identificado en la grabación'. "
        "Prohibido atribuir por deducción."))
    resumen: str


class InformePleno(BaseModel):
    """Informe estructurado de un pleno. Lo devuelven el generador y el corrector."""
    fecha_pleno: str | None = Field(None, description="YYYY-MM-DD solo si se menciona en la grabación; si no, null")
    resumen_ejecutivo: str = Field(description="2-4 párrafos con lo esencial del pleno")
    orden_del_dia: list[PuntoOrdenDia]
    intervenciones: list[Intervencion] = Field(description="Principales intervenciones por partido/concejal")
    ruegos_y_preguntas: list[str] = Field(description="Un elemento por ruego o pregunta; lista vacía si no hubo turno")
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

PROMPT_GENERADOR = """Eres el redactor de informes de los plenos del Ayuntamiento de
Enguídanos (Cuenca). Recibes la transcripción literal de un pleno, con marcas de tiempo
[HH:MM:SS] al inicio de cada segmento, y produces un informe estructurado en el JSON
que se te pide.

REGLAS INNEGOCIABLES:
1. Usa ÚNICAMENTE información presente en la transcripción. Prohibido inferir,
   completar huecos o usar conocimiento externo.
2. Si un dato no consta o no se entiende, usa la vía de escape del esquema:
   null, "no consta", "sin votación" o "no identificado en la grabación", según el campo.
3. Cada votación debe llevar el timestamp donde se anuncia su resultado. Los números
   de votos solo si se dicen en voz alta; si se aprueba "por unanimidad" sin contar,
   modalidad="unanimidad" y los números en null.
4. Atribuye una intervención a una persona SOLO si la propia grabación la identifica
   ("tiene la palabra el concejal de...", "responde la alcaldesa..."). Nunca por deducción.
5. La transcripción es automática y puede contener errores; si un fragmento es
   incoherente, no lo interpretes creativamente: descártalo o marca "no consta".
6. Redacta en español claro y neutro, apto para un documento municipal público.
"""

PROMPT_AUDITOR = """Eres el auditor de calidad de informes de plenos del Ayuntamiento de
Enguídanos. Recibes la transcripción literal de un pleno (con marcas [HH:MM:SS]) y un
informe en JSON generado a partir de ella. Tu único trabajo: encontrar afirmaciones del
informe que la transcripción NO respalde.

Comprueba una a una las afirmaciones verificables: resultados y números de votaciones,
nombres y cargos, importes, fechas, acuerdos adoptados y atribuciones de intervenciones.

Para cada problema devuelve: la sección, la afirmación dudosa, el motivo y una cita
literal de la transcripción como evidencia. Si el informe es fiel a la transcripción,
devuelve la lista de problemas VACÍA. No inventes problemas menores de estilo: solo
faltas de fidelidad a la fuente."""

PROMPT_CORRECTOR = """Eres el corrector de informes de plenos del Ayuntamiento de
Enguídanos. Recibes: la transcripción literal (con marcas [HH:MM:SS]), el informe completo
en JSON, y la lista de problemas detectados por un auditor (cada uno con su evidencia).

Devuelve el informe COMPLETO corregido, en el mismo esquema JSON:
1. Corrige exclusivamente lo señalado en los problemas, apoyándote en la transcripción.
2. Si la transcripción no permite resolver un problema, aplica la vía de escape del
   esquema (null, "no consta", "no identificado en la grabación") en ese dato.
3. No toques el resto del informe.
4. Mismas reglas que el redactor: nada que no esté en la transcripción."""


# ══════════════════════════════════════════════════════════════════════════════
# Llamadas a Gemini y bucle de fiabilidad
# ══════════════════════════════════════════════════════════════════════════════

import os

MAX_VUELTAS = 3
MODELO_DEFECTO = "gemini-2.5-pro"


def _reintentar_gemini(fn, intentos: int = 4):
    """Ejecuta fn(); ante 429 o error de servidor (5xx, incl. "high demand") reintenta
    con el mismo backoff exponencial que _reintentar() en procesar_pleno.py (2,4,8 min)."""
    import time
    from google.genai import errors as genai_errors

    for i in range(intentos):
        try:
            return fn()
        except genai_errors.APIError as e:
            if e.code not in (429, 500, 502, 503) or i == intentos - 1:
                raise
            time.sleep(120 * 2 ** i)


def _llamar_gemini(instrucciones: str, contenido: str, schema: type[BaseModel]) -> BaseModel:
    """Una llamada a Gemini con salida estructurada validada contra `schema`."""
    from google import genai  # import perezoso: los tests no necesitan el SDK

    def llamada():
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        return client.models.generate_content(
            model=os.environ.get("GEMINI_MODEL", MODELO_DEFECTO),
            contents=contenido,
            config={
                "system_instruction": instrucciones,
                "response_mime_type": "application/json",
                "response_schema": schema,
                "temperature": 0,
            },
        )

    resp = _reintentar_gemini(llamada)
    if resp.parsed is not None:
        return resp.parsed
    return schema.model_validate_json(resp.text)


def generar_informe(transcripcion: str) -> InformePleno:
    return _llamar_gemini(PROMPT_GENERADOR, f"TRANSCRIPCIÓN DEL PLENO:\n\n{transcripcion}", InformePleno)


def auditar_informe(transcripcion: str, informe: InformePleno) -> AuditoriaInforme:
    contenido = (f"TRANSCRIPCIÓN DEL PLENO:\n\n{transcripcion}\n\n"
                 f"INFORME A AUDITAR (JSON):\n\n{informe.model_dump_json()}")
    return _llamar_gemini(PROMPT_AUDITOR, contenido, AuditoriaInforme)


def corregir_informe(transcripcion: str, informe: InformePleno, problemas: list[Problema]) -> InformePleno:
    probs = "\n".join(f"- [{p.seccion}] {p.afirmacion_dudosa} → {p.motivo} (evidencia: {p.evidencia})"
                      for p in problemas)
    contenido = (f"TRANSCRIPCIÓN DEL PLENO:\n\n{transcripcion}\n\n"
                 f"INFORME COMPLETO (JSON):\n\n{informe.model_dump_json()}\n\n"
                 f"PROBLEMAS DETECTADOS POR EL AUDITOR:\n{probs}")
    return _llamar_gemini(PROMPT_CORRECTOR, contenido, InformePleno)


def bucle_informe(transcripcion: str, generar=None, auditar=None, corregir=None):
    """Generador → auditor → (corrector → auditor)* con tope MAX_VUELTAS.

    Devuelve (informe, problemas_pendientes). Si problemas_pendientes no está
    vacía, el informe se publica con esos puntos marcados como "no verificado".
    Los kwargs permiten inyectar fakes en los tests.
    """
    generar = generar or generar_informe
    auditar = auditar or auditar_informe
    corregir = corregir or corregir_informe

    informe = generar(transcripcion)
    problemas = auditar(transcripcion, informe).problemas
    vueltas = 0
    while problemas and vueltas < MAX_VUELTAS:
        informe = corregir(transcripcion, informe, problemas)
        vueltas += 1
        problemas = auditar(transcripcion, informe).problemas
    return informe, problemas
