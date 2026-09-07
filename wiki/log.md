# Log de operaciones

Registro append-only. Una entrada por cada `ingest`/`query`/`lint` ejecutado sobre la wiki. Formato: `## [YYYY-MM-DD] operación | Título`.

## [2026-07-06] scaffold | Creación de la estructura inicial wiki/ + raw/

## [2026-07-06] ingest | Bot Telegram → OpenRouter → GitHub Pages: estado del sistema y errores resueltos
## [2026-07-06] ingest | Debug: Bot Telegram → Gemini no responde como se espera
## [2026-07-06] ingest | Agenda Automática — Plan de Implementación
## [2026-07-06] ingest | Bot Telegram + Cloudflare Worker: Plan de Implementación
## [2026-07-06] ingest | Bandos / desc_short / NewsModal / Gemma4 — Implementation Plan
## [2026-07-06] ingest | LLM Wiki (patrón Karpathy) con Obsidian — Implementation Plan
## [2026-07-06] ingest | Bot Telegram + Cloudflare Worker + GitHub Actions: diseño del flujo de publicación de eventos
## [2026-07-06] ingest | Spec: Bandos originales, desc_short, modal en News y fix Gemma 4
## [2026-07-06] ingest | Spec: LLM Wiki (patrón Karpathy) con Obsidian

## [2026-07-06] lint | 0 hallazgos

## [2026-07-29] query | Qué se hizo con Cloudflare, por qué y cómo funciona

## [2026-07-30] ingest | Actualización clasificacion-ia, fallback-modelos-ia, limpieza-artefactos-tokenizacion desde código actual (commit fb75788: fallback Nemotron)
## [2026-07-30] query | Dónde se ejecuta procesar_telegram.py (Cloudflare/GitHub/Hostinger)
## [2026-07-30] ingest | Renombrado github-pages-deploy → hostinger-deploy; actualizado github-actions, sistema-agenda-automatica, eventos-json, gate-deploy-condicional, fuente-unica-eventos-json, overview, index para reflejar migración de hosting a Hostinger (confirmada 2026-07-22, ver memoria project_hosting)
## [2026-07-30] ingest | Nuevo concepto por-que-cloudflare-worker: Actions no puede recibir webhooks, de ahí el Worker como endpoint HTTPS intermedio
## [2026-07-30] query | Verificación del flujo end-to-end contra el mental model del usuario: la imagen no viaja por Cloudflare (solo file_id), y el orden es main→deploy→Hostinger, no al revés

## [2026-08-07] ingest | Nuevo concepto latencia-workflow-run: diagnóstico del incidente 2026-08-06 (evento confirmado no aparecía en producción durante ~27 min por retraso de entrega del trigger workflow_run, no por caché ni fallo del bot) y solución propuesta (workflow_dispatch directo por API en vez de esperar el evento workflow_run)
## [2026-08-08] ingest | Pipeline de informes de plenos: spec de diseño + implementación real. Divergencia mayor documentada: la spec definía publicación automática con cron y feed RSS, pero toda esa capa se construyó, se probó y se eliminó (YouTube bloquea yt-dlp desde IPs de datacenter); el pipeline se ejecuta a mano en local. Nuevas páginas: pipeline-plenos, por-que-plenos-en-local, via-de-escape-en-el-esquema, bucle-generador-auditor-corrector

## [2026-08-08] ingest | Cierre del pipeline de plenos: borrado de render_markdown (código muerto, nunca se llamaba) y del CSS no-op; tests de render reescritos contra el PDF real; documentada la transcripción como prueba de auditoría (misma cadena que lee Gemini, publicada pero no enlazada); registrados los 5 pendientes para producción (claves del Ayuntamiento, migración a gemini-2.5-pro, visto bueno del funcionario, nube del PC de secretaría, audios que debe entregar el funcionario para probar el modo --audio)

## [2026-08-21] ingest | Acta oficial de plenos: rellenar la plantilla del Ayuntamiento
## [2026-08-21] ingest | Corrección tras revisión: wiki/overview.md y bucle-generador-auditor-corrector.md seguían describiendo el pipeline de plenos anterior al acta oficial (informe en PDF, sin flujo en dos pasos ni --publicar)

## [2026-08-21] query | Qué modelo de Gemini se usa para el informe de plenos y desde qué plataforma se consume

