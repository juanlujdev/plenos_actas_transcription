---
type: concept
date_updated: 2026-10-11
source_count: 1
---

# Un pleno en varias grabaciones, y dos plenos el mismo día

El pipeline ([[pipeline-plenos]]) asumía **un pleno = una grabación = una carpeta por
fecha**. El pleno ordinario de octubre de 2026 rompió las dos primeras cosas (se emitió en
dos vídeos de YouTube por un accidente) y un extraordinario con la misma fecha que un
ordinario rompió la tercera.

## Un pleno en dos vídeos: se resolvió a mano, y es lo correcto

Opciones valoradas, de mejor a peor:

1. Aceptar varias fuentes en la app y unir el audio con ffmpeg.
2. Transcribir cada parte por separado y fusionar. **Descartada de plano:** la etiqueta de
   locutor no es estable entre transcripciones (la «A» de la parte 2 puede ser otra
   persona), y el prefijado («1-A», «2-A») hace que el modelo vea más voces de las que hay
   ([[diarizacion-como-andamiaje]]).
3. Unir los audios a mano y pasarlos como `--audio`.
4. Dos actas y fusionarlas en Word. 5. Procesar solo una parte (acta incompleta sin aviso).

**Decisión:** fue un accidente, así que no se automatizó la unión (opción 1: ffmpeg
obligatorio en el `.exe`, ~80-100 MB, y código para un caso que quizá no vuelva). Se hizo
la opción 3. Lo único que se cambió en el asistente: **acepta un archivo arrastrado donde
pide la URL** (`flujo_pleno_nuevo`, variable `local`). Antes el archivo local solo era el
último recurso si fallaba la descarga, y con la parte 1 descargable habría procesado media
sesión sin avisar.

Receta manual (PowerShell, en una carpeta temporal):

```
yt-dlp --cookies-from-browser firefox -x --audio-format mp3 -o "parte1.%(ext)s" <url1>
yt-dlp --cookies-from-browser firefox -x --audio-format mp3 -o "parte2.%(ext)s" <url2>
# lista.txt:  file 'parte1.mp3' / file 'parte2.mp3'
ffmpeg -f concat -safe 0 -i lista.txt -c copy pleno_completo.mp3
```

Se comprueba con `ffprobe` que la suma de duraciones coincide con la del unido y se
escucha el corte para descartar audio repetido. Con ambos mp3 del mismo códec, `-c copy`
vale. Consecuencia: **la guía de verificación no lleva enlaces a YouTube** (no hay
`video_url`); los minutos son los del audio unido, y hay que restar la duración de la
parte 1 para localizarlos en el segundo vídeo.

### Descargar de YouTube desde casa (lo que hubo que desatascar)

- `429` + «Sign in to confirm you're not a bot» también ocurre desde una IP doméstica, no
  solo de datacenter ([[por-que-plenos-en-local]]).
- `--cookies-from-browser` funciona con **Firefox** (cuenta secundaria, basta con tener
  la sesión iniciada; no hace falta que sea el navegador principal). Chrome/Edge
  recientes cifran las cookies y suelen fallar al descifrarlas.
- Con las cookies, el siguiente error («n challenge solving failed», «The page needs to be
  reloaded») era la **falta de un runtime de JavaScript**: `winget install DenoLand.Deno`
  y `pip install -U "yt-dlp[default]"`, y reabrir la terminal.

## Dos plenos el mismo día: la carpeta lleva el tipo

`dir_borrador(fecha)` era `<actas>/<fecha>/`, y el asistente ofrece «Empezar de cero y
sustituirlo» cuando existe: un extraordinario habría borrado la transcripción, el
`informe.json`, la convocatoria y `entrada.json` del ordinario (solo sobrevivían los
`.docx`, porque su nombre lleva el tipo).

**Decisión:** `procesar_pleno.clave_pleno(fecha, tipo)` → `<fecha>-ordinario` y
`<fecha>-extraordinario`. Primero el ordinario conservaba el nombre solo con la fecha (para no
tocar carpetas antiguas), pero en el explorador no se distinguía cuál era cuál: se cambió.
Las carpetas antiguas (solo la fecha) siguen siendo válidas: el asistente las reutiliza para un
ordinario si no existe la nueva, y `plenos_guardados` las lista. Los
ficheros de dentro conservan el prefijo de la fecha pura (la guía y las comprobaciones
llaman a `fecha_larga` con ella), así que solo cambia el nombre de la carpeta, y la
**clave** de la carpeta es lo que circula en `--rehacer-informe`/`--rehacer-acta` y en
`rehacer_pleno`, mientras `clave[:10]` da la fecha.

- El asistente **pregunta** «¿Ordinario o extraordinario?» tras la fecha. El tipo lo
  decide quien procesa, no el modelo, porque la carpeta hay que conocerla antes de
  transcribir; la plantilla del acta sigue decidiéndola `informe.tipo_sesion`. Si ambos
  difieren, `procesar_pleno` imprime un aviso en vez de elegir uno en silencio.
- En CLI: `--extraordinario`. El tipo se guarda en `entrada.json` y
  `_rehacer_informe` lo reutiliza.
- `plenos_guardados` acepta carpetas `AAAA-MM-DD(-ordinario|-extraordinario)?` y el menú de
  rehacer muestra el tipo.
- Descartado: detectar la colisión y proponer `-2` (más simple, pero el nombre no dice
  cuál es cuál).

## Relacionado

[[asistente-para-la-funcionaria]], [[guia-de-verificacion]], [[pipeline-plenos]],
[[diarizacion-como-andamiaje]], [[por-que-plenos-en-local]]
