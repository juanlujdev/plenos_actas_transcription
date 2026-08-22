---
type: concept
date_updated: 2026-08-22
source_count: 5
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

## Lo que el auditor no puede detectar

**Errores que ya vienen en la transcripción.** El auditor compara el informe contra la transcripción, así que si Whisper transcribió mal un nombre y el informe lo copia fielmente, el auditor da su visto bueno. Por eso la spec insiste en que la revisión humana contra el audio es una capa irreemplazable.

De ahí sale una consecuencia de diseño poco obvia: al añadir el listado de la corporación municipal al generador para que corrija los nombres deformados, **hubo que dárselo también al auditor**. Si no, vería "Sergio de Fez Cerezuela" en el informe, buscaría esa cadena en la transcripción (que dice "Féceres Zuela"), no la encontraría, y la marcaría como afirmación no respaldada — quemando las tres vueltas de corrección en cada ejecución sin arreglar nada. El auditor tiene instrucción explícita de no señalar esas correcciones ni el tiempo verbal.

**El mismo patrón se repitió en 2026-08-21** con la convocatoria oficial del pleno, que también reciben los tres roles por el mismo motivo (ver [[convocatoria-como-fuente]]). Dos casos bastan para enunciar la regla general:

> Toda fuente autorizada que se le dé al generador para que escriba algo que la transcripción no contiene hay que dársela también al auditor, o la marcará como inventada.

La regla ya lleva tres aplicaciones: el listado de la corporación, la convocatoria oficial ([[convocatoria-como-fuente]]) y, desde 2026-08-22, el bloque que explica qué significa una etiqueta de locutor ([[diarizacion-como-andamiaje]]). En este último caso lo que el auditor no debe señalar es la **propagación**: que el informe atribuya a una persona todas las intervenciones de una etiqueta que la grabación identifica una sola vez.

Cuando hay convocatoria, el auditor gana además su comprobación más importante, que es la inversa: señalar un punto redactado como si se hubiera debatido, acordado o votado cuando la transcripción no lo respalda, **aunque figure en la convocatoria**. La convocatoria dice lo previsto, no lo ocurrido.

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
3. **Un error de contenido real** que hay que llevar a la revisión humana (la atribución cruzada entre los dos concejales apellidados Martínez).

Distinguir cuál de los tres es cada pendiente es exactamente lo que se hace al leer la lista final antes de enviar el acta a la secretaria.

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

[[pipeline-plenos]], [[via-de-escape-en-el-esquema]], [[convocatoria-como-fuente]], [[2026-07-31-plenos-youtube-pipeline-design]], [[2026-08-21-convocatoria-y-ajustes-acta]], [[2026-08-22-primera-ejecucion-e2e-acta-oficial]], [[persistir-lo-caro-antes-de-lo-fragil]], [[clasificacion-ia]], [[por-que-plenos-en-local]]
