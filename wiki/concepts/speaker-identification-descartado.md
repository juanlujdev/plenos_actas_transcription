---
type: concept
date_updated: 2026-09-09
source_count: 1
---

# Por qué no se usa Speaker Identification de AssemblyAI

El dashboard de coste de AssemblyAI desglosa cinco líneas — Universal-3.5 Pro, Keyterms
Prompting, Prompting, Speaker Diarization y **Speaker Identification** — y esta última
sale a **$0**: [[pipeline-plenos]] no la usa. Preguntado el 2026-09-09 si convenía
activarla en lugar de la identificación de voces que hace el modelo, la respuesta fue
**no**, y no por precio.

## Qué es realmente

No es biometría de voz ni enrolamiento previo. La documentación es literal: *"Speaker
Identification uses conversation content to infer who's speaking and applies the
identifiers you provide"*. Se le pasa una lista de nombres o roles (con `description`
opcional) en `speech_understanding.request.speaker_identification`, **exige
`speaker_labels: true`** —corre por encima de la diarización, no la sustituye— y devuelve
un `mapping` de etiqueta a nombre.

Es decir: **la misma inferencia textual que ya hace el generador** al rellenar
`identificacion_locutores` (ver [[diarizacion-como-andamiaje]]), hecha por otro modelo con
menos contexto — sin la convocatoria, sin `CORPORACION`, sin la jerarquía de pruebas ni la
regla de exclusión.

## Las cuatro razones

1. **Perdería la prueba, que es todo el valor.** El mapa de voces del 2026-09-07 obliga a
   justificar cada nombre con **cita literal y timestamp**, lo audita el auditor y lo pinta
   la guía con enlaces al vídeo ([[guia-de-verificacion]]). El add-on devuelve un mapping
   pelado: nombre sí, prueba no. Es volver al estado que costó dos atribuciones falsas.
2. **No arregla el fallo real; lo maquilla.** El fallo del 3 de septiembre no fue de
   identificación sino de **fusión**: una etiqueta contenía a dos concejalas. Speaker
   Identification opera sobre esas mismas etiquetas, así que le pondría un nombre a la
   etiqueta contaminada, con más aplomo y sin dejar rastro. Tampoco ve el conflicto de
   turnos alternos, que se detecta en Python (`plenos_guia.conflictos_turnos_alternos`)
   precisamente porque un modelo no puede.
3. **La lista de nombres la pones tú, y eso empuja a rellenar.** Ocho nombres en la
   petición presionan a asignar ocho. El pipeline defiende el *"no identificado en la
   grabación"* como salida legítima ([[via-de-escape-en-el-esquema]]); el add-on no promete
   esa honestidad y no documenta qué hace con un locutor que no encaja.
4. **Los plenos están fuera de su régimen de uso.** `effort: low` (el valor por defecto)
   está pensado para transcripciones **de menos de 10 minutos** con voces bien segmentadas.
   Aquí son de 2 a 3,5 h, con micrófono ambiente, interrupciones y público variable.
   `effort: medium` existe justo para ese caso, pero solo sube el listón de una inferencia
   que ya se hace mejor documentada.

## El coste no entra en la decisión

Los add-ons se suman al ritmo base: Universal-3.5 Pro $0,21/h + diarización $0,02 +
keyterms $0,05 + prompting $0,05 = **$0,33/h** de lo que hoy se paga. Speaker
Identification son **$0,02/h más**, unos siete céntimos por pleno. Es irrelevante: el
argumento es de trazabilidad, no de dinero.

## Lo que sí podría justificarlo algún día

Usarlo como **segunda opinión** pintada en la guía junto al mapa del generador: donde
coincidan, tranquilidad; donde discrepen, revisar. Se descarta por ahora porque añade una
fuente que puede contradecir sin criterio para arbitrar, y el detector determinista de
turnos alternos ya cubre el caso que importa. Reabrir solo si el mapa vuelve a fallar **y**
ese fallo es de identificación, no de fusión.

El margen de mejora real sigue estando aguas arriba, en que la diarización no funda voces
(`speaker_options` con `min 6 / max 15` desde el 2026-09-07). Ningún add-on de
identificación arregla eso.

## Relacionado

[[diarizacion-como-andamiaje]], [[pipeline-plenos]], [[guia-de-verificacion]],
[[via-de-escape-en-el-esquema]], [[2026-08-22-plenos-assemblyai-diarizacion]]
