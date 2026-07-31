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
