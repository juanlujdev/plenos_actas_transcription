---
type: concept
date_updated: 2026-08-22
source_count: 5
---

# La vía de escape va dentro del esquema

Principio de diseño anti-alucinación de [[pipeline-plenos]], enunciado en [[2026-07-31-plenos-youtube-pipeline-design]] e implementado literalmente en `scripts/plenos_informe.py`.

## El principio

**Todo dato que la transcripción pueda no contener es `Optional` o tiene un valor explícito de "no consta", para que el esquema nunca fuerce al modelo a inventar.**

Un esquema que declara `a_favor: int` obliga al modelo a poner un número aunque nadie lo haya dicho en voz alta. Uno que declara `a_favor: int | None` le da una salida honesta. El objetivo no es detectar la alucinación después, sino **quitarle al modelo el incentivo estructural de producirla**.

Ejemplos en el esquema real:

- `Votacion.resultado`: `Literal["aprobado", "rechazado", "sin votación", "no consta"]`
- `Votacion.modalidad`: `Literal["unanimidad", "recuento", "no consta"]`
- `a_favor` / `en_contra` / `abstenciones`: `int | None`, con la instrucción "solo si se dice el número en la grabación"
- `PuntoOrdenDia.votacion`: `Votacion | None` — `null` si el punto no se sometió a votación
- `BloqueRuegos.formulados_por`: si la grabación no identifica a quien formula el ruego, el valor exacto `"no identificado en la grabación"`
- `tipo_sesion`: `Literal["ordinaria", "extraordinaria", "no consta"]`, con la instrucción de no deducirlo del contenido
- `presidente`: `str | None`, solo si la grabación identifica a quien preside
- `asistentes` / `ausentes`: `list[str]` cuya vía de escape es la **lista vacía** — "no consta" no es lo mismo que "no asistió nadie"
- `fecha_pleno`, `hora_inicio`, `hora_fin`: `str | None`, solo si se mencionan en la grabación

Las instrucciones por campo viajan en `Field(description=...)`, no en comentarios de Python: los comentarios no llegan al modelo, las descripciones sí (viajan dentro del JSON Schema que acompaña a la llamada).

Desde la migración a OpenRouter ([[2026-08-22-plenos-openrouter-gemini-pro]]) ese esquema se envía en modo `strict`, que exige todas las propiedades en `required`. `_esquema_estricto()` lo normaliza, y eso **no toca la vía de escape**: la de un campo opcional es admitir `null`, no estar ausente del JSON. Un esquema estricto que obliga a *escribir* el campo pero permite escribirlo como `null` es, si acaso, más fiel a esta idea que uno que deja al modelo omitirlo.

> El ejemplo canónico de este principio durante meses fue `Intervencion.interviniente`. Esa clase **ya no existe**: el rediseño del acta oficial ([[2026-08-21-acta-oficial-plenos-design]]) disolvió la sección de intervenciones dentro del texto de cada punto, y su vía de escape sobrevive en `BloqueRuegos.formulados_por`, que usa el mismo literal.

## Qué NO es una violación del principio

La vía de escape prohíbe que el **modelo** invente lo que no oyó. No prohíbe rellenar un hueco con un dato que el sistema conoce por otra vía fiable. Dos casos legítimos, ambos de 2026-08-21:

- **La convocatoria oficial** ([[convocatoria-como-fuente]]) aporta títulos, numeración, expedientes y tipo de sesión. Es un documento del Ayuntamiento, no una deducción: hace que el modelo tenga menos cosas que no saber, en vez de darle permiso para suponerlas.
- **La fecha del CLI.** `procesar_pleno` conoce la fecha con certeza (de `--fecha`, del título del vídeo o de la entrada guardada). Si el modelo no la oye en la grabación, se rellena con ella antes de renderizar — pero **solo el `null`**: nunca pisa una fecha que sí conste en la grabación.

La línea que separa ambos casos: ¿el dato viene de una fuente autorizada, o de que el modelo rellene un hueco porque el esquema le obliga? Lo primero es sano; lo segundo es lo que este principio existe para impedir.

## El fallo que demostró que el principio se puede romper aguas abajo

En el primer informe real publicado apareció esto en el PDF:

> `Votación: Rechazado (1 a favor, 0 en contra, 0 abstenciones)`

Es imposible: si nadie vota en contra, nada puede quedar rechazado. El JSON era correcto — `en_contra: null`, `abstenciones: null`, o sea "no consta" — pero `plenos_render.py` los imprimía con `v.en_contra or 0`, convirtiendo la ausencia de dato en la afirmación "cero votos en contra".

**La lección:** el esquema puede ser impecable y el renderizador puede fabricar el dato igualmente. La vía de escape tiene que respetarse en toda la cadena, no solo en la capa que habla con el LLM. El render ahora imprime únicamente los recuentos que constan, y hay dos tests que fijan ese comportamiento.

## El límite del principio: la vía de escape solo cubre lo que el esquema sabe representar

