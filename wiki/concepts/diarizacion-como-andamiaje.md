---
type: concept
date_updated: 2026-09-07
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

El bloque `DIARIZACION` de `plenos_informe.py` la fija así:

1. La misma etiqueta es la misma persona durante toda la sesión — **salvo que el
   transcriptor haya fundido dos voces parecidas**, que ocurrió y tiene su propio apartado
   más abajo.
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

Por eso la configuración se inclina deliberadamente a **partir de más antes que a fundir**,
y por eso la revisión humana contra la grabación sigue siendo irreemplazable: la
diarización de una sala con micrófono ambiente y gente hablando encima no es perfecta, y el
auditor no puede detectar un error que ya viene en la transcripción.

## El riesgo se materializó: el pleno del 3 de septiembre de 2026

Este apartado describía un riesgo teórico. **Ocurrió**, y de la forma exacta que anticipaba.

El acta generada atribuyó a *"La Sra. Teniente de Alcalde, Dª Lorena Luján Chujfi"* unos
ruegos sobre la limpieza de los baños del hogar del jubilado. Los formuló **la presidenta de
la Asociación de Jubilados**. La etiqueta `Interviniente B` contenía a las dos:

```
[00:00:32] B: Damos comienzo al Pleno ordinario del 30 de septiembre...   ← quien preside
[03:00:59] B: ...que llevo como presidenta de la asociación de jubilados  ← otra persona
```

**Corrección del 2026-09-08: esa presidenta NO era una vecina asistente.** Es
**Mª Rosario Cerdán Pérez, "Chari", concejala del equipo de gobierno**, que preside además
la Asociación de Jubilados. Lo dice la propia grabación tres minutos después —
*"[03:03:39] Ahora te voy a hacer una pregunta, Chari. ¿Por qué no has pedido la subvención
de la Diputación para asociaciones de jubilados?"* — y lo confirmó el desarrollador. La
etiqueta fundía a **dos concejalas**, no a una concejala y una vecina.

El diagnóstico de la mezcla seguía siendo correcto; la identidad de la segunda voz, no. Y
esa confusión no era casual: el bloque PÚBLICO ASISTENTE de `CORPORACION` ponía como ejemplo
de cómo nombrar a alguien del público, literalmente, *"la presidenta de la Asociación de
Jubilados"* — el único cargo del pueblo que lo ostenta una concejala. En la corrida del
2026-09-08 el acta volvió a atribuir esos ruegos a ese cargo, sin nombre, como si fueran de
una vecina. Desde entonces `CORPORACION` dice quién es (y el ejemplo del público es otro),
así que la grabación y el listado ya no se contradicen. Los socios de la asociación que
asisten como público y hablan de sus mismos asuntos **sí** son vecinos: la regla distingue a
la presidenta de sus socios.

Toda la transcripción de ese pleno —3h29, siete concejales, la secretaria y varios vecinos—
salió con **6 etiquetas**.

El modelo no se equivocó: aplicó la regla 2 correctamente sobre una etiqueta que ya venía
contaminada. Y el auditor tampoco podía verlo, por lo que dice el párrafo anterior.

**La causa fue una premisa falsa en el código, no un error de cálculo.** El comentario de
`speaker_options` decía literalmente *"La corporación son 7 miembros más la secretaria; el
público no interviene"*. El público sí interviene: en los plenos de Enguídanos asisten
vecinos y en ruegos y preguntas intervienen tres o cuatro. Con siete concejales, la
secretaria y esos vecinos, el máximo real ronda las **doce voces**, y el tope estaba en
diez. Al no poder crear etiquetas nuevas, el transcriptor fundió.

Lo corregido el 2026-09-07:

- `speaker_options` pasa a `min_speakers_expected: 6` / `max_speakers_expected: 15`. El
  máximo va holgado a propósito: partir de más cuesta una atribución perdida, fundir cuesta
  una atribución falsa.

  Los números salen de la corporación real, no de una estimación: **seis concejales, la
  delegada y quien preside son ocho**, y aunque falte alguno **nunca bajan de seis**; con
  los vecinos que asisten, **nunca pasan de doce**. De ahí el mínimo justo en ese suelo y el
  máximo con margen por encima del techo, porque pasarse de máximo no cuesta nada y quedarse
  corto fusiona.

  **Los dos son límites duros, no pistas**, y conviene tenerlo presente antes de tocarlos.
  La documentación de AssemblyAI es literal: del mínimo, *"a hard lower limit on the number
  of speaker labels. The model won't return fewer speakers than this"*; del máximo, *"if
  more people speak than this, the additional speakers are merged into existing labels"*.
  Es decir: **el máximo bajo no es que estorbe, es que fusiona por diseño**, que es
  exactamente lo que ocurrió.

  De ahí también una corrección a la primera versión de este arreglo, que bajaba el mínimo
  de 6 a 4. Iba en la dirección equivocada: el mínimo **empuja a separar**, que es el lado
  seguro, así que bajarlo le da permiso al modelo para agrupar de menos. Vuelve a 6, que es
  además el suelo real de asistencia. Detalle sospechoso que lo respalda: la transcripción
  del 3 de septiembre salió con **exactamente 6 etiquetas**, que era el mínimo configurado
  entonces — con doce personas hablando, el mínimo parecía estar sujetando el resultado por
  abajo mientras el máximo lo sujetaba por arriba.
