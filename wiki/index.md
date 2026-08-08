# Índice de la wiki

Catálogo de la documentación viva del proyecto (patrón LLM Wiki de Karpathy). Ver `CLAUDE.md` sección "LLM Wiki" para las convenciones.

## Fuentes

| Página | Fuente original | Actualizado |
|--------|------------------|-------------|
| [[bot-telegram-openrouter-deploy]] | `docs/superpowers/bot-telegram-openrouter-deploy.md` | 2026-07-06 |
| [[debug-telegram-gemini-429]] | `docs/superpowers/debug-telegram-gemini-429.md` | 2026-07-06 |
| [[2026-06-26-agenda-automatica]] | `docs/superpowers/plans/2026-06-26-agenda-automatica.md` | 2026-07-06 |
| [[2026-06-28-bot-telegram-cloudflare-webhook]] | `docs/superpowers/plans/2026-06-28-bot-telegram-cloudflare-webhook.md` | 2026-07-06 |
| [[2026-07-01-bandos-desc-short-news-modal]] | `docs/superpowers/plans/2026-07-01-bandos-desc-short-news-modal.md` | 2026-07-06 |
| [[2026-07-06-llm-wiki-obsidian]] | `docs/superpowers/plans/2026-07-06-llm-wiki-obsidian.md` | 2026-07-06 |
| [[2026-06-28-bot-telegram-cloudflare-webhook-design]] | `docs/superpowers/specs/2026-06-28-bot-telegram-cloudflare-webhook-design.md` | 2026-07-06 |
| [[2026-07-01-bandos-desc-short-news-modal-design]] | `docs/superpowers/specs/2026-07-01-bandos-desc-short-news-modal-design.md` | 2026-07-06 |
| [[2026-07-06-llm-wiki-obsidian-design]] | `docs/superpowers/specs/2026-07-06-llm-wiki-obsidian-design.md` | 2026-07-06 |
| [[2026-07-31-plenos-youtube-pipeline-design]] | `docs/superpowers/specs/2026-07-31-plenos-youtube-pipeline-design.md` ⚠️ parcialmente superada | 2026-08-08 |

## Entidades

| Página | Descripción | Actualizado |
|--------|-------------|-------------|
| [[telegram-bot]] | Bot de Telegram (`scripts/procesar_telegram.py`) que clasifica y publica eventos — se ejecuta en GitHub Actions | 2026-07-06 |
| [[cloudflare-worker]] | Worker que recibe el webhook de Telegram y dispara GitHub Actions | 2026-07-30 |
| [[github-actions]] | Workflows de scan/confirm/deploy/diagnóstico | 2026-07-30 |
| [[hostinger-deploy]] | Build Vite + deploy a Hostinger por FTP con gate condicional (antes GitHub Pages) | 2026-07-30 |
| [[clasificacion-ia]] | Clasificación de publicaciones con Gemini/OpenRouter (Gemma + fallback Nemotron) | 2026-07-30 |
| [[eventos-json]] | `public/data/eventos.json`, fuente única de verdad del contenido dinámico | 2026-07-30 |
| [[sistema-agenda-automatica]] | El sistema completo de publicación automática de eventos/bandos | 2026-07-30 |
| [[pipeline-plenos]] | Informes de plenos desde la grabación (Groq + Gemini), ejecución manual en local | 2026-08-08 |

## Conceptos

| Página | Descripción | Actualizado |
|--------|-------------|-------------|
| [[confirmacion-si-no]] | Por qué la confirmación manual SI/NO en dos ejecuciones asíncronas | 2026-07-06 |
| [[gate-deploy-condicional]] | Por qué el gate y el trigger `workflow_run` en el deploy | 2026-07-30 |
| [[fallback-modelos-ia]] | Historial de elección/migración de modelos de IA, manejo de 429 y fallback Gemma→Nemotron | 2026-07-30 |
| [[limpieza-artefactos-tokenizacion]] | Limpieza de `<pad>`/`톱` (Gemma 4) y bloques `<think>` (Nemotron) | 2026-07-30 |
| [[fuente-unica-eventos-json]] | Por qué unificar datos en un solo JSON fetcheado en runtime | 2026-07-30 |
| [[desc-short-truncado]] | Por qué `desc_short` y truncado en News/Agenda | 2026-07-06 |
| [[doble-validacion-propietario]] | Doble validación de `TELEGRAM_OWNER_ID` (Worker + script) | 2026-07-06 |
| [[patron-llm-wiki-karpathy]] | El patrón "LLM Wiki" de Karpathy aplicado a este proyecto | 2026-07-06 |
| [[por-que-cloudflare-worker]] | Por qué Cloudflare y no GitHub Actions directamente para el webhook | 2026-07-30 |
| [[latencia-workflow-run]] | Por qué el deploy puede tardar hasta ~30 min en dispararse tras un commit del bot, y la solución propuesta (dispatch directo) | 2026-08-07 |
| [[por-que-plenos-en-local]] | Por qué se construyó y luego se borró toda la automatización del pipeline de plenos | 2026-08-08 |
| [[via-de-escape-en-el-esquema]] | Diseño anti-alucinación: el esquema nunca debe forzar al modelo a inventar | 2026-08-08 |
| [[bucle-generador-auditor-corrector]] | Los tres roles LLM y el `while` determinista que verifica el informe | 2026-08-08 |

## Síntesis

| Página | Pregunta | Actualizado |
|--------|----------|-------------|
| [[cloudflare-worker-que-por-que-como]] | Qué se hizo con Cloudflare, por qué y cómo funciona | 2026-07-29 |
| [[donde-se-ejecuta-el-bot]] | Dónde corre procesar_telegram.py: GitHub Actions, no Cloudflare ni Hostinger | 2026-07-30 |
| [[flujo-completo-corregido]] | Flujo end-to-end verificado: la imagen no viaja por Cloudflare; orden main→Hostinger | 2026-07-30 |

## Pendientes de ingerir

Ninguna.
