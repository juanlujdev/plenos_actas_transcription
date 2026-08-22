---
type: entity
date_updated: 2026-08-22
source_count: 6
---

# Pipeline del acta de plenos

Genera el borrador del **acta oficial del Ayuntamiento** de cada sesión plenaria a partir
de su grabación, rellenando la plantilla Word que usa la secretaría. **Se ejecuta a mano
desde el PC del desarrollador**, no está automatizado (ver [[por-que-plenos-en-local]]).

Hasta 2026-08-21 el pipeline producía un "informe" en PDF con formato propio
(`plenos_render.py`, fpdf2). Desde
[[2026-08-21-acta-oficial-plenos-design]] produce en su lugar el documento que de verdad
usa el Ayuntamiento: la plantilla oficial rellenada, en `.docx`, como **borrador** que
revisa y sella una persona antes de publicarse. Ver [[via-de-escape-en-el-esquema]] y
[[bucle-generador-auditor-corrector]] para los dos mecanismos de fiabilidad que no
cambiaron con este rediseño.

## Flujo en dos pasos

**Paso 1 — generar el borrador** (nunca toca `public/`):

```
audio (YouTube o fichero local)
  → yt-dlp descarga la pista de audio tal cual
  → AssemblyAI universal-3-5-pro transcribe el audio ENTERO (language_code=es)
       ├─ diarización: speaker_labels + speaker_options {min 6, max 10}
       └─ prompt + keyterms_prompt + custom_spelling (nombres de la corporación)
     [respaldo si no hay clave o si falla: ffmpeg trocea en fragmentos de 30 min a
      mono 64 kbps → Groq whisper-large-v3 por fragmento, verbose_json]
  → transcripción con marcas [HH:MM:SS] y etiqueta de locutor
  → bucle gemini-2.5-pro (vía OpenRouter) generador→auditor→corrector
       ([[bucle-generador-auditor-corrector]])
       ├─ + CORPORACION (para escribir bien los nombres)
       ├─ + DIARIZACION (qué significa una etiqueta de locutor,
       │    [[diarizacion-como-andamiaje]])
       └─ + convocatoria oficial en PDF, opcional ([[convocatoria-como-fuente]])
  → render determinista InformePleno → .docx sobre la plantilla oficial (sin LLM)
  → uploads/actas/<fecha>/  (acta .docx, transcripción, informe.json, entrada.json,
                             convocatoria.pdf si se pasó)
```

**Paso 2 — publicar**, tras el email a la secretaria, su revisión y su sello:

```
python scripts/procesar_pleno.py --publicar <fecha> --pdf "<acta sellada>"
  → public/plenos/<fecha>-pleno.pdf + <fecha>-transcripcion.md
  → entrada en public/data/plenos.json
  → commit manual → deploy ([[hostinger-deploy]])
```

`--publicar` es **el único punto del pipeline que escribe en `public/`**. Todo lo del
paso 1 cae en `uploads/actas/<fecha>/`, que está gitignorado — así lo que se genera
automáticamente no puede llegar a `public/` sin el visto bueno de la secretaria.

## Ficheros

| Fichero | Responsabilidad |
|---|---|
| `scripts/procesar_pleno.py` | Orquestación y CLI: `--url` \| `--audio` \| `--rehacer-informe` \| `--publicar` |
| `scripts/plenos_informe.py` | Esquemas pydantic, los 3 prompts, llamadas a OpenRouter, bucle |
| `scripts/plenos_acta.py` | `InformePleno` → `.docx` sobre la plantilla oficial (sin LLM) |
| `scripts/plantillas/` | `acta_ordinaria.docx`, `acta_extraordinaria.docx` — plantillas oficiales del Ayuntamiento, convertidas desde Word 97 y versionadas |
| `scripts/test_plenos.py` | Tests de funciones puras (runner casero, sin pytest) |
| `uploads/actas/<fecha>/` | Borrador: acta `.docx`, transcripción, `informe.json`, `entrada.json`, `convocatoria.pdf` (gitignorado) |
| `src/components/pages/AyuntamientoPage.jsx` | La sección "Actas de los plenos" de la web, que lista `plenos.json` |
| `public/plenos/` | Solo tras `--publicar`: `<fecha>-pleno.pdf`, `<fecha>-transcripcion.md` |
| `public/data/plenos.json` | Índice que lee `usePlenos` → `PlenosView` |

