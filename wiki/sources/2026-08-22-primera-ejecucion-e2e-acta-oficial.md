---
type: source-summary
date_updated: 2026-08-22
---

# Primera ejecución end-to-end del acta oficial (2026-08-22)

Conversación de trabajo del 2026-08-22, sin spec ni plan. Tercera intervención del día
sobre [[pipeline-plenos]], después del cambio a OpenRouter
([[2026-08-22-plenos-openrouter-gemini-pro]]) y del cambio a AssemblyAI diarizado
([[2026-08-22-plenos-assemblyai-diarizacion]]). Es **la validación end-to-end real que la
wiki llevaba pendiente desde el rediseño del acta oficial**: un pleno entero, con
convocatoria, de principio a fin.

Material: pleno extraordinario del 7 de julio de 2026 (`5UETzjDRRtw`, 2h16m) y su
convocatoria oficial en PDF. Se ejecutó en Git Bash con `ASSEMBLYAI_API_KEY` y
`OPENROUTER_API_KEY` exportadas en la sesión.

## Resultado

**El pipeline completa el recorrido y produce el acta**: `2026-07-07-acta-extraordinaria.docx`
sobre la plantilla oficial, con 7 puntos (4 resolutiva / 3 control), tipo de sesión
determinado, fecha y horas. Hicieron falta **tres ejecuciones** porque las dos primeras
murieron por fallos de infraestructura, no de contenido.

## Los tres fallos que hubo que arreglar para llegar al final

### 1. La transcripción se escribía DESPUÉS del bucle LLM

`procesar_pleno` llamaba a `bucle_informe` y solo escribía el `.md` con el resultado ya en
la mano. Cualquier excepción del LLM tiraba **lo único que cuesta dinero y no se puede
repetir gratis**: los 0,48 $ y los minutos de la transcripción de AssemblyAI. Es lo que
pasó en la primera ejecución, que dejó `uploads/actas/` sin crear siquiera.

Arreglado invirtiendo el orden: transcripción, convocatoria y `entrada.json` se guardan
antes de la primera llamada al modelo. Ver [[persistir-lo-caro-antes-de-lo-fragil]].

La transcripción de esa ejecución **no llegó a perderse**: AssemblyAI la conserva por
`transcript_id`, y el log lo había impreso. Un `GET` gratis a
`/v2/transcript/<id>` más `formatear_utterances` reconstruyó el borrador y permitió
seguir con `--rehacer-informe` sin volver a pagar.

### 2. OpenRouter entrega fallos del proveedor con HTTP 200

Las dos primeras ejecuciones murieron con el mismo error de superficie —el auditor
devolvía `content: None` y pydantic reventaba con un `ValidationError` de tipos que no
decía nada de la causa— pero la causa solo se conoció al instrumentar.

El volcado de la respuesta cruda lo dejó claro:

```json
"finish_reason": "error",
"error": {"code": 504, "message": "Upstream idle timeout exceeded",
          "metadata": {"error_type": "timeout"}}
```

El modelo se había atascado razonando —el campo `reasoning` repite once veces la misma
frase, *"Auditing Speaker Assignments"*, reformulada—, Google dejó de emitir tokens y
OpenRouter cortó por inactividad. **Fallo transitorio del proveedor, entregado con HTTP
200 y el error dentro de `choices[0]`**, de modo que el reintento de `_peticion`, que solo
miraba 429 y 5xx de transporte, no se activaba.

Arreglado en tres capas:

- `_peticion` reintenta también los `choices[0].error`, con el mismo backoff (2/4/8 min).
- `_llamar_llm` comprueba el contenido antes de dárselo a pydantic: si viene vacío, lanza
  un `RuntimeError` con `finish_reason`, `native_finish_reason` y el `usage`, y vuelca la
  respuesta completa a un JSON en el directorio temporal.
- El log imprime el desglose de tokens (entrada / salida / de ellos razonamiento) en vez
  del total, que era justo el dato que no permitía diagnosticar.

### 3. El log truncaba lo que servía para revisar

Los títulos del orden del día se cortaban a 80 caracteres y las objeciones del auditor a
90, para que cupieran en una línea de terminal. El `.docx` y el JSON siempre llevaron el
texto íntegro —`titulo` no tiene límite en el esquema—, pero el rastro de consola es lo
que se lee para decidir si el bucle va bien, así que el truncado se quitó.

