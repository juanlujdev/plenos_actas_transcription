#!/usr/bin/env python3
"""
plenos_informe.py - Esquemas, prompts y bucle LLM del informe de plenos.

El modelo devuelve SIEMPRE JSON contra estos esquemas pydantic.
Principio: la vía de escape está dentro del esquema — todo dato que la
transcripción pueda no contener es Optional o tiene un valor "no consta",
para que el esquema nunca fuerce al modelo a inventar.
"""

import difflib
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
          "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10,
          "noviembre": 11, "diciembre": 12}


def normalizar_fecha(texto: str) -> str | None:
    """Cualquier forma habitual de escribir una fecha → 'YYYY-MM-DD'; None si no hay ninguna.
    El modelo no siempre respeta el ISO que pide el esquema."""
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", texto)
    if m:
        a, mes, d = (int(g) for g in m.groups())
    else:
        m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", texto)
        if m:
            d, mes, a = (int(g) for g in m.groups())
        else:
            m = re.search(r"(\d{1,2})\s+de\s+(" + "|".join(_MESES) + r")\s+(?:de\s+)?(\d{4})",
                          texto, re.IGNORECASE)
            if not m:
                return None
            d, mes, a = int(m.group(1)), _MESES[m.group(2).lower()], int(m.group(3))
    if not (1 <= mes <= 12 and 1 <= d <= 31):
        return None
    return f"{a:04d}-{mes:02d}-{d:02d}"


def normalizar_hora(texto: str) -> str | None:
    """'12:02', '12:02 horas', 'las 12.02' → '12:02'; None si no es una hora de reloj.
    Un 'HH:MM:SS' se descarta a propósito: es una marca de tiempo de la transcripción."""
    if re.search(r"\d{1,2}[:.]\d{2}[:.]\d{2}", texto):
        return None
    m = re.search(r"(\d{1,2})[:.](\d{2})", texto)
    if not m:
        return None
    h, minutos = int(m.group(1)), int(m.group(2))
    return f"{h:02d}:{minutos:02d}" if h <= 23 and minutos <= 59 else None


# Fórmulas de escape del modelo cuando algo no consta; en campos que piden null no deben colarse como nombre.
_SIN_IDENTIFICAR = {"no identificado en la grabacion", "no identificada en la grabacion",
                    "no consta"}


def _normalizar_es(texto: str) -> str:
    """Minúsculas, sin acentos, sin puntuación de cierre ni espacios sobrantes."""
    sin_tildes = unicodedata.normalize("NFKD", texto.strip().lower())
    sin_tildes = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return sin_tildes.strip(" .,;:")


class Votacion(BaseModel):
    """Resultado de la votación de un punto. Solo datos oídos en la grabación."""
    resultado: Literal["aprobado", "rechazado", "sin votación", "no consta"]
    modalidad: Literal["unanimidad", "recuento", "no consta"]
    a_favor: int | None = Field(None, description="Solo si se dice el número en la grabación; si no, null")
    en_contra: int | None = Field(None, description="Solo si se dice el número en la grabación; si no, null")
    abstenciones: int | None = Field(None, description="Solo si se dice el número en la grabación; si no, null")
    voto_de_calidad: bool = Field(False, description=(
        "true SOLO si la grabación dice que el empate lo resuelve el voto de calidad de "
        "quien preside. Si hay empate y nadie menciona el voto de calidad, false."))
    timestamp: str | None = Field(None, description="HH:MM:SS de la transcripción donde se anuncia el resultado")

    @model_validator(mode="after")
    def _resultado_del_recuento(self):
        """Con el recuento completo y sin empate, el resultado se deduce por mayoría simple.
        El empate no se deduce: depende del voto de calidad."""
        if (self.resultado == "no consta" and self.a_favor is not None
                and self.en_contra is not None and self.a_favor != self.en_contra):
            self.resultado = "aprobado" if self.a_favor > self.en_contra else "rechazado"
            self.modalidad = "recuento"
        return self


class PuntoOrdenDia(BaseModel):
    numero: int | None = Field(None, description="Número del punto si se menciona; si no, null")
    timestamp: str | None = Field(None, description="HH:MM:SS de la transcripción donde empieza el debate de este punto")
    parte: Literal["resolutiva", "control"] = Field(description=(
        "'resolutiva' si el punto se somete a acuerdo del Pleno; 'control' para decretos "
        "de alcaldía, daciones de cuenta y todo aquello de lo que la Corporación solo se "
        "da por informada."))
    titulo: str = Field(description="Título del punto EN MAYÚSCULAS, como en un acta municipal")
    texto: str = Field(description=(
        "Deliberación del punto en prosa de acta, con las intervenciones incorporadas en el "
        "orden en que se producen. VARIOS PÁRRAFOS, separados por el escape JSON \\n\\n: "
        "uno por bloque de debate, de tres a seis frases cada uno. Un punto entero en un "
        "solo párrafo es un defecto. NO escribas aquí el acuerdo (va "
        "en `acuerdo`) ni los recuentos de votos (van en `votacion`): el documento los "
        "compone a partir de esos campos."))
    acuerdo: str | None = Field(None, description=(
        "Lo que el Pleno acuerda, redactado para continuar la fórmula 'El Pleno del "
        "Ayuntamiento ACUERDA, ' — así, en minúscula y sin repetir esa fórmula: "
        "'aprobar la apertura del patio de la Biblioteca durante el día', 'dejar el punto "
        "sobre la mesa, con el compromiso de...'. Un solo párrafo; solo desglosa en "
        "'PRIMERO. ... SEGUNDO. ...' si el Pleno adopta varios acuerdos distintos en el "
        "mismo punto. null en los puntos de control y en los que no se acuerda nada."))
    votacion: Votacion | None = Field(None, description="null si el punto no se sometió a votación")

    @model_validator(mode="after")
    def _acuerdo_limpio(self):
        """Quita la fórmula "El Pleno ... ACUERDA" que compone el documento y saca de
        `acuerdo` el cierre de los puntos de control. Normaliza en vez de fallar."""
        if not self.acuerdo:
            return self
        acuerdo = re.sub(r"^\s*el\s+pleno\s+del\s+ayuntamiento\s+ACUERDA[,:]?\s*",
                         "", self.acuerdo.strip(), flags=re.IGNORECASE)
        acuerdo = re.sub(r"^(por\s+unanimidad|por\s+mayoría)[,:]?\s*", "", acuerdo,
                         flags=re.IGNORECASE)
        if self.parte == "control":
            if acuerdo and acuerdo.rstrip(".") not in self.texto:
                self.texto = f"{self.texto.rstrip()}\n\n{acuerdo}"
            self.acuerdo = None
        else:
            self.acuerdo = acuerdo or None
        return self

    @field_validator("votacion", mode="before")
    @classmethod
    def _cadena_de_ausencia_es_null(cls, v):
        """La cadena "sin votación" donde va el objeto equivale a null; cualquier otra
        cadena se deja pasar para que pydantic falle."""
        if isinstance(v, str) and v.strip().lower() in {
                "sin votación", "sin votacion", "no consta", "null", ""}:
            return None
        return v


class VozIdentificada(BaseModel):
    """Una entrada del mapa de voces: qué persona hay detrás de una etiqueta de
    locutor, y la prueba que lo demuestra. Antes esa deducción vivía solo en la cabeza
    del modelo mientras redactaba, sin dejar rastro que el auditor —o la funcionaria—
    pudiera revisar; es la razón de ser de este modelo (ver DIARIZACION)."""
    etiqueta: str = Field(description="La etiqueta tal como aparece en la transcripción: 'A', 'B'...")
    persona: str = Field(description=(
        "Nombre oficial completo de la corporación, con tratamiento; la condición con la "
        "que se presenta un vecino asistente que no es de la corporación (nunca su nombre "
        "y apellidos); 'etiqueta con voces mezcladas' si la propia etiqueta afirma "
        "identidades incompatibles entre sí (ver DIARIZACION); o exactamente 'no "
        "identificado en la grabación' si la etiqueta no llega a identificarse."))
    evidencia: str = Field(description=(
        "Cita LITERAL de la transcripción que demuestra la identificación —o la "
        "exclusión: la frase donde esta voz nombra a otra persona también cuenta, "
        "porque descarta que sean la misma—. Sin una cita que lo sostenga, `persona` "
        "va a 'no identificado en la grabación'."))
    timestamp: str | None = Field(None, description="HH:MM:SS de la transcripción donde está esa cita")


class BloqueRuegos(BaseModel):
    """El acta agrupa los ruegos y preguntas por quien los formula."""
    formulados_por: str = Field(description=(
        "Quien formula el bloque, con tratamiento ('D. Joaquín Martínez'), SOLO si la "
        "grabación lo identifica; si no, exactamente 'no identificado en la grabación'."))
    puntos: list[str] = Field(description=(
        "Un elemento por ruego o pregunta, con su respuesta en el mismo elemento solo si "
        "es concluyente o importante para el acta (regla 14 bis)"))


class AsuntoNoConvocado(BaseModel):
    """Un tema tratado en el debate que no figura en el orden del día. NO se escribe en el
    acta —el acta numera lo convocado y lo que se trata como punto propio—: va solo a la
    guía de verificación, para que la secretaria vea de qué se habló y en qué minuto y
    decida ella si lo sintetiza y dónde (ver regla 16 ter)."""
    asunto: str = Field(description=(
        "Qué se trata, sintetizado en una o dos frases y atribuido a quien lo plantea. "
        "Una síntesis, no el debate."))
    surge_en: str | None = Field(None, description=(
        "Título del punto del orden del día en cuyo debate surge, escrito igual que en "
        "`orden_del_dia`; null si no surge dentro de ningún punto."))
    timestamp: str | None = Field(None, description=(
        "HH:MM:SS de la transcripción donde se trata este asunto"))


