---
type: concept
date_updated: 2026-08-22
source_count: 1
---

# La diarización como andamiaje, no como identidad

Desde 2026-08-22 la transcripción de [[pipeline-plenos]] viene **diarizada**: AssemblyAI
`universal-3-5-pro` separa las voces y cada línea sale como
`[HH:MM:SS] Interviniente A: texto` (ver
[[2026-08-22-plenos-assemblyai-diarizacion]]).

Esa etiqueta es exactamente lo que dice ser y nada más: **una voz, no una persona**. El
transcriptor sabe que dos intervenciones son de la misma garganta; no sabe de quién.
Confundir esas dos cosas es lo que convertiría una mejora técnica en una invención con
pinta de oficial, que es justo lo que [[via-de-escape-en-el-esquema]] existe para evitar.

## La regla

El bloque `DIARIZACION` de `scripts/plenos_informe.py` la fija así:

1. La misma etiqueta es la misma persona durante toda la sesión.
2. Si **en cualquier momento** la grabación identifica a quien lleva una etiqueta —se
   presenta, la Presidencia le da la palabra por su nombre o su cargo, alguien le responde
   nombrándole—, se le atribuyen **todas** las intervenciones de esa etiqueta, también las
   anteriores.
3. Si una etiqueta no se identifica nunca, sus intervenciones siguen siendo *"no
   identificado en la grabación"*. Nada de deducir por el orden de palabra, por el tema,
   por cuánto habla o por el reparto de la corporación.
4. Las etiquetas **no se escriben en el acta**: son andamiaje de la transcripción, igual
   que los timestamps.

El punto 2 es el que hace valiosa la diarización. Antes, una intervención solo podía
atribuirse si la grabación identificaba a quien hablaba **en ese momento**; ahora una sola
identificación en toda la sesión ancla el resto. En un pleno real eso rinde mucho: el
arranque suele identificar a casi todo el mundo.

Y sigue sin ser una inferencia: la cadena "esta voz es la de X" + "estas líneas son de
esta voz" está enteramente respaldada por la grabación. Lo que cambia no es la regla de
fidelidad, sino cuánta información hay para aplicarla.

## Por qué el auditor también lo recibe

Es el mismo patrón que ya obligó a dar `CORPORACION` y la convocatoria al auditor (ver
[[bucle-generador-auditor-corrector]] y [[convocatoria-como-fuente]]):

> Toda fuente autorizada que se le dé al generador para que escriba algo que la
> transcripción no contiene hay que dársela también al auditor, o la marcará como
> inventada.

Sin el bloque, el auditor vería *"D. Fernando Pons manifiesta..."* en un punto donde esa
línea de la transcripción solo dice `Interviniente C:`, no encontraría el nombre, y la
marcaría como afirmación no respaldada — quemando las tres vueltas del bucle en cada
ejecución. Su instrucción explícita es la contraria: la propagación es la conducta
esperada; lo que **sí** debe señalar es que se ponga nombre a una etiqueta que la
grabación no identifica nunca, o que se mezclen etiquetas distintas en una misma persona.

El corrector lo recibe igualmente, porque es quien reescribe las atribuciones que el
auditor objeta.

## El riesgo que introduce

La propagación amplifica: si la diarización parte a una persona en dos etiquetas, el peor
efecto es que una de ellas se quede sin identificar — recuperable, honesto. Pero si
**funde** a dos personas en una etiqueta, la propagación pone en boca de una lo que dijo
la otra, y eso es una falsedad en un documento que se sella.

Por eso la configuración se inclina deliberadamente a **partir de más antes que a fundir**
(`min_speakers_expected: 6`, `max_speakers_expected: 10`), y por eso la revisión humana
contra la grabación sigue siendo irreemplazable: la diarización de una sala con micrófono
ambiente y gente hablando encima no es perfecta, y el auditor no puede detectar un error
que ya viene en la transcripción.

## Relacionado

[[2026-08-22-plenos-assemblyai-diarizacion]], [[pipeline-plenos]],
[[bucle-generador-auditor-corrector]], [[via-de-escape-en-el-esquema]],
[[convocatoria-como-fuente]]