`plenos_render.py` (JSON → PDF, fpdf2) se borró: su único consumidor era el documento
publicado, que ahora es el acta sellada, no un PDF de formato propio.

## CLI

```powershell
python -u scripts/procesar_pleno.py --url "https://www.youtube.com/watch?v=..."
python -u scripts/procesar_pleno.py --url "https://..." --convocatoria "C:\ruta\orden-del-dia.pdf"
python -u scripts/procesar_pleno.py --audio "C:\ruta.mp3" --fecha 2026-07-07 --titulo "..."
python -u scripts/procesar_pleno.py --rehacer-informe 2026-07-07
python scripts/procesar_pleno.py --publicar 2026-07-07 --pdf "C:\ruta\acta-sellada.pdf"
```

`--rehacer-informe` reutiliza la transcripción ya guardada y solo repite la parte del LLM: permite iterar sobre los prompts sin volver a transcribir, que ahora además es la parte que cuesta dinero. También reutiliza la convocatoria que quedó guardada en el borrador, así que no hay que volver a pasarla en cada iteración.

`--convocatoria` es opcional y vale en los tres modos de generación. Es el orden del día que el Ayuntamiento publica antes de la sesión: de ahí salen los títulos exactos, la numeración, los expedientes y el tipo de sesión — ver [[convocatoria-como-fuente]].

El desarrollador ejecuta todo esto en **Git Bash**, no en PowerShell (`export VAR=...`, rutas `~/`, salida a fichero con `| tee ~/pleno.log`). Ambos shells sirven; los ejemplos de arriba están en sintaxis PowerShell porque es lo que documenta `CLAUDE.md`.

Requiere `ASSEMBLYAI_API_KEY` y `OPENROUTER_API_KEY`, más `python-docx` (dependencia local
del pipeline, no va en `scripts/requirements.txt` porque ese fichero es del bot de Telegram
y corre en GitHub Actions). `GROQ_API_KEY` y `ffmpeg` solo hacen falta para la rama de
respaldo.

## Por qué es un borrador y no el documento final

El acta que genera el pipeline es el texto que un modelo redactó a partir de una
transcripción automática: fiel a la grabación en la medida en que lo garantizan
[[via-de-escape-en-el-esquema]] y [[bucle-generador-auditor-corrector]], pero sin validez
legal hasta que la secretaria — Interventora del Ayuntamiento la revise, complete lo que
falte (el número de expediente, cualquier hueco `___________`) y la selle. Solo ese PDF
sellado es lo que `--publicar` sube a la web; nada generado automáticamente llega a
`public/` sin pasar por esa revisión humana.

El tipo de sesión (ordinaria/extraordinaria) decide qué plantilla se usa. Si no consta en
la grabación, el acta **no se genera** — elegir plantilla a ciegas produciría un
encabezado equivocado en un documento que va a sellarse.

## Modelos y cuotas (2026-08)

- **AssemblyAI `universal-3-5-pro`** desde 2026-08-22 ([[2026-08-22-plenos-assemblyai-diarizacion]]): **$0,21/h**, unos **$0,48 por pleno**. **No hay capa gratuita**: se dan $50 de crédito al abrir cuenta, que a pleno mensual dan para años. Ninguna restricción de plan gratuito condiciona el diseño de esta rama — el troceado y las esperas largas son cosa de Groq. Tope de 5 GB / 10 h por petición, así que el audio sube entero y no se trocea. Aporta lo que Whisper no daba: **diarización** ([[diarizacion-como-andamiaje]]), `keyterms_prompt`/`custom_spelling` para los nombres propios, y español fijado con `language_code`.
- **Groq `whisper-large-v3`**, ahora solo como respaldo: 20 req/min, 7.200 s de audio/hora, 28.800 s/día, **25 MB por fichero** (100 MB en la capa de pago). Devuelve `retry-after` en sus 429; `_espera_tras_error` la respeta con tope de 65 min. Esa rama conserva el troceado con ffmpeg.
- **`google/gemini-2.5-pro` vía OpenRouter** desde 2026-08-22 ([[2026-08-22-plenos-openrouter-gemini-pro]]). Antes se llamaba a Google AI Studio con el SDK `google.genai` y el alias `gemini-flash-latest`, porque `gemini-2.5-pro` tiene **cupo 0** en la capa gratuita de Google y `gemini-2.5-flash` devuelve 404 *"no longer available to new users"*. OpenRouter da acceso al modelo que la spec pedía sin abrir cuenta de facturación con Google — el mismo movimiento que hizo el bot de agenda en 2026-06-27, ver [[fallback-modelos-ia]].
- **Ya no es gratis.** Una petición trivial costó $0,0018, casi todo tokens de razonamiento (176 de `reasoning` frente a 5 de prompt): `2.5-pro` razona antes de responder y eso se factura como salida, así que el coste no escala solo con la transcripción. Estimación por pleno: **0,15–0,80 €**.
- **El modelo está fijo en `plenos_informe.MODELO`**, no en una env var. Se eligió a propósito y es de pago; `GEMINI_MODEL` desapareció para que nadie lo cambie de paso en un documento que va a sellarse.