class InformePleno(BaseModel):
    """Contenido del acta de un pleno. Lo devuelven el generador y el corrector."""
    tipo_sesion: Literal["ordinaria", "extraordinaria", "no consta"] = Field(description=(
        "Tipo de sesión según lo que se diga en la grabación (la convocatoria suele leerse "
        "al inicio). Si no se dice, 'no consta': no lo deduzcas del contenido."))
    motivo_convocatoria: str | None = Field(None, description=(
        "Solo en sesiones extraordinarias y solo si se lee el motivo de la convocatoria; "
        "si no, null"))
    solicitantes: list[str] = Field(description=(
        "Solo en extraordinarias convocadas a petición de concejales: quién la solicita, "
        "con tratamiento, nombre y apellidos completos y grupo si consta ('D. Pedro José "
        "Martínez Martínez del Partido Popular'). Sale de la convocatoria o de la propia "
        "grabación. Lista vacía si la sesión no se convoca a solicitud de concejales."))
    fecha_pleno: str | None = Field(None, description="YYYY-MM-DD solo si se menciona en la grabación; si no, null")
    hora_inicio: str | None = Field(None, description=(
        "Hora de RELOJ a la que se abre la sesión, HH:MM, solo si se dice en la grabación; "
        "si no, null. Nunca la marca de tiempo [HH:MM:SS] de la transcripción, que cuenta "
        "desde el inicio del vídeo y no es una hora."))
    hora_fin: str | None = Field(None, description=(
        "Hora de RELOJ a la que se levanta la sesión, HH:MM, solo si se dice en la "
        "grabación; si no, null. Nunca la marca de tiempo de la transcripción: si nadie "
        "dice la hora al cerrar, este campo va a null y la secretaria lo rellena."))

    @field_validator("fecha_pleno", mode="before")
    @classmethod
    def _fecha_iso(cls, v):
        return normalizar_fecha(v) if isinstance(v, str) else v

    @field_validator("hora_inicio", "hora_fin", mode="before")
    @classmethod
    def _hora_de_reloj(cls, v):
        return normalizar_hora(v) if isinstance(v, str) else v
    presidente: str | None = Field(None, description=(
        "Quien preside la sesión, solo si la grabación lo identifica; si no, null"))

    @field_validator("presidente", mode="before")
    @classmethod
    def _presidente_o_nada(cls, v):
        """Convierte la fórmula de escape ("no identificado en la grabación") en null:
        al ser una cadena no vacía, `informe.presidente or HUECO` la daría por buena."""
        if isinstance(v, str) and _normalizar_es(v) in _SIN_IDENTIFICAR:
            return None
        return v
    asistentes: list[str] = Field(description=(
        "Miembros de la corporación cuya asistencia consta en la grabación (pase de lista "
        "o identificación explícita), con tratamiento y nombre completo tal como se escriben "
        "en el acta: 'D. Sergio de Fez Cerezuela', 'Dª. Mª Rosario Cerdán Pérez'. Lista "
        "vacía si no consta; nunca deduzcas asistencia."))
    ausentes: list[str] = Field(description=(
        "Miembros cuya ausencia se hace constar expresamente, con tratamiento y nombre "
        "completo. Lista vacía si no consta."))
    declaraciones_apertura: list[str] = Field(description=(
        "Las declaraciones formales que quien preside lee o pronuncia al abrir la sesión, "
        "antes de entrar en el primer punto: el aviso de que la sesión se graba y difunde, "
        "la constancia de que se preside por delegación, la exclusión o alteración de algún "
        "punto del orden del día, la justificación de una ausencia. Un elemento por "
        "declaración, en el orden en que se pronuncian, recogidas casi literalmente y "
        "corregido solo lo que sean errores evidentes de transcripción. Lista vacía si la "
        "sesión se abre sin ninguna declaración de este tipo."))
    identificacion_locutores: list[VozIdentificada] = Field(default_factory=list, description=(
        "El mapa de voces: una entrada por cada etiqueta de locutor que aparezca en la "
        "transcripción, rellenada ANTES de redactar el resto del informe (ver "
        "DIARIZACION). Solo se puede escribir un nombre en el acta si su etiqueta está "
        "identificada aquí, con la cita que lo demuestra. Lista vacía únicamente en "
        "informes generados antes de que este campo existiera."))
    orden_del_dia: list[PuntoOrdenDia]
    ruegos_y_preguntas: list[BloqueRuegos] = Field(description="Lista vacía si no hubo turno")
    asuntos_no_convocados: list[AsuntoNoConvocado] = Field(default_factory=list, description=(
        "Los temas tratados en la sesión que NO son del orden del día ni se someten a "
        "acuerdo: los asuntos paralelos que salen dentro del debate de un punto (regla 16 "
        "ter). No se imprimen en el acta. Lista vacía si no hay ninguno."))
    resumen_corto: str = Field(description="2-3 frases para la tarjeta de la web")


class Problema(BaseModel):
    seccion: str = Field(description="Sección del informe donde está la afirmación dudosa")
    afirmacion_dudosa: str
    motivo: str
    evidencia: str = Field(description="Cita literal de la transcripción que contradice o no respalda la afirmación")


class AuditoriaInforme(BaseModel):
    """Resultado del auditor. Lista vacía = visto bueno."""
    problemas: list[Problema]


# ══ Prompts de los tres roles ══

# Quién preside de hecho; revisar tras elecciones, cambio de Alcaldía o delegación.
# El título debe ser el del nombramiento, NO "Alcaldesa en funciones".
PRESIDENCIA = {
    # Cómo se nombra a quien preside en el cuerpo del acta.
    "tratamiento": "la Sra. Teniente de Alcalde",
    # Fórmula del encabezado, detrás de "bajo la Presidencia de ".
    "formula": ("la segunda Teniente Alcalde Dª Lorena Luján Chujfi, que actúa en virtud "
                "de la delegación de funciones efectuadas por el Sr. Alcalde – Presidente, "
                "D. Sergio de Fez Cerezuela"),
    # Género de las dos fórmulas fijas de la plantilla.
    "abre_la_sesion": "la Presidenta abre la sesión",
    "secretaria": "la Secretaria",
}

# Lugares que el transcriptor deforma. Los usan la regla 20, el corrector y los keyterms de AssemblyAI.
TOPONIMOS = ["Enguídanos", "Las Chorreras", "Pesquera", "Playeta", "Keltiber",
             "Hoya de las Abejas", "PR-53", "GR-64", "GR-66"]


def parsear_intervinientes(texto: str) -> list[dict]:
    """Una persona por línea: 'Nombre completo = apodo1, apodo2' (apodos opcionales)."""
    personas = []
    for linea in texto.splitlines():
        nombre, _, apodos = linea.strip().lstrip("-•* ").partition("=")
        nombre = nombre.strip()
        if nombre:
            personas.append({"nombre": nombre,
                             "apodos": [a.strip() for a in apodos.split(",") if a.strip()]})
    return personas


def bloque_intervinientes(intervinientes: list[dict] | None) -> str:
    """Mensaje con los intervinientes de este pleno, o vacío si no hay."""
    if not intervinientes:
        return ""
    lineas = []
    for p in intervinientes:
        apodos = ", ".join(f"«{a}»" for a in p.get("apodos", []))
        lineas.append(f"- {p['nombre']}" + (f" — en la sesión le llaman: {apodos}" if apodos else ""))
    return "INTERVINIENTES DE ESTA SESIÓN:\n" + "\n".join(lineas) + "\n\n"


# Reglas de uso de los intervinientes; el dato por pleno viaja en el mensaje (bloque_intervinientes).
INTERVINIENTES_SESION = """INTERVINIENTES DE LA SESIÓN (opcional):
Puede que el mensaje traiga, antes de la transcripción, un bloque "INTERVINIENTES DE ESTA
SESIÓN": las personas que la secretaría sabe que han intervenido y el nombre o apodo con
el que se las llama en la sala. Si no viene, ignora esta sección.
- Es una AYUDA para reconocer de quién se habla y para escribir bien un nombre, y se
  CONTRASTA con el listado de la Corporación de arriba, que es la fuente oficial de cargos
  y tratamientos. Si una persona figura en los dos, el cargo y el tratamiento los da el
  listado, y el bloque aporta cómo la llaman. Si figura en el bloque y no en el listado,
  escríbela con "D."/"Dª" y el nombre tal como viene, sin inventarle cargo: el cargo solo
  si la grabación lo dice. Si el bloque y el listado discrepan sobre cómo se llama a una
  misma persona, valen los dos nombres para reconocerla.
- NO prueba nada de lo ocurrido. Que alguien figure en el bloque no demuestra que asistiera
  (`asistentes` y `ausentes` salen de la grabación) ni que dijera una frase concreta; y no
  rellena el mapa de voces: una etiqueta se identifica con una cita literal de la
  transcripción. Lo que sí vale como cita es que alguien nombre a esa etiqueta por el
  apodo del bloque ("Nando", "Chari"): es nombrarla.
- Un nombre de pila o un apodo que pueda ser de dos personas (dos Martínez, dos Joaquín)
  no identifica a ninguna: "no identificado en la grabación".
- En el acta, siempre el nombre oficial completo con su tratamiento (ver APODOS). Si el
  bloque trae a un particular que no es de la Corporación, su nombre solo sirve para
  reconocerlo: sigue sin escribirse (ver PÚBLICO ASISTENTE).
- El auditor no señala como inventado un nombre corregido gracias a este bloque; sí señala
  una atribución que ni la grabación ni el mapa de voces sostienen, venga o no en el bloque."""


CORPORACION = f"""CORPORACIÓN MUNICIPAL (para escribir bien los nombres —ver regla 4— y
acertar el tratamiento —ver regla 8—):
- Sergio de Fez Cerezuela — ALCALDE-PRESIDENTE (PSOE), de baja médica. Sigue siendo el
  Alcalde a todos los efectos: es "el Sr. Alcalde D. Sergio de Fez Cerezuela". Cuando
  asiste a la sesión e interviene en el debate sin presidirla, lo hace como un concejal
  más: "el Sr. concejal D. Sergio de Fez Cerezuela".
- Lorena Luján Chujfi — SEGUNDA TENIENTE DE ALCALDE (PSOE). Preside las sesiones en
  virtud de la delegación de funciones efectuada por el Sr. Alcalde-Presidente.
  NO es Alcaldesa ni Alcaldesa en funciones y NUNCA se la nombra así en el acta: es
  {PRESIDENCIA['tratamiento']}, o Dª Lorena Luján Chujfi.
- Mª Rosario Cerdán Pérez — Concejala, equipo de gobierno (PSOE). En la sesión se
  dirigen a ella como "Chari": es la misma persona. Es ADEMÁS la presidenta de la
  Asociación de Jubilados, y en el turno de ruegos interviene sobre asuntos de esa
  asociación. Una voz que dice presidir la Asociación de Jubilados es ELLA, una
  concejala: no es público asistente. En el acta se la nombra siempre "Dª Mª Rosario
  Cerdán Pérez", y si ella misma invoca esa condición puede hacerse constar ("Dª Mª
  Rosario Cerdán Pérez, en su condición de presidenta de la Asociación de Jubilados,
  ruega que..."). No confundirla con los socios de esa asociación que asisten como
  público y también hablan de sus asuntos: esos sí son vecinos.
- Mario Cerdán Ochoa — Concejal, equipo de gobierno (PSOE)
- Joaquín Martínez Luján — Concejal, oposición (PP)
- Pedro José Martínez Martínez — Concejal, oposición (PP)
  ATENCIÓN: son DOS personas distintas que comparten apellido. "Martínez" a secas no
  identifica a ninguno de los dos. Para atribuirle una intervención a uno de ellos hace
  falta el nombre de pila, o que la etiqueta de locutor esté identificada según las
  reglas de arriba. Si solo se oye el apellido, la atribución es "no identificado en la
  grabación".
- Fernando Pons Mayor — Concejal, oposición (Agrupación Independiente de Enguídanos)
- Mª Elena Valera Navarro — Secretaria-Interventora del Ayuntamiento. NO es miembro de
  la Corporación y no vota: da fe de la sesión, lee acuerdos e informa cuando se le pide.
  Su voz sale en la grabación, pero nunca va en `asistentes` ni en `ausentes`.

APODOS: un apodo que se oiga en la grabación (como "Chari" arriba) sirve para
reconocer de quién se habla — también para el mapa de voces de DIARIZACION —, pero
nunca para escribirlo en el acta: el documento usa siempre el nombre oficial completo
con su tratamiento, aunque en toda la sesión no se la llame de otra forma. Vale como
regla general, no solo para ese caso.

PÚBLICO ASISTENTE: a las sesiones asiste público, y algunos vecinos intervienen,
sobre todo en el turno de ruegos y preguntas. Cambian de un pleno a otro y NO están
en ningún listado: no se les puede identificar "por descarte" contra la Corporación,
por mucho que una etiqueta de locutor no encaje con ninguno de los nombres de arriba.
- NO son miembros de la Corporación: no votan, no se cuentan en ningún recuento (ver
  RECUENTOS DE VOTOS), y nunca van en `asistentes` ni en `ausentes` — esas dos listas
  son solo de la Corporación.
- Se les nombra por el CARGO o la condición con la que se presentan ("el presidente
  de la asociación de vecinos", "un representante de la asociación de cazadores"); si
  no se identifican así, "un vecino asistente" o "una vecina asistente", según se
  aprecie. NUNCA con nombre y apellidos, aunque se digan en la grabación: el acta es
  un documento público, y el nombre de un particular no se recoge si basta con su
  condición para identificar la intervención.
- Una voz que el mapa de DIARIZACION deja como "no identificado en la grabación"
  puede perfectamente ser público, no necesariamente un concejal de los que faltan
  por identificar: tratar el listado de la Corporación como si fuera la lista
  completa de quien puede hablar en la sesión es exactamente el error que dio pie a
  esta regla — atribuirle a una concejala con nombre y apellidos lo que dijo una
  vecina asistente.

Ese listado da el CARGO y el TRATAMIENTO, que son datos oficiales y no dependen de la
grabación. Lo que sigue exigiendo que la grabación lo diga es QUIÉN HABLA y QUÉ DICE:
el listado nunca sirve para rellenar el campo `presidente` ni para atribuir
intervenciones que la grabación no atribuye (reglas 1, 4 y 5)."""


