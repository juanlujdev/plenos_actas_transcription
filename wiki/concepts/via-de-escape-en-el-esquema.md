---
type: concept
date_updated: 2026-08-08
source_count: 1
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
- `Intervencion.interviniente`: si la grabación no identifica a la persona, el valor exacto `"no identificado en la grabación"`
- `fecha_pleno`: `str | None`, solo si se menciona en la grabación

Las instrucciones por campo viajan en `Field(description=...)`, no en comentarios de Python: los comentarios no llegan al modelo, las descripciones sí (van en el `response_schema` de Gemini).

## El fallo que demostró que el principio se puede romper aguas abajo

En el primer informe real publicado apareció esto en el PDF:

> `Votación: Rechazado (1 a favor, 0 en contra, 0 abstenciones)`

Es imposible: si nadie vota en contra, nada puede quedar rechazado. El JSON era correcto — `en_contra: null`, `abstenciones: null`, o sea "no consta" — pero `plenos_render.py` los imprimía con `v.en_contra or 0`, convirtiendo la ausencia de dato en la afirmación "cero votos en contra".

**La lección:** el esquema puede ser impecable y el renderizador puede fabricar el dato igualmente. La vía de escape tiene que respetarse en toda la cadena, no solo en la capa que habla con el LLM. El render ahora imprime únicamente los recuentos que constan, y hay dos tests que fijan ese comportamiento.

## Relación con las otras capas

Es la primera de las tres capas de garantía de la spec, y la única que actúa *antes* de que el modelo escriba. Las otras dos son [[bucle-generador-auditor-corrector]] (fidelidad a la transcripción, actúa después) y la revisión humana contra la grabación (ver [[por-que-plenos-en-local]], que la convirtió en permanente).

Ninguna sustituye a las otras: pydantic garantiza la forma del JSON, no su veracidad; un dato falso pero bien formado pasa la validación sin problema.

## Relacionado

[[pipeline-plenos]], [[bucle-generador-auditor-corrector]], [[2026-07-31-plenos-youtube-pipeline-design]], [[por-que-plenos-en-local]]
