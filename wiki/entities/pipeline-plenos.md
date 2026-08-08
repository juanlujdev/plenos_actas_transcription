---
type: entity
date_updated: 2026-08-08
source_count: 1
---

# Pipeline de informes de plenos

Genera un informe estructurado de cada sesión plenaria a partir de su grabación. **Se ejecuta a mano desde el PC del desarrollador**, no está automatizado (ver [[por-que-plenos-en-local]]).

## Flujo

```
audio (YouTube o fichero local)
  → yt-dlp descarga la pista de audio tal cual
  → ffmpeg trocea en fragmentos de 30 min recodificando a mono 64 kbps
  → Groq whisper-large-v3 transcribe cada fragmento (language=es, verbose_json)
  → unión con marcas [HH:MM:SS] absolutas
  → bucle Gemini generador→auditor→corrector  ([[bucle-generador-auditor-corrector]])
  → render determinista JSON→PDF (fpdf2, sin LLM)
  → public/plenos/ + public/data/plenos.json
  → revisión humana del PDF → commit a mano → deploy ([[hostinger-deploy]])
```

## Ficheros

| Fichero | Responsabilidad |
|---|---|
| `scripts/procesar_pleno.py` | Orquestación y CLI |
| `scripts/plenos_informe.py` | Esquemas pydantic, los 3 prompts, llamadas Gemini, bucle |
| `scripts/plenos_render.py` | JSON → PDF (fpdf2, fuentes core cp1252) |
| `scripts/test_plenos.py` | Tests de funciones puras (runner casero, sin pytest) |
| `public/plenos/` | `<fecha>-pleno.pdf`, `-transcripcion.md`, `-informe.json` |
| `public/data/plenos.json` | Índice que lee `usePlenos` → `PlenosView` |

## CLI

```powershell
python -u scripts/procesar_pleno.py --url "https://www.youtube.com/watch?v=..."
python -u scripts/procesar_pleno.py --audio "C:\ruta.mp3" --fecha 2026-07-07 --titulo "..."
python -u scripts/procesar_pleno.py --rehacer-informe 2026-07-07
```

`--rehacer-informe` reutiliza la transcripción ya guardada y solo repite la parte Gemini: permite iterar sobre los prompts sin gastar cuota de Groq, que en la capa gratuita es el recurso escaso.

Requiere `GROQ_API_KEY`, `GEMINI_API_KEY`, `GEMINI_MODEL` y `ffmpeg` en el PATH.

## Modelos y cuotas (capa gratuita, 2026-08)

- **Groq `whisper-large-v3`**: 20 req/min, 7.200 s de audio/hora, 28.800 s/día, **25 MB por fichero** (100 MB en la capa de pago). Devuelve `retry-after` en sus 429; `_espera_tras_error` la respeta con tope de 65 min.
- **Gemini**: `gemini-2.5-pro` (el que pedía la spec) tiene **cupo 0** en la capa gratuita, y `gemini-2.5-flash` devuelve 404 "no longer available to new users". Se usa el alias `gemini-flash-latest`. Migrar a `pro` exige activar facturación, decisión aplazada hasta que el desarrollo esté validado — ver [[clasificacion-ia]] para el patrón equivalente en el bot de agenda.

## Gotchas

- **No pedir a yt-dlp que convierta el audio.** Si el original ya es del formato pedido, copia el flujo e ignora el bitrate; los fragmentos salían a 25,3 MB y Groq devolvía **413**. La compresión la hace `trocear_audio` con ffmpeg. Trocear directamente el fichero descargado ahorra además una generación de pérdida (opus→aac, no opus→aac→aac).
- **Whisper deforma los nombres propios.** `plenos_informe.CORPORACION` lleva el listado de la corporación municipal para que el generador los escriba bien. **El auditor recibe ese mismo listado**: sin él marcaría las correcciones como afirmaciones no respaldadas y el bucle daría tres vueltas inútiles en cada ejecución. Actualizar tras cada elección municipal.
- Los recuentos de votos que no constan van a `null` y **no se imprimen**. Llegó a publicarse *"Rechazado (1 a favor, 0 en contra, 0 abstenciones)"* — imposible y fabricado — porque el render convertía `null` en `0`, saltándose [[via-de-escape-en-el-esquema]].
- Los timestamps se guardan en el JSON como rastro de verificación, pero **no se imprimen** en el PDF: es un acta, no un índice del vídeo.
- El informe se redacta **en presente de indicativo** con registro de acta ("Se debate...", "Se acuerda..."), por petición del Ayuntamiento.
- Usar `python -u`: al redirigir la salida a fichero, sin eso Python la almacena en búfer y parece colgado.