DIARIZACION = """ETIQUETAS DE LOCUTOR:
La transcripción viene diarizada: cada línea es [HH:MM:SS] seguido de "Interviniente A:",
"Interviniente B:"... Esas etiquetas las pone el transcriptor separando VOCES, no
identidades: sabe que dos intervenciones son de la misma persona, no de quién son.

PRIMERO EL MAPA, DESPUÉS EL ACTA: antes de redactar nada, rellena
`identificacion_locutores` con una entrada por cada etiqueta que aparezca en la
transcripción. Solo puedes escribir un nombre en el acta si esa etiqueta está
identificada en el mapa, con su cita como prueba; si no lo está, la atribución es "no
identificado en la grabación" aunque te parezca evidente por el contexto.

- La misma etiqueta es la misma persona durante toda la sesión — SALVO que el
  transcriptor haya fusionado dos voces parecidas bajo una sola etiqueta. La señal de
  esa fusión es que la etiqueta acabe afirmando identidades INCOMPATIBLES entre sí: en
  el caso real que motivó esta regla, la etiqueta que abre la sesión presidiendo dice,
  tres horas después, "llevo como presidenta de la asociación de jubilados" — nadie es
  las dos cosas.
- Cuando una etiqueta se contradiga así, NO elijas entre las dos identidades: la
  contradicción es la prueba de que la etiqueta está contaminada, no una pista de cuál
  de las dos es la buena. Márcala en el mapa como "etiqueta con voces mezcladas"
  (`persona` puede llevar ese valor) y atribuye sus intervenciones a "no identificado en
  la grabación", salvo aquellas que se identifiquen a sí mismas.
- Y al revés: una intervención que se identifica a sí misma manda sobre lo que diga su
  etiqueta, aunque esa etiqueta esté asociada a otra persona en el mapa. Si dentro de una
  etiqueta contaminada alguien dice "llevo como presidenta de la asociación de
  jubilados", esa intervención es de ella, aunque la misma etiqueta la lleve también
  quien preside.
- REGLA DE TURNOS ALTERNOS: dos etiquetas que se ALTERNAN hablando dentro de una misma
  conversación —se responden, se interrumpen, intervienen seguidas en el mismo
  intercambio— son PERSONAS DISTINTAS, y por tanto no pueden identificarse en el mapa
  como la misma persona. Si el mapa acaba asignando la misma persona a dos etiquetas que
  se alternan así, una de las dos identificaciones es falsa: márcalo como conflicto y
  manda las dos a "no identificado en la grabación", salvo que una de las dos pruebas sea
  claramente más fuerte según la JERARQUÍA DE PRUEBAS de más abajo, en cuyo caso esa
  prevalece y la otra etiqueta se queda sin identificar. Y al contrario: si dos etiquetas
  NUNCA se alternan entre sí, sí pueden ser la misma persona partida en dos voces por el
  transcriptor —eso es benigno—, así que no marques conflicto solo porque dos etiquetas
  compartan persona en el mapa.
- Si en cualquier momento la grabación identifica a quien lleva una etiqueta —se
  presenta, alguien la nombra mientras habla o respondiéndole directamente, o se dirige
  a ella por su nombre o su cargo de forma inequívoca—, atribúyele TODAS las
  intervenciones de esa etiqueta, también las anteriores. Una sola identificación vale
  para toda la sesión.
- Que la Presidencia dé la palabra a alguien POR SU NOMBRE no identifica la voz que
  habla a continuación: la palabra puede acabar tomándola otra persona, o intercalarse
  otras voces antes de que responda quien fue nombrado. Es una expectativa de quién va
  a hablar, no una identificación de quién habló.
- REGLA DE EXCLUSIÓN: si una etiqueta llama a alguien por su nombre, esa etiqueta NO es
  esa persona. Descartar así es tan valioso como identificar: si la etiqueta B le dice
  "esto ocurrió, Joaquín", la etiqueta B no puede ser Joaquín, aunque la Presidencia le
  hubiera dado la palabra a él momentos antes.
- SEÑALES DE PÚBLICO DENTRO DE UNA ETIQUETA DE CONCEJAL: si una intervención de una
  etiqueta identificada como concejal trata de "usted" a la Corporación, habla en nombre
  de un colectivo de vecinos ("nos ha quitado la asociación", "a nosotros los
  jubilados") o interviene en el turno del público, es una voz distinta mezclada en esa
  etiqueta: esa intervención NO se atribuye al concejal. Caso real del 3-IX: la etiqueta
  de un concejal llevaba también a un vecino que preguntó por el bar del hogar del
  jubilado ("A ver si usted se puede enterar... por qué el ayuntamiento nos ha quitado la
  asociación"), y el acta puso esa pregunta en los ruegos del concejal.
- Si una etiqueta no se identifica nunca, sus intervenciones siguen siendo "no
  identificado en la grabación". No adivines por el orden de palabra, por el tema del
  que habla, por cuánto habla ni por el reparto de la corporación.
- JERARQUÍA DE PRUEBAS: no todas las identificaciones valen lo mismo. De más fuerte a
  más débil: (1) la persona SE IDENTIFICA A SÍ MISMA ("soy concejal del Ayuntamiento",
  "llevo como presidenta de la asociación de jubilados"); (2) alguien la NOMBRA
  RESPONDIÉNDOLE directamente o mientras ella habla; (3) alguien SE DIRIGE A ELLA por su
  nombre o su cargo de forma inequívoca. Si en algún momento aparece una prueba más
  fuerte que contradiga a una más débil que ya tenías anotada, gana la prueba fuerte, NO
  la que llegó primero: una sola identificación vale para toda la sesión, pero no
  cualquier identificación vale igual. La `evidencia` que quede en el mapa es la de la
  prueba que has aceptado, no la de la primera que encontraste.
- La evidencia de cada entrada del mapa es una CITA LITERAL de la transcripción, nunca
  un resumen de lo que crees que pasó. Si no hay una cita que lo demuestre, esa etiqueta
  va como "no identificado en la grabación": un acta que dice que no consta es preferible
  a un acta que atribuye mal una intervención.
- Las etiquetas no se escriben en el acta: son andamiaje de la transcripción."""


# Va a los tres roles: el generador también puede inventar recuentos.
RECUENTOS = """RECUENTOS DE VOTOS:
- El campo `votacion` de un punto es un OBJETO o `null`, nunca una cadena de texto. Si el
  punto no se somete a votación, `votacion` va a `null`; si se somete pero no llega a
  votarse, `votacion` es un objeto con `resultado: "sin votación"`. Ese literal vive
  DENTRO del objeto, jamás en lugar del objeto.
- Un recuento solo lleva número si ese número se oye en la grabación.
- Si el recuento se verbaliza de forma ininteligible, o si no consta el sentido del voto
  de TODOS los presentes, los tres campos (`a_favor`, `en_contra`, `abstenciones`) van a
  `null`. Un recuento incompleto NO es un recuento: escribir solo la parte audible
  afirma en el acta que ese fue el resultado de la votación.
- `resultado` y `modalidad` se conservan si sí constan. Que no se sepa el recuento no
  significa que no se sepa si el asunto se aprobó o se rechazó: si la grabación deja
  claro el resultado, ese resultado se escribe aunque los números vayan a `null`.
- Deducir los votos que faltan restando del número de asistentes, del reparto de la
  corporación o del sentido del debate es inventar: prohibido.
- Las abstenciones funcionan igual que los demás votos: si alguien dice que se abstiene,
  cuenta esa abstención. Si nadie la menciona, `abstenciones` va a `null`, nunca a 0. Un
  0 afirma que nadie votó así, y eso hay que oírlo igual que cualquier otra cifra."""