- **La regla 1 deja de darse por buena sin más.** "La misma etiqueta es la misma persona"
  es cierta *salvo que el transcriptor haya fundido voces*, y la señal es que una misma
  etiqueta afirme identidades incompatibles (presidir la sesión y presidir la asociación de
  jubilados). Cuando eso pasa, la etiqueta se marca como contaminada y sus intervenciones
  van a "no identificado", salvo las que se identifiquen solas.
- Los prompts aprenden que **existe público**: que no vota, que no va en `asistentes` ni
  `ausentes`, que cambia en cada pleno y por tanto no se le puede identificar por descarte
  contra la corporación, y que se le nombra por la condición con que se presenta ("la
  presidenta de la Asociación de Jubilados") y **nunca con nombre y apellidos** — el acta se
  publica en la web y los datos de particulares no se recogen si basta con su condición.

La lección que queda: **el riesgo estaba bien identificado y la mitigación mal calibrada**,
porque descansaba sobre un dato del mundo real que nadie había comprobado. Un número de
configuración que codifica una suposición sobre quién habla en una sala merece la misma
desconfianza que un dato que escribe el modelo.

## El mapa de voces (2026-09-07)

De este fallo salió también un cambio de fondo: la identificación de voces deja de ser una
deducción implícita del modelo mientras redacta y pasa a ser **un dato explícito y
auditable** del informe (`identificacion_locutores`). Cada etiqueta lleva a quién
corresponde, la **cita literal** que lo demuestra y su timestamp; el acta solo puede
nombrar a quien esté en ese mapa, el auditor lo revisa como parte de su trabajo, y la
funcionaria lo ve al principio de la guía de verificación, con enlaces al vídeo.

El valor no es que el modelo acierte más —que también, porque ha de justificar cada nombre
con una cita en vez de con una corazonada—, sino que **cuando falle se vea en un sitio y en
dos minutos**: ocho líneas con sus enlaces, en lugar de descubrirlo leyendo el acta entera y
tropezando con una frase rara, que es como se encontró este error.

Dos reglas nuevas salen directamente de las dos pistas que había en esta transcripción y
que nadie usó:

- **Dar la palabra por el nombre no identifica a quien habla después.** En el minuto 1:46 la
  Presidencia dice *"pues Joaquín, ¿tú tienes algo que decir de este acta?"* y tomó la
  palabra otra persona. De ahí salió la segunda atribución falsa del acta: una intervención
  de Dª Mª Rosario Cerdán Pérez firmada por D. Joaquín Martínez Luján.
- **Regla de exclusión: si una voz llama a alguien por su nombre, esa voz no es esa
  persona.** En el minuto 5:49 esa misma voz decía *"esto ocurrió, Joaquín"*. Descartar es
  tan valioso como identificar, y es lo que resolvió el caso al revisarlo a mano.

### Dos reglas más, del hueco simétrico

Las reglas anteriores detectan *una etiqueta que dice ser dos personas*. Preguntado por el
caso contrario, apareció el hueco simétrico: **dos etiquetas identificadas como la misma
persona**, que nada detectaba. Puede significar que el transcriptor partió a una persona en
dos voces (benigno) o que una de las dos identificaciones es falsa (no lo es).

- **Regla de turnos alternos.** Dos etiquetas que se alternan hablando en un mismo
  intercambio —se responden, se interrumpen— **son personas distintas**: nadie se responde a
  sí mismo. Si el mapa las asigna a la misma persona, una identificación es falsa y ambas
  van a "no identificado" salvo que una tenga prueba claramente más fuerte. El matiz
  importa: dos etiquetas que **nunca** se alternan sí pueden ser la misma persona partida en
  dos voces, y eso no se marca.
- **Jerarquía de pruebas.** Identificarse a uno mismo > que alguien te nombre respondiéndote
  > que se dirijan a ti por nombre o cargo. Y la consecuencia que cierra el "gana la
  primera" de la regla de propagación: *si una prueba más fuerte contradice a una más débil
  ya anotada, gana la fuerte, no la que llegó primero*.

**La detección de la primera vive en Python, no solo en el prompt** (`plenos_guia.
conflictos_turnos_alternos`). El motivo es sutil: la propia regla resuelve el conflicto
mandando ambas voces a "no identificado", que es **indistinguible de un hueco honesto**. Si
solo dependiera del modelo, un conflicto no detectado se vería igual que una sesión donde
nadie se identificó. Calculado sobre la transcripción, se detecta siempre y se pinta en la
guía con el mismo peso visual que una etiqueta contaminada.

Comprobado contra el pleno del 3 de septiembre: sus **seis etiquetas se alternan entre sí**
—las quince combinaciones posibles, cientos de veces—, luego las seis son demostrablemente
personas distintas y ese pleno no tiene este conflicto. Seis voces distintas para doce o más
personas hablando es, a su vez, la medida de cuánto fundió el transcriptor.

## Relacionado

[[2026-08-22-plenos-assemblyai-diarizacion]], [[pipeline-plenos]],
[[bucle-generador-auditor-corrector]], [[via-de-escape-en-el-esquema]],
[[convocatoria-como-fuente]]