## [2026-08-21] ingest | Convocatoria oficial y ajustes posteriores al rediseño del acta: `--convocatoria` (PDF escaneado entero a Gemini, a los tres roles, forma vs fondo), Lorena Luján preside en funciones, fecha del CLI rellena el hueco, la web pasa de "Informes" a "Actas", el bucle narra su progreso. Nueva fuente sin spec ni plan; nuevo concepto convocatoria-como-fuente
## [2026-08-21] lint | 3 wikilinks rotos a `github-pages-deploy` en sources/, secuela del renombrado a [[hostinger-deploy]] del 2026-07-30 que no actualizó los backlinks. Corregidos

## [2026-08-22] ingest | Plenos: del SDK de Gemini a OpenRouter con `gemini-2.5-pro`. Cambio acotado al bucle LLM de plenos (el bot de agenda no se toca): `requests` contra OpenRouter, modelo fijo en código (`GEMINI_MODEL` desaparece), `response_format` `json_schema` en modo strict con normalización del esquema pydantic, PDF de la convocatoria por el plugin file-parser en engine `native` (el default es OCR de pago). Verificado con smoke test contra la API real: salida estructurada con vías de escape respetadas, escaneo sin capa de texto leído, sin fallback de proveedor. Resuelve el pendiente 2 de producción; primer sitio del proyecto donde se paga por token. Nueva fuente sin spec ni plan

## [2026-08-22] ingest | Plenos: de Groq Whisper a AssemblyAI `universal-3-5-pro` con diarización. Segunda intervención del día sobre el pipeline (la primera fue el bucle LLM a OpenRouter); esta toca la transcripción. AssemblyAI pasa a principal y **Groq se conserva como respaldo a petición del usuario**: `transcribir()` elige por presencia de `ASSEMBLYAI_API_KEY`. Desaparece el troceado con ffmpeg en la rama principal (tope 5 GB / 10 h por petición). La transcripción sale como `[HH:MM:SS] Interviniente A: texto`, y un bloque `DIARIZACION` nuevo va a los tres roles del bucle explicando que la etiqueta es una voz y no una identidad. `CORPORACION` gana a Elena (secretaria) y el apodo "Chari". Webhooks descartados (payload sin contenido y hace falta endpoint público): se sondea cada 20 s. Verificado contra la API real sobre 20 min del pleno `5UETzjDRRtw`: 8 etiquetas coherentes, nombres propios correctos, ~$0,09 de coste. De paso se descubrió que `yt-dlp` estaba obsoleto y YouTube devolvía 403 desde la IP residencial — no era el bloqueo por IP de datacenter. Nueva fuente sin spec ni plan; nuevo concepto diarizacion-como-andamiaje

## [2026-08-22] ingest | Primera ejecución end-to-end del acta oficial

Tercera intervención del día sobre el pipeline de plenos, y la que faltaba desde el rediseño: un pleno entero (`5UETzjDRRtw`, 7 de julio, 2h16m) con su convocatoria, de audio a `.docx`. **El pipeline llega al final y produce el acta**, pero hicieron falta tres ejecuciones. Las dos primeras murieron en el auditor por dos fallos de infraestructura distintos: la transcripción se escribía DESPUÉS del bucle LLM (una excepción tiraba los 0,48 $ de AssemblyAI; rescatada por `transcript_id`, que el log imprimía) y OpenRouter entrega los cortes del proveedor con HTTP 200 y el error dentro de `choices[0]` —504 *"Upstream idle timeout exceeded"* tras atascarse el modelo repitiendo el mismo razonamiento once veces—, que `_peticion` no reintentaba. Ambos arreglados con 15 tests nuevos. El bucle terminó con 3 objeciones sin resolver, las tres reales: un empate entre dos propuestas que `Votacion` no sabe representar, un recuento parcial (3 votos de 6 asistentes) presentado como final, y una atribución cruzada entre los dos concejales apellidados Martínez. Se añadió a `PROMPT_CORRECTOR` la regla de que un recuento objetado va a `null` y no a otra cifra, y quedó demostrado que está incompleta: el generador no la tiene y el parcial sigue permitido. Nuevo concepto persistir-lo-caro-antes-de-lo-fragil. Pendiente: leer el `.docx` contra la grabación, empezando por si Sergio de Fez asistió estando de baja.

## [2026-08-23] ingest | Reglas de recuento y decisiones sobre el acta

