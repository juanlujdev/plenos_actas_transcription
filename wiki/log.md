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