## Gotchas

- **`yt-dlp` hay que mantenerlo actualizado.** El 2026-08-22 devolvía **HTTP 403** en todos los clientes de YouTube desde el propio PC del desarrollador: no era el bloqueo por IP de datacenter de [[por-que-plenos-en-local]], sino que la versión instalada (`2026.07.04`) había quedado desfasada. `pip install -U yt-dlp` lo arregla; conviene hacerlo antes de cada pleno.
- **No pedir a yt-dlp que convierta el audio.** Si el original ya es del formato pedido, copia el flujo e ignora el bitrate; los fragmentos salían a 25,3 MB y Groq devolvía **413**. La compresión la hace `trocear_audio` con ffmpeg. Trocear directamente el fichero descargado ahorra además una generación de pérdida (opus→aac, no opus→aac→aac). Con AssemblyAI nada de esto interviene: el fichero sube tal cual.
- **La API de AssemblyAI tiene tres trampas de forma.** `speech_models` es un **array** (`speech_model` singular está deprecado) y `universal-3-5-pro` **no es el modelo por defecto**; `min_speakers_expected`/`max_speakers_expected` van **dentro de `speaker_options`**, aunque varios ejemplos de la documentación los pongan al nivel superior, donde la API los ignora; y en `custom_spelling` el campo `to` admite **una sola palabra** y distingue mayúsculas. Hay tests con un `requests` falso que fijan el cuerpo de la petición para que esto no se rompa en silencio.
- **Sin webhooks: se sondea.** El webhook de AssemblyAI solo entrega `transcript_id` y `status` (habría que hacer el `GET` igual) y exige un endpoint público que responda 2xx en 10 s — imposible en un pipeline que corre a mano en un PC. Sondeo cada 20 s.
- **Whisper deforma los nombres propios** (y AssemblyAI también, menos). `plenos_informe.CORPORACION` lleva el listado de la corporación municipal para que el generador los escriba bien. **El auditor recibe ese mismo listado**: sin él marcaría las correcciones como afirmaciones no respaldadas y el bucle daría tres vueltas inútiles en cada ejecución. Actualizar tras cada elección municipal **y cada vez que cambie quién preside** (ver abajo). Los mismos nombres viajan además en `AAI_KEYTERMS` y `AAI_SPELLING`, que atacan la deformación **antes** de que llegue al LLM. Desde 2026-08-22 `CORPORACION` recoge también a **Elena, la secretaria** —su voz sale en la grabación, pero no es miembro de la Corporación, no vota y nunca va en `asistentes`/`ausentes`— y que a **Mª Rosario Cerdán Pérez la llaman "Chari"**; ambos datos salieron de escuchar la grabación real.
- **Una etiqueta de locutor es una voz, no una identidad.** El bloque `DIARIZACION` va a los tres roles y define cuándo puede propagarse una identificación a toda la sesión y cuándo no. Todo el razonamiento, y el riesgo que introduce, en [[diarizacion-como-andamiaje]].
- **Quién preside decide el tratamiento del acta.** A 2026-08-21, el Alcalde-Presidente Sergio de Fez Cerezuela está **de baja médica** y **Lorena Luján Chujfi ejerce la Alcaldía en funciones**; presidió ya el pleno del 7 de julio. Los prompts tratan a quien preside por su cargo y en su género — *"la Sra. Alcaldesa"*, nunca *"el Sr. Alcalde"* —, y `CORPORACION` recoge la situación. Ese dato sirve **solo para el tratamiento**: hay un guardarraíl explícito que prohíbe usarlo para rellenar el campo `presidente` o atribuir intervenciones, que siguen exigiendo que la grabación lo diga. Es también lo que hace correcto conservar el `LORENA LUJÁN CHUJFI` precargado en la celda "Presidida por" de la plantilla cuando `presidente` es `null`.
- **La convocatoria (`--convocatoria`) va a los tres roles, auditor incluido**, y manda en la forma mientras la grabación manda en el fondo. Es el mismo patrón que `CORPORACION`, y trae su propio riesgo (redactar como debatido un punto que solo estaba previsto). Todo el razonamiento en [[convocatoria-como-fuente]].
- **La convocatoria no se convierte a texto: el PDF entero va al modelo** como parte multimodal. Las del Ayuntamiento son escaneos —un JPEG sin capa de texto—, así que `pypdf` no saca nada y extraerlas exigiría OCR. Viaja en base64 con el plugin `file-parser` de OpenRouter en **engine `native`**: el engine por defecto es un OCR de pago que devolvería texto plano y perdería la maquetación.
- **El JSON Schema de pydantic no vale tal cual para el modo `strict` de OpenRouter**, que exige todas las propiedades en `required` y prohíbe `default`. `_esquema_estricto()` lo normaliza antes de enviarlo. No debilita [[via-de-escape-en-el-esquema]]: la vía de escape de los campos opcionales es admitir `null`, no faltar. Cinco tests lo fijan.
- **La fecha del CLI rellena `fecha_pleno` si el modelo no la oye**, pero nunca pisa una que sí conste en la grabación. No es una invención: `procesar_pleno` la conoce con certeza por `--fecha`, por el título del vídeo o por la entrada guardada.
- Los recuentos de votos que no constan van a `null` y **no se imprimen**. Llegó a publicarse *"Rechazado (1 a favor, 0 en contra, 0 abstenciones)"* — imposible y fabricado — porque el antiguo render en PDF convertía `null` en `0`, saltándose [[via-de-escape-en-el-esquema]]. El render actual (`plenos_acta.py`) hereda esa lección y tiene tests dedicados.
- Los timestamps se guardan en el JSON como rastro de verificación, pero **no se imprimen** en el acta: sirven para auditar contra la grabación, no para el lector.
- El acta se redacta **en presente de indicativo** con registro y fórmulas de acta municipal ("Toma la palabra...", "El Pleno ACUERDA...", "La Corporación se da por informada"), por ser el estilo real del Ayuntamiento (ver [[2026-08-21-acta-oficial-plenos-design]]).
- Usar `python -u`: al redirigir la salida a fichero, sin eso Python la almacena en búfer y parece colgado.
- **El acta generada es un borrador, no el documento oficial.** Se envía por email a la secretaria, que lo completa y lo sella; solo entonces `--publicar` lo lleva a `public/`. Nada del pipeline escribe ahí antes de eso.
- **El tipo de sesión decide la plantilla**, y si no consta en la grabación el acta no se genera: elegir a ciegas produciría un encabezado equivocado en un documento que se sella.
- **La transcripción se guarda ANTES de llamar al LLM**, no después. Es lo único del
  pipeline que cuesta dinero y no se puede repetir gratis; el bucle LLM, en cambio, se
  repite por céntimos con `--rehacer-informe`. Ver [[persistir-lo-caro-antes-de-lo-fragil]].
