---
type: source-summary
date_updated: 2026-08-22
---

# Plenos: del SDK de Gemini a OpenRouter con `gemini-2.5-pro`

Fuente: conversación de trabajo del 2026-08-22, sin spec ni plan previos. Cambio acotado
al bucle LLM de [[pipeline-plenos]]; el bot de agenda ([[clasificacion-ia]]) no se tocó.

## Qué se decidió

El bucle generador→auditor→corrector deja de hablar con Google AI Studio a través del SDK
`google.genai` y pasa por **OpenRouter**, con el modelo **`google/gemini-2.5-pro`**. Es la
misma migración de proveedor que ya hizo el bot de agenda en 2026-06-27, un año de
proyecto más tarde y por un motivo distinto: allí fue para dejar de pelearse con los 429
del tier gratuito de Google, aquí para poder usar el modelo que la spec pedía desde el
principio y que en la capa gratuita de Google AI Studio tiene **cupo 0**. Ver
[[fallback-modelos-ia]] para el historial completo de proveedores del proyecto.

Con ello queda resuelto el punto 2 de los pendientes de producción de [[pipeline-plenos]].

## Qué cambió en el código

Todo en `scripts/plenos_informe.py`, ~90 líneas del bloque de llamadas:

| Antes | Ahora |
|---|---|
| SDK `google.genai` (import perezoso) | `requests` contra `https://openrouter.ai/api/v1/chat/completions` |
| `GEMINI_API_KEY` + `GEMINI_MODEL` | `OPENROUTER_API_KEY`; modelo fijo en `plenos_informe.MODELO` |
| `config={"response_schema": <clase pydantic>}` | `response_format: {"type": "json_schema", "strict": true}` |
| `types.Part.from_bytes(mime_type="application/pdf")` | parte `{"type": "file"}` en base64 + plugin `file-parser` |
| `_reintentar_gemini` sobre `genai.errors.APIError` | `_peticion` sobre códigos HTTP, mismo backoff 2/4/8 min |

Tres detalles que no son evidentes:

1. **El esquema de pydantic no vale tal cual para `strict`.** El modo estricto exige que
   *todas* las propiedades estén en `required` y prohíbe `default`; pydantic deja fuera de
   `required` los campos con valor por defecto, que aquí son justamente los opcionales.
   `_esquema_estricto()` recorre el JSON Schema, pone todas las propiedades en `required`,
   fija `additionalProperties: false` y borra los `default`. **No debilita
   [[via-de-escape-en-el-esquema]]**: la vía de escape de esos campos es admitir `null`,
   no estar ausentes, y eso lo conserva el `anyOf` del propio esquema. Hay cinco asserts
   en `scripts/test_plenos.py` que lo fijan.
2. **El PDF de la convocatoria viaja con `plugins: [{"id": "file-parser", "pdf":
   {"engine": "native"}}]`.** El engine por defecto de OpenRouter es un OCR de pago que
   devolvería texto plano y perdería la maquetación — justo lo que
   [[convocatoria-como-fuente]] quiere evitar. Con `native` el escaneo le llega al modelo
   como imagen.
3. **El modelo se hardcodea, no se configura por entorno.** `gemini-2.5-pro` se eligió a
   propósito y es de pago; una env var invitaría a cambiarlo sin pensar en un documento
   que se sella. `GEMINI_MODEL` desaparece.

No quedó código residual: el SDK `google.genai` ya no se importa en ningún sitio y no
estaba en `scripts/requirements.txt` (ese fichero es del bot, que corre en Actions).

## Verificación

Smoke test contra la API real (`scratchpad/smoke_openrouter.py`, la clave se borró después):

- **Salida estructurada strict** con el esquema real `InformePleno` sobre una
  transcripción falsa de seis líneas: sesión ordinaria, dos puntos bien clasificados
  (1 resolutiva / 1 control), votación `aprobado`/`unanimidad` sin números inventados,
  y `presidente`/`fecha_pleno` en `null` — las vías de escape se respetan.
- **PDF escaneado sin capa de texto** (`uploads/Pleno_24_Junio_2015_Parte_1.pdf`, 1
  página, `pypdf` no extrae nada) leído correctamente por el engine `native`: devolvió
  *"AYUNTAMIENTO DE ENGUÍDANOS (CUENCA) ACTA DE LA SESION 06/2015 DE 24 DE JUNIO..."*.
- **Sin fallback silencioso**: la respuesta trae `model: google/gemini-2.5-pro`,
  `provider: Google`.
- `python scripts/test_plenos.py` en verde, incluidos los cinco tests nuevos.

Sigue faltando la validación end-to-end con un pleno real.

## Coste

Ahora hay coste por llamada, cosa que no pasaba con la capa gratuita. Una petición trivial
("responde OK") salió **$0,0018**, de los que casi todo fue el razonamiento: 176 tokens de
`reasoning` frente a 5 de prompt. `gemini-2.5-pro` es un modelo razonador y esos tokens se
facturan como salida, así que el coste no escala solo con el tamaño de la transcripción.
La estimación previa de **0,15–0,80 € por pleno** (2 a 7 llamadas con la transcripción
entera) se sostiene.

## Relacionado

[[pipeline-plenos]], [[fallback-modelos-ia]], [[via-de-escape-en-el-esquema]],
[[bucle-generador-auditor-corrector]], [[convocatoria-como-fuente]], [[clasificacion-ia]]
