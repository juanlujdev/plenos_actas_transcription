# CLAUDE.md

Guía para Claude Code (claude.ai/code) al trabajar en este repositorio.

## Qué es esto

Genera el borrador del **acta oficial del Ayuntamiento de Enguídanos** de cada sesión
plenaria a partir de su grabación, rellenando la plantilla Word que usa la secretaría:
audio → transcripción diarizada con AssemblyAI `universal-3-5-pro` (Groq
`whisper-large-v3` + troceado ffmpeg como respaldo) → bucle `gemini-2.5-pro` (vía
OpenRouter) generador→auditor→corrector (esquemas pydantic, temperatura 0, máx. 3
vueltas) → acta `.docx` sobre la plantilla oficial (sin LLM) → `uploads/actas/<fecha>/`.

El acta generada es un **borrador**: se envía por email a la secretaria, que lo completa,
lo revisa y lo sella. El pipeline termina ahí. Nada de lo que genera se publica en
ninguna web.

Es software a medida para el Ayuntamiento de Enguídanos: los nombres de la corporación,
quién preside y las plantillas `.docx` son los suyos, en código.

Se separó del repositorio `juanlujdev/enguidanos_web` el 2026-09-08, donde nació en julio
de 2026. Ver `docs/superpowers/specs/2026-09-08-separacion-repo-plenos-design.md`.

## Cómo ejecutar