- **Si una ejecución muere igualmente, la transcripción se puede rescatar de AssemblyAI**
  con el `transcript_id` que el log imprime al empezar a sondear: un `GET` a
  `/v2/transcript/<id>` la devuelve intacta y gratis.
- **OpenRouter entrega los fallos del proveedor con HTTP 200 y el error dentro de
  `choices[0]`** (`finish_reason: "error"`, 504 *"Upstream idle timeout exceeded"* cuando
  el modelo se atasca razonando y Google deja de emitir). `_peticion` los reintenta como
  un 5xx; una respuesta sin contenido lanza un error legible con `finish_reason` y `usage`
  y vuelca la respuesta cruda a un fichero temporal para poder diagnosticarla.
- **El log no trunca**: los títulos del orden del día y las objeciones del auditor se
  imprimen enteros. Se cortaban a 80 y 90 caracteres para que cupieran en la terminal,
  pero ese rastro es lo que se lee para decidir si el bucle va bien.

## La transcripción como auditoría

El `.md` que se guarda junto al acta es **exactamente la misma cadena que recibe Gemini** (`transcribir()` → variable `transcripcion` → `bucle_informe()` y `write_text()`), no una versión resumida. Es por tanto la prueba de auditoría del acta: si una afirmación no aparece ahí, el modelo la inventó.

