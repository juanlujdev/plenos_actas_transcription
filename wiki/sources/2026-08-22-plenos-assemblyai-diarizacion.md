---
type: source-summary
date_updated: 2026-08-22
---

# Plenos: de Groq Whisper a AssemblyAI con diarización

Fuente: conversación de trabajo del 2026-08-22, sin spec ni plan previos. El usuario pegó
once páginas de la documentación de AssemblyAI (transcripción de pre-recorded audio,
prompting de Universal-3.5-Pro, diarización, multicanal, idioma, custom spelling, filler
words, word search, recorte, estados, borrado) más la de webhooks y el precio, y pidió
implementarlo. Segunda intervención del día sobre [[pipeline-plenos]], después de
[[2026-08-22-plenos-openrouter-gemini-pro]]; esta toca la **transcripción**, aquella tocaba
el bucle LLM.

## Qué se decidió

La transcripción pasa a **AssemblyAI `universal-3-5-pro`**, con **Groq `whisper-large-v3`
como respaldo**. El usuario pidió explícitamente conservar Groq ("déjalo como fallback"),
así que no se borró nada: `transcribir()` elige AssemblyAI si hay `ASSEMBLYAI_API_KEY`, y
cae a la rama de Groq si no la hay o si la petición falla.

El motivo no es la calidad de la transcripción —que también mejora—, sino la
**diarización**: Whisper devuelve un muro de texto sin locutores, y un acta necesita saber
quién interviene. Ver [[diarizacion-como-andamiaje]] para cómo se usa esa información sin
romper la regla de no atribuir nada que la grabación no diga.

Coste: **$0,21/h**, unos **$0,48 por pleno** de 2 h 17. A cambio desaparecen el troceado
con ffmpeg, los 413 por tamaño y las esperas de hasta 65 min del cupo horario gratuito de
Groq.

**AssemblyAI no tiene capa gratuita**: da **$50 de crédito** al abrir cuenta y a partir de
ahí se paga por hora de audio. Con ~$0,48 por pleno mensual, ese crédito cubre del orden de
100 sesiones — años de funcionamiento antes de poner una tarjeta. No hay por tanto ninguna
restricción de plan gratuito que condicione el diseño: el troceado y las esperas largas del
pipeline son y siguen siendo cosa de Groq.

## Qué cambió en el código

`scripts/procesar_pleno.py`:

| Antes | Ahora |
|---|---|
| `trocear_audio` + `transcribir_chunks` siempre | `transcribir()` decide: AssemblyAI, o Groq con troceado |
| Troceado obligatorio en fragmentos de 30 min | El audio sube **entero**: el tope es 5 GB / 10 h por petición |
| `unir_segmentos` (verbose_json de Whisper) | `formatear_utterances` (utterances de AssemblyAI) |
| `[HH:MM:SS] texto` | `[HH:MM:SS] Interviniente A: texto` |

El formato de marcas se conserva a propósito (`_hms()` es ahora común a las dos ramas):
`plenos_acta.py`, `--rehacer-informe` y los prompts siguen viendo la misma forma de
transcripción, venga de donde venga.

Cuerpo de la petición a `POST /v2/transcript`:

```python
{"audio_url": ..., "speech_models": ["universal-3-5-pro"], "language_code": "es",
 "speaker_labels": True,
 "speaker_options": {"min_speakers_expected": 6, "max_speakers_expected": 10},
 "prompt": AAI_PROMPT, "keyterms_prompt": AAI_KEYTERMS, "custom_spelling": AAI_SPELLING}
```

Cuatro detalles de la API que la documentación no pone en el mismo sitio:

1. **`speech_models` es un array**; el `speech_model` (singular) de las guías está
   deprecado. Y `universal-3-5-pro` **no es el modelo por defecto**: hay que pedirlo.
2. **`min_speakers_expected` y `max_speakers_expected` van dentro de `speaker_options`.**
   Varios ejemplos de la documentación los muestran al nivel superior, donde la API los
   ignora. Se usa un rango en vez de `speakers_expected` (exacto) porque no todos los
   miembros de la corporación intervienen en todas las sesiones.
3. **`custom_spelling`**: el campo `to` admite **una sola palabra** y distingue
   mayúsculas; `from` admite varias y no las distingue. Por eso `AAI_SPELLING` solo
   contiene apellidos sueltos (Chujfi, Luján, Cerdán, Cerezuela, Enguídanos) y los nombres
   completos viajan en `keyterms_prompt` (tope: 1.000 términos, 6 palabras cada uno).