La primera ejecución end-to-end real ([[2026-08-22-primera-ejecucion-e2e-acta-oficial]])
enseñó un modo de fallo que la vía de escape **no** evita. La votación del punto 1 del
pleno del 7 de julio no fue a favor o en contra de una propuesta: fue **entre dos
alternativas** —plenos mensuales o cada 40 días— y quedó empatada a 3. `Votacion` no
modela eso. Sus campos son `a_favor` / `en_contra` / `abstenciones`, y ninguno admite "3
votos para la opción A y 3 para la opción B". El modelo escribió:

> `aprobado · recuento · 3 a favor · 3 en contra · 0 abstenciones`

Cada campo por separado respeta el esquema; el conjunto afirma algo que no ocurrió. El
auditor lo detectó y el corrector no pudo resolverlo, porque no había forma correcta de
expresarlo dentro del esquema: agotó las tres vueltas.

> **Corregido el 2026-08-23** ([[2026-08-23-reglas-de-recuento-y-decisiones-de-acta]]):
> este análisis daba por hecho que el `"aprobado"` era falso porque venía de un empate. Al
> leer la transcripción resultó que **sí hubo desempate**, por el voto de calidad de quien
> preside, y que la periodicidad quedó fijada en 40 días (00:17:19). El `resultado` era
> correcto. Lo falso era solo la forma: "tres en contra" cuando nadie votó en contra, y el
> `0` de abstenciones. La lección de abajo se mantiene, pero su ejemplo es más pequeño de
> lo que parecía — y por eso **se decidió no tocar el esquema**: el acta ya reflejaba bien
> el acuerdo, y [[acta-oficial-11-febrero-2026]] demuestra que la secretaria narra estas
> votaciones en prosa en vez de estructurarlas.

**La lección:** `int | None` protege del dato que el modelo no oyó, no del **caso que el
esquema no contempla**. Ante un hecho que no cabe en la forma disponible, el modelo no se
calla: lo dobla hasta que entra. Un esquema incompleto empuja a inventar igual que un
esquema sin nulls, solo que de forma menos visible.

De la misma ejecución sale un segundo matiz, sobre los recuentos **parciales**. En el
punto 5 solo 3 de los 6 asistentes verbalizaron su voto. Escribir `1 a favor, 2 en contra`
—cierto por separado— afirma en un acta que ese fue el recuento de la votación. La vía de
escape correcta ahí no es rellenar lo que falta ni poner lo que consta: es `null` en todos
los campos, porque **un recuento incompleto no es un recuento**. La regla añadida a
`PROMPT_CORRECTOR` el 2026-08-22 recoge la prohibición de deducir votos restando de los
asistentes y la del `0` de relleno, pero permitía todavía el recuento parcial y vive solo
en el corrector: el `0` del punto 1 lo escribió el generador, que no la tiene. Ambas cosas
siguen abiertas.

## Dos vías de escape para lo mismo es peor que una

`PuntoOrdenDia.votacion` es `Votacion | None`, y dentro del objeto `resultado` admite el
literal `"sin votación"`. Son dos maneras muy parecidas de decir que no hubo votación —una
para el punto que nunca se somete a votación, otra para el que se somete y no llega a
votarse— y el 2026-08-23 el modelo las mezcló: escribió la **cadena** `"sin votación"`
donde iba el objeto, en los tres puntos de control a la vez, y tiró la generación entera.

Lo destapó un cambio de prompt que insistía mucho en `null` y en votaciones. Es decir: la
ambigüedad llevaba meses ahí y solo hizo falta empujar un poco al modelo hacia uno de los
dos lados.

**La lección:** una vía de escape es una salida honesta; **dos vías de escape para el
mismo hecho son una trampa**. Si el esquema ofrece dos formas parecidas de decir lo mismo,
tarde o temprano el modelo va a fabricar una tercera que no valida. Cuando se añadan
vías de escape nuevas, conviene comprobar que no solapen con las existentes.

El arreglo fue de dos capas —decirlo explícitamente en el prompt y normalizar en el
parseo— y deliberadamente **estrecho**: solo se convierten a `null` las cadenas que
significan ausencia. Una cadena con contenido (`"aprobado por unanimidad"`) sigue fallando,
porque normalizarla afirmaría que no hubo votación cuando sí la hubo. Normalizar la salida
del modelo es legítimo cuando su intención es inequívoca; deja de serlo en cuanto haya que
adivinar.

## Relación con las otras capas

Es la primera de las tres capas de garantía de la spec, y la única que actúa *antes* de que el modelo escriba. Las otras dos son [[bucle-generador-auditor-corrector]] (fidelidad a la transcripción, actúa después) y la revisión humana contra la grabación (ver [[por-que-plenos-en-local]], que la convirtió en permanente).

Ninguna sustituye a las otras: pydantic garantiza la forma del JSON, no su veracidad; un dato falso pero bien formado pasa la validación sin problema.

## Relacionado

[[pipeline-plenos]], [[bucle-generador-auditor-corrector]], [[convocatoria-como-fuente]], [[2026-07-31-plenos-youtube-pipeline-design]], [[2026-08-21-acta-oficial-plenos-design]], [[2026-08-21-convocatoria-y-ajustes-acta]], [[por-que-plenos-en-local]], [[2026-08-22-primera-ejecucion-e2e-acta-oficial]]