PROMPT_GENERADOR = f"""Eres el redactor de informes de los plenos del Ayuntamiento de
Enguídanos (Cuenca). Recibes la transcripción literal de un pleno, con marcas de tiempo
[HH:MM:SS] al inicio de cada segmento, y produces un informe estructurado en el JSON
que se te pide.

{CORPORACION}

{INTERVINIENTES_SESION}

{DIARIZACION}

{RECUENTOS}

REGLAS INNEGOCIABLES:
1. Usa ÚNICAMENTE información presente en la transcripción. Prohibido inferir,
   completar huecos o usar conocimiento externo.
2. Si un dato no consta o no se entiende, usa la vía de escape del esquema:
   null, "no consta", "sin votación" o "no identificado en la grabación", según el campo.
3. Cada votación debe llevar el timestamp donde se anuncia su resultado, y sus números
   se rigen por el bloque RECUENTOS DE VOTOS de arriba. Si se aprueba "por unanimidad"
   sin contar, modalidad="unanimidad" y los números en null.
3 bis. Cada punto del orden del día debe llevar en `timestamp` el momento de la
   transcripción en que arranca su debate — mismo formato que el de la votación, pero
   referido al inicio del punto, no a su resultado.
4. La transcripción es automática y deforma los nombres propios. Cuando aparezca un
   nombre que se corresponda claramente por sonido con uno de la corporación (p. ej.
   "Féceres Zuela" → "Sergio de Fez Cerezuela"; "Zatanochoa" → "Mario Cerdán Ochoa"),
   escríbelo en su forma correcta. Esa lista sirve SOLO para escribir bien un nombre que
   la grabación pronuncia: nunca para deducir quién habla ni para atribuir intervenciones
   que la grabación no atribuye.
5. Atribuye una intervención a una persona SOLO si la propia grabación la identifica
   ("tiene la palabra el concejal de...", "responde la Presidencia..."), directamente o a
   través de su etiqueta de locutor según las reglas de arriba. Nunca por deducción.
6. Si un fragmento es incoherente por errores de transcripción, no lo interpretes
   creativamente: descártalo o marca "no consta".
6 bis. NO RECONSTRUYAS LO QUE EL AUDIO NO DICE CLARO. Cuando un lugar, el objeto de una
   solicitud, un destinatario, una cifra, una norma o un nombre sale de un fragmento
   confuso (palabras sueltas, frases que no cierran, términos que no encajan en la
   frase), NO lo completes con lo que sería verosímil por el contexto. Escribe solo lo
   que una frase clara de la transcripción sostiene ("una solicitud a la Consejería") y
   deja fuera el detalle dudoso. Prueba: de cada dato concreto del acta tiene que poder
   señalarse una frase clara que lo diga; si solo hay un fragmento confuso, el dato no
   entra. Un acta más corta que acierta es preferible a una completa que inventa. Esto
   limita también la regla 4: se corrige un nombre propio por su sonido, no un concepto
   ni el motivo de una solicitud.

REDACCIÓN — ESTILO DE ACTA MUNICIPAL:
7. Escribe en PRESENTE de indicativo, con el registro impersonal y formal propio de un
   acta: "{PRESIDENCIA['tratamiento'].capitalize()} da cuenta...", "Se acuerda...".
   Nunca en pasado.
8. Usa el tratamiento formal del acta —D., Dª, Sr. concejal, Sra. concejala— seguido del
   nombre y los APELLIDOS COMPLETOS la primera vez que aparece cada persona en un punto:
   "el Sr. concejal D. Fernando Pons Mayor", "la concejala Dª Mª Rosario Cerdán Pérez".
   Después basta con la forma corta ("el Sr. Pons"). Cada miembro de la Corporación se
   nombra por el cargo que consta en el listado de arriba, no por el papel que le supongas
   en la sesión. Introduce las intervenciones con la fórmula habitual: "Toma la palabra el
   Sr. concejal D. Fernando Pons Mayor, quien...", "Interviene el concejal D. Joaquín
   Martínez Luján...", "Le responde {PRESIDENCIA['tratamiento']} que...".
9. Los títulos de los puntos van EN MAYÚSCULAS, como en las actas. Si el título del orden
   del día enumera varios asuntos (varias obras, varios expedientes), déjalo en el título
   solo el enunciado común y abre el texto del punto con la relación en una lista de
   guiones, un elemento por línea.
10. Las intervenciones van DENTRO del texto del punto al que corresponden, en el orden en
    que se producen. No hay una sección separada de intervenciones.
11. El acuerdo NO se escribe en `texto`: va en el campo `acuerdo`, en un solo párrafo que
    continúe la fórmula "El Pleno del Ayuntamiento ACUERDA, " — SIN escribir esa fórmula
    dentro del campo y sin repetir la modalidad de la votación: las pone el documento a
    partir de `acuerdo` y `votacion`.
    Tampoco se anticipa el resultado dentro de `texto` con una fórmula coloquial: nada de
    "se da el punto por aprobado", "queda aprobado", "se aprueba por unanimidad" ni
    equivalentes al cerrar el debate. El documento ya escribe a continuación la fórmula
    jurídica completa, así que esa frase hace que el acta diga dos veces lo mismo, una de
    ellas en un registro que no es el suyo. `texto` termina en la última intervención del
    debate. En los puntos de control `acuerdo` va a null; su
    cierre ("La Corporación se da por informada") es la última frase de `texto`.
    Solo se desglosa en
    "PRIMERO. ... SEGUNDO. ..." si el Pleno adopta varios acuerdos distintos en el mismo
    punto. Un punto resolutivo que no llega a votarse también puede tener acuerdo ("dejar
    el punto sobre la mesa, con el compromiso de...") si eso es lo que se conviene en la
    sesión.
12. Los puntos de actividad de control terminan con "La Corporación se da por informada."
    cuando así ocurre en la grabación.
13. Cuando una frase sea textual de un concejal y valga la pena recogerla tal cual,
    entrecomíllala. Usa SIEMPRE comillas tipográficas dobles (“ ”), nunca rectas
    (" ') ni angulares (« »): es el criterio del acta oficial del Ayuntamiento. Vale
    igual para los nombres entrecomillados de proyectos, montes o parajes, y tiene que
    ser el mismo en `texto` y en `acuerdo` — el mismo paraje entrecomillado de dos formas
    distintas en el mismo punto es un defecto.
14. PÁRRAFOS. Un punto DEBATIDO lleva en `texto` varios párrafos, separados por el escape
    JSON \\n\\n, uno por bloque —la exposición del proponente, la réplica de la oposición,
    la respuesta del equipo de gobierno, el cierre—, de tres a seis frases cada uno:
    escrito de un tirón sale como un muro de texto que nadie puede leer.
    Un punto que se despacha en una frase, en cambio, lleva UN solo párrafo y se acaba
    ahí. Nunca añadas un párrafo para cumplir esta regla: repetir con otras palabras lo
    que ya dice la frase anterior ("No se presentan escritos" detrás de "La Presidencia
    informa de que no se han presentado escritos para este punto del orden del día") es
    mucho peor que un párrafo único, porque el acta se repite a sí misma.
14 bis. LAS RESPUESTAS EN RUEGOS Y PREGUNTAS. Cada ruego o pregunta es UN elemento de
    `puntos`. Si recibe respuesta y la respuesta es CONCLUYENTE o importante para el acta
    —un dato con documento (regla 15), un compromiso con plazo o responsable, una negativa
    motivada, un trámite ya iniciado, la remisión a otro órgano—, va en el MISMO elemento,
    en una frase atribuida a quien responde ("{PRESIDENCIA['tratamiento'].capitalize()}
    responde que...", "El Sr. concejal D. Sergio de Fez Cerezuela contesta que..."). Se
    omiten las respuestas que no cierran nada: evasivas, aclaraciones de pasada, ironías
    y el tira y afloja de réplicas (regla 16). Si responde una voz que el mapa no
    identifica, se recoge sin nombre ("se responde que...") en vez de atribuírsela a
    alguien. Un ruego sin respuesta clara se deja sin ella: no escribas "queda pendiente"
    salvo que alguien lo diga.
15. CIFRAS, IMPORTES Y DATOS DE TERCEROS. Un acta municipal es un documento público que se
    archiva: una cifra escrita en ella queda como dato oficial del Ayuntamiento aunque en
    la sesión fuera solo un comentario. Por eso:
    - Se recoge la cifra que el interviniente vincula a un documento identificable: el
      presupuesto de un expediente, una factura, una partida, un acta anterior, una
      declaración tributaria, una ampliación de crédito. Escríbela con su fuente ("con un
      presupuesto de 48.279 euros", "una ampliación de crédito de 81.000 euros que figura
      en un acta").
    - Se OMITE la cifra suelta que alguien lanza de memoria en el fragor del debate y que
      no sostiene ningún argumento del punto: importes accesorios, sumas redondeadas de
      pasada, costes citados de oídas. Omitirlas no empobrece el acta; escribirlas
      convierte un comentario en un dato municipal.
    - Si una estimación es relevante porque es justo lo que se discute, recógela atribuida
      a quien la hace y calificada como lo que es: "cuando valoraciones informales la
      sitúan en torno a los 4.000 o 5.000 euros".
    - Si en la propia sesión alguien rectifica o matiza una cifra, el acta recoge la
      rectificación, no solo la cifra inicial.
    - Lo mismo con los datos de terceros: nombres de empresas, adjudicatarios o
      particulares se escriben cuando el interviniente los lee de un documento; una
      imputación hablada sobre alguien que no está en la sesión y no consta en ningún
      documento no se traslada al acta.
16. Concreto y sobrio: recoge los argumentos de cada postura y las decisiones, sin
    reproducir el tira y afloja. Cuando el debate se agría, el acta lo resume en una
    frase ("El debate se vuelve tenso, con acusaciones de mala gestión por parte de la
    oposición y defensas del trabajo realizado por parte del equipo de Gobierno"), no
    transcribe los reproches uno a uno. Esa fórmula vale para la crítica política; el
    reproche PERSONAL (insulto, acusación a una persona, amenaza) se trata en la 16 quater.
16 bis. LO QUE UN CONCEJAL PIDE QUE CONSTE. La regla 16 poda el tira y afloja, pero no
    puede podar una observación que el interviniente pide expresamente que conste en acta
    ("que conste en acta", "que quede reflejado", "quiero que se recoja"), ni la reserva,
    la discrepancia o la advertencia con la que sostiene su postura sobre el asunto que se
    trata. Esas van al `texto` del punto, en el sitio donde se producen, atribuidas a quien
    las hace y en UNA o DOS frases, redactadas en el registro del acta: se recoge lo que
    afirma, no cómo lo dice ni cuántas veces lo repite. Si se explica de forma tan confusa
    que no se entiende qué afirma, se omite (regla 6) — nunca se interpreta lo que quiso
    decir. Y sigue fuera del acta lo que no es una observación: la réplica de reproches
    personales más allá de la frase única que prevé la 16 quater, la insistencia y la
    anécdota que no aportan ni postura ni dato.
16 ter. LOS ASUNTOS QUE NO ESTÁN EN EL ORDEN DEL DÍA. En estos plenos es habitual que
    dentro del debate de un punto se acaben tratando temas paralelos. Esos temas NO se
    redactan en el acta: van a `asuntos_no_convocados`, uno por tema, sintetizado en una o
    dos frases con quién lo plantea, el título del punto en cuyo debate surge y su
    timestamp. Solo los que importan para el asunto que se está tratando o para el
    Ayuntamiento; el comentario de pasada no es un asunto. No confundir con la regla 24: lo
    que se trata como punto propio y se somete a acuerdo o a votación es un punto del orden
    del día aunque no estuviera convocado, y va en `orden_del_dia`, no aquí.
16 quater. INSULTOS Y ACUSACIONES PERSONALES. Un reproche PERSONAL —un insulto, una
    acusación dirigida a una persona, una amenaza— no se resume en una fórmula neutra que
    reparta la culpa: se recoge QUIÉN se lo dirige a QUIÉN, en una o dos frases, con la
    expresión literal entre comillas cuando es lo que se dijo ("D. X dirige a Dª Y las
    expresiones “...”; Dª Y responde que..."), atribuido según el mapa de voces (si la voz
    no está identificada, "un concejal no identificado en la grabación").
    a) No califiques tú el intercambio ("tenso enfrentamiento", "altercado", "fuerte
       discusión") ni lo hagas pasar por simétrico: "mutuas", "recíprocas" o "ambas
       partes" solo si CADA parte dirige a la otra un reproche personal en la grabación y
       puedes citar uno de cada lado. Si fue en un solo sentido, el acta lo dice en un
       solo sentido. Quien se defiende o explica su voto no está acusando.
    b) Lo político NO es personal: criticar la gestión o discrepar de un voto va en el
       resumen de la regla 16.
    c) No añadas gravedad ni intención que la grabación no diga, ni traslades lo que
       alguien cuenta que otra persona dijo fuera de la sesión. Los verbos que califican
       ("amenaza", "insulta", "acusa", "miente") son ya una calificación: úsalos solo si
       la propia frase lo es literalmente; si no, "afirma que..." o "le dice que..." con lo
       que dijo. "Te expulsen del grupo por la traición" no es "amenaza con promover su
       expulsión": es lo que dijo, y así se recoge.
17. No cites marcas de tiempo dentro de los textos redactados, ni escribas recuentos de
    votos en el texto: los recuentos van en el campo `votacion` y el documento compone la
    frase a partir de ahí.
18. LA APERTURA DE LA SESIÓN. Lo que quien preside declara antes de entrar en el primer
    punto —el aviso de que la sesión se graba y se difunde, la constancia de que preside
    por delegación, la exclusión de un punto del orden del día, una ausencia justificada—
    NO es parte del punto 1: va en `declaraciones_apertura`, casi literal. El texto del
    punto 1 empieza en el debate de ese punto.
19. FECHAS Y HORAS. `fecha_pleno` va en YYYY-MM-DD, y `hora_inicio` y `hora_fin` en HH:MM
    de RELOJ, tal como se dicen en la sesión ("siendo las doce horas y dos minutos").
    Las marcas [HH:MM:SS] de la transcripción cuentan desde el inicio del vídeo y NO son
    horas: usar la última como `hora_fin` haría constar en el acta que el Pleno se
    levantó de madrugada. Si nadie dice la hora de cierre, `hora_fin` va a null.
20. ESPAÑOL CLARO, NEUTRO Y CORRECTO. Cuida las tildes, la concordancia de género y
    número y el uso de mayúsculas. Los topónimos van en su forma correcta y escritos
    igual en todo el informe: {", ".join(TOPONIMOS)}, El Salto, la Gran Vía
    (Enguídanos siempre con tilde) — la única excepción son los títulos que se copian literalmente de la convocatoria
    (regla 21), que se respetan tal como los escribe el Ayuntamiento aunque no lleven
    tilde. Y no repitas dentro de un mismo punto algo que ya has escrito: si una frase no
    aporta un dato, una postura o una decisión que no estuviera ya, sobra.

LA CONVOCATORIA OFICIAL:
Puede que junto a la transcripción recibas la CONVOCATORIA del pleno: el documento con el
orden del día que el Ayuntamiento publica ANTES de la sesión, a menudo escaneado. Si la
recibes, mándate por estas cuatro reglas. Si no, ignóralas.
21. La convocatoria manda en la FORMA. Los títulos exactos de los puntos, su numeración,
    los números de expediente y el tipo de sesión (ordinaria o extraordinaria, y el motivo
    si es extraordinaria) se toman de ella, no de lo que se entienda en el audio. Copia los
    títulos literalmente, en mayúsculas.
22. La grabación manda en el FONDO. Qué se debate, qué se acuerda, qué se vota y quién
    interviene sale SOLO de la transcripción. La convocatoria dice lo previsto; el acta
    recoge lo ocurrido, y no siempre coinciden.
23. Un punto que figura en la convocatoria pero del que la grabación no dice nada NO se
    redacta como si se hubiera tratado. Si en la grabación se retira, se aplaza o se deja
    sobre la mesa, hazlo constar así; si sencillamente no aparece, omítelo.
24. Un punto que se trata en la grabación y no está en la convocatoria SÍ va al acta —
    suele ser un asunto de urgencia —, con `numero` en null si no se le da número.
"""

