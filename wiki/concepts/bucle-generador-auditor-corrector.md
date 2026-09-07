---
type: concept
date_updated: 2026-09-07
source_count: 6
---

# Bucle generador → auditor → corrector

Mecanismo de fiabilidad de [[pipeline-plenos]] para que el informe sea fiel a la transcripción. Diseñado en [[2026-07-31-plenos-youtube-pipeline-design]], implementado en `scripts/plenos_informe.py` y aprobado por el usuario en un checkpoint explícito durante el desarrollo.

## Los tres roles

Un mismo modelo (temperatura 0) con **tres prompts distintos**, cada uno una función Python con su `response_schema`:

1. **Generador** — transcripción → `InformePleno`. Prohibido inferir o rellenar huecos; lo que no conste usa [[via-de-escape-en-el-esquema]].
2. **Auditor** — transcripción + informe → `AuditoriaInforme`: lista de problemas concretos, cada uno con sección, afirmación dudosa, motivo y **cita literal** de la transcripción como evidencia. Lista vacía = visto bueno.
3. **Corrector** — transcripción + informe completo + problemas → `InformePleno` corregido. Recibe siempre el contexto entero, nunca solo el punto a corregir, y devuelve **el mismo esquema que el generador**, de modo que el bucle es estable en tipos y el auditor siempre revisa el mismo objeto.

## El bucle

```python
informe = generar(transcripcion)
problemas = auditar(transcripcion, informe).problemas
vueltas = 0
while problemas and vueltas < MAX_VUELTAS:   # MAX_VUELTAS = 3
    informe = corregir(transcripcion, informe, problemas)
    vueltas += 1
    problemas = auditar(transcripcion, informe).problemas
return informe, problemas
```

**Sin framework de agentes**: no hay herramientas ni autonomía que orquestar, así que el flujo de control es un `while` propio y determinista. El tope de 3 vueltas existe porque dos prompts en desacuerdo pueden ciclar indefinidamente. Si tras el tope quedan problemas, se devuelven como pendientes y se listan por consola al terminar la generación — **no se escriben dentro del acta**, que tiene que salir limpia para la secretaria; es en ese momento, antes de enviarla por email, cuando se decide si hace falta revisar algo a mano (ver [[pipeline-plenos]]).

Los tres roles se pueden inyectar como parámetros (`generar=`, `auditar=`, `corregir=`), lo que permite probar el bucle con fakes sin tocar la red — es lo que hacen los tests.

## El ping-pong: cuando el auditor se contradice a sí mismo (2026-08-29)

En el pleno del 19 de mayo el bucle agotó las tres vueltas y dejó el acta afirmando un
resultado de votación que la grabación no declara. El rastro, sobre el mismo campo
`orden_del_dia[0].votacion.resultado`:

| | |
|---|---|
| Auditoría 1 | «`aprobado` no está respaldado: hay empate con abstención → **rechazo**» |
| Corrector v1 | pone `rechazado` — obedeció |
| Auditorías 2 y 3 | no lo mencionan: `rechazado` pasa el filtro dos veces |
| Auditoría 4 | «`rechazado` no está respaldado: un concejal dice **"Aprobada"**» |

**El corrector hizo su trabajo las dos veces; el que pidió una cosa y su contraria fue el
auditor.** La objeción con la que terminó la ejecución era el auditor objetando su propia
corrección. Y la respuesta correcta no era ninguno de los dos valores: la grabación
(`[00:57:20]`–`[00:58:04]`) canta votos en contra de dos grupos, una abstención, un
«¿quién vota a favor?» sin respuesta audible y un «Aprobada» suelto dicho por un concejal
de la oposición que acababa de votar en contra. Era `resultado: "no consta"`, la
[[via-de-escape-en-el-esquema]] que el corrector tenía instrucción de usar y no usó.

### La raíz: el auditor muestrea, no verifica

Las cuatro auditorías completas devolvieron **cuatro conjuntos distintos** de objeciones y
ninguno vacío. Sobre 148.665 caracteres, cada pasada encuentra un subconjunto distinto de
defectos: no es verificación monótona, es muestreo independiente. Por eso la condición de
salida —«una auditoría completa devuelve lista vacía»— es prácticamente inalcanzable y el
bucle agota siempre el tope.