Tras `--publicar` se copia a `public/plenos/` —o sea, se despliega a Hostinger— pero **deliberadamente no se enlaza desde la web**: es apoyo de verificación, no contenido para el visitante. Decisión consciente del usuario, asumiendo que es accesible por URL directa, porque se trata de una sesión pública que ya está íntegra en YouTube.

La spec original preveía además publicar el **informe** en Markdown además de en PDF. No se implementó: `render_markdown()` llegó a escribirse pero nunca se llamó desde el pipeline, y se borró en 2026-08-08 por ser código muerto — antes, por tanto, de que el propio PDF de informe desapareciera del todo con el rediseño del acta oficial.

## Estado

Primera ejecución end-to-end real el 2026-08-08, con el pipeline de informe/PDF anterior al rediseño, sobre "PLENO EXTRAORDINARIO 7 DE JULIO 2026" (2h16m): transcripción correcta, auditor con visto bueno a la primera, PDF de 2 páginas.

El rediseño del acta oficial ([[2026-08-21-acta-oficial-plenos-design]]) se implementó y se validó de dos formas parciales el 2026-08-21: `python scripts/test_plenos.py` en verde, y una validación aislada del render (`plenos_acta.render_acta`) contra el patrón de estilo del acta del 11 de febrero, con un informe de prueba construido a mano — ver
`.superpowers/sdd/2026-08-21-acta-oficial-plenos/validacion-estilo.md`. Ese mismo día se le añadieron los cinco ajustes de [[2026-08-21-convocatoria-y-ajustes-acta]], el mayor de ellos la convocatoria oficial.

El 2026-08-22 se migró el bucle a OpenRouter con `gemini-2.5-pro` y se verificó contra la
API real con un smoke test: salida estructurada `strict` sobre el esquema `InformePleno`
(vías de escape respetadas, puntos bien clasificados) y lectura de un PDF escaneado por el
engine `native`, sin fallback de proveedor. Detalle en
[[2026-08-22-plenos-openrouter-gemini-pro]].

Ese mismo día se cambió la transcripción a AssemblyAI `universal-3-5-pro` con diarización
([[2026-08-22-plenos-assemblyai-diarizacion]]), verificada contra la API real sobre 20
minutos del pleno extraordinario `5UETzjDRRtw`: 8 etiquetas de locutor con reparto
coherente, nombres propios correctos, y un arranque de sesión que identifica a quien
preside y a otra concejala por su apodo. La rama del LLM **todavía no se ha ejecutado
sobre una transcripción diarizada**.

**La validación end-to-end real se hizo el 2026-08-22** ([[2026-08-22-primera-ejecucion-e2e-acta-oficial]]),
sobre el mismo pleno extraordinario del 7 de julio (`5UETzjDRRtw`, 2h16m) con su
convocatoria oficial. El pipeline **completa el recorrido y produce el acta**
(`2026-07-07-acta-extraordinaria.docx`, 7 puntos, tipo de sesión determinado), pero
hicieron falta tres ejecuciones: las dos primeras murieron por fallos de infraestructura
—no de contenido— que están arreglados y con tests (orden de escritura de la
transcripción, y los cortes del proveedor que llegan con HTTP 200).

El bucle terminó con **3 objeciones sin resolver**, las tres reales: un empate entre dos
propuestas que el esquema no sabe representar, un recuento parcial presentado como final y
una atribución cruzada entre los dos concejales apellidados Martínez. El detalle y lo que
implica cada una, en [[2026-08-22-primera-ejecucion-e2e-acta-oficial]].