PROMPT_AUDITOR = f"""Eres el auditor de calidad de informes de plenos del Ayuntamiento de
Enguídanos. Recibes la transcripción literal de un pleno (con marcas [HH:MM:SS]) y un
informe en JSON generado a partir de ella. Tu único trabajo: encontrar afirmaciones del
informe que la transcripción NO respalde.

Comprueba una a una las afirmaciones verificables: resultados y números de votaciones,
nombres y cargos, importes, fechas, acuerdos adoptados y atribuciones de intervenciones.

{CORPORACION}

{INTERVINIENTES_SESION}

{DIARIZACION}

{RECUENTOS}

El redactor y el corrector tienen ese mismo bloque de RECUENTOS, así que un recuento en
`null` es la conducta esperada cuando el número no se oye, NO una inconsistencia: no lo
señales, ni pidas rellenarlo deduciéndolo del debate o de una parte audible del recuento.
Un `resultado` con los números en `null` es una votación correctamente redactada. Lo que
sí debes señalar es el caso contrario: un número escrito que la grabación no dice.

El redactor tiene esas mismas instrucciones. Que atribuya a una persona TODAS las
intervenciones de una etiqueta que la grabación identifica una sola vez es la conducta
esperada, no una invención: NO lo señales, aunque el fragmento concreto que estás
comprobando no repita el nombre. Lo que sí debes señalar es que ponga nombre a una
etiqueta que la grabación no identifica en ningún momento, o que mezcle en una misma
persona intervenciones de etiquetas distintas.

REVISA EL MAPA DE VOCES (`identificacion_locutores`) como parte de tu trabajo, y
hazlo antes que las atribuciones sueltas: por cada entrada, comprueba que su
`evidencia` es una cita que existe de verdad en la transcripción y que sostiene esa
`persona` para esa `etiqueta` (o su exclusión). Es mucho más fácil revisar ocho
entradas del mapa que las cuarenta atribuciones que dependen de él repartidas por el
informe — y si una entrada del mapa está mal, todas las atribuciones que arrastra
también lo están. Objeta cualquier atribución del informe a una persona cuya etiqueta
no esté identificada en el mapa con una cita que la sostenga, aunque la frase suene
plausible por sí sola.

BUSCA ACTIVAMENTE LAS ETIQUETAS CONTAMINADAS: para cada etiqueta, lee TODAS sus
intervenciones en la transcripción, no solo la que cita el mapa, y comprueba si entre
ellas hay dos que se identifiquen como personas distintas e incompatibles entre sí — el
generador no puede ver este patrón mientras redacta punto a punto, y tú sí lees la
transcripción entera. Es exactamente el fallo real del pleno del 3 de septiembre de
2026: la etiqueta que abre la sesión presidiendo dijo, tres horas después, "llevo como
presidenta de la asociación de jubilados", y el informe atribuyó ese ruego a la Teniente
de Alcalde cuando lo había formulado una vecina asistente. Si encuentras ese patrón,
objétalo aunque el mapa marque la etiqueta como identificada con una cita real: la cita
puede ser literal y aun así la etiqueta seguir mezclando a dos personas.

COMPRUEBA TAMBIÉN EL PATRÓN CONTRARIO: dos etiquetas DISTINTAS identificadas en el mapa
como la MISMA persona. Repasa si esas dos etiquetas se alternan hablando en algún tramo
de la conversación —se responden, se interrumpen, intervienen seguidas en el mismo
intercambio—: si se alternan, no pueden ser la misma persona (ver REGLA DE TURNOS
ALTERNOS en DIARIZACION) y el mapa está mal en al menos una de las dos. Objétalo aunque
las dos citas sean literales.

Y comprueba que la `evidencia` de cada entrada del mapa es la prueba de MÁS PESO que la
transcripción ofrece para esa etiqueta, según la JERARQUÍA DE PRUEBAS de DIARIZACION
(autoidentificación > nombrada respondiendo > dirigida por su nombre o cargo), y no una
prueba más débil que otro pasaje de la misma etiqueta contradice con una más fuerte. Si
encuentras en la transcripción una prueba más fuerte que la que el mapa cita, objétalo:
la evidencia registrada tiene que ser la que gana, no la que el generador encontró
primero.

La transcripción es automática y deforma los nombres propios, así que el redactor tiene
instrucciones de corregirlos contra esa lista. NO señales como problema que el informe
escriba "Sergio de Fez Cerezuela" donde la transcripción dice "Féceres Zuela", ni casos
equivalentes: es la corrección esperada. Sí debes señalar que se atribuya una
intervención a una persona concreta cuando la grabación no la identifique.

DATOS SIN UNA FRASE CLARA QUE LOS SOSTENGA (regla 6 bis del redactor): objeta cada lugar,
objeto de una solicitud, destinatario, cifra, norma o nombre que el informe afirme y que
ninguna frase CLARA de la transcripción respalde, aunque suene plausible por el contexto.
Si lo único que hay es un fragmento confuso, cítalo como evidencia y explica que de ahí no
se deduce el dato: la corrección esperada es dejar solo lo que sí se entiende. No lo
confundas con la corrección de un nombre propio por su sonido, que es lo esperado.

REPROCHES PERSONALES (regla 16 quater del redactor): objeta una frase del informe que
califique un intercambio ("tenso enfrentamiento", "altercado", "fuerte discusión") cuando
no lo hace la grabación; objeta "mutuas", "recíprocas" o "ambas partes" si la transcripción
no contiene un reproche personal de CADA parte (la evidencia es la cita del lado que
falta); y objeta un insulto, una acusación o una amenaza atribuidos a quien no los dijo
(evidencia: la cita de quien sí). NO es un problema que el informe recoja, con nombre y
entre comillas, una expresión ofensiva que la transcripción contiene: es lo que pide esa
regla. Tampoco que resuma como crítica política lo que no es un reproche personal.

RESPUESTAS EN RUEGOS (regla 14 bis del redactor): la respuesta que figure junto a un ruego
se audita como cualquier atribución. Que falte la respuesta a un ruego NO es un problema:
el redactor solo recoge las concluyentes.

VOTACIONES: comprueba que el `resultado` de cada votación y el texto de su `acuerdo`
digan lo mismo que el recuento que se oye. Con más votos a favor que en contra el asunto
se aprueba, aunque haya abstenciones; un acuerdo que "rechaza" lo que se aprobó es el
error más grave que puede tener un acta.

UNA ETIQUETA MEZCLADA NO INVALIDA UN RECUENTO: los números de una votación se oyen, los dice
quien los dice. Que la voz que los pronuncia esté en una etiqueta marcada como «voces
mezcladas» afecta a QUIÉN habló, no a CUÁNTOS votos se dijeron. No pidas quitar ni anular
un recuento por esa razón; solo si la cifra no se oye en la grabación o no coincide con ella.
Tampoco dudes de un recuento porque el debate previo fuera confuso.

La FECHA del pleno la fija la herramienta con el dato de quien lo procesa, no la
grabación: no objetes `fecha_pleno` aunque en la sesión se diga otra fecha por error.

Tampoco es un problema el tiempo verbal ni el estilo: el informe se redacta en presente
a propósito.

Tampoco son problema las fórmulas y el tratamiento propios de un acta municipal: que el
informe escriba "{PRESIDENCIA['tratamiento']}", "D. Joaquín Martínez Luján", "Toma la
palabra...", "La Corporación se da por informada", "El Pleno del Ayuntamiento ACUERDA" o
los títulos en mayúsculas es la redacción esperada, no una afirmación inventada, aunque la
transcripción no contenga esas palabras literales. Los cargos y tratamientos salen del
listado de la Corporación, que es fuente oficial: que quien preside aparezca como
{PRESIDENCIA['tratamiento']} y no como alcaldesa, o que el Alcalde titular aparezca como
tal aunque no presida, es lo correcto. Sí debes señalar que se atribuya una intervención a
una persona que la grabación no identifica.

El redactor tiene instrucciones de OMITIR del acta las cifras accesorias que se dicen de
palabra sin documento que las respalde, y de no trasladar imputaciones habladas sobre
terceros que no constan en ningún documento. Una cifra que está en la transcripción y no
en el informe NO es un problema: es la depuración esperada. Tu trabajo es el sentido
contrario — datos que el informe afirma y la transcripción no respalda —, nunca reclamar
que se añada lo que se omitió.

`asuntos_no_convocados` es una lista de trabajo para la secretaria, no parte del acta: son
los temas paralelos que salieron en el debate y que el redactor tiene instrucciones de NO
redactar como puntos. Que un asunto figure ahí y no en `orden_del_dia` es lo correcto —
solo objétalo si ese asunto se sometió de verdad a acuerdo o a votación en la grabación,
porque entonces es un punto y el acta lo está dejando fuera. Su contenido se audita como
todo lo demás: que la transcripción respalde lo que dice.

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

CAMPOS RECIÉN MODIFICADOS:
Puede que al final del mensaje veas un bloque CAMPOS QUE ACABA DE MODIFICAR EL CORRECTOR
con rutas del JSON (`orden_del_dia[1].texto`, `asistentes[5]`). Son los campos que han
cambiado en la última vuelta, calculados comparando el informe anterior con el nuevo. NO
es una lista de problemas: es dónde mirar primero. Repásalos con especial atención,
porque una corrección puede arreglar lo que se le pidió y estropear de paso algo que nadie
discutía — cambiar un nombre entero cuando solo había que matizarlo, por ejemplo. Después
sigue con tu revisión habitual del informe COMPLETO: esta pista no la sustituye, y un
problema fuera de esas rutas se señala igual.

Para cada problema devuelve: la sección, la afirmación dudosa, el motivo y una cita
literal de la transcripción como evidencia. Si el informe es fiel a la transcripción,
devuelve la lista de problemas VACÍA. No inventes problemas menores de estilo: solo
faltas de fidelidad a la fuente."""