## Coste y tiempos medidos

| Llamada | Entrada | Salida | De ella, razonamiento | Tiempo |
|---|---|---|---|---|
| Generador | 51.136 | 9.287 | 6.360 | 82 s |
| Auditor | 53.318 | 11.466 | 11.214 | 94–191 s |
| Corrector | 52.700 | 9.000–12.500 | 5.800–9.600 | 73–109 s |

Dos hechos que salen de ahí:

- **El auditor gasta casi toda su salida en razonar** (11.214 de 11.466 tokens) y es
  siempre la llamada más larga. Es también la que se atascó las dos veces: el modo de
  fallo del 504 no le tocó al generador ni al corrector por casualidad.
- Una sola llamada de auditor costó **0,062 $** según `cost_details.upstream_inference_cost`.
  Con las 8 llamadas del peor caso, el bucle entero encaja en la estimación previa de
  0,15–0,80 € por pleno.

## Hallazgos de contenido: qué escribió mal el modelo

El bucle terminó agotando las tres vueltas con **3 objeciones sin resolver**. Ninguna es
ruido; las tres apuntan a algo real:

1. **Un empate 3-3 forzado al molde equivocado.** La votación del punto 1 no fue a favor o
   en contra de una propuesta: fue **entre dos alternativas** (plenos mensuales vs. cada
   40 días), y quedó empatada a 3. El esquema `Votacion` no modela ese caso, así que el
   modelo lo escribió como `aprobado · 3 a favor · 3 en contra · 0 abstenciones`. Ver
   [[via-de-escape-en-el-esquema]]: cuando el esquema no tiene forma de representar lo que
   pasó, el modelo lo fuerza al molde disponible.
2. **Un recuento parcial presentado como final.** En el punto 5 solo 3 de los 6 asistentes
   verbalizan su voto; el informe puso `1 a favor, 2 en contra`, que en un acta afirma
   implícitamente ser el recuento completo.
3. **Atribución cruzada entre los dos concejales apellidados Martínez.** Una intervención
   de Pedro José Martínez quedó atribuida a Joaquín Martínez. `CORPORACION` los lista a
   ambos pero no avisa de que comparten apellido.

Queda además **pendiente de verificar contra la grabación** que el informe liste a Sergio
de Fez Cerezuela entre los asistentes, cuando `CORPORACION` lo da de baja médica y por eso
preside Lorena Luján. O asistió pese a la baja, o es una atribución falsa en un documento
que se sella.

## La regla de recuentos del corrector

Entre la segunda y la tercera ejecución, el bucle quemó sus tres vueltas discutiendo el
recuento del punto 5: el auditor lo rechazaba por ininteligible y el corrector respondía
**cambiando la cifra** (5 en contra → 4 en contra → …) en vez de poner `null`. Se añadió a
`PROMPT_CORRECTOR` una regla explícita: ante un recuento objetado la corrección es `null`,
nunca otra cifra; prohibido deducir los votos que faltan restando de los asistentes;
prohibido el `0` de relleno; `resultado` y `modalidad` se conservan si constan.

La ejecución siguiente demostró que la regla estaba **incompleta en dos sentidos**, y
ambos siguen abiertos:

- Está solo en el corrector, pero el `0` de relleno del punto 1 lo escribió el
  **generador**, que no la tiene.
- Permitía el recuento parcial ("pon número solo en lo que se oye"), que es justo lo que
  el auditor rechazó en el punto 5. Si el recuento no está completo, van todos a `null`.

## Tests añadidos

`test_plenos.py` gana 15 comprobaciones, todas sin red: que la transcripción queda
en disco aunque el bucle reviente, que una respuesta sin contenido produce un
`RuntimeError` legible y no un error de pydantic, que un corte del proveedor se reintenta y
que tras agotar los intentos el error sigue siendo legible, y que la regla de recuentos
sigue en el prompt del corrector con su numeración sin saltos.

## Relacionado

[[pipeline-plenos]], [[persistir-lo-caro-antes-de-lo-fragil]],
[[bucle-generador-auditor-corrector]], [[via-de-escape-en-el-esquema]],
[[diarizacion-como-andamiaje]], [[convocatoria-como-fuente]],
[[2026-08-22-plenos-openrouter-gemini-pro]], [[2026-08-22-plenos-assemblyai-diarizacion]],
[[2026-08-21-acta-oficial-plenos-design]]
