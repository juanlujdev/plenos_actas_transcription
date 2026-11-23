---
type: concept
date_updated: 2026-11-23
source_count: 1
---

# Corporación, presidencia y plantillas configurables

**Estado: implementada (2026-11-23); regresión con el pleno del 3-IX pendiente.**
Fuente: `docs/superpowers/specs/2026-11-23-corporacion-configurable-design.md`.

## Por qué

Los nombres de la corporación, quién preside y las plantillas estaban en constantes
(`CORPORACION`, `PRESIDENCIA`, `PERSONAS_VOZ`, `AAI_KEYTERMS`). Un cambio de gobierno o de
presidencia obligaba a tocar código y reconstruir el `.exe`. Ahora los datos viven en
`corporacion.py` y se editan desde el asistente (opción 3, «Cambiar la corporación o las
plantillas»); ver [[asistente-para-la-funcionaria]].

## Decisiones

- **La corporación viaja en el mensaje, no en los prompts.** Los prompts son estáticos y
  `cabecera_mensaje` añade el bloque de la corporación a los cuatro roles, auditor incluido
  (si no, marcaría los nombres corregidos como no respaldados; ver
  [[bucle-generador-auditor-corrector]]). Las voces (`personas_voz`) salen de la misma fuente
  ([[voces-confirmadas-por-la-secretaria]]).
- **La semilla es la corporación histórica y no se edita.** `corporacion_inicial.json` es la
  de antes de la moción. El asistente trabaja sobre una copia (`CORPORACION_JSON`). Cada pleno
  guarda en `entrada.json` la corporación con que se procesó; los plenos antiguos sin ella
  caen a la semilla, que es justo la que se usó.
- **La plantilla se valida por render de prueba**, no por inspección de su estructura: lo que
  importa es que `render_acta` pueda rellenarla.
- **La plantilla sustituta tiene que ser del tipo que se sustituye.** `validar_plantilla`
  comprueba la celda «Tipo Convocatoria» (empieza por «Ordinaria» o «Extraordinaria») antes
  del render, porque `render_acta` no la escribe en un ordinario y una plantilla de
  extraordinario pasaría por buena.
- **Antes de empezar un pleno se avisa de quién preside y por qué**
  (`corporacion.aviso_presidencia`), junto al coste habitual, para poder cancelar y corregirlo
  en la opción 3.
- **No se consulta el saldo** de AssemblyAI ni OpenRouter: la primera no tiene API de saldo y la
  segunda exige management key o límite de gasto en la clave.
- **«Alcaldesa»**: `normalizar_cargos` solo actúa cuando la corporación no tiene Alcaldesa
  titular (`hay_alcaldesa`).

## Decisiones tomadas al implementar

- El aviso de apellido compartido (Cerdán) se acepta: es una ambigüedad real, no un fallo.
- El cierre usa siempre el tratamiento de la presidencia.
- «Presidida por» muestra el nombre sin «Dª», como en la plantilla.
- Un coste que la API no da se muestra «no disponible» y no entra en el promedio (nunca 0,00 $).
- Pendiente: regresión con el pleno del 3-IX (`--rehacer-informe 2026-09-03` y
  `python quejas_pleno.py 2026-09-03`, ~5 $); ese pleno no está en el PC de desarrollo y
  requiere OK del usuario.
