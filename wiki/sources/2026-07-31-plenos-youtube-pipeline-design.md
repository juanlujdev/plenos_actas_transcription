---
type: source-summary
date_updated: 2026-08-08
---

# Pipeline automático de informes de plenos: diseño

Fuente: `docs/superpowers/specs/2026-07-31-plenos-youtube-pipeline-design.md` (2026-07-31, estado: aprobado en brainstorming).

> ⚠️ **Esta spec está parcialmente superada por la implementación.** Toda la capa de automatización que describe (cron, feed RSS, state, workflow) se eliminó durante las pruebas end-to-end. Ver [[por-que-plenos-en-local]] para la causa y [[pipeline-plenos]] para lo que existe de verdad. El diseño del informe (esquemas, prompts, bucle, render) sí se implementó tal cual.

## Resumen

Spec de diseño para generar automáticamente, a partir de la grabación de cada pleno del Ayuntamiento, cuatro entregables: transcripción literal con timestamps, informe estructurado (resumen ejecutivo, orden del día con votaciones, intervenciones, ruegos y preguntas), PDF publicado en la sección Plenos, y entrada en la web.

**Decisión de partida:** publicación totalmente automática sin revisión humana previa, mitigada con una pasada de auto-verificación del modelo y aviso por Telegram. (Esta decisión se revirtió en la práctica — ver [[por-que-plenos-en-local]].)

### Decisiones técnicas documentadas

| Decisión | Elección | Motivo |
|---|---|---|
| Detección de vídeo nuevo | Cron de Actions cada 2h sondeando el feed RSS del canal | Cero infraestructura nueva; plenos mensuales, latencia irrelevante |
| Transcripción | Groq `whisper-large-v3` | Calidad en castellano, ~0,2 €/pleno, capa gratuita |
| Informe | Gemini 2.5 Pro | 1M de contexto (el pleno entero en una llamada), capa gratuita |
| ¿Un agente por sección? | No — bucle generador→auditor→corrector con contexto completo | Las secciones dependen del contexto global |
| Formato fuente | JSON validado con pydantic; MD/PDF/web derivan por código | Con publicación automática la validación programática es crítica |
| ¿Framework de agentes? | No — cada rol es una función Python | No hay herramientas ni autonomía que orquestar |
| Revisión humana previa | No | Decisión del usuario; mitigación: auditor + Telegram + rollback git |
| Carpeta de secretaría | Fase final desacoplada | No se sabía qué había en ese PC |

Ver [[bucle-generador-auditor-corrector]] y [[via-de-escape-en-el-esquema]] para los dos mecanismos de fiabilidad, ambos implementados fielmente.

### Las tres capas de garantía

La spec insiste en que ninguna sustituye a las otras: **pydantic** garantiza la forma del JSON (no un dato falso bien formado); el **auditor** garantiza fidelidad a la transcripción (no errores que ya trae la transcripción); las **pruebas con audio real** garantizan que la transcripción es fiel al pleno (capa humana). Incluye una nota de honestidad técnica explícita: las medidas reducen la alucinación a mínimos, pero ningún LLM garantiza el 0%.

### Riesgo principal anticipado

La spec ya identificaba que **YouTube bloquea a veces las descargas desde IPs de datacenter** ("confirm you're not a bot"), con plan B documentado pero no montado: secret `YT_COOKIES`. Este riesgo se materializó en la primera prueba real y acabó decidiendo la arquitectura — ver [[por-que-plenos-en-local]].

### Plan de pruebas y proceso

Material previsto: 1 vídeo del canal + 2 audios de ~4h de una funcionaria. Desarrollo con `superpowers:subagent-driven-development`, con **checkpoint obligatorio con el usuario** en la tarea de prompts y esquemas (se cumplió). Coste estimado en producción: ~1 €/pleno.

## Entidades y conceptos relacionados

[[pipeline-plenos]], [[por-que-plenos-en-local]], [[bucle-generador-auditor-corrector]], [[via-de-escape-en-el-esquema]], [[por-que-plenos-en-local]]