Continuación de la ejecución e2e: se leen el `.docx` generado, la transcripción en crudo y el **acta oficial del 11 de febrero** (documento de la secretaria, ingerido como fuente propia) para decidir qué de las tres objeciones pendientes era error del modelo, del esquema o del auditor. Resultado: una era **falso positivo del auditor** (atribución correcta, índice equivocado), otra era fallo de forma con el fondo correcto —el empate del punto 1 **sí se resolvió** por voto de calidad y la periodicidad quedó en 40 días, 00:17:19— y la tercera un recuento parcial que hacía que el acta se contradijera a sí misma. De seis cambios propuestos se aplicaron tres: bloque `RECUENTOS` compartido por generador y corrector (recuento incompleto → todo a `null`, `resultado` se conserva, abstención verbalizada sí cuenta, nunca `0` de relleno) y aviso de que hay dos concejales apellidados Martínez. El usuario descartó los otros tres, incluido estructurar las votaciones entre alternativas: el acta oficial demuestra que la secretaria las narra en prosa y no tabula nada. El cambio destapó una ambigüedad vieja del esquema —dos vías de escape para "no hubo votación"— que hizo escribir al modelo la cadena `"sin votación"` donde va el objeto; arreglado con prompt + `field_validator` estrecho. Confirmado que Sergio de Fez asistió pese a la baja. Se vio en vivo el reintento del 504 y se documentó que la petición cortada llega con `cost: 0` para el usuario. 17 tests nuevos. Nuevas fuentes: 2026-08-23-reglas-de-recuento-y-decisiones-de-acta y acta-oficial-11-febrero-2026.

## [2026-08-29] update | Forma del acta: negrita, sangría, alineación y comillas

Lectura del `.docx` del pleno del **19 de mayo** contra el acta oficial de febrero para corregir la forma. Se confirmaron cuatro defectos de formato con evidencia de estilo: ningún run en negrita en los 37 párrafos del orden del día, el primer punto centrado (`align=CENTER`, heredado del párrafo de ejemplo de la plantilla al reutilizarlo como modelo en `_poner_parrafos`), `first_line_indent=None` en todo el documento y ausencia de encabezado para RUEGOS Y PREGUNTAS. La extracción de fuentes del acta real zanjó cómo escribir el encabezado —`LiberationSerif-Bold` sobre `2º) TÍTULO.-` **dentro** del primer párrafo del punto, no como línea aparte— y fijó el criterio de comillas: **tipográficas dobles `“ ”`**, como en `“LOSILLA, MATALLANA Y OTROS”`. Los cuatro se arreglaron en `plenos_acta.py`; la unificación de comillas es determinista (`comillas()` sobre `_escribir`), no una petición al modelo. Para los defectos de TEXTO —duplicidad de la fórmula de acuerdo y redundancia— el usuario eligió **la vía de solo-prompts frente a un agente revisor final**: ver [[revisor-final-descartado]]. 16 tests nuevos.

## [2026-08-29] update | El bucle detecta el ping-pong del auditor

Primera ejecución completa con los prompts nuevos (pleno del 19 de mayo): 8 llamadas, 22 minutos, 3 vueltas agotadas y **1 objeción sin resolver que era el auditor objetando su propia corrección** — pidió `rechazado` en la auditoría 1 y `aprobado` en la 4 sobre la misma votación, y el acta se quedó afirmando un resultado que la grabación no declara. Diagnóstico: el auditor **muestrea, no verifica**, así que la condición de salida ("una auditoría completa devuelve lista vacía") es inalcanzable sobre 148.665 caracteres. Se descartó rediseñarlo a una sola auditoría canónica: de las tres correcciones reales de contenido de esa ejecución, **dos nacieron en las auditorías 2 y 3**, que ese diseño elimina. Implementada la etapa 1: historial por campo (`_aplanar`), detección de oscilación A→B→A, escape para las disputas que siguen abiertas al agotar las vueltas (`_AMBIGUOS`: `votacion.resultado` → `"no consta"`, reimpuesto en cada vuelta), salida temprana si una corrección no cambia nada, y log por vuelta. Un test cazó un bug de la primera versión: A→A se contaba como oscilación. La etapa 2 (corrector de parches con `json_path`) queda sin hacer por el modo `strict` de OpenRouter. De paso, el cierre de `procesar_pleno` sale ahora como SUCCESS / WARNING / ERROR con color solo si hay terminal. 16 tests nuevos. Detalle en [[bucle-generador-auditor-corrector]].