Lo que **todavía no se ha hecho** es la lectura del `.docx` contra la grabación. Al
hacerla, lo primero que conviene comprobar —además de si algún punto convocado aparece
redactado con contenido que no se debatió— es si **Sergio de Fez Cerezuela asistió de
verdad**: el informe lo pone entre los asistentes y `CORPORACION` lo da de baja médica.

## Fallos conocidos, sin arreglar

Los detectó la revisión final de la rama del rediseño y siguen abiertos:

- **`--rehacer-informe` no puede recuperar de `tipo_sesion="no consta"`.** Si el modelo no determina el tipo de sesión, el acta no se genera y el mensaje de consola invita a corregir el `informe.json` — pero **nada vuelve a leer ese fichero**, y repetir el comando llama otra vez al modelo a temperatura 0 sobre la misma transcripción, así que devuelve lo mismo. La única salida documentada para el caso límite es un bucle que no puede terminar. Arreglo previsto (~6 líneas): un `--rehacer-acta <fecha>` que valide el JSON del borrador y llame directamente a `render_acta`. Pasar `--convocatoria` lo evita en la práctica, porque el tipo de sesión sale de ahí.
- **La regla de recuentos vive solo en el corrector, y admite recuentos parciales.**
  `PROMPT_CORRECTOR` prohíbe desde el 2026-08-22 cambiar una cifra objetada por otra,
  deducir votos restando de los asistentes y rellenar con `0`. Pero el `0` de relleno del
  punto 1 lo escribió el **generador**, que no tiene esa regla; y la propia regla permite
  todavía poner número "solo en lo que se oye", que es como se coló un recuento de 3 votos
  sobre 6 asistentes presentado como resultado final. Arreglo previsto: llevar la regla
  también a `PROMPT_GENERADOR` y endurecerla a "recuento incompleto → todos los campos a
  `null`".
- **`Votacion` no modela una votación entre alternativas.** Un empate entre dos propuestas
  (mensual vs. cada 40 días) no cabe en `a_favor`/`en_contra`/`abstenciones`, y el modelo
  lo dobla hasta que entra. Mientras el esquema no lo contemple, lo correcto es recuentos a
  `null` y el detalle en `texto` — y eso hay que decírselo en el prompt, porque el modelo
  por su cuenta prefiere rellenar. Ver [[via-de-escape-en-el-esquema]].
- **El informe corregido vive solo en memoria durante el bucle.** Si la última auditoría
  agota los reintentos, se pierden las vueltas de corrector ya pagadas (~0,3 $ y un cuarto
  de hora). Con el reintento de los cortes del proveedor el caso quedó raro, así que se
  dejó abierto a sabiendas.
- **Los formatos de hora y fecha del modelo se parsean sin red.** `hora_inicio`, `hora_fin` y `fecha_pleno` son `str | None` sin patrón: un `"15:54:00"` o un `"11/02/2026"` revientan `render_acta` con un `ValueError` que sube hasta `procesar_pleno`, en un punto donde la transcripción y el JSON **ya están escritos** pero sus rutas y los pendientes del auditor no llegan a imprimirse nunca. El esquema tiene vía de escape para la *ausencia* del dato, no para su *forma*.

## Pendiente para pasar a producción

De los cinco asuntos abiertos a 2026-08-08, el punto 4 quedó resuelto por el propio
rediseño del acta oficial; los otros cuatro siguen abiertos:

