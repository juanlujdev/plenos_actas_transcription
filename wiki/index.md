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

## Entidades

| Página | Descripción | Actualizado |
|--------|-------------|-------------|
| [[telegram-bot]] | Bot de Telegram (`scripts/procesar_telegram.py`) que clasifica y publica eventos | 2026-07-06 |
| [[cloudflare-worker]] | Worker que recibe el webhook de Telegram y dispara GitHub Actions | 2026-07-06 |
| [[github-actions]] | Workflows de scan/confirm/deploy/diagnóstico | 2026-07-06 |
| [[github-pages-deploy]] | Build Vite + deploy a GitHub Pages con gate condicional | 2026-07-06 |
| [[clasificacion-ia]] | Clasificación de publicaciones con Gemini/OpenRouter (Gemma) | 2026-07-06 |
| [[eventos-json]] | `public/data/eventos.json`, fuente única de verdad del contenido dinámico | 2026-07-06 |
| [[sistema-agenda-automatica]] | El sistema completo de publicación automática de eventos/bandos | 2026-07-06 |

## Conceptos

| Página | Descripción | Actualizado |
|--------|-------------|-------------|
| [[confirmacion-si-no]] | Por qué la confirmación manual SI/NO en dos ejecuciones asíncronas | 2026-07-06 |
| [[gate-deploy-condicional]] | Por qué el gate y el trigger `workflow_run` en el deploy | 2026-07-06 |
| [[fallback-modelos-ia]] | Historial de elección/migración de modelos de IA y manejo de 429 | 2026-07-06 |
| [[limpieza-artefactos-tokenizacion]] | Limpieza de `<pad>`/`톱` en respuestas de Gemma 4 | 2026-07-06 |
| [[fuente-unica-eventos-json]] | Por qué unificar datos en un solo JSON fetcheado en runtime | 2026-07-06 |
| [[desc-short-truncado]] | Por qué `desc_short` y truncado en News/Agenda | 2026-07-06 |
| [[doble-validacion-propietario]] | Doble validación de `TELEGRAM_OWNER_ID` (Worker + script) | 2026-07-06 |
| [[patron-llm-wiki-karpathy]] | El patrón "LLM Wiki" de Karpathy aplicado a este proyecto | 2026-07-06 |

## Síntesis

| Página | Pregunta | Actualizado |
|--------|----------|-------------|

## Pendientes de ingerir

Ninguna.
