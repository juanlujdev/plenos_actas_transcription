#!/usr/bin/env python3
"""
plenos_informe.py - Esquemas, prompts y bucle LLM del informe de plenos.

El modelo devuelve SIEMPRE JSON contra estos esquemas pydantic.
Principio: la vía de escape está dentro del esquema — todo dato que la
transcripción pueda no contener es Optional o tiene un valor "no consta",
para que el esquema nunca fuerce al modelo a inventar.
"""

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
          "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10,
          "noviembre": 11, "diciembre": 12}


def normalizar_fecha(texto: str) -> str | None:
    """Cualquier forma habitual de escribir una fecha → 'YYYY-MM-DD'; None si no hay
    ninguna. El esquema pide ISO, pero el modelo devuelve a veces '19 de mayo de 2026'
    y el acta reventaba al componer la cabecera, después de haber pagado la
    transcripción y tres vueltas de LLM. Una descripción de campo no es una validación:
    lo que el documento necesita en un formato concreto se normaliza aquí."""
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
    Un 'HH:MM:SS' se descarta a propósito: es una marca de tiempo de la transcripción,
    no una hora. El modelo dio 'hora_fin': '02:39:28' —el minuto 2h39 de la grabación—
    y el acta habría dicho que el Pleno se levantó a las dos de la madrugada."""
    if re.search(r"\d{1,2}[:.]\d{2}[:.]\d{2}", texto):
        return None
    m = re.search(r"(\d{1,2})[:.](\d{2})", texto)
    if not m:
        return None
    h, minutos = int(m.group(1)), int(m.group(2))
    return f"{h:02d}:{minutos:02d}" if h <= 23 and minutos <= 59 else None


# Fórmulas de escape que el modelo escribe cuando algo no consta. En los campos que las
# admiten (el mapa de voces, quién formula un ruego) son prosa legítima que el acta
# imprime; en los que piden null son una cadena no vacía que se cuela en el documento
# como si fuera un nombre. Ver _presidente_o_nada.
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
        """El acuerdo es la continuación de una fórmula que compone el documento, no una
        frase suelta. El modelo tiende a devolverla ya escrita ("El Pleno del Ayuntamiento
        ACUERDA, rechazar...") y el acta salía diciéndola dos veces; y a colar en `acuerdo`
        el cierre de un punto de control ("La Corporación se da por informada"), que no es
        un acuerdo del Pleno. Se normaliza en vez de fallar: son defectos de forma, y el
        contenido es correcto."""
        if not self.acuerdo:
            return self
        acuerdo = re.sub(r"^\s*el\s+pleno\s+del\s+ayuntamiento\s+ACUERDA[,:]?\s*",
                         "", self.acuerdo.strip(), flags=re.IGNORECASE)
        acuerdo = re.sub(r"^(por\s+unanimidad|por\s+mayoría)[,:]?\s*", "", acuerdo,
                         flags=re.IGNORECASE)
        if self.parte == "control":
            # No se pierde: si el texto no lo dice ya, ese cierre pasa al final del punto.
            if acuerdo and acuerdo.rstrip(".") not in self.texto:
                self.texto = f"{self.texto.rstrip()}\n\n{acuerdo}"
            self.acuerdo = None
        else:
            self.acuerdo = acuerdo or None
        return self

    @field_validator("votacion", mode="before")
    @classmethod
    def _cadena_de_ausencia_es_null(cls, v):
        """El modelo escribe a veces la cadena "sin votación" donde va el objeto: hay dos
        vías de escape parecidas (`votacion: null` y `resultado: "sin votación"`) y las
        confunde. La intención es inequívoca —no hubo votación—, así que se normaliza en
        vez de tirar la generación entera del informe. Cualquier otra cadena se deja
        pasar para que pydantic falle: ahí sí se estaría perdiendo información."""
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
    puntos: list[str] = Field(description="Un elemento por ruego o pregunta")


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
        """El campo pide null cuando no se identifica a quien preside, pero el modelo
        devuelve la fórmula de escape que sí usan otros campos ("no identificado en la
        grabación"). Como es una cadena no vacía, `informe.presidente or HUECO` la da por
        buena y el acta del 2026-09-03 cerró con "...cumpliendo con el objeto del acto, no
        identificado en la grabación levanta la sesión...", además de poner esa frase en la
        celda "Presidida por". Normalizar aquí arregla los dos sitios a la vez y deja el
        hueco que la secretaria rellena, que es lo que el campo quería decir."""
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


# ══════════════════════════════════════════════════════════════════════════════
# Prompts de los tres roles
# ══════════════════════════════════════════════════════════════════════════════

# Quién ocupa la Alcaldía y quién preside de hecho. Es lo primero que hay que revisar
# tras una elección municipal, un cambio de Alcaldía o una delegación de funciones: de
# aquí salen el tratamiento de todo el acta y la fórmula del encabezado. El acta la firma
# la secretaría, así que el título tiene que ser el que consta en el nombramiento —
# "Segunda Teniente de Alcalde que preside por delegación", NO "Alcaldesa en funciones",
# que sería un cargo que nadie le ha dado.
PRESIDENCIA = {
    # Cómo se nombra a quien preside en el cuerpo del acta, cada vez que interviene.
    "tratamiento": "la Sra. Teniente de Alcalde",
    # Fórmula del encabezado, detrás de "bajo la Presidencia de ".
    "formula": ("la segunda Teniente Alcalde Dª Lorena Luján Chujfi, que actúa en virtud "
                "de la delegación de funciones efectuadas por el Sr. Alcalde – Presidente, "
                "D. Sergio de Fez Cerezuela"),
    # Género de las dos fórmulas fijas de la plantilla.
    "abre_la_sesion": "la Presidenta abre la sesión",
    "secretaria": "la Secretaria",
}

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
  dirigen a ella como "Chari": es la misma persona.
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
- Se les nombra por el CARGO o la condición con la que se presentan ("la presidenta
  de la Asociación de Jubilados", "un representante de la asociación de vecinos"); si
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


# Va a los tres roles. La regla vivía solo en el corrector, y el dato inventado que la
# incumplía lo había escrito el generador: una restricción que se le impone al corrector
# la necesita también quien redacta primero.
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
   ("tiene la palabra el concejal de...", "responde la alcaldesa..."), directamente o a
   través de su etiqueta de locutor según las reglas de arriba. Nunca por deducción.
6. Si un fragmento es incoherente por errores de transcripción, no lo interpretes
   creativamente: descártalo o marca "no consta".

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
    transcribe los reproches uno a uno.
16 bis. LO QUE UN CONCEJAL PIDE QUE CONSTE. La regla 16 poda el tira y afloja, pero no
    puede podar una observación que el interviniente pide expresamente que conste en acta
    ("que conste en acta", "que quede reflejado", "quiero que se recoja"), ni la reserva,
    la discrepancia o la advertencia con la que sostiene su postura sobre el asunto que se
    trata. Esas van al `texto` del punto, en el sitio donde se producen, atribuidas a quien
    las hace y en UNA o DOS frases, redactadas en el registro del acta: se recoge lo que
    afirma, no cómo lo dice ni cuántas veces lo repite. Si se explica de forma tan confusa
    que no se entiende qué afirma, se omite (regla 6) — nunca se interpreta lo que quiso
    decir. Y sigue fuera del acta lo que no es una observación: el reproche personal, la
    insistencia y la anécdota que no aportan ni postura ni dato.
16 ter. LOS ASUNTOS QUE NO ESTÁN EN EL ORDEN DEL DÍA. En estos plenos es habitual que
    dentro del debate de un punto se acaben tratando temas paralelos. Esos temas NO se
    redactan en el acta: van a `asuntos_no_convocados`, uno por tema, sintetizado en una o
    dos frases con quién lo plantea, el título del punto en cuyo debate surge y su
    timestamp. Solo los que importan para el asunto que se está tratando o para el
    Ayuntamiento; el comentario de pasada no es un asunto. No confundir con la regla 24: lo
    que se trata como punto propio y se somete a acuerdo o a votación es un punto del orden
    del día aunque no estuviera convocado, y va en `orden_del_dia`, no aquí.
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
    igual en todo el informe: Enguídanos con tilde, Las Chorreras, El Salto, la Gran Vía
    — la única excepción son los títulos que se copian literalmente de la convocatoria
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

PROMPT_CORRECTOR = f"""Eres el corrector de informes de plenos del Ayuntamiento de
Enguídanos. Recibes: la transcripción literal (con marcas [HH:MM:SS]), el informe completo
en JSON, y la lista de problemas detectados por un auditor (cada uno con su evidencia).

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
   (Enguídanos, Las Chorreras), salvo en los títulos copiados de la convocatoria.
   Si al corregir otra cosa te encuentras una de estas, arréglala: son de forma, no
   tocan el fondo de lo que se dijo ni de lo que se acordó."""


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


def _reensamblar_sse(lineas) -> dict:
    """Reensambla un stream SSE de OpenRouter en la misma forma que devuelve la API sin
    streaming, para que el resto del código no note la diferencia. Función aparte de la
    red porque es lo único con lógica que testear."""
    trozos, usage, fin, error = [], {}, None, None
    for linea in lineas:
        # Los ": OPENROUTER PROCESSING" son los keep-alive que mantienen viva la conexión
        # mientras el modelo razona: justo lo que evita el idle timeout.
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
    """POST a OpenRouter; ante 429 o error de servidor reintenta con el mismo backoff
    exponencial que _reintentar() en procesar_pleno.py (2, 4, 8 min).

    Va en streaming, y no por interactividad: sin él la petición no emite un solo byte
    mientras gemini-2.5-pro razona — el auditor pasa minutos pensando —, el proveedor la
    da por ociosa y la corta con un 504 "Upstream idle timeout exceeded" dentro de un
    HTTP 200. Como la temperatura es 0, reintentarla producía exactamente el mismo
    razonamiento y el mismo corte: cuatro intentos idénticos y el bucle muerto. Con SSE
    llegan los deltas y los keep-alive, así que la conexión nunca está ociosa.
    """
    cuerpo = {**cuerpo, "stream": True, "stream_options": {"include_usage": True}}
    for i in range(intentos):
        # timeout de tupla: 30 s para conectar y 300 s ENTRE trozos, no en total — con
        # streaming el tope global no tiene sentido y cortaría auditorías legítimas.
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
        r.raise_for_status()
        # Sin esto requests decodifica el SSE como ISO-8859-1 (text/event-stream no
        # declara charset) y se destrozan los acentos de todo el informe.
        r.encoding = "utf-8"
        with r:
            datos = _reensamblar_sse(r.iter_lines(decode_unicode=True))
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
    # `error` manda sobre `content`: un stream cortado a mitad deja JSON truncado, que
    # pydantic rechazaría con un error de parseo que no dice nada de la causa real.
    if eleccion.get("error") or not contenido:
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
                    convocatoria: bytes | None = None,
                    rutas_tocadas: list[str] | None = None) -> AuditoriaInforme:
    # El auditor recibe la convocatoria igual que el generador. Sin ella marcaría
    # cada título tomado del orden del día como afirmación no respaldada — la
    # transcripción trae el nombre destrozado por Whisper — y quemaría las tres
    # vueltas sin arreglar nada. Es el mismo motivo por el que recibe CORPORACION.
    #
    # `rutas_tocadas` son los campos que el corrector acaba de cambiar, calculados en
    # Python comparando el JSON anterior con el nuevo — no se le pregunta a él qué
    # tocó, que es justo el que se equivoca. Es una pista de dónde mirar primero, no
    # un recorte del ámbito: el auditor sigue revisando el informe entero.
    _log("  → AUDITOR (busca afirmaciones que la transcripción no respalde"
         + (f"; {_plural(len(rutas_tocadas), 'campo recién tocado', 'campos recién tocados')})"
            if rutas_tocadas else ")"))
    contenido = (f"TRANSCRIPCIÓN DEL PLENO:\n\n{transcripcion}\n\n"
                 f"INFORME A AUDITAR (JSON):\n\n{informe.model_dump_json()}")
    if rutas_tocadas:
        contenido += ("\n\nCAMPOS QUE ACABA DE MODIFICAR EL CORRECTOR:\n"
                      + "\n".join(f"- {r}" for r in rutas_tocadas))
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


def _aplanar(valor, prefijo: str = ""):
    """{'a': [{'b': 1}]} → {'a[0].b': 1}. Solo hojas: lo que hay que comparar entre
    vueltas son los valores concretos, que es donde el corrector cambia una cosa por
    otra."""
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


# Campos donde una disputa NO puede resolverse eligiendo uno de los dos valores: el acta
# estaría afirmando como oficial algo que el propio auditor discute. La vía de escape del
# esquema es la única salida honesta, y es además lo que hace la secretaria en el acta
# real ante una votación que nadie declara: narra lo que oyó y no proclama resultado.
# Cada entrada lleva el valor de escape y las pistas que delatan que una objeción del
# auditor habla de ese campo (`Problema.seccion` es prosa del modelo, no una ruta).
_AMBIGUOS = {
    "votacion.resultado": ("no consta", ("votaci", "resultado")),
}


def _escape_de(ruta: str):
    """(valor de escape, pistas) de una ruta en disputa, o None si no hay escape seguro."""
    for sufijo, entrada in _AMBIGUOS.items():
        if ruta.endswith(sufijo):
            return entrada
    return None


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
    # Las rutas que el corrector acaba de tocar viajan al auditor en una lista mutable
    # que se rellena antes de cada llamada: los fakes que inyectan los tests tienen
    # firma (transcripcion, informe) y ese contrato no se toca.
    rutas_tocadas: list[str] = []
    generar = generar or (lambda t: generar_informe(t, convocatoria))
    auditar = auditar or (lambda t, i: auditar_informe(t, i, convocatoria, rutas_tocadas))
    corregir = corregir or (lambda t, i, p: corregir_informe(t, i, p, convocatoria))

    informe = generar(transcripcion)
    problemas = auditar(transcripcion, informe).problemas
    vueltas, llamadas = 0, 2
    # Historial de cada campo del informe a lo largo de las vueltas, para detectar el
    # ping-pong: el auditor pide un valor, dos vueltas después pide el contrario, y el
    # corrector obedece a los dos. Se detecta sobre el informe y no sobre las objeciones
    # porque `Problema.seccion` es prosa que escribe el modelo, no una ruta fiable.
    historial = {ruta: [valor] for ruta, valor in _aplanar(informe.model_dump())}
    congelados: dict[str, object] = {}

    while problemas and vueltas < MAX_VUELTAS:
        if narrar:
            _log(f"\n  ── vuelta {vueltas + 1} de {MAX_VUELTAS} "
                 f"({_plural(len(problemas), 'objeción abierta', 'objeciones abiertas')}) ──")
        informe = corregir(transcripcion, informe, problemas)
        vueltas += 1
        llamadas += 1

        datos = informe.model_dump()
        plano = dict(_aplanar(datos))
        # Oscilación es A → B → A: el campo cambia en esta vuelta y vuelve a un valor
        # que ya tuvo antes. Un campo que el corrector deja igual (A → A) no es ping-pong.
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
                continue  # se anota en el log, pero no se toca: no hay escape seguro
            congelados[ruta] = entrada[0]
        if congelados:
            # Se reimponen en cada vuelta: el corrector devuelve el informe entero y
            # volvería a proponer el valor en disputa mientras el auditor lo reclame.
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
            # El corrector ya no cambia nada: las vueltas que quedan son dinero tirado.
            if narrar:
                _log("     el corrector no ha cambiado nada; se sale sin agotar las vueltas")
            break

        rutas_tocadas[:] = cambios
        problemas = auditar(transcripcion, informe).problemas
        llamadas += 1

    # Salir con objeciones abiertas sobre un campo que el bucle ya cambió significa que
    # el auditor sigue discutiendo un valor que él mismo hizo cambiar: es el ping-pong
    # que no llega a cerrarse porque se acaban las vueltas antes. Pasó de verdad el
    # 2026-08-29 con la votación del punto 1 —el auditor pidió "rechazado" en la primera
    # auditoría y "aprobado" en la cuarta—, y el acta se quedó afirmando un resultado
    # que la grabación no declara. Aquí se cambia por la vía de escape: un hueco que
    # rellena la secretaria es un fallo recuperable; una votación inventada, no.
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
                    # Solo los cambios: repetir 'rechazado' tres veces no dice nada.
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
    return informe, problemas