**Se ejecuta a mano desde el PC, no hay automatización.** Los plenos son mensuales y
YouTube bloquea las descargas desde IPs de datacenter ("Sign in to confirm you're not a
bot"), así que el cron de GitHub Actions que preveía la spec original se eliminó: no
funcionaba sin cookies de Google, y mantenerlas vivas era más trabajo que ejecutar un
comando al mes. Ejecutar en local recupera además la revisión humana antes de enviar
nada a la secretaria.

```powershell
# Vídeo de YouTube (descarga el audio con yt-dlp)
python -u procesar_pleno.py --url "https://www.youtube.com/watch?v=..."

# Audio local, sin vídeo
python -u procesar_pleno.py --audio "C:\ruta\pleno.mp3" --fecha 2026-07-07 --titulo "Pleno ordinario"

# Con la convocatoria: de ahí salen los títulos exactos, la numeración y los expedientes
python -u procesar_pleno.py --url "https://..." --convocatoria "C:\ruta\orden-del-dia.pdf"

# Rehacer solo el acta de un pleno ya transcrito (tras tocar prompts; NO vuelve a transcribir)
python -u procesar_pleno.py --rehacer-informe 2026-07-07

# Recomponer solo el .docx desde el informe.json guardado (tras tocar plenos_acta.py).
# Sin LLM y sin coste: es la forma de iterar el formato del acta.
python procesar_pleno.py --rehacer-acta 2026-07-07
```

Requiere `ASSEMBLYAI_API_KEY` y `OPENROUTER_API_KEY` en el entorno. `GROQ_API_KEY` y
`ffmpeg` solo hacen falta para el respaldo (y para procesar plenos sin clave de
AssemblyAI). El modelo (`google/gemini-2.5-pro`) está fijo en `plenos_informe.MODELO`: es
de pago y se eligió a propósito, no es un valor que se cambie por entorno.

Dependencias: `pip install -r requirements.txt` (`pydantic`, `python-docx`, `requests`,
`yt-dlp`).

## Asistente guiado para la funcionaria del Ayuntamiento

`python asistente_plenos.py` es un menú de preguntas que envuelve el pipeline (sin
duplicar su lógica) para que la funcionaria genere el borrador sin terminal ni jerga
técnica. `construir_exe.ps1` empaqueta ese script con PyInstaller `--onefile` en el
ejecutable que se le entrega. **Todo cambio en el código va también al `.exe`:
reconstruirlo con `construir_exe.ps1` es parte del cambio, siempre.** PyInstaller congela
el código, así que un script tocado y un `.exe` sin reconstruir hacen que la funcionaria
pruebe la versión anterior y su feedback no sirva. Las claves de API del ejecutable van
en `Configuración (no tocar)/configuracion.env` (junto al `.exe`), no en variables de
entorno del sistema, para poder cambiarlas sin reconstruirlo. `ACTAS_DIR` y `YT_DLP_EXE`
son las dos variables de entorno que redirigen el pipeline fuera del repo (carpeta de
borradores y binario de yt-dlp, respectivamente); sin definirlas, el flujo del
desarrollador no cambia. Detalle de cada decisión en
`wiki/concepts/asistente-para-la-funcionaria.md`.

## Ficheros clave

```
procesar_pleno.py     ← orquestación y CLI: --url | --audio | --rehacer-informe | --rehacer-acta
plenos_informe.py     ← esquemas pydantic + los 3 prompts + bucle LLM
plenos_acta.py        ← InformePleno → .docx sobre la plantilla oficial (sin LLM)
plenos_guia.py        ← InformePleno + transcripción → guía de verificación .html
asistente_plenos.py   ← menú guiado para la funcionaria
construir_exe.ps1     ← empaquetado PyInstaller del asistente
plantillas/           ← acta_ordinaria.docx, acta_extraordinaria.docx
test_plenos.py        ← tests de funciones puras (runner casero, sin pytest)
uploads/actas/<fecha>/← borrador: acta .docx, guía .html, transcripción, informe.json,
                        objeciones.json, entrada.json (gitignorado)
```

Tests: `python test_plenos.py`. No hay pytest ni linter.

## Gotchas

- **AssemblyAI transcribe el pleno entero de una: no se trocea.** El tope es 5 GB / 10 h
  por petición, así que el audio de yt-dlp sube tal cual, sin ffmpeg y sin recodificar.
  El troceado solo vive en la rama de Groq, que sí topa a 25 MB por fichero.
- **La diarización es la razón de pagar AssemblyAI** (~0,21 $/h, ≈0,40 $ por pleno).
  Whisper devuelve un muro de texto sin locutores; `universal-3-5-pro` marca cada
  intervención con una etiqueta de voz y la transcripción sale como
  `[HH:MM:SS] Interviniente A: ...`. `transcribir()` elige AssemblyAI si hay
  `ASSEMBLYAI_API_KEY` y cae a Groq si falta o si la petición falla.
- **La etiqueta de locutor es una voz, no una identidad.** El bloque
  `plenos_informe.DIARIZACION` se lo dice a los tres roles: misma etiqueta = misma
  persona, y basta con que la grabación identifique a esa etiqueta UNA vez para
  atribuirle toda la sesión; si no se identifica nunca, sigue siendo "no identificado en
  la grabación". Va también al auditor por el mismo motivo que `CORPORACION`: si no,
  marcaría cada atribución propagada como afirmación no respaldada y quemaría las vueltas.
- **Los nombres se corrigen ya en la transcripción, no solo en los prompts.**
  `AAI_KEYTERMS` (nombres de la corporación y vocabulario de acta), `AAI_PROMPT`
  (contexto en prosa) y `AAI_SPELLING` (`from` admite varias palabras, `to` solo una y
  distingue mayúsculas) atacan el destrozo de nombres antes de que llegue al LLM.
- **No pedir a yt-dlp que convierta el audio**: si el original ya es del formato pedido
  copia el flujo e ignora el bitrate. En la rama de Groq la compresión (mono 64 kbps) la
  hace `trocear_audio` con ffmpeg; sin eso los fragmentos superaban los 25 MB por fichero
  de la capa gratuita y la API devolvía 413.
- **Nada de webhooks**: el payload de AssemblyAI solo trae `transcript_id` y `status` (hay
  que hacer el GET igual) y exige un endpoint público que conteste 2xx en 10 s. Esto corre
  en tu PC, así que se sondea cada 20 s.
- **Los nombres propios los deforma Whisper.** `plenos_informe.CORPORACION` lleva el
  listado de la corporación para que el generador los escriba bien — y el auditor
  también lo recibe, porque si no marcaría esas correcciones como afirmaciones no
  respaldadas y el bucle daría vueltas inútiles. Actualizar tras cada elección municipal.
- **El cargo no es el papel que se juega en la sesión.** `plenos_informe.PRESIDENCIA`
  fija cómo se nombra a quien preside, en el encabezado y en cada intervención; de ahí
  sale también el género de las fórmulas fijas ("verificada por la Secretaria… la
  Presidenta abre la sesión"). Revisarlo cada vez que cambie quién preside. Hoy
  Sergio de Fez Cerezuela sigue siendo **el Alcalde** pese a la baja médica, y Lorena
  Luján Chujfi preside como **Segunda Teniente de Alcalde por delegación de funciones**:
  NO es "Alcaldesa en funciones", que es un cargo que nadie le ha dado, y llamarla así
  en un documento que se sella es un error de fondo, no de estilo. Cuando el Alcalde
  asiste sin presidir, interviene como un concejal más.
- **El acta no reparte los puntos en A) resolutiva / B) control / C) ruegos.** La
  plantilla oficial trae esas tres bandas, pero el acta que la secretaría firma numera
  los puntos como vienen en el orden del día y los escribe seguidos bajo un único
  encabezado "ORDEN DEL DÍA". `render_acta` reaprovecha la banda de A) como ese
  encabezado y elimina las otras cuatro tablas. `parte` sigue existiendo, pero solo para
  saber si el punto termina en acuerdo o en "La Corporación se da por informada".