Eso tiene una consecuencia contraintuitiva: **las auditorías repetidas son lo que sube el
recall**. De las tres correcciones reales de contenido de esa ejecución, dos nacieron en
las auditorías 2 y 3 (`asistentes`/`ausentes` incompletos y el titular del vehículo mal
atribuido). Se descartó por eso rediseñar el bucle a una sola auditoría canónica: habría
producido un acta peor.

### Lo que se implementó (etapa 1)

Detección **determinista, sobre el informe y no sobre las objeciones** — `Problema.seccion`
es prosa que escribe el modelo, no una ruta fiable:

1. `_aplanar()` convierte el informe en `{ruta: valor}` y se guarda el **historial de cada
   campo** por vuelta. De ahí salen gratis el recuento de campos modificados y el rastro.
2. **Oscilación** = A → B → A: el campo cambia en esta vuelta y vuelve a un valor que ya
   tuvo. Un campo que el corrector deja igual **no** es ping-pong — confundir A → A con
   una oscilación fue un bug real, cazado por un test antes de llegar a producción.
3. **Disputa sin cerrar**: si el bucle termina con objeciones abiertas sobre un campo que
   él mismo cambió, es el mismo ping-pong que no llegó a completarse porque se acabaron
   las vueltas. Es exactamente lo que pasó el 19 de mayo, y la detección de oscilación
   sola **no** lo habría cazado.
4. En ambos casos se aplica la **vía de escape** (`_AMBIGUOS`), no se elige un bando, y el
   valor se **reimpone en cada vuelta** posterior: el corrector devuelve el informe entero
   y volvería a proponer el valor en disputa mientras el auditor lo reclame.
5. **Salida temprana**: si una corrección no cambia nada, las vueltas restantes son dinero
   tirado.
6. **El auditor de cada vuelta recibe las rutas que el corrector acaba de tocar**
   (`CAMPOS QUE ACABA DE MODIFICAR EL CORRECTOR`). Se calculan en Python comparando los
   dos JSON — no se le pregunta al corrector qué cambió, que es justo el que se equivoca —
   y su prompt dice explícitamente que es **dónde mirar primero, no un recorte del
   ámbito**: sigue auditando el informe entero. Es la mitad útil de la "verificación de
   regresión acotada" de la etapa 2, sin su coste ni su pérdida de recall: habría cazado
   el "José Ríos" en la vuelta 2 en vez de la 3.

Hoy `_AMBIGUOS` solo cubre `votacion.resultado`, y a propósito: es el campo donde el acta
afirma algo con valor jurídico y el único con un escape inequívoco. Una oscilación en
`texto` se registra en el log pero no se toca — inventar semántica de escape para prosa
sería peor que el problema.

La objeción **sigue viva en los pendientes**: el escape no la resuelve, evita que el acta
afirme lo que se discute. Un hueco que rellena la secretaria es un fallo recuperable; una
votación fabricada, no.

### Lo que quedó fuera (etapa 2, sin implementar)

Que el corrector devuelva un **parche** (`json_path`, valor anterior, valor nuevo,
justificación) en vez del `InformePleno` entero, más la verificación de regresión acotada
a las rutas que tocó. Es la ganancia arquitectónica real —en esa misma ejecución el
corrector, arreglando el punto 2, escribió «titularidad de D. José Ríos» sin que nadie se
lo pidiera— pero choca con el modo `strict` de OpenRouter: `valor_nuevo` es de tipo
variable y acabaría serializado como cadena, que es la clase de bug de
[[via-de-escape-en-el-esquema]]. Requiere acotar los parches a prosa y escalares.

## Lo que el auditor no puede detectar

**Errores que ya vienen en la transcripción.** El auditor compara el informe contra la transcripción, así que si Whisper transcribió mal un nombre y el informe lo copia fielmente, el auditor da su visto bueno. Por eso la spec insiste en que la revisión humana contra el audio es una capa irreemplazable.