## La transcripción como auditoría

El `.md` que se guarda junto al PDF es **exactamente la misma cadena que recibe Gemini** (`transcribir_chunks()` → variable `transcripcion` → `bucle_informe()` y `write_text()`), no una versión resumida. Es por tanto la prueba de auditoría del informe: si una afirmación del PDF no aparece ahí, el modelo la inventó.

Se publica en `public/plenos/` —o sea, se despliega a Hostinger— pero **deliberadamente no se enlaza desde la web**: es apoyo de verificación, no contenido para el visitante. Decisión consciente del usuario, asumiendo que es accesible por URL directa, porque se trata de una sesión pública que ya está íntegra en YouTube.

La spec preveía además publicar el **informe** en Markdown además de en PDF. No se implementó: `render_markdown()` llegó a escribirse pero nunca se llamó desde el pipeline, y se borró en 2026-08-08 por ser código muerto. El PDF cubre la función de documento legible.

## Estado

Primera ejecución end-to-end real el 2026-08-08 sobre "PLENO EXTRAORDINARIO 7 DE JULIO 2026" (2h16m): transcripción correcta, auditor con visto bueno a la primera, PDF de 2 páginas. Validación humana final delegada al funcionario del Ayuntamiento.

## Pendiente para pasar a producción

Cinco asuntos abiertos a 2026-08-08, ninguno de código:

1. **Claves de API del Ayuntamiento.** Las pruebas se han hecho con las claves personales del desarrollador en capa gratuita. En producción hay que sustituirlas por claves generadas en cuentas del Ayuntamiento, con su tarjeta vinculada, para acceder a los modelos de pago de Groq y Gemini. Mientras se siga probando con claves personales, **no proponer activar facturación**.
2. **Migrar a `gemini-2.5-pro`.** El modelo que pedía la spec, imposible en capa gratuita (cupo 0). Se cambia solo el valor de `GEMINI_MODEL`, sin tocar código. Motivo técnico: sigue mejor las reglas estrictas de los prompts (no inferir, vías de escape, atribución solo si es explícita) y su auditor detecta mejor las afirmaciones no respaldadas — relevante en un documento público sobre votaciones. Coste estimado ~0,15-0,77 €/pleno frente a céntimos con flash.
3. **Visto bueno del funcionario** sobre el PDF generado. De su revisión pueden salir ajustes de los prompts (tono, extensión, qué se recoge de cada punto). Iterar es barato: `--rehacer-informe` no gasta cuota de Groq.
4. **Averiguar qué usa el PC de secretaría** (Drive, OneDrive u otro) para dejar allí una carpeta con los informes generados. Es la "fase final desacoplada" que [[2026-07-31-plenos-youtube-pipeline-design]] dejó fuera de alcance por desconocer ese equipo. Si resulta ser una nube compartida, abre además la vía para automatizar el pipeline sin depender de YouTube (ver la tabla de alternativas en [[por-que-plenos-en-local]]).
5. **Los audios de plenos que debe entregar el funcionario.** La spec contaba con dos grabaciones de ~4h que nunca llegaron. Son el único material que ejercitaría el modo `--audio`, hoy implementado pero **probado solo con audio sintético**: sin vídeo de YouTube de por medio, hay que pasar `--fecha` y `--titulo` a mano. Conviene estar atento la primera vez que se use con material real, sobre todo si el audio viene en un formato o calidad distintos de los que sirve YouTube.

## Relacionado

[[2026-07-31-plenos-youtube-pipeline-design]], [[por-que-plenos-en-local]], [[bucle-generador-auditor-corrector]], [[via-de-escape-en-el-esquema]], [[hostinger-deploy]], [[github-actions]]