- **El auditor se contradice, y el bucle lo detecta.** Pidió `rechazado` en la primera
  auditoría y `aprobado` en la cuarta sobre la misma votación; el corrector obedeció a
  las dos y el acta acabó afirmando un resultado que la grabación no declara.
  `bucle_informe` guarda el historial de cada campo (`_aplanar`) y, cuando un campo
  oscila (A→B→A) o sigue objetado al terminar las vueltas, aplica la **vía de escape** de
  `_AMBIGUOS` (`votacion.resultado` → `"no consta"`) en vez de elegir un bando, y la
  reimpone en cada vuelta. La objeción sigue en los pendientes: el escape no la resuelve,
  evita que el acta afirme lo que se discute. También sale antes si una corrección no
  cambia nada, y pasa al auditor de cada vuelta las rutas que el corrector acaba de tocar
  (calculadas en Python, no preguntándole a él) como pista de dónde mirar primero — sin
  dejar de auditar el informe entero.
  El razonamiento entero, y lo que se descartó, en
  `wiki/concepts/bucle-generador-auditor-corrector.md`.
- **La forma del acta vive en `plenos_acta.py`.** El título del punto va en negrita, en
  mayúsculas y **en su propio párrafo**, terminado en punto (`2º) TÍTULO.`), y el cuerpo
  del debate empieza en el renglón siguiente. Ese párrafo de título es el único del punto
  sin sangría de primera línea; los demás la llevan (`SANGRIA`, en twips exactos porque
  Word redondea). La alineación se pone a `None` a propósito: la plantilla trae su párrafo
  de ejemplo centrado y contagiaba el centrado al primer punto. Las comillas se unifican a
  las tipográficas dobles `“ ”` en `comillas()`, de forma determinista: es el criterio del
  acta oficial y no se le pide al modelo, que ya mezcló los dos tipos en el mismo punto.
  La decisión de no añadir un cuarto agente revisor está en
  `wiki/concepts/revisor-final-descartado.md`.
- **RUEGOS Y PREGUNTAS llega por dos caminos y solo debe escribirse una vez.** Cuando la
  convocatoria lo numera, el modelo ya lo devuelve como un punto de `orden_del_dia` (con
  su texto) y el render le pone su encabezado numerado; el encabezado suelto sin numerar
  que añade `render_acta` es solo para cuando el orden del día NO lo trae. Añadirlo
  siempre lo duplicaba en el acta (`6º) RUEGOS Y PREGUNTAS.` seguido de `RUEGOS Y
  PREGUNTAS`), así que ahora se comprueba antes.
- **El acuerdo va en su propio campo, no dentro de `texto`.** El documento compone
  "El Pleno del Ayuntamiento ACUERDA, … , por tres votos a favor y tres en contra" a
  partir de `acuerdo` + `votacion`, e integra el recuento en esa misma frase. Cuando el
  modelo escribía el acuerdo dentro del texto, el acta lo decía dos veces. Si el empate
  lo rompe la Presidencia, `voto_de_calidad` lo hace constar.
- **Cada escalón del pipeline se puede repetir sin repetir el de abajo.** La transcripción
  se guarda antes del bucle LLM y el `informe.json` antes del render, así que
  `--rehacer-informe` no vuelve a transcribir y `--rehacer-acta` no vuelve a llamar al
  LLM. Un fallo al componer el `.docx` no tira el bucle: `render_acta` va dentro de un
  try/except que avisa y remite a `--rehacer-acta`.
- **La descripción de un campo no es una validación.** El modelo devolvió
  `fecha_pleno: "19 de mayo de 2026"` y `hora_fin: "02:39:28"` (una marca de tiempo de la
  transcripción, no una hora) pese a que el esquema pedía ISO y HH:MM; la primera reventó
  el render tras un bucle ya pagado y la segunda habría hecho constar que el Pleno se
  levantó de madrugada. Todo campo cuyo formato necesite el documento se normaliza en el
  esquema (`normalizar_fecha`, `normalizar_hora`, `_acuerdo_limpio`), no solo se describe.
- **Una cifra escrita en el acta queda como dato oficial del Ayuntamiento.** La regla 15
  del generador solo admite importes que el interviniente vincula a un documento
  identificable (expediente, factura, modelo 347, ampliación de crédito); las cifras
  sueltas dichas de memoria en el debate se omiten, y las estimaciones relevantes se
  recogen atribuidas y calificadas como tales. El auditor tiene el aviso complementario:
  una cifra que está en la transcripción y no en el informe es la depuración esperada,
  no un problema que reclamar.
- Los recuentos de votos que no constan van a `null` y **no se imprimen**; nunca
  rellenarlos con 0 (llegó a publicarse "rechazado, 0 en contra", que es imposible).