1. **Claves de API del Ayuntamiento.** Las pruebas se han hecho con las claves personales del desarrollador. En producción hay que sustituirlas por claves generadas en cuentas del Ayuntamiento, con su tarjeta vinculada. Desde el 2026-08-22 el pipeline gasta saldo real **dos veces** en cada ejecución —OpenRouter por el bucle LLM (0,15–0,80 €) y AssemblyAI por la transcripción (~$0,48)—, y es saldo personal del desarrollador: es el argumento más fuerte para hacer este cambio pronto. Total estimado por pleno: **0,6–1,3 €**. Matiz de urgencia: la parte de AssemblyAI sale del crédito inicial de $50, que a pleno mensual dura años; la de OpenRouter es saldo recargable que se agota de verdad.
2. ~~**Migrar a `gemini-2.5-pro`.**~~ **Resuelto** el 2026-08-22 por [[2026-08-22-plenos-openrouter-gemini-pro]], por la vía de OpenRouter en vez de la facturación con Google. El motivo técnico se mantiene: `pro` sigue mejor las reglas estrictas de los prompts (no inferir, vías de escape, atribución solo si es explícita) y su auditor detecta mejor las afirmaciones no respaldadas — relevante en un documento público sobre votaciones. El pleno real del 2026-08-22 dio la primera evidencia a favor: el auditor cazó una atribución falsa (una intervención dada al público siendo de un concejal), un recuento parcial presentado como completo y un empate mal modelado, y sostuvo las tres objeciones frente a un corrector que insistía en rellenar. No hay comparación directa con `flash` sobre el mismo pleno.
3. **Visto bueno de la secretaria** sobre el acta generada. De su revisión pueden salir ajustes de los prompts (tono, extensión, qué se recoge de cada punto). Iterar es barato: `--rehacer-informe` reutiliza la transcripción y no vuelve a pagarla.
4. ~~Averiguar qué usa el PC de secretaría (Drive, OneDrive u otro) para dejar allí una carpeta con los informes generados.~~ **Resuelto** por [[2026-08-21-acta-oficial-plenos-design]]: no hace falta averiguar nada de ese equipo — el borrador se envía por **email** a la secretaria y ella devuelve el PDF sellado, sin depender de ninguna nube compartida. La vía de automatizar el pipeline vía carpeta compartida (que este punto dejaba abierta, ver [[por-que-plenos-en-local]]) queda descartada junto con él.
5. **Los audios de plenos que debe entregar el funcionario.** La spec original contaba con dos grabaciones de ~4h que nunca llegaron. Son el único material que ejercitaría el modo `--audio`, hoy implementado pero **probado solo con audio sintético**: sin vídeo de YouTube de por medio, hay que pasar `--fecha` y `--titulo` a mano. Conviene estar atento la primera vez que se use con material real, sobre todo si el audio viene en un formato o calidad distintos de los que sirve YouTube.

## Cómo lo ve el visitante de la web

La sección de [[hostinger-deploy]] que lista los plenos vive en
`src/components/pages/AyuntamientoPage.jsx` y lee `public/data/plenos.json`. Hasta
2026-08-21 se titulaba *"Informes de los plenos"* y advertía: *"Resumen automático de cada
sesión a partir de la grabación. El documento oficial es el acta aprobada por el Pleno."*

Esa nota quedó **falsa y peligrosa** con el rediseño: el fichero detrás del enlace pasó a
ser el acta sellada por la Secretaría, y el texto le decía al vecino que un documento con
validez legal era un resumen automático no oficial. Ni la spec ni el plan miraron el
frontend — ambos hablaban solo de `scripts/` —, así que lo detectó la revisión final de la
rama, no el diseño.

Ahora dice *"Actas de los plenos"*, el botón es *"Acta PDF ↓"* y la nota describe el acta
como *"revisada, completada y sellada por la Secretaría-Intervención del Ayuntamiento"*.
**Deliberadamente no dice "aprobada por el Pleno"**: la aprobación del acta es el primer
punto de la sesión siguiente, y lo que se publica es la sellada, no necesariamente ya
aprobada. Si en el futuro se decide publicar solo actas aprobadas, ese texto puede
afinarse.

## Relacionado

[[2026-08-22-primera-ejecucion-e2e-acta-oficial]], [[2026-08-22-plenos-assemblyai-diarizacion]], [[2026-08-22-plenos-openrouter-gemini-pro]], [[persistir-lo-caro-antes-de-lo-fragil]], [[2026-08-21-acta-oficial-plenos-design]], [[2026-08-21-convocatoria-y-ajustes-acta]], [[2026-07-31-plenos-youtube-pipeline-design]], [[diarizacion-como-andamiaje]], [[convocatoria-como-fuente]], [[por-que-plenos-en-local]], [[bucle-generador-auditor-corrector]], [[via-de-escape-en-el-esquema]], [[fallback-modelos-ia]], [[hostinger-deploy]], [[github-actions]]
