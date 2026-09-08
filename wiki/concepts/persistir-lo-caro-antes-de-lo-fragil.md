---
type: concept
date_updated: 2026-08-22
source_count: 1
---

# Lo caro se guarda antes de lo frágil

Regla de orden de escritura en [[pipeline-plenos]], aprendida pagándola el 2026-08-22
([[2026-08-22-primera-ejecucion-e2e-acta-oficial]]).

## El principio

**Cuando un paso cuesta dinero o tiempo irrepetible y el siguiente puede fallar, el
resultado del primero se persiste antes de empezar el segundo.**

En el pipeline de plenos hay exactamente un paso así: la transcripción. Cuesta ~0,48 $ de
AssemblyAI y unos minutos de subida y sondeo, y su entrada —el audio de un vídeo de
YouTube— puede dejar de estar disponible. Todo lo que viene después (el bucle
generador→auditor→corrector, el render del `.docx`) es repetible por céntimos con
`--rehacer-informe`.

`procesar_pleno` hacía justo lo contrario: llamaba a `bucle_informe` y escribía la
transcripción con el informe ya en la mano, en el mismo bloque. Mientras el bucle
funcionó, daba igual. La primera vez que el auditor devolvió una respuesta inválida, el
proceso murió con la transcripción **solo en memoria** y `uploads/actas/` sin crear.

Ahora el orden es: crear el directorio del borrador → escribir la transcripción, la
convocatoria y `entrada.json` → *después* llamar al modelo. `entrada.json` se escribe dos
veces a propósito: la primera sin `resumen_corto`, que es lo único suyo que depende del
LLM, y la segunda ya completa. Escribirlo dos veces cuesta nada; no tenerlo obliga a pagar
otra transcripción entera.

## Por qué no basta con "el pipeline no debería fallar"

Falla. En la misma sesión falló dos veces por causas distintas, ninguna imputable al
código propio: una respuesta sin contenido y un timeout del proveedor aguas arriba. Un
paso que depende de un modelo de terceros por HTTP tiene una probabilidad de fallo que no
se puede llevar a cero desde este lado, así que la pregunta útil no es cómo evitar el
fallo sino **qué se pierde cuando ocurra**.

La misma lógica explica por qué `--rehacer-informe` y `--rehacer-acta` existen
([[pipeline-plenos]]): iterar sobre los prompts o sobre el formato del documento sin
volver a pagar lo caro es el mismo principio aplicado al trabajo del desarrollador. Cada
escalón se puede repetir sin repetir el de abajo.

## El corolario: lo caro suele ser recuperable si dejas el identificador

La transcripción de la ejecución fallida **no se perdió**, pese al fallo. AssemblyAI la
conserva por `transcript_id`, y el log lo había impreso al empezar a sondear:

```
  transcribiendo (id 06b6e8cc-4db2-4497-bbf7-ac2f8454d81c); un pleno tarda unos minutos...
```

Un `GET` gratis a `/v2/transcript/<id>` devolvió las `utterances` intactas. Que ese `print`
existiera —puesto para que el sondeo no pareciera un cuelgue— fue lo que convirtió una
pérdida de 0,48 $ en un rescate de dos minutos.

**Registrar el identificador que el proveedor te devuelve es la mitad barata de esta
regla.** La otra mitad, escribir el resultado en disco, es la que evita necesitar el
rescate.

## Lo que todavía no cumple la regla

Dentro del bucle LLM, el informe corregido vive **solo en memoria** hasta que el bucle
termina. Si la última auditoría falla tras tres vueltas de corrector —que es exactamente lo
que pasó en la segunda ejecución— se pierden esas tres correcciones, unos 0,3 $ y un cuarto
de hora. Es menos dinero que una transcripción, y con el reintento de los cortes del
proveedor el caso quedó raro, así que se dejó abierto a sabiendas. El arreglo, si algún día
molesta: volcar cada informe intermedio junto a la transcripción.

## Relacionado

[[pipeline-plenos]], [[2026-08-22-primera-ejecucion-e2e-acta-oficial]],
[[bucle-generador-auditor-corrector]], [[por-que-plenos-en-local]]
