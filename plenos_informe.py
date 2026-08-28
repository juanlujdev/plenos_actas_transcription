#!/usr/bin/env python3
"""
plenos_informe.py - Esquemas, prompts y bucle LLM del informe de plenos.

El modelo devuelve SIEMPRE JSON contra estos esquemas pydantic.
Principio: la vía de escape está dentro del esquema — todo dato que la
transcripción pueda no contener es Optional o tiene un valor "no consta",
para que el esquema nunca fuerce al modelo a inventar.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


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
    parte: Literal["resolutiva", "control"] = Field(description=(
        "'resolutiva' si el punto se somete a acuerdo del Pleno; 'control' para decretos "
        "de alcaldía, daciones de cuenta y todo aquello de lo que la Corporación solo se "
        "da por informada."))
    titulo: str = Field(description="Título del punto EN MAYÚSCULAS, como en un acta municipal")
    texto: str = Field(description=(
        "Deliberación del punto en prosa de acta, con las intervenciones incorporadas en el "
        "orden en que se producen. Separa los párrafos con una línea en blanco: uno por "
        "bloque de debate, de tres a seis frases cada uno. NO escribas aquí el acuerdo (va "
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
    solicitantes: list[str] = Field(description=(
        "Solo en extraordinarias convocadas a petición de concejales: quién la solicita, "
        "con tratamiento, nombre y apellidos completos y grupo si consta ('D. Pedro José "
        "Martínez Martínez del Partido Popular'). Sale de la convocatoria o de la propia "
        "grabación. Lista vacía si la sesión no se convoca a solicitud de concejales."))
    fecha_pleno: str | None = Field(None, description="YYYY-MM-DD solo si se menciona en la grabación; si no, null")
    hora_inicio: str | None = Field(None, description="HH:MM solo si se dice en la grabación; si no, null")
    hora_fin: str | None = Field(None, description="HH:MM solo si se dice en la grabación; si no, null")
    presidente: str | None = Field(None, description=(
        "Quien preside la sesión, solo si la grabación lo identifica; si no, null"))
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

Ese listado da el CARGO y el TRATAMIENTO, que son datos oficiales y no dependen de la
grabación. Lo que sigue exigiendo que la grabación lo diga es QUIÉN HABLA y QUÉ DICE:
el listado nunca sirve para rellenar el campo `presidente` ni para atribuir
intervenciones que la grabación no atribuye (reglas 1, 4 y 5)."""


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
    continúe la fórmula "El Pleno del Ayuntamiento ACUERDA, ". Solo se desglosa en
    "PRIMERO. ... SEGUNDO. ..." si el Pleno adopta varios acuerdos distintos en el mismo
    punto. Un punto resolutivo que no llega a votarse también puede tener acuerdo ("dejar
    el punto sobre la mesa, con el compromiso de...") si eso es lo que se conviene en la
    sesión.
12. Los puntos de actividad de control terminan con "La Corporación se da por informada."
    cuando así ocurre en la grabación.
13. Cuando una frase sea textual de un concejal y valga la pena recogerla tal cual,
    entrecomíllala.
14. PÁRRAFOS. El texto de un punto se parte en párrafos separados por una línea en blanco,
    uno por bloque de debate —la exposición del proponente, la réplica de la oposición, la
    respuesta del equipo de gobierno, el cierre—, de tres a seis frases cada uno. Un punto
    entero en un solo párrafo es un defecto.
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
17. No cites marcas de tiempo dentro de los textos redactados, ni escribas recuentos de
    votos en el texto: los recuentos van en el campo `votacion` y el documento compone la
    frase a partir de ahí.
18. LA APERTURA DE LA SESIÓN. Lo que quien preside declara antes de entrar en el primer
    punto —el aviso de que la sesión se graba y se difunde, la constancia de que preside
    por delegación, la exclusión de un punto del orden del día, una ausencia justificada—
    NO es parte del punto 1: va en `declaraciones_apertura`, casi literal. El texto del
    punto 1 empieza en el debate de ese punto.
19. Español claro y neutro.

LA CONVOCATORIA OFICIAL:
Puede que junto a la transcripción recibas la CONVOCATORIA del pleno: el documento con el
orden del día que el Ayuntamiento publica ANTES de la sesión, a menudo escaneado. Si la
recibes, mándate por estas cuatro reglas. Si no, ignóralas.
20. La convocatoria manda en la FORMA. Los títulos exactos de los puntos, su numeración,
    los números de expediente y el tipo de sesión (ordinaria o extraordinaria, y el motivo
    si es extraordinaria) se toman de ella, no de lo que se entienda en el audio. Copia los
    títulos literalmente, en mayúsculas.
21. La grabación manda en el FONDO. Qué se debate, qué se acuerda, qué se vota y quién
    interviene sale SOLO de la transcripción. La convocatoria dice lo previsto; el acta
    recoge lo ocurrido, y no siempre coinciden.
22. Un punto que figura en la convocatoria pero del que la grabación no dice nada NO se
    redacta como si se hubiera tratado. Si en la grabación se retira, se aplaza o se deja
    sobre la mesa, hazlo constar así; si sencillamente no aparece, omítelo.
23. Un punto que se trata en la grabación y no está en la convocatoria SÍ va al acta —
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
