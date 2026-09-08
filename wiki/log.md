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

## [2026-09-08] query+fix | KeyError choices en classify_with_gemini: OpenRouter 200 con error; fallback arreglado y mensajes de error legibles ([[clasificacion-ia]], [[fallback-modelos-ia]])