# Pasada aparte con una sola pregunta; se ejecuta siempre, no solo con etiquetas marcadas como mezcladas.
PROMPT_ATRIBUCIONES = f"""Eres un auditor de atribuciones de los informes de plenos del
Ayuntamiento de Enguídanos. Recibes la transcripción diarizada de un pleno y el informe
en JSON. Haces UNA sola comprobación, y la haces a fondo: ¿lo que el informe pone en boca
de una persona lo dijo de verdad esa persona?

{CORPORACION}

{INTERVINIENTES_SESION}

{DIARIZACION}

Cómo trabajar:
1. Recorre el informe buscando toda frase que atribuya algo a una persona concreta con
   nombre y tratamiento: intervenciones en `orden_del_dia[].texto`, ruegos y preguntas
   (`ruegos_y_preguntas[].formulados_por` y sus `puntos`) y declaraciones de apertura.
2. Para cada una, localiza en la transcripción el turno que la sustenta y mira la
   etiqueta de locutor. Comprueba que esa etiqueta está en `identificacion_locutores`
   con esa persona y que el contenido del turno es propio de ella.
3. Fíjate sobre todo en las señales de que dentro de una etiqueta identificada como
   concejal habla otra voz (ver SEÑALES DE PÚBLICO): trata de «usted» a la Corporación,
   habla en nombre de vecinos o de una asociación, pregunta por un servicio del pueblo
   como usuario, o interviene en el turno del público. Revisa también los cambios bruscos
   de tono o de tema dentro de una misma etiqueta y los turnos donde la persona responde
   a otra que no se alterna con ella.
4. Objeta SOLO atribuciones dudosas con una base en la transcripción: cita literalmente
   el turno que delata la mezcla en `evidencia`. La corrección correcta es atribuir la
   intervención sin nombre («un vecino pregunta…», «se pregunta…») o a «no identificado
   en la grabación»; dilo en `motivo`.

NO señales: erratas de redacción, estilo, cifras, votaciones ni nada que no sea quién dijo
qué (los números de un recuento no son una atribución: que los diga una etiqueta mezclada
no los invalida); de eso se ocupa otro auditor. Si todas las atribuciones están sostenidas, devuelve la
lista VACÍA. No inventes problemas."""

PROMPT_CORRECTOR = f"""Eres el corrector de informes de plenos del Ayuntamiento de
Enguídanos. Recibes: la transcripción literal (con marcas [HH:MM:SS]), el informe completo
en JSON, y la lista de problemas detectados por un auditor (cada uno con su evidencia).

{CORPORACION}

{INTERVINIENTES_SESION}

{DIARIZACION}

{RECUENTOS}

Devuelve el informe COMPLETO corregido, en el mismo esquema JSON:
1. Corrige exclusivamente lo señalado en los problemas, apoyándote en la transcripción.
2. Si la transcripción no permite resolver un problema, aplica la vía de escape del
   esquema (null, "no consta", "no identificado en la grabación") en ese dato.
3. RECUENTOS DE VOTOS. Si el auditor objeta un número de votos, la corrección NO es
   cambiar ese número por otro que encaje mejor: es poner `null`, según el bloque
   RECUENTOS DE VOTOS de arriba. Un recuento objetado que se sustituye por otra cifra
   sigue siendo una cifra que nadie dijo, y el auditor volverá a rechazarla.
4. No toques el resto del informe.
5. Mismas reglas que el redactor: nada que no esté en la transcripción.
6. Conserva la redacción en presente de indicativo, el registro y las fórmulas de acta
   municipal (tratamiento D./Dª/Sr./Sra. con apellidos completos, "Toma la palabra...",
   títulos en mayúsculas, el acuerdo en el campo `acuerdo` y no dentro de `texto`, los
   párrafos separados por línea en blanco) y el nivel de detalle del texto original; no lo
   resumas ni lo pases a pasado.
   Los cargos salen del listado de la Corporación: quien preside es
   {PRESIDENCIA['tratamiento']}, nunca alcaldesa; el Alcalde titular es el Sr. Alcalde
   aunque no presida.
7. No devuelvas al informe una cifra o un dato de un tercero que el redactor omitió: si el
   auditor no lo señala como problema, es que la omisión era deliberada.
8. Si recibes la CONVOCATORIA oficial del pleno, sigue mandando en la forma (títulos
   literales, numeración, expedientes, tipo de sesión) mientras la grabación manda en el
   fondo. No añadas contenido a un punto convocado del que la transcripción no habla:
   eso es justo lo que el auditor señala.
9. MISMOS CRITERIOS DE FORMA QUE EL REDACTOR, y no los deshagas al corregir: comillas
   tipográficas dobles (“ ”) en todo el informe y las mismas en `texto` y en `acuerdo`;
   ninguna fórmula coloquial de resultado dentro de `texto` ("se da el punto por
   aprobado", "queda aprobado"), porque el documento compone la fórmula jurídica a partir
   de `acuerdo` y `votacion` y el acta acabaría diciéndolo dos veces; ninguna frase que
   repita lo que ya dice otra del mismo punto; y topónimos correctos y uniformes
   ({", ".join(TOPONIMOS)}), salvo en los títulos copiados de la convocatoria.
   Si al corregir otra cosa te encuentras una de estas, arréglala: son de forma, no
   tocan el fondo de lo que se dijo ni de lo que se acordó.
10. TAMBIÉN TE OBLIGAN, al corregir, las reglas de fondo del redactor sobre estos tres
   puntos, y no las deshagas:
   - 6 bis: no completes con lo verosímil un lugar, objeto, destinatario o cifra que solo
     sale de un fragmento confuso; escribe lo que una frase clara sostiene y deja fuera el
     resto.
   - 14 bis: cada ruego o pregunta es un elemento de `puntos`, con su respuesta en el mismo
     elemento solo si es concluyente; no añadas respuestas que el auditor no reclame.
   - 16 quater: un insulto o acusación personal se atribuye a quien lo dijo, con la
     expresión literal entre comillas si procede; sin calificar el intercambio
     ("tenso enfrentamiento") y sin "mutuas" salvo que cada parte lo dirija a la otra.
   Si el auditor objeta una frase de este tipo, la corrección es atribuir o recortar según
   estas reglas, nunca sustituirla por otra calificación o reconstrucción distinta."""


# ══ Llamadas al LLM (OpenRouter) y bucle de fiabilidad ══

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
# Modelo distinto del redactor. No admite `temperature` (HTTP 400); usa `reasoning`.
MODELO_AUDITOR = "anthropic/claude-opus-5.5"


def _plural(n: int, singular: str, plural: str) -> str:
    """'1 objeción' / '3 objeciones'."""
    return f"{n} {singular if n == 1 else plural}"


def _log(texto: str) -> None:
    """Progreso por consola; flush porque la salida suele ir a un fichero con `| tee`."""
    print(texto, flush=True)


def verificar_respuesta(r):
    """raise_for_status() pero dejando el cuerpo de la respuesta en el mensaje
    (ahí viene la causa, p. ej. "insufficient credits")."""
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        cuerpo = " ".join((r.text or "").split())[:300]
        if not cuerpo:
            raise
        # `from None` evita duplicar la excepción en el registro.
        raise requests.HTTPError(f"{e} :: {cuerpo}", response=r) from None
    return r


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


def _reensamblar_sse(lineas) -> dict:
    """Reensambla un stream SSE de OpenRouter en la forma de la respuesta sin streaming."""
    trozos, usage, fin, error = [], {}, None, None
    for linea in lineas:
        # ": OPENROUTER PROCESSING" son keep-alive.
        if not linea or linea.startswith(":"):
            continue
        if not linea.startswith("data:"):
            continue
        dato = linea[5:].strip()
        if dato == "[DONE]":
            break
        trozo = json.loads(dato)
        error = trozo.get("error") or error
        if trozo.get("usage"):
            usage = trozo["usage"]
        for eleccion in trozo.get("choices") or []:
            trozos.append((eleccion.get("delta") or {}).get("content") or "")
            fin = eleccion.get("finish_reason") or fin
            error = eleccion.get("error") or error
    eleccion = {"finish_reason": fin, "message": {"content": "".join(trozos)}}
    if error:
        eleccion["error"] = error
    return {"choices": [eleccion], "usage": usage}


def _peticion(cuerpo: dict, intentos: int = 4) -> dict:
    """POST a OpenRouter; ante 429 o error de servidor reintenta con backoff exponencial
    (2, 4, 8 min). Va en streaming para que la conexión no quede ociosa mientras el modelo
    razona: si no, el proveedor la corta con un 504 idle timeout y, con temperatura 0,
    reintentar daría el mismo corte."""
    cuerpo = {**cuerpo, "stream": True, "stream_options": {"include_usage": True}}
    for i in range(intentos):
        # timeout (conexión, entre trozos): con streaming no hay tope global.
        r = requests.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
            json=cuerpo,
            stream=True,
            timeout=(30, 300),
        )
        if (r.status_code == 429 or r.status_code >= 500) and i < intentos - 1:
            r.close()
            espera = 120 * 2 ** i
            _log(f"     OpenRouter devolvió {r.status_code}; esperando {espera // 60} min y reintentando...")
            time.sleep(espera)
            continue
        verificar_respuesta(r)
        # text/event-stream no declara charset: sin esto requests asume ISO-8859-1.
        r.encoding = "utf-8"
        with r:
            datos = _reensamblar_sse(r.iter_lines(decode_unicode=True))
        # Un corte del proveedor a mitad de generación llega con HTTP 200 y el error
        # dentro del choice; es transitorio, se reintenta como un 5xx.
        fallo = (datos["choices"][0] or {}).get("error")
        if fallo and i < intentos - 1:
            espera = 120 * 2 ** i
            _log(f"     el proveedor cortó la respuesta ({fallo.get('code')}: "
                 f"{fallo.get('message')}); esperando {espera // 60} min y reintentando...")
            time.sleep(espera)
            continue
        return datos


def _llamar_llm(instrucciones: str, contenido: str, schema: type[BaseModel],
                convocatoria: bytes | None = None, etiqueta: str = "llm",
                modelo: str = MODELO) -> BaseModel:
    """Una llamada al modelo con salida estructurada validada contra `schema`.
    `convocatoria` (bytes del PDF) viaja en crudo: son escaneos sin capa de texto."""
    partes = [{"type": "text", "text": contenido}]
    cuerpo = {
        "model": modelo,
        "messages": [
            {"role": "system", "content": instrucciones},
            {"role": "user", "content": partes},
        ],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": schema.__name__.lower(),
            "strict": True,
            "schema": _esquema_estricto(schema.model_json_schema()),
        }},
    }
    if modelo == MODELO:
        cuerpo["temperature"] = 0
    else:
        cuerpo["reasoning"] = {"enabled": True}
    if convocatoria is not None:
        partes.insert(0, {"type": "file", "file": {
            "filename": "convocatoria.pdf",
            "file_data": "data:application/pdf;base64," + base64.b64encode(convocatoria).decode(),
        }})
        # engine "native": el de por defecto es un OCR de pago que devuelve texto plano.
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
    # `error` manda sobre `content` (un stream cortado deja JSON truncado). Puede haber
    # 200 con content vacío (presupuesto agotado razonando); se vuelca para diagnosticar.
    if eleccion.get("error") or not contenido:
        volcado = Path(tempfile.gettempdir()) / f"openrouter-{etiqueta}-{int(time.time())}.json"
        volcado.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        raise RuntimeError(
            f"{etiqueta}: OpenRouter devolvió una respuesta sin contenido "
            f"(finish_reason={eleccion.get('finish_reason')!r}, "
            f"native={eleccion.get('native_finish_reason')!r}, usage={uso}). "
            f"Respuesta completa en {volcado}")
    return schema.model_validate_json(contenido)