- **Los temas tratados fuera del orden del día NO van al acta: van a la guía.** El
  generador los recoge en `asuntos_no_convocados` (regla 16 ter: síntesis de una o dos
  frases, punto en que surge, timestamp) y solo `plenos_guia.py` los pinta, con el minuto
  enlazado, para que la secretaria decida si los sintetiza y dónde. `plenos_acta.py` no lee
  ese campo. Distinto de la regla 24: un asunto de urgencia que se vota SÍ es un punto del
  acta.
- **Lo que un concejal pide expresamente que conste, consta.** La regla 16 poda el tira y
  afloja; la 16 bis la exceptúa cuando alguien pide que su observación conste en acta, o
  cuando la reserva o discrepancia sostiene su postura sobre el asunto: una o dos frases,
  atribuidas. El disparador es una frase objetiva de la transcripción, no un juicio de
  "relevancia", para que el auditor pueda comprobarlo.
- **La convocatoria (`--convocatoria`) va al auditor además del generador.** Si solo la
  viera el generador, el auditor buscaría en la transcripción los títulos tomados del
  orden del día, encontraría el destrozo de Whisper y los marcaría como no respaldados,
  quemando las tres vueltas. Mismo motivo que `CORPORACION`.
- **La convocatoria manda en la forma, la grabación en el fondo.** De la convocatoria
  salen títulos, numeración, expedientes y tipo de sesión; qué se debatió y qué se votó
  sale solo del audio. Un punto convocado del que la grabación no habla NO se redacta:
  redactar lo previsto como si hubiera ocurrido es una invención con pinta de oficial.
- **La convocatoria no se convierte a texto: el PDF entero va al modelo.** Las del
  Ayuntamiento son escaneos (un JPEG sin capa de texto), así que `pypdf` no saca nada;
  Gemini las lee y además conserva la maquetación. Viaja en base64 con el plugin
  `file-parser` de OpenRouter en engine `native` — el engine por defecto es un OCR de
  pago que devolvería texto plano. Se guarda en el borrador para que
  `--rehacer-informe` la reutilice sin volver a pasarla.
- Los timestamps se guardan en el JSON como rastro para verificar contra la grabación,
  pero no se imprimen en el acta.
- Groq documenta `retry-after` en sus 429; `_espera_tras_error` la respeta (tope 65 min)
  porque el cupo horario de la capa gratuita puede pedir esperas largas.
- Usar `python -u`: sin eso, al redirigir la salida a un fichero no se ve el progreso.
- **El acta generada es un borrador, no el documento oficial.** Se envía por email a la
  secretaria, que lo completa, lo revisa y lo sella. El pipeline no publica nada en
  ningún sitio y no toca git en ningún caso.
- **El tipo de sesión decide la plantilla.** Si no consta en la grabación no se genera el
  acta: elegir plantilla a ciegas produciría un encabezado equivocado en un documento
  que se sella.

---

## LLM Wiki — documentación viva del proyecto

Patrón de [Andrej Karpathy](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f):
en vez de re-derivar contexto en cada consulta, el LLM construye y mantiene una wiki
markdown persistente en `wiki/`. Obsidian es solo el visor (graph view, backlinks);
Claude Code escribe, el usuario cura fuentes y pregunta.

### Estructura

```
wiki/
  index.md       ← catálogo de entidades, conceptos y pendientes
  log.md         ← registro append-only de operaciones
  overview.md    ← síntesis general del proyecto
  sources/       ← una página resumen por fuente ingerida
  entities/      ← pipeline-plenos
  concepts/      ← decisiones y patrones (p. ej. "por qué el bucle de tres agentes")
  synthesis/     ← respuestas de queries archivadas cuando son sustanciales
```

### Convenciones

Frontmatter obligatorio en `sources/`, `entities/`, `concepts/`, `synthesis/`:

```yaml
---
type: source-summary | entity | concept | synthesis
date_updated: YYYY-MM-DD
source_count: <n>   # opcional, solo entity/concept
---
```

- `[[wikilinks]]` para que Obsidian dibuje el grafo de conexiones.
- `log.md`: una línea por operación, formato `## [YYYY-MM-DD] operación | Título`.

### Reglas fundamentales

- Nunca modificar `docs/superpowers/**` — son fuentes inmutables, solo se leen.
- Toda ingesta o query sustancial actualiza `index.md` y añade una entrada a `log.md`.
- Las contradicciones entre fuentes se documentan explícitamente en la página afectada —
  nunca se "resuelven" en silencio.
- Los resúmenes de `sources/` son factuales; la interpretación va en `synthesis/`.
- Las queries se responden sintetizando desde `wiki/`, nunca leyendo las fuentes crudas
  directamente (si `wiki/` no tiene la respuesta, se hace `ingest` primero).