## [2026-09-04] ingest | Asistente de actas para la funcionaria

Nuevo `scripts/asistente_plenos.py`: envuelve el pipeline de plenos en un menú guiado
para que la funcionaria del Ayuntamiento genere el borrador del acta sin terminal ni
jerga técnica, sin duplicar la lógica del pipeline (`procesar_pleno`, `plenos_informe`,
`plenos_acta` no se tocan). Se empaqueta con PyInstaller `--onefile`
(`scripts/construir_exe.ps1`); las claves de API viven en
`Configuración (no tocar)/configuracion.env` en vez de en variables de entorno del
sistema, para poder cambiarlas a las cuentas del Ayuntamiento con el Bloc de notas sin
reconstruir el ejecutable; `yt-dlp.exe` viaja aparte del `.exe` y se autoactualiza
porque YouTube lo rompe cada pocos meses y en ese PC no habrá quien lo arregle; el
registro (`Configuración (no tocar)/registros/`) se queda con toda la salida del
pipeline sin filtrar, mientras que la pantalla solo muestra una traducción amable de
una decena de marcadores conocidos. La funcionaria genera el borrador pero no publica:
el asistente no toca `public/` ni git, y `--publicar` sigue siendo del desarrollador.
La fecha del pleno la escribe ella a mano, con la fecha deducida del título de YouTube
solo como sugerencia confirmable, porque un error ahí acabaría en el nombre de la
carpeta y en el encabezado de un documento que se sella. De paso queda resuelto en la
práctica el fallo conocido de `--rehacer-informe` con `tipo_sesion="no consta"`: al
rehacer, si el borrador no tiene guardada la convocatoria, el asistente la pide antes,
que es lo único que aporta el dato que faltaba. Nueva página
`wiki/concepts/asistente-para-la-funcionaria.md`; actualizada `wiki/entities/pipeline-plenos.md`
(tabla de ficheros, sección nueva, fallo marcado como resuelto en la práctica).

## [2026-09-07] query | La diarización fundió dos personas en una etiqueta

## [2026-09-07] ingest | La guía de verificación y las lecciones de la primera ejecución real


## [2026-09-07] query | Por qué la guía no se regeneró en el pleno del 3 de septiembre

Diagnóstico de una corrida real (13:36→14:26, exe del 09:50): el acta y el `informe.json`
salieron bien, pero la guía HTML se quedó en la versión de las 01:30 y el
`COMPROBAR ANTES DE SELLAR.txt` volvió a citar rutas internas (`orden_del_dia[0]`) sin
frase que buscar ni minuto que oír. Causa única en el log:
`PermissionError` al reescribir la guía —la del pase anterior estaba abierta— dentro del
try/except **compartido** de `_componer_guia`, que se llevó por delante también el `.txt`;
el asistente lo reescribió luego por su cuenta con `objeciones=()`, cayendo al camino
degradado de `_avisos_legibles`. Arreglado con un try por fichero (el `.txt` primero,
porque no depende de la guía) y un nombre alternativo con la hora cuando el HTML está
bloqueado. De paso, `_ruta_legible` traduce ya `identificacion_locutores[n]` →
`Mapa de voces — etiqueta D`, que era la única de las tres objeciones que seguía saliendo
cruda. Actualizada `wiki/concepts/guia-de-verificacion.md`.

## [2026-09-07] query | Por qué el auditor objetó una votación que el acta había resuelto bien

Análisis forense del punto 1º del pleno del 3 de septiembre (dos subagentes: transcripción
y bucle LLM). La grabación **nunca declara el resultado** —"rechaz*" tiene cero apariciones
en las 1.314 líneas; a las 00:16:25 solo se canta "3 a favor, 2 abstenciones y 2 en contra"
y se pasa al punto siguiente—, así que el auditor tuvo que deducir si eso aprueba o
rechaza, y osciló entre mayoría simple de emitidos y mayoría absoluta sobre los 7
concejales. Ningún prompt fija esa regla: la palabra "mayoría" aparece una sola vez en
`plenos_informe.py` y es una regex que la borra (`:108`).