def generar_informe(transcripcion: str, convocatoria: bytes | None = None,
                    intervinientes: list[dict] | None = None) -> InformePleno:
    fuentes = f"{len(transcripcion):,} caracteres de transcripción"
    if convocatoria:
        fuentes += f" + convocatoria ({len(convocatoria) // 1024} KB)"
    _log(f"  → GENERADOR ({fuentes})")
    informe = _llamar_llm(PROMPT_GENERADOR,
                          f"{bloque_intervinientes(intervinientes)}"
                          f"TRANSCRIPCIÓN DEL PLENO:\n\n{transcripcion}",
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
                    convocatoria: bytes | None = None,
                    rutas_tocadas: list[str] | None = None,
                    intervinientes: list[dict] | None = None) -> AuditoriaInforme:
    # El auditor recibe la convocatoria (como CORPORACION): sin ella marcaría los títulos
    # del orden del día como no respaldados. `rutas_tocadas` es solo una pista de dónde
    # mirar primero; sigue auditando el informe entero.
    _log("  → AUDITOR (busca afirmaciones que la transcripción no respalde"
         + (f"; {_plural(len(rutas_tocadas), 'campo recién tocado', 'campos recién tocados')})"
            if rutas_tocadas else ")"))
    contenido = (f"{bloque_intervinientes(intervinientes)}TRANSCRIPCIÓN DEL PLENO:\n\n{transcripcion}\n\n"
                 f"INFORME A AUDITAR (JSON):\n\n{informe.model_dump_json()}")
    if rutas_tocadas:
        contenido += ("\n\nCAMPOS QUE ACABA DE MODIFICAR EL CORRECTOR:\n"
                      + "\n".join(f"- {r}" for r in rutas_tocadas))
    auditoria = _llamar_llm(PROMPT_AUDITOR, contenido, AuditoriaInforme,
                               convocatoria, "auditor", MODELO_AUDITOR)
    if not auditoria.problemas:
        _log("     visto bueno, sin objeciones")
    else:
        _log(f"     {_plural(len(auditoria.problemas), 'objeción', 'objeciones')}:")
        for p in auditoria.problemas:
            _log(f"       • [{p.seccion}] {p.afirmacion_dudosa}")
            _log(f"         motivo: {p.motivo}")
    return auditoria


def auditar_atribuciones(transcripcion: str, informe: InformePleno,
                         convocatoria: bytes | None = None,
                         intervinientes: list[dict] | None = None) -> AuditoriaInforme:
    """Auditoría con una sola pregunta: ¿lo dijo quien el informe dice? (PROMPT_ATRIBUCIONES)."""
    _log("  → AUDITOR DE ATRIBUCIONES (¿lo dijo quien el informe dice?)")
    contenido = (f"{bloque_intervinientes(intervinientes)}TRANSCRIPCIÓN DEL PLENO:\n\n{transcripcion}\n\n"
                 f"INFORME A AUDITAR (JSON):\n\n{informe.model_dump_json()}")
    auditoria = _llamar_llm(PROMPT_ATRIBUCIONES, contenido, AuditoriaInforme,
                            None, "atribuciones", MODELO_AUDITOR)
    if not auditoria.problemas:
        _log("     atribuciones sostenidas, sin objeciones")
    else:
        _log(f"     {_plural(len(auditoria.problemas), 'objeción', 'objeciones')}:")
        for p in auditoria.problemas:
            _log(f"       • [{p.seccion}] {p.afirmacion_dudosa}")
            _log(f"         motivo: {p.motivo}")
    return auditoria


def corregir_informe(transcripcion: str, informe: InformePleno, problemas: list[Problema],
                     convocatoria: bytes | None = None,
                     intervinientes: list[dict] | None = None) -> InformePleno:
    probs = "\n".join(f"- [{p.seccion}] {p.afirmacion_dudosa} → {p.motivo} (evidencia: {p.evidencia})"
                      for p in problemas)
    contenido = (f"{bloque_intervinientes(intervinientes)}TRANSCRIPCIÓN DEL PLENO:\n\n{transcripcion}\n\n"
                 f"INFORME COMPLETO (JSON):\n\n{informe.model_dump_json()}\n\n"
                 f"PROBLEMAS DETECTADOS POR EL AUDITOR:\n{probs}")
    _log(f"  → CORRECTOR ({_plural(len(problemas), 'objeción', 'objeciones')} que resolver)")
    return _llamar_llm(PROMPT_CORRECTOR, contenido, InformePleno, convocatoria, "corrector")


def _aplanar(valor, prefijo: str = ""):
    """{'a': [{'b': 1}]} → {'a[0].b': 1}. Solo hojas."""
    if isinstance(valor, dict):
        for clave, sub in valor.items():
            yield from _aplanar(sub, f"{prefijo}.{clave}" if prefijo else clave)
    elif isinstance(valor, list):
        for i, sub in enumerate(valor):
            yield from _aplanar(sub, f"{prefijo}[{i}]")
    else:
        yield prefijo, valor


def _fijar(datos: dict, ruta: str, valor) -> None:
    """Escribe `valor` en una ruta aplanada ('orden_del_dia[0].votacion.resultado')."""
    partes = re.findall(r"[^.\[\]]+|\[\d+\]", ruta)
    obj = datos
    for parte in partes[:-1]:
        obj = obj[int(parte[1:-1])] if parte.startswith("[") else obj[parte]
    ultima = partes[-1]
    if ultima.startswith("["):
        obj[int(ultima[1:-1])] = valor
    else:
        obj[ultima] = valor


# Campos donde una disputa no se resuelve eligiendo un valor: se usa la vía de escape.
# Cada entrada: valor de escape y pistas de que una objeción habla de ese campo
# (`Problema.seccion` es prosa, no una ruta).
_AMBIGUOS = {
    "votacion.resultado": ("no consta", ("votaci", "resultado")),
}


def _escape_de(ruta: str):
    """(valor de escape, pistas) de una ruta en disputa, o None si no hay escape seguro."""
    for sufijo, entrada in _AMBIGUOS.items():
        if ruta.endswith(sufijo):
            return entrada
    return None


# Calificaciones vetadas por la regla 16 quater; una prohibición literal se comprueba en código.
_CALIFICACIONES_VETADAS = ("tenso enfrentamiento", "fuerte discusión", "altercado",
                           "acusaciones mutuas", "reproches mutuos", "acusaciones recíprocas")


def _palabras(texto: str) -> list[str]:
    """Minúsculas, sin acentos ni signos."""
    plano = unicodedata.normalize("NFD", texto.lower())
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", plano)


_COMILLAS = re.compile("“([^”]+)”|«([^»]+)»|\"([^\"]+)\"")
_ELIPSIS = re.compile(r"\[?(?:…|\.\.\.)\]?")
_MARCAS = re.compile(r"\[\d{1,2}:\d{2}:\d{2}\]|Interviniente \w+:")


def _textos_del_informe(informe: InformePleno) -> list[tuple[str, str]]:
    """(ruta, texto) de todo el texto libre que acaba impreso en el acta."""
    textos = [(f"orden_del_dia[{i}].texto", p.texto) for i, p in enumerate(informe.orden_del_dia)]
    textos += [(f"orden_del_dia[{i}].acuerdo", p.acuerdo or "")
               for i, p in enumerate(informe.orden_del_dia)]
    textos += [(f"ruegos_y_preguntas[{i}]", " ".join(b.puntos))
               for i, b in enumerate(informe.ruegos_y_preguntas)]
    textos += [(f"declaraciones_apertura[{i}]", d)
               for i, d in enumerate(informe.declaraciones_apertura)]
    return textos


def citas_no_halladas(informe: InformePleno, transcripcion: str) -> list[Problema]:
    """Una cita entre comillas es literal: al menos el 70 % de sus pares de palabras consecutivas
    tiene que estar en la transcripción. Se saltan las de menos de cinco palabras; los puntos
    suspensivos parten la cita."""
    limpia = _palabras(_MARCAS.sub(" ", transcripcion))
    pares = set(zip(limpia, limpia[1:]))
    problemas = []
    for sitio, texto in _textos_del_informe(informe):
        for m in _COMILLAS.finditer(texto):
            cita = next(g for g in m.groups() if g)
            for trozo in _ELIPSIS.split(cita):
                palabras = _palabras(trozo)
                if len(palabras) < 5:
                    continue
                pares_cita = list(zip(palabras, palabras[1:]))
                hallados = sum(1 for par in pares_cita if par in pares)
                if hallados / len(pares_cita) < 0.7:
                    problemas.append(Problema(
                        seccion=sitio,
                        afirmacion_dudosa=f"Cita literal: «{trozo.strip()}»",
                        motivo="Esas palabras no aparecen seguidas en la transcripción: una cita "
                               "entre comillas es literal. Busca lo que se dijo de verdad y "
                               "cítalo tal cual, o quita las comillas y parafrasea sin añadir "
                               "gravedad ni verbos que la frase no tenga.",
                        evidencia="(comprobación automática de citas)"))
    return problemas


def toponimos_parecidos(informe: InformePleno) -> list[Problema]:
    """Marca palabras casi iguales (>= 0,8) a un topónimo de TOPONIMOS sin serlo. Enguídanos
    queda fuera porque «enguidano» es un gentilicio."""
    conocidos = {" ".join(_palabras(t)) for t in TOPONIMOS}
    problemas, vistos = [], set()
    for sitio, texto in _textos_del_informe(informe):
        palabras = _palabras(texto)
        for topo in TOPONIMOS:
            if topo == "Enguídanos":
                continue
            ref = _palabras(topo)
            n = len(ref)
            for i in range(len(palabras) - n + 1):
                cand = " ".join(palabras[i:i + n])
                if cand in conocidos or cand in vistos:
                    continue
                if difflib.SequenceMatcher(None, cand, " ".join(ref)).ratio() >= 0.8:
                    vistos.add(cand)
                    problemas.append(Problema(
                        seccion=sitio,
                        afirmacion_dudosa=f"El texto dice «{cand}».",
                        motivo=f"Se parece mucho al lugar «{topo}» pero no es igual: escríbelo "
                               f"como «{topo}» si es ese lugar, y si no lo es, confirma en la "
                               "transcripción que se dijo así.",
                        evidencia="(comprobación automática de topónimos)"))
    return problemas


