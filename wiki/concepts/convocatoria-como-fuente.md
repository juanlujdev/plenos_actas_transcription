---
type: concept
date_updated: 2026-08-22
source_count: 1
---

# La convocatoria como segunda fuente del acta

El Ayuntamiento publica el **orden del día** antes de cada sesión, con los títulos exactos
de los puntos, su numeración y los números de expediente. Desde 2026-08-21,
[[pipeline-plenos]] lo acepta con `--convocatoria <pdf>` y se lo pasa al modelo junto a la
transcripción.

Resuelve de una vez lo que la transcripción no puede dar bien: los títulos administrativos
(que Whisper destroza), la numeración de los puntos, los expedientes y el tipo de sesión.
No toca la arquitectura — es un parámetro más al lado de `transcripcion` — pero tiene dos
consecuencias que no se ven a primera vista.

## Consecuencia 1: el auditor también la necesita

Si la convocatoria la viera solo el generador, este escribiría el título exacto del orden
del día, el auditor lo buscaría en la transcripción, encontraría el destrozo de Whisper y
lo marcaría como afirmación no respaldada. Las tres vueltas de
[[bucle-generador-auditor-corrector]] se quemarían sin arreglar nada y el acta saldría
peor que sin convocatoria.

**Es exactamente el mismo fallo que ya obligó a pasarle `CORPORACION` al auditor** cuando
se añadió el listado de la corporación para corregir los nombres. Segundo caso del mismo
patrón, y por eso vale la pena enunciarlo como regla general:

> Toda fuente autorizada que se le dé al generador para que escriba algo que la
> transcripción no contiene hay que dársela también al auditor, o la marcará como
> inventada.

La reciben los tres roles: generador, auditor y corrector. Hay un test
(`convocatoria: la recibe el AUDITOR`) que lo fija para que nadie lo quite sin enterarse.

## Consecuencia 2: la convocatoria manda en la forma, la grabación en el fondo

Este es el riesgo real que introduce la idea. **La convocatoria dice lo previsto; el acta
recoge lo ocurrido, y no siempre coinciden**: los puntos se retiran, se dejan sobre la
mesa, o entran por urgencia fuera del orden del día.

Si el modelo tratase la convocatoria como verdad, redactaría puntos que nunca se
debatieron — un dato inventado **con pinta de oficial**, que es peor que un hueco, porque
nadie lo pone en duda al leerlo.

La regla que llevan los prompts (reglas 17-20 del generador):

| Sale de la convocatoria | Sale de la grabación |
|---|---|
| Títulos exactos, en mayúsculas | Qué se debate y con qué argumentos |
| Numeración de los puntos | Qué se acuerda |
| Números de expediente | Qué se vota y con qué resultado |
| Tipo de sesión y motivo | Quién interviene |

Y las dos asimetrías:

- Un punto **convocado del que la grabación no habla** no se redacta como si se hubiera
  tratado. Si se retira o se deja sobre la mesa, se hace constar así; si sencillamente no
  aparece, se omite.
- Un punto **tratado y no convocado** sí va al acta (suele ser un asunto de urgencia), con
  `numero` en `null` si no se le da número.

El auditor tiene esto como **comprobación principal cuando hay convocatoria**: señalar un
punto redactado como debatido, acordado o votado cuando la transcripción no lo respalda,
*aunque figure en la convocatoria*. Es lo que convierte al auditor en la defensa contra el
único riesgo que este cambio añade.

## Por qué el PDF va entero al modelo, sin extraer texto

Las convocatorias del Ayuntamiento son **escaneos**: comprobado sobre el orden del día real
del 7 de julio de 2026, el PDF contiene un único JPEG de 157 KB y **cero texto extraíble**.
`pypdf` no saca nada de ahí, y extraerlo exigiría OCR — una dependencia pesada para un
comando que se ejecuta una vez al mes.

En su lugar, el PDF viaja en crudo como parte multimodal:

```python
partes.insert(0, {"type": "file", "file": {
    "filename": "convocatoria.pdf",
    "file_data": "data:application/pdf;base64," + base64.b64encode(convocatoria).decode(),
}})
cuerpo["plugins"] = [{"id": "file-parser", "pdf": {"engine": "native"}}]
```

Ese `engine: "native"` es imprescindible desde la migración a OpenRouter
([[2026-08-22-plenos-openrouter-gemini-pro]]): el extractor por defecto es un OCR de pago
que devolvería texto plano, o sea justo lo que este diseño evita. Con `native` el escaneo
le llega al modelo como imagen, verificado sobre un PDF sin capa de texto.

El modelo lee escaneos, así que no hace falta OCR ni dependencia nueva, y además **conserva la
maquetación** —la lista numerada, la columna de expedientes— que un texto aplanado
perdería. Es un caso de usar una capacidad que ya se está pagando en vez de añadir una
herramienta.

`leer_convocatoria()` acepta solo `.pdf` y devuelve `bytes`, sin interpretar el contenido.
La convocatoria se guarda en `uploads/actas/<fecha>/<fecha>-convocatoria.pdf` para que
`--rehacer-informe` la reutilice sola al iterar sobre los prompts.

## Relación con la vía de escape

No la debilita, la complementa. [[via-de-escape-en-el-esquema]] impide que el modelo
invente lo que no sabe; la convocatoria hace que **haya menos cosas que no sepa**, y lo
hace con un documento oficial del Ayuntamiento, no con una deducción del modelo. Es la
misma categoría que `CORPORACION`: una fuente autorizada, no una excepción al principio.

Además desbloquea dos huecos que hoy son trabajo manual o callejón sin salida:

- **`tipo_sesion`.** Si no consta en la grabación, el acta no se genera y
  `--rehacer-informe` vuelve a llamar al modelo a temperatura 0 sobre la misma
  transcripción, así que devuelve lo mismo: un bucle que no puede terminar. La
  convocatoria lo dice siempre.
- **El número de expediente.** Hoy se vacía a `___________` a propósito, porque el
  `PLN/2026/N` de la plantilla es un número de ejemplo que publicarlo sería falsificar. Si
  la convocatoria trae el real, deja de ser trabajo de la secretaria.

## Relacionado

[[pipeline-plenos]], [[bucle-generador-auditor-corrector]], [[via-de-escape-en-el-esquema]],
[[2026-08-21-convocatoria-y-ajustes-acta]]
