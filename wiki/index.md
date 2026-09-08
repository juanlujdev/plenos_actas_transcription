# Índice de la wiki

Catálogo de la documentación viva del proyecto (patrón LLM Wiki de Karpathy). Ver
`CLAUDE.md` sección "LLM Wiki" para las convenciones.

## Fuentes

| Página | Fuente original | Actualizado |
|--------|------------------|-------------|
| [[2026-07-31-plenos-youtube-pipeline-design]] | `docs/superpowers/specs/2026-07-31-plenos-youtube-pipeline-design.md` ⚠️ parcialmente superada | 2026-08-08 |
| [[2026-08-21-acta-oficial-plenos-design]] | `docs/superpowers/specs/2026-08-21-acta-oficial-plenos-design.md` | 2026-08-21 |
| [[2026-08-21-convocatoria-y-ajustes-acta]] | conversación de trabajo del 2026-08-21 (sin spec ni plan) | 2026-08-21 |
| [[2026-08-22-plenos-openrouter-gemini-pro]] | conversación de trabajo del 2026-08-22 (sin spec ni plan) | 2026-08-22 |
| [[2026-08-22-plenos-assemblyai-diarizacion]] | conversación de trabajo del 2026-08-22 (sin spec ni plan) | 2026-08-22 |
| [[2026-08-22-primera-ejecucion-e2e-acta-oficial]] | conversación de trabajo del 2026-08-22 (sin spec ni plan) | 2026-08-22 |
| [[2026-08-23-reglas-de-recuento-y-decisiones-de-acta]] | conversación de trabajo del 2026-08-23 (sin spec ni plan) | 2026-08-23 |
| [[acta-oficial-11-febrero-2026]] | acta borrador del Ayuntamiento en PDF (documento oficial) | 2026-08-23 |
| [[2026-09-07-guia-forense-y-literal-de-escape]] | conversación de trabajo del 2026-09-07 (sin spec ni plan) | 2026-09-07 |

## Entidades

| Página | Descripción | Actualizado |
|--------|-------------|-------------|
| [[pipeline-plenos]] | Acta oficial de plenos desde la grabación (AssemblyAI diarizado + `gemini-2.5-pro` vía OpenRouter + plantilla Word), ejecución manual en local; validado end-to-end el 2026-08-22 | 2026-09-08 |

## Conceptos

| Página | Descripción | Actualizado |
|--------|-------------|-------------|
| [[bucle-generador-auditor-corrector]] | Los tres roles LLM y el `while` determinista que verifica el acta; qué pasa cuando lo que oscila es una regla de derecho y no un dato | 2026-09-07 |
| [[via-de-escape-en-el-esquema]] | Diseño anti-alucinación: el esquema nunca debe forzar al modelo a inventar — ni ofrecerle dos vías de escape para lo mismo, ni dos gramáticas para decir "no consta" | 2026-09-07 |
| [[diarizacion-como-andamiaje]] | La etiqueta de locutor es una voz, no una identidad: cuándo puede propagarse, qué riesgo trae y el día que ese riesgo ocurrió | 2026-09-07 |
| [[convocatoria-como-fuente]] | El orden del día oficial como segunda fuente: manda en la forma, la grabación manda en el fondo | 2026-08-22 |
| [[guia-de-verificacion]] | Por qué el acta lleva una guía HTML con los minutos del vídeo, y por qué no es un segundo .docx | 2026-09-07 |
| [[persistir-lo-caro-antes-de-lo-fragil]] | Lo que cuesta dinero se escribe en disco antes de llamar a lo que puede fallar | 2026-08-22 |
| [[fallback-modelos-ia]] | Por qué el modelo que redacta el acta no tiene respaldo y la transcripción sí | 2026-09-08 |
| [[por-que-plenos-en-local]] | Por qué se construyó y luego se borró toda la automatización del pipeline | 2026-08-22 |
| [[revisor-final-descartado]] | Por qué la revisión de forma del acta se hizo con prompts y código, y no con un cuarto agente | 2026-08-29 |
| [[asistente-para-la-funcionaria]] | Por qué el asistente para la funcionaria se empaqueta con PyInstaller, con claves en fichero de texto, yt-dlp autoactualizable y sin capacidad de publicar | 2026-09-07 |

## Síntesis

Ninguna. Las que había (`cloudflare-worker-que-por-que-como`, `donde-se-ejecuta-el-bot`,
`flujo-completo-corregido`) eran del bot de agenda y se quedaron en `enguidanos_web`.

## Pendientes de ingerir

Ninguna.
