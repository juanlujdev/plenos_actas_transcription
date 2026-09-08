# Actas de plenos — del audio al borrador del acta oficial

Genera el borrador del **acta oficial del Ayuntamiento de Enguídanos** a partir de la
grabación de cada sesión plenaria, rellenando la plantilla Word que usa la secretaría.

```
audio del pleno (YouTube o fichero local)
  → transcripción diarizada (AssemblyAI universal-3-5-pro)
  → bucle generador → auditor → corrector (gemini-2.5-pro vía OpenRouter)
  → acta .docx sobre la plantilla oficial, sin LLM
  → uploads/actas/<fecha>/
```

El resultado es un **borrador**. Se envía por email a la secretaria, que lo completa, lo
revisa y lo sella. El pipeline termina ahí: no publica nada en ninguna web y no toca git.

Junto al acta se genera una **guía de verificación** en HTML, con los minutos enlazados a
la grabación, para que quien revise pueda contrastar cada afirmación contra el vídeo.

## Requisitos

```bash
pip install -r requirements.txt
```

Variables de entorno:

| Variable | Para qué | ¿Obligatoria? |
|---|---|---|
| `ASSEMBLYAI_API_KEY` | Transcripción con diarización (quién dice qué) | Sí |
| `OPENROUTER_API_KEY` | El bucle de redacción del acta con `gemini-2.5-pro` | Sí |
| `GROQ_API_KEY` | Respaldo de transcripción con `whisper-large-v3` | No |
| `ACTAS_DIR` | Redirige la carpeta de borradores fuera del repo | No |
| `YT_DLP_EXE` | Ruta a un binario de `yt-dlp` concreto | No |

`ffmpeg` solo hace falta para el respaldo de Groq, que trocea el audio antes de subirlo.

Coste aproximado por pleno: unos 0,40 $ de AssemblyAI (~0,21 $/h) más lo que consuma el
bucle de Gemini.

## Uso

```powershell
# Vídeo de YouTube (descarga el audio con yt-dlp)
python -u procesar_pleno.py --url "https://www.youtube.com/watch?v=..."

# Audio local
python -u procesar_pleno.py --audio "C:\ruta\pleno.mp3" --fecha 2026-07-07 --titulo "Pleno ordinario"

# Con la convocatoria: de ahí salen los títulos exactos, la numeración y los expedientes
python -u procesar_pleno.py --url "https://..." --convocatoria "C:\ruta\orden-del-dia.pdf"

# Rehacer el acta de un pleno ya transcrito, sin volver a transcribir
python -u procesar_pleno.py --rehacer-informe 2026-07-07

# Recomponer solo el .docx desde el informe.json guardado: sin LLM y sin coste
python procesar_pleno.py --rehacer-acta 2026-07-07
```

Usa `python -u`: sin eso, al redirigir la salida a un fichero no se ve el progreso.

**Se ejecuta a mano, no hay automatización.** YouTube bloquea las descargas desde IPs de
datacenter, así que el cron en CI que se llegó a construir se eliminó. Los plenos son
mensuales: no compensa. Ejecutar en local mantiene además la revisión humana.

## El ejecutable para el Ayuntamiento

`asistente_plenos.py` es un menú de preguntas que envuelve el pipeline para que la
funcionaria del Ayuntamiento genere el borrador sin terminal ni jerga técnica.

```powershell
powershell -ExecutionPolicy Bypass -File .\construir_exe.ps1
```

Deja el ejecutable listo en `entrega\Actas de Plenos del Ayuntamiento\`. Las claves de API
van en `Configuración (no tocar)\configuracion.env`, junto al `.exe`, para poder cambiarlas
sin reconstruirlo.

> **Todo cambio en el código va también al `.exe`.** PyInstaller congela el código: un
> script tocado y un `.exe` sin reconstruir hacen que la funcionaria pruebe la versión
> anterior y su feedback no sirva. Reconstruirlo es parte del cambio, siempre.

## Tests

```bash
python test_plenos.py
```

Runner casero, sin pytest ni linter. Cubre las funciones puras del pipeline.

## Documentación

- `CLAUDE.md` — guía de trabajo y la lista de gotchas, que es donde está el conocimiento
  caro de este proyecto.
- `wiki/` — wiki markdown persistente (patrón LLM Wiki). `wiki/entities/pipeline-plenos.md`
  es el mejor punto de entrada; `wiki/concepts/` explica cada decisión y lo que se descartó.
- `docs/superpowers/` — specs y planes de implementación (no versionados).

## Origen

Este proyecto nació dentro de `juanlujdev/enguidanos_web` en julio de 2026 y se separó a
su propio repositorio el 2026-09-08, conservando su historia. Las actas ya no se publican
en la web del municipio: el producto es el borrador que recibe la secretaria.

## Licencia

MIT. Ver `LICENSE`.