El bucle detectó la oscilación y congeló `votacion.resultado` a `"no consta"`, pero la
detección compara valores exactos y `acuerdo` es texto libre, así que su oscilación de
sentido es invisible: el corrector lo dejó en "Aprobar". `plenos_acta.py:170` compone
entonces `ACUERDA, {acuerdo}` **descartando el recuento** — el escape produjo un acta más
afirmativa que cualquiera de los dos bandos, contradiciendo al párrafo anterior, que dice
que el concejal votó en contra.

Cuatro causas encadenadas, no una: (1) el resultado no se proclama en el audio; (2) ningún
prompt dice qué mayoría rige; (3) el escape congela una hoja de un grupo acoplado sin
tocar `acuerdo`, que es el campo que el documento imprime; (4) el punto tuvo DOS votaciones
(19 de mayo por asentimiento, 7 de julio con recuento) y `PuntoOrdenDia.votacion` es una
sola (`:94`) — el auditor ya lo objetó en la corrida del 6-S y era irresoluble por
construcción, y el escape acabó neutralizando también la votación unánime que nadie
discutía.

Defecto distinto encontrado de paso: `plenos_acta.py:222` hace `informe.presidente or
HUECO`, y el literal de escape `"no identificado en la grabación"` es truthy, así que el
acta cierra con *"…cumpliendo con el objeto del acto, no identificado en la grabación
levanta la sesión…"*. No está entre las objeciones que se le avisan a la funcionaria.

**Corregido al cerrar el análisis:** esta entrada se escribió dando por buena la última
objeción del auditor, que resultó ser la equivocada. El usuario, presente en la sesión, lo
zanjó: 3 a favor, 2 en contra y 2 abstenciones **aprueba** por mayoría simple (art. 47.1
LRBRL), el acuerdo del acta era correcto y "el documento lo ha hecho bien". El fallo del
pipeline es, por tanto, el inverso del que parecía: no equivocar el acuerdo, sino producir
una **objeción falsa contra un acta correcta** y enseñársela a la funcionaria con enlace al
minuto — y de paso perder el recuento, que `plenos_acta.py:170` descarta cuando el resultado
queda en "no consta".

Sin cambios de código: el usuario decidió no tocar nada de esto. Los cuatro arreglos posibles
(regla de mayoría en el auditor, render sin cautela, validador de coherencia acuerdo/resultado
y varias votaciones por punto) quedan listados en `wiki/entities/pipeline-plenos.md`.

## [2026-09-07] ingest | Sesión del 2026-09-07: guía, forense de la votación y literal de escape

Nueva página `wiki/sources/2026-09-07-guia-forense-y-literal-de-escape.md` con la sesión
entera. Dos arreglos aplicados y tres problemas diagnosticados sin tocar.

**Arreglado — la guía no se regeneraba:** un `PermissionError` al reescribir el HTML
bloqueado se llevaba por delante el `COMPROBAR ANTES DE SELLAR.txt`, porque `_componer_guia`
los envolvía en el mismo try. Un try por fichero, el `.txt` primero, nombre alternativo con la
hora si el HTML está bloqueado, y `_ruta_legible` traduciendo `identificacion_locutores[n]`.

**Arreglado — el literal de escape colado como nombre propio:** el modelo escribió
`"no identificado en la grabación"` en `presidente`, que pide `null`, y como es una cadena no
vacía `informe.presidente or HUECO` la tomó por un nombre: el acta cerró con "…cumpliendo con
el objeto del acto, no identificado en la grabación levanta la sesión…". Arreglado con un
`field_validator` (`_presidente_o_nada`) y cambiando el cierre a `or PRESIDENCIA["tratamiento"]`
— el acta ya afirma "la Presidenta abre la sesión" desde ahí, así que el cierre no tiene por
qué ser más tímido que la apertura. Se revirtió un intento de vaciar la celda "Presidida por",
que la spec deja a propósito con el valor de la plantilla y cuyo nombre es el correcto.

Actualizadas `wiki/concepts/via-de-escape-en-el-esquema.md` (sección nueva: dos gramáticas
para decir "no consta" y el modelo las intercambia), `wiki/concepts/bucle-generador-auditor-corrector.md`
(sección nueva: cuando lo que oscila es una regla de derecho y no un dato),
`wiki/entities/pipeline-plenos.md` (fallo conocido nuevo con los cuatro arreglos pendientes y
su acoplamiento) y `wiki/index.md`.
