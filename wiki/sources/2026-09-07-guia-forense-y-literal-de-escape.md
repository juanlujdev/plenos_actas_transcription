---
type: source-summary
date_updated: 2026-09-07
---

# Sesión del 2026-09-07: la guía que no se regeneró, la votación que sí era correcta y el literal de escape

Conversación de trabajo sobre [[pipeline-plenos]], sin spec ni plan previos. Arranca de la
primera ejecución del ejecutable de [[asistente-para-la-funcionaria]] sobre el pleno del 3
de septiembre de 2026 y termina con dos arreglos aplicados y tres problemas diagnosticados
pero deliberadamente sin tocar.

## 1. La guía de verificación no se regeneró (arreglado)

Síntoma doble reportado por el usuario: el `<fecha>-guia-de-verificacion.html` seguía siendo
el de una corrida anterior, y el `COMPROBAR ANTES DE SELLAR.txt` volvía a citar rutas
internas (`orden_del_dia[0]`) sin frase que buscar ni minuto que oír.

**Una sola causa**, en el log de la corrida (13:36→14:26):

```
La guía de verificación no se ha podido componer: PermissionError: [Errno 13]
Permission denied: '...2026-09-03-guia-de-verificacion.html'
```

La guía de la corrida anterior estaba abierta y Windows bloqueó el fichero. Como
`_componer_guia` envolvía la guía HTML y el `.txt` en el **mismo** try/except, al fallar la
primera el `.txt` nunca se escribió; `asistente_plenos.py` lo reescribió después por su
cuenta con `objeciones=()`, cayendo al camino degradado de `_avisos_legibles`.

Arreglos: un try por fichero con el `.txt` primero (no depende de la guía), nombre
alternativo con la hora cuando el HTML está bloqueado, y `_ruta_legible` traduciendo también
`identificacion_locutores[n]` → `Mapa de voces — etiqueta D`. Cuatro tests nuevos. Detalle en
[[guia-de-verificacion]].

## 2. La votación del punto 1º: el acta estaba bien (sin cambios)

El usuario pidió investigar la objeción que el auditor sostuvo hasta el final: que el acta
del 7 de julio se había rechazado y el informe la daba por aprobada. Análisis con dos
subagentes (transcripción y bucle LLM).

**Hechos establecidos:**

- La grabación **nunca declara el resultado**. `rechaz*`, `decae` y `mayoría` tienen cero
  apariciones en las 1.314 líneas de la transcripción. A las `[00:16:25]` quien preside canta
  solo el recuento —*"3 a favor, 2 abstenciones y 2 en contra"*— y pasa al punto siguiente.
- El punto tuvo **dos votaciones**: el acta del 19 de mayo por asentimiento (`[00:02:06]`) y
  la del 7 de julio con recuento. `PuntoOrdenDia.votacion` es una sola (`plenos_informe.py:94`).
- El auditor osciló entre dos criterios jurídicos que nadie le había fijado: mayoría simple
  de votos emitidos (auditorías 0 y 2 → aprobado) y mayoría absoluta sobre los 7 concejales
  (auditoría 3 → rechazado). Con temperatura 0, no es ruido: es la única variable libre en un
  cálculo que ningún prompt determina.
- El bucle detectó la oscilación de `votacion.resultado` y la congeló a `"no consta"`; el
  `acuerdo`, texto libre, es invisible al detector de ping-pong y se quedó con la última
  orden del auditor ("Aprobar").

**Resolución del usuario, que invierte el diagnóstico inicial:** el acuerdo del acta es
**correcto**. 3 a favor, 2 en contra, 2 abstenciones aprueba por mayoría simple (art. 47.1
LRBRL: hay mayoría simple cuando los afirmativos superan a los negativos; las abstenciones no
computan). La auditoría 3, la que quedó en pie, aplicaba una mayoría absoluta que no rige
aquí. El usuario, presente en la sesión, lo confirmó: *"el recuento está bien y quedó
aprobada, el documento lo ha hecho bien"*.

Es decir: **el fallo del pipeline no fue equivocar el acuerdo, sino producir una objeción
falsa contra un acta correcta** —y enseñársela a la funcionaria en la guía y en el `.txt` con
enlace al minuto, mandándola a "corregir" lo que estaba bien—, y de paso perder el recuento,
porque `plenos_acta.py:170` descarta las cifras cuando `resultado == "no consta"`.

Decisión del usuario: **no tocar nada de esto todavía**. Ver [[bucle-generador-auditor-corrector]]
y [[via-de-escape-en-el-esquema]] para el análisis; los tres arreglos pendientes quedan
listados en [[pipeline-plenos]].

## 3. El literal de escape colado como nombre propio (arreglado)

Defecto independiente encontrado durante el análisis. `presidente` es `str | None` y su
descripción pide `null` cuando la grabación no identifica a quien preside, pero el modelo
devolvió la fórmula de escape que sí usan otros campos: `"no identificado en la grabación"`.
Como es una cadena no vacía, `informe.presidente or HUECO` la dio por buena y el acta del 3-S
cerró literalmente con:

> *"Y no habiendo más asuntos que tratar y cumpliendo con el objeto del acto, **no
> identificado en la grabación** levanta la sesión a las veintiuno horas…"*

No estaba entre las objeciones que la guía le avisa a la funcionaria.

Arreglo en dos sitios, ninguno de ellos el que parecía:

- `InformePleno._presidente_o_nada`, un `field_validator` que normaliza el literal a `None`
  — el principio del proyecto de que *la descripción de un campo no es una validación*.
- `plenos_acta.formula_cierre` pasa de `or HUECO` a `or PRESIDENCIA["tratamiento"]`: el acta
  ya afirma "la Presidenta abre la sesión" desde `PRESIDENCIA` sin pedirle permiso a la
  grabación, y el cierre no tiene por qué ser más tímido que la apertura.

**Un intento de arreglo revertido:** se vació también la celda "Presidida por" a `HUECO`, por
creer que el `LORENA LUJÁN CHUJFI` que aparecía era un valor de muestra colado de la
plantilla. Rompió un test que documentaba la decisión contraria de la spec —la plantilla es
la oficial del Ayuntamiento y la secretaria revisa el borrador antes de sellarlo, así que su
valor es más seguro que un hueco que igualmente habría que rellenar— y el usuario confirmó
que el dato es real: Lorena Luján Chujfi preside de verdad. Revertido.

## Relacionado

[[pipeline-plenos]], [[guia-de-verificacion]], [[via-de-escape-en-el-esquema]],
[[bucle-generador-auditor-corrector]], [[asistente-para-la-funcionaria]],
[[diarizacion-como-andamiaje]], [[persistir-lo-caro-antes-de-lo-fragil]]