De ahí sale una consecuencia de diseño poco obvia: al añadir el listado de la corporación municipal al generador para que corrija los nombres deformados, **hubo que dárselo también al auditor**. Si no, vería "Sergio de Fez Cerezuela" en el informe, buscaría esa cadena en la transcripción (que dice "Féceres Zuela"), no la encontraría, y la marcaría como afirmación no respaldada — quemando las tres vueltas de corrección en cada ejecución sin arreglar nada. El auditor tiene instrucción explícita de no señalar esas correcciones ni el tiempo verbal.

**El mismo patrón se repitió en 2026-08-21** con la convocatoria oficial del pleno, que también reciben los tres roles por el mismo motivo (ver [[convocatoria-como-fuente]]). Dos casos bastan para enunciar la regla general:

> Toda fuente autorizada que se le dé al generador para que escriba algo que la transcripción no contiene hay que dársela también al auditor, o la marcará como inventada.

La regla ya lleva tres aplicaciones: el listado de la corporación, la convocatoria oficial ([[convocatoria-como-fuente]]) y, desde 2026-08-22, el bloque que explica qué significa una etiqueta de locutor ([[diarizacion-como-andamiaje]]). En este último caso lo que el auditor no debe señalar es la **propagación**: que el informe atribuya a una persona todas las intervenciones de una etiqueta que la grabación identifica una sola vez.

Cuando hay convocatoria, el auditor gana además su comprobación más importante, que es la inversa: señalar un punto redactado como si se hubiera debatido, acordado o votado cuando la transcripción no lo respalda, **aunque figure en la convocatoria**. La convocatoria dice lo previsto, no lo ocurrido.

## Cuando lo que oscila no es un dato sino una regla (2026-09-07)

El ping-pong de 2026-08-29 era el auditor contradiciéndose sobre un **hecho**. El pleno del 3
de septiembre enseñó una variante peor: el auditor contradiciéndose sobre una **regla de
derecho que nadie le había dado**, con el escape disparándose encima y dejando el acta peor
que cualquiera de las dos posturas.

Punto 1º, aprobación de las actas anteriores. Quien preside canta el recuento —*"3 a favor, 2
abstenciones y 2 en contra"* (`[00:16:25]`)— y pasa al punto siguiente **sin declarar el
resultado**: `rechaz*` y `mayoría` tienen cero apariciones en las 1.314 líneas de la
transcripción. Así que decidir si eso aprueba o rechaza no es leer, es aplicar una norma. Y
la norma no está en ningún prompt: la palabra "mayoría" aparece una sola vez en
`plenos_informe.py`, dentro de una regex que la borra.

El auditor la derivó de cero cada vuelta, y le salió distinta:

| Auditoría | Criterio aplicado | Veredicto |
|---|---|---|
| 0 y 2 | mayoría simple de votos emitidos (3 > 2) | aprobado |
| 3 (la que quedó) | mayoría absoluta sobre los 7 concejales | rechazado |

Con temperatura 0, esa variación no es ruido del modelo: **es la única variable libre en un
cálculo que el sistema dejó sin fijar**. La regla correcta existe y es determinada (art. 47.1
LRBRL: hay mayoría simple cuando los afirmativos superan a los negativos, las abstenciones no
computan), así que las auditorías 0 y 2 acertaban y la 3, la que sobrevivió, se equivocaba.

### El escape congeló la hoja y la disputa se mudó al campo de al lado

`bucle_informe` detectó la oscilación `rechazado → no consta → rechazado` en
`votacion.resultado` y aplicó [[via-de-escape-en-el-esquema]]: congelado a `"no consta"` y
reimpuesto cada vuelta. Pero:

- **`acuerdo` es invisible al detector.** `_aplanar` compara valores exactos, y `acuerdo` es
  texto libre: su redacción nunca se repite palabra por palabra aunque su *sentido* oscile.
  El corrector de la vuelta 3 lo reescribió a "Aprobar" obedeciendo a la auditoría 2, y ahí
  se quedó.
- **Congelar `resultado` no cerró la disputa: la desplazó.** El auditor siguiente vio
  `acuerdo: rechazar` junto a `resultado: no consta`, replanteó el fondo, y el corrector movió
  el campo que quedaba libre.