4. **`disfluencies` se queda en `false`**, que es el valor por defecto: AssemblyAI elimina
   "eh", "mmm", "hmm" salvo que se pidan. Un acta no los recoge, así que el
   comportamiento por defecto es justo el que se quiere.

`scripts/plenos_informe.py`:

- Nuevo bloque **`DIARIZACION`**, inyectado en los **tres** prompts —
  [[diarizacion-como-andamiaje]] explica por qué el auditor también lo necesita.
- `CORPORACION` gana dos datos que salieron de la propia grabación: **Elena, secretaria**
  del Ayuntamiento (su voz está en el audio, pero no es miembro de la Corporación, no vota
  y nunca va en `asistentes`/`ausentes`), y que a **Mª Rosario Cerdán Pérez la llaman
  "Chari"**.
- `PROMPT_CORRECTOR` pasa a ser f-string para poder incluir el bloque.

## Por qué no hay webhooks

AssemblyAI los ofrece y se descartaron: el payload trae **solo `transcript_id` y
`status`** (hay que hacer el `GET` igual), y exige un endpoint público que conteste 2xx en
10 s, con 10 reintentos cada 10 s. [[pipeline-plenos]] se ejecuta a mano en el PC del
desarrollador ([[por-que-plenos-en-local]]), donde no hay endpoint público que valga. Se
sondea cada 20 s.

También se descartó `multichannel` (la grabación de YouTube es mono, y activarlo suma ~40%
de tiempo de proceso) y se dejaron sin usar `audio_start_from`/`audio_end_at` y el
word-search, disponibles si algún día hace falta recortar un preámbulo.

## Verificación

Ejecución real contra la API, con el pleno extraordinario de YouTube `5UETzjDRRtw`
(2 h 17). La clave se pasó por un fichero temporal fuera del repo y se borró después.

| Muestra | Configuración | Resultado |
|---|---|---|
| 3 min (min 05:00) | min 6 / max 10 | 8 etiquetas — **parte** a la misma persona |
| 3 min (min 05:00) | solo max 10 | 2 etiquetas — **funde** a gente distinta |
| 20 min (desde el inicio) | min 6 / max 10 | 8 etiquetas, reparto coherente |

La conclusión intermedia (que el suelo de 6 locutores causaba el exceso de etiquetas) era
falsa: con 20 minutos y esa misma configuración el reparto es coherente. **El problema era
la falta de muestra**, no el parámetro. Se conserva min 6 / max 10.

Calidad de la transcripción: sale bien *"don Sergio de Fez Cerezuela"*, *"don Mario Cerdán
Ochoa"*, *"don Fernando Pons Mayor"*, *"moción de censura"*, *"delegación de funciones"*.
Y el arranque del pleno es material ideal para la regla de propagación de
[[diarizacion-como-andamiaje]]: quien preside se identifica al abrir la sesión ("presido
este pleno en virtud de la delegación de funciones efectuada por el señor Alcalde
Presidente, don Sergio de Fez Cerezuela"), y a otra concejala la llaman "Chari" dos veces.

Coste del test: 26 minutos de audio, ~$0,09. Copia de la prueba en
`uploads/prueba-assemblyai-20min.md` (gitignorado).

Tests offline añadidos a `scripts/test_plenos.py`: formato de `formatear_utterances`
(incluida la conversión de ms), topes de `custom_spelling` y `keyterms_prompt`, y un
`requests` falso que fija el cuerpo de la petición y el sondeo hasta `completed` — es lo
que impide que el anidamiento de `speaker_options` o el array `speech_models` se rompan
en silencio.

## Efecto colateral: yt-dlp estaba obsoleto

La descarga del vídeo falló con **HTTP 403** en todos los clientes de YouTube. No era el
bloqueo por IP de datacenter de [[por-que-plenos-en-local]] —esto se ejecutaba en el PC del
desarrollador—, sino que `yt-dlp 2026.07.04` había quedado desfasado frente a los cambios
de YouTube. `pip install -U yt-dlp` (a `2026.08.19`) lo arregló. Es mantenimiento
recurrente del pipeline, no un incidente puntual.

## Relacionado

[[pipeline-plenos]], [[diarizacion-como-andamiaje]],
[[2026-08-22-plenos-openrouter-gemini-pro]], [[bucle-generador-auditor-corrector]],
[[via-de-escape-en-el-esquema]], [[por-que-plenos-en-local]], [[fallback-modelos-ia]]