def incoherencias(informe: InformePleno, transcripcion: str | None = None) -> list[Problema]:
    """Comprobaciones deterministas que se suman a las objeciones del auditor en cada vuelta:
    - acuerdo que contradice el resultado de la votación;
    - resultado contrario a un recuento completo sin empate;
    - calificaciones vetadas por la regla 16 quater;
    - citas entre comillas que no están en la transcripción (si se pasa);
    - topónimos casi iguales a uno de TOPONIMOS."""
    problemas = []
    for i, punto in enumerate(informe.orden_del_dia):
        v, sitio = punto.votacion, f"orden_del_dia[{i}]"
        if v and v.a_favor is not None and v.en_contra is not None and v.a_favor != v.en_contra:
            esperado = "aprobado" if v.a_favor > v.en_contra else "rechazado"
            if v.resultado in ("aprobado", "rechazado") and v.resultado != esperado:
                problemas.append(Problema(
                    seccion=f"{sitio}.votacion",
                    afirmacion_dudosa=f"El resultado es '{v.resultado}' con {v.a_favor} a favor "
                                      f"y {v.en_contra} en contra.",
                    motivo="Por mayoría simple ese recuento da el resultado contrario. Revisa en "
                           "la transcripción si el recuento o el resultado están mal.",
                    evidencia="(comprobación automática del recuento)"))
        acuerdo = (punto.acuerdo or "").lower()
        if v and v.resultado == "aprobado" and re.search(r"\b(rechaz|desestim|no aprob)", acuerdo):
            problemas.append(Problema(
                seccion=f"{sitio}.acuerdo",
                afirmacion_dudosa=f"El acuerdo dice: «{punto.acuerdo}»",
                motivo=f"La votación del punto es 'aprobado' ({v.a_favor} a favor, "
                       f"{v.en_contra} en contra, {v.abstenciones} abstenciones) y el acuerdo "
                       "habla de rechazar. El acuerdo tiene que decir lo que se votó.",
                evidencia="(comprobación automática acuerdo/votación)"))
        if v and v.resultado == "rechazado" and acuerdo and not re.search(
                r"\b(rechaz|desestim|no aprob|no se aprueba)", acuerdo):
            problemas.append(Problema(
                seccion=f"{sitio}.acuerdo",
                afirmacion_dudosa=f"El acuerdo dice: «{punto.acuerdo}»",
                motivo="La votación del punto es 'rechazado' y el acuerdo no lo refleja.",
                evidencia="(comprobación automática acuerdo/votación)"))

    textos = [(f"orden_del_dia[{i}].texto", p.texto) for i, p in enumerate(informe.orden_del_dia)]
    textos += [(f"ruegos_y_preguntas[{i}]", " ".join(b.puntos))
               for i, b in enumerate(informe.ruegos_y_preguntas)]
    for sitio, texto in textos:
        for vetada in _CALIFICACIONES_VETADAS:
            if vetada in texto.lower():
                problemas.append(Problema(
                    seccion=sitio,
                    afirmacion_dudosa=f"El texto califica el intercambio de «{vetada}».",
                    motivo="La regla 16 quater prohíbe que el redactor califique el intercambio "
                           "o lo haga simétrico: hay que decir quién dijo qué a quién, con la "
                           "frase literal, y quitar la calificación.",
                    evidencia="(comprobación automática de la regla 16 quater)"))
    if transcripcion:
        problemas += citas_no_halladas(informe, transcripcion)
    return problemas + toponimos_parecidos(informe)


def restaurar_recuentos(antes: InformePleno, despues: InformePleno):
    """Devuelve `despues` con los recuentos completos que el corrector haya borrado y un aviso
    por cada uno, para que una persona los confirme contra la grabación."""
    if len(antes.orden_del_dia) != len(despues.orden_del_dia):
        return despues, []
    puntos, avisos = [], []
    for i, (a, d) in enumerate(zip(antes.orden_del_dia, despues.orden_del_dia)):
        v = a.votacion
        completo = v and v.a_favor is not None and v.en_contra is not None
        perdido = completo and (d.votacion is None or d.votacion.a_favor is None
                                or d.votacion.en_contra is None)
        if not perdido or a.numero != d.numero:
            puntos.append(d)
            continue
        base = d.votacion or v
        restaurada = base.model_copy(update={
            "a_favor": v.a_favor, "en_contra": v.en_contra, "abstenciones": v.abstenciones,
            "modalidad": "recuento"})
        puntos.append(d.model_copy(update={"votacion": restaurada}))
        avisos.append(Problema(
            seccion=f"orden_del_dia[{i}].votacion",
            afirmacion_dudosa=f"Recuento {v.a_favor} a favor, {v.en_contra} en contra"
                              f"{'' if v.abstenciones is None else f', {v.abstenciones} abstenciones'}.",
            motivo="El corrector borró este recuento y se ha restaurado: un recuento que se oye "
                   "no se anula por dudas sobre quién habla. Confírmalo contra la grabación.",
            evidencia="(comprobación automática de recuentos)"))
    return despues.model_copy(update={"orden_del_dia": puntos}), avisos


def bucle_informe(transcripcion: str, convocatoria: bytes | None = None,
                  generar=None, auditar=None, corregir=None,
                  intervinientes: list[dict] | None = None, atribuciones=None):
    """Generador → auditor → (corrector → auditor)* con tope MAX_VUELTAS.

    `convocatoria` (bytes del PDF o None) e `intervinientes` ([{'nombre', 'apodos'}] o
    None) los reciben los tres roles. Devuelve (informe, problemas_pendientes): los
    pendientes se listan por consola, no se escriben en el acta. Los kwargs
    generar/auditar/corregir/atribuciones inyectan fakes en los tests."""
    # Con fakes inyectados (tests) no se narra.
    narrar = not any((generar, auditar, corregir))
    # Lista mutable rellenada antes de cada auditoría: los fakes de los tests tienen
    # firma (transcripcion, informe).
    rutas_tocadas: list[str] = []
    # Solo si los hay, para no cambiar la firma de los fakes.
    extra = {"intervinientes": intervinientes} if intervinientes else {}
    generar = generar or (lambda t: generar_informe(t, convocatoria, **extra))
    auditar = auditar or (lambda t, i: auditar_informe(t, i, convocatoria, rutas_tocadas,
                                                       **extra))
    corregir = corregir or (lambda t, i, p: corregir_informe(t, i, p, convocatoria,
                                                             **extra))

    # La auditoría de atribuciones se hace una sola vez, sobre lo que redacta el generador.
    if atribuciones is None and narrar:
        atribuciones = lambda t, i: auditar_atribuciones(t, i, convocatoria, **extra)
    pendiente_atribuciones = [atribuciones]

    def revisar(inf):
        problemas = auditar(transcripcion, inf).problemas
        if pendiente_atribuciones[0]:
            problemas = problemas + pendiente_atribuciones[0](transcripcion, inf).problemas
            pendiente_atribuciones[0] = None
        return problemas + incoherencias(inf, transcripcion)

    informe = generar(transcripcion)
    problemas = revisar(informe)
    vueltas, llamadas = 0, 2
    # Historial por campo para detectar el ping-pong (se mira el informe, no las
    # objeciones: `Problema.seccion` no es una ruta fiable).
    historial = {ruta: [valor] for ruta, valor in _aplanar(informe.model_dump())}
    congelados: dict[str, object] = {}
    avisos_recuentos: list[Problema] = []

    while problemas and vueltas < MAX_VUELTAS:
        if narrar:
            _log(f"\n  ── vuelta {vueltas + 1} de {MAX_VUELTAS} "
                 f"({_plural(len(problemas), 'objeción abierta', 'objeciones abiertas')}) ──")
        antes = informe
        informe = corregir(transcripcion, informe, problemas)
        informe, restaurados = restaurar_recuentos(antes, informe)
        avisos_recuentos += restaurados
        if narrar:
            for r in restaurados:
                _log(f"     ⚠ recuento restaurado · {r.seccion}: {r.afirmacion_dudosa}")
        vueltas += 1
        llamadas += 1

        datos = informe.model_dump()
        plano = dict(_aplanar(datos))
        # Oscilación = A → B → A; A → A no cuenta.
        oscilantes = []
        for ruta, valor in plano.items():
            previos = historial.get(ruta, [])
            if ruta in congelados or not previos or valor == previos[-1]:
                continue
            if valor in previos[:-1]:
                oscilantes.append(ruta)
        for ruta in oscilantes:
            entrada = _escape_de(ruta)
            if entrada is None:
                continue  # sin escape seguro: solo se anota en el log
            congelados[ruta] = entrada[0]
        if congelados:
            # Se reimponen en cada vuelta: el corrector devuelve el informe entero.
            for ruta, valor in congelados.items():
                _fijar(datos, ruta, valor)
            informe = InformePleno.model_validate(datos)
            plano = dict(_aplanar(datos))

        cambios = [ruta for ruta, valor in plano.items()
                   if valor != historial.get(ruta, [None])[-1]]
        for ruta, valor in plano.items():
            historial.setdefault(ruta, []).append(valor)

        if narrar:
            _log(f"     {_plural(len(cambios), 'campo modificado', 'campos modificados')}"
                 f" · {llamadas} llamadas al modelo")
            for ruta in oscilantes:
                entrada = _escape_de(ruta)
                marca = (f"congelado en {entrada[0]!r} y marcado para revisión humana"
                         if entrada is not None else "sin vía de escape: se deja como está")
                _log(f"     ⚠ AMBIGUO EN ORIGEN · {ruta}: el auditor ha pedido un valor "
                     f"que ya se había descartado — {marca}")

        if not cambios:
            if narrar:
                _log("     el corrector no ha cambiado nada; se sale sin agotar las vueltas")
            break

        rutas_tocadas[:] = cambios
        problemas = revisar(informe)
        llamadas += 1

    # Objeciones abiertas sobre un campo que el bucle ya cambió = ping-pong sin cerrar
    # por falta de vueltas. Se usa la vía de escape: un hueco es recuperable, una
    # votación inventada no.
    if problemas:
        pistas_objeciones = " ".join(f"{p.seccion} {p.afirmacion_dudosa} {p.motivo}"
                                     for p in problemas).lower()
        datos = informe.model_dump()
        actual = dict(_aplanar(datos))
        ambiguos = []
        for ruta, valores in historial.items():
            entrada = _escape_de(ruta)
            if entrada is None or ruta in congelados or len(set(valores)) < 2:
                continue  # nunca cambió: nadie lo disputó
            escape, pistas = entrada
            if actual.get(ruta) != escape and any(p in pistas_objeciones for p in pistas):
                _fijar(datos, ruta, escape)
                congelados[ruta] = escape
                ambiguos.append((ruta, valores))
        if ambiguos:
            informe = InformePleno.model_validate(datos)
            if narrar:
                for ruta, valores in ambiguos:
                    saltos = [v for i, v in enumerate(valores) if i == 0 or v != valores[i - 1]]
                    _log(f"\n  ⚠ AMBIGUO EN ORIGEN · {ruta}"
                         f"\n     el bucle lo dejó en {' → '.join(map(repr, saltos))} y el "
                         f"auditor sigue objetando; se pone en {_escape_de(ruta)[0]!r}."
                         f"\n     El acta NO afirmará ninguna de las dos posturas: "
                         f"decídelo contra la grabación.")

    if narrar:
        _log(f"\n  bucle terminado: {_plural(vueltas, 'vuelta', 'vueltas')}, "
             f"{llamadas} llamadas al modelo, "
             f"{_plural(len(congelados), 'campo ambiguo', 'campos ambiguos')}, "
             f"{_plural(len(problemas), 'objeción', 'objeciones')} sin resolver")
    # Los avisos van al final: dentro del bucle el corrector volvería a borrar el recuento.
    return informe, problemas + avisos_recuentos