- **El render remató.** `plenos_acta.py:170` compone `ACUERDA, {acuerdo}` y **descarta el
  recuento** cuando el resultado es `"no consta"`. El escape, cuyo propósito es no afirmar lo
  que se discute, produjo un acta *más* afirmativa que cualquiera de los dos bandos: "Aprobar"
  a secas, sin cifras ni cautela, contradiciendo al párrafo anterior, que narra que el
  concejal votó en contra.

### Lo grave no fue el acuerdo, fue la objeción

El desenlace invierte el diagnóstico. **El acuerdo del acta era correcto**: el acta del 7 de
julio quedó aprobada, y el usuario, presente en la sesión, lo confirmó. El fallo del pipeline
fue el contrario del que parecía —producir una **objeción falsa contra un documento
correcto** y enseñársela a la funcionaria en [[guia-de-verificacion]] con enlace al minuto,
mandándola a "corregir" lo que estaba bien.

Una falsa alarma es el único defecto que una guía de verificación no puede permitirse: la
empuja a introducir un error y quema la confianza en las objeciones que sí valen. Es el
espejo de [[diarizacion-como-andamiaje]] — allí el andamiaje afirmaba de más, aquí el revisor
duda de más.

**Las cuatro causas encadenadas**, ninguna suficiente por sí sola: (1) la grabación no
proclama el resultado; (2) ningún prompt fija qué mayoría rige; (3) el escape congela una hoja
de un grupo acoplado sin tocar el campo que el documento imprime; (4) el punto tuvo **dos
votaciones** —el acta del 19 de mayo por asentimiento y la del 7 de julio con recuento— y
`PuntoOrdenDia.votacion` es una sola, así que el escape neutralizó también la votación unánime
que nadie discutía. El auditor había objetado esa fusión ya en la corrida anterior, con una
objeción correcta e **irresoluble por construcción**: no existe el campo donde ponerlo.

A 2026-09-07 **no se ha tocado nada de esto**, por decisión del usuario. Los cuatro arreglos
posibles están listados en [[pipeline-plenos]].

## Coste

Mínimo 2 llamadas al modelo (generar + auditar); máximo 8 (generar + 4 auditorías + 3 correcciones). En la primera ejecución real el auditor dio el visto bueno a la primera, así que fueron 2.

Con `gemini-2.5-pro` y un pleno entero (146.000 caracteres de transcripción), el peor caso se midió el 2026-08-22 ([[2026-08-22-primera-ejecucion-e2e-acta-oficial]]): las 8 llamadas, unos 20 minutos de reloj y ~0,06 $ por llamada de auditor. **El auditor es sistemáticamente el rol más caro y más lento**: gasta casi toda su salida razonando (11.214 de 11.466 tokens en una auditoría típica) y tarda entre 94 y 191 s, frente a los 82 s del generador.

## El auditor es también el rol que se rompe

Las dos ejecuciones fallidas del 2026-08-22 murieron **las dos en una llamada del auditor**, y no por casualidad: es la llamada más larga y la que más razona, así que es la que se atasca. En una de ellas el campo `reasoning` de la respuesta repetía once veces la misma frase reformulada —*"Auditing Speaker Assignments"*—, Google dejó de emitir tokens y OpenRouter cortó la petición con `finish_reason: "error"` y un 504 *"Upstream idle timeout exceeded"* **dentro de un HTTP 200**.

De ahí salen dos cosas que el bucle ya lleva incorporadas:

- `_peticion` reintenta los fallos que vienen con HTTP 200 y el error dentro de `choices[0]`, no solo los 429 y 5xx de transporte.
- Una respuesta sin contenido produce un error legible con `finish_reason` y `usage`, y vuelca la respuesta cruda a un fichero. Antes el `None` viajaba hasta pydantic, que fallaba con un error de tipos que no decía nada de la causa.

Queda sin resolver que el informe corregido vive solo en memoria: si la última auditoría agota los reintentos, se pierden las vueltas de corrector ya pagadas (ver [[persistir-lo-caro-antes-de-lo-fragil]]).

## Cuando el bucle agota las vueltas: qué significan los pendientes

En la primera ejecución completa el bucle terminó con **3 objeciones sin resolver**, y ninguna era ruido del auditor. Los pendientes de este bucle tienden a marcar una de estas tres cosas:

1. **Un caso que el esquema no sabe representar** — el corrector no puede resolver la objeción porque no hay forma correcta de escribirlo (el empate entre dos propuestas, ver [[via-de-escape-en-el-esquema]]).
2. **Una regla que solo tiene uno de los roles.** La regla sobre recuentos no verificables se añadió a `PROMPT_CORRECTOR`, pero el dato inventado que la incumplía lo había escrito el **generador**. Corolario de la regla de simetría de más arriba, en su otra dirección: *una restricción que le impones al corrector la necesita también el generador, o el bucle gastará vueltas arreglando lo que se produce de nuevo cada vez*.
3. **Un error de contenido real** que hay que llevar a la revisión humana.
4. **Un falso positivo del auditor.** Añadido el 2026-08-23: la tercera objeción de aquella ejecución decía que el informe atribuía una intervención a Joaquín Martínez; el JSON final decía Pedro José Martínez, que era lo correcto, y la objeción señalaba además un punto donde esa frase ni aparecía. El auditor **también se equivoca, y en la misma dirección que el generador**: nombres parecidos, índices cambiados.

Distinguir cuál de los cuatro es cada pendiente es exactamente lo que se hace al leer la lista final antes de enviar el acta a la secretaria — y por eso los pendientes se listan por consola en vez de escribirse dentro del acta: son material para una persona, no conclusiones.

Un pendiente del tipo 4 tiene además una consecuencia cara: el corrector gasta una vuelta entera intentando "arreglar" algo que ya estaba bien, y puede empeorarlo. Es el argumento más fuerte contra subir `MAX_VUELTAS`.

## El bucle narra su progreso (2026-08-21)

Cada llamada tarda minutos y el bucle puede dar tres vueltas, así que sin rastro no se sabía si avanzaba, en qué rol estaba ni qué había objetado el auditor. Ahora cada rol se anuncia por consola:

```
  → GENERADOR (146,090 caracteres de transcripción + convocatoria (153 KB))
     generador responde en 45s, 62,134 tokens
     sesión extraordinaria · 3 puntos (2 resolutiva / 1 control) · 1 bloque de ruegos
       1º APROBACIÓN SI PROCEDE DEL ACTA DE LA SESIÓN ANTERIOR
       ...
  → AUDITOR (busca afirmaciones que la transcripción no respalde)
     auditor responde en 52s, 63,034 tokens
     1 objeción:
       • [orden_del_dia] El punto 4, ordenanza de terrazas, se aprueba por unanimidad
         motivo: figura en la convocatoria pero la grabación no lo trata

  ── vuelta 1 de 3 ──
  → CORRECTOR (1 objeción que resolver)
```

Lo que hace útil el rastro para iterar sobre los prompts:

- **Los títulos que sacó el generador**, uno por línea: es la comprobación directa de si la convocatoria está funcionando.
- **Las objeciones del auditor con su motivo**: ahí se ve si está quemando vueltas repitiendo la misma queja, que es el modo de fallo característico de este bucle.
- Los **429 del proveedor ya no son silencio**: antes esperaba 2, 4 u 8 minutos sin decir nada.

Dos detalles de implementación: el `print` lleva `flush=True` porque la salida suele ir a un fichero con `| tee`, y el bucle **solo narra cuando corre de verdad** — si hay fakes inyectados estamos en los tests, y ahí las cabeceras solo ensucian la salida.

## Relacionado

[[pipeline-plenos]], [[via-de-escape-en-el-esquema]], [[convocatoria-como-fuente]], [[2026-07-31-plenos-youtube-pipeline-design]], [[2026-08-21-convocatoria-y-ajustes-acta]], [[2026-08-22-primera-ejecucion-e2e-acta-oficial]], [[persistir-lo-caro-antes-de-lo-fragil]], [[clasificacion-ia]], [[por-que-plenos-en-local]], [[2026-09-07-guia-forense-y-literal-de-escape]], [[guia-de-verificacion]]
