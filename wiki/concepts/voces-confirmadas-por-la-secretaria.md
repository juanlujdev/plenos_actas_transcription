---
type: concept
date_updated: 2026-10-12
source_count: 1
---

# Voces confirmadas por la secretaría

**Estado: adoptada (2026-10-12).** Se quitó y se volvió a poner el mismo día; tras probarla
en la app sobre el pleno del 7-X se decidió conservarla («me ha parecido útil»). Se
entrega a la secretaria en el `.exe` nuevo, con el LÉEME actualizado (apartado 5).

Tras el pleno del 7-X ([[pleno-en-varias-grabaciones-y-mismo-dia]]) el acta salió con muchos
«un concejal no identificado en la grabación». Se comparó con una ejecución anterior de la
misma grabación: la transcripción y la diarización eran las mismas (95 % de los turnos con
la misma etiqueta, 8 etiquetas), y lo que cambiaba era la identificación de cada etiqueta
por el modelo.

## Qué se vio

- **La primera ejecución identificaba casi todo, y al menos una atribución la contradice
  la propia transcripción**: puso D = Joaquín, pero D dice «¿Habéis visto esa obra?
  Joaquín…» (le habla a Joaquín). Lo mismo con C = Fernando («¿Sabes, Nando?»).
- **La segunda marcó A, C, D y E como «etiqueta con voces mezcladas»** y por eso dejó 12
  intervenciones sin identificar. Es lo que piden las reglas ([[diarizacion-como-andamiaje]]:
  un «no consta» es preferible a una atribución equivocada), pero deja a la secretaria sin
  ayuda. Entre las dos ejecuciones no cambió el código que identifica voces: es variación
  del modelo, y puede repetirse en cualquier pleno.
- **La causa de fondo es la diarización**: un micrófono de sala, siete concejales, la
  secretaria y público dan 8 etiquetas para al menos 9 personas, y AssemblyAI mezcla voces.
  El código ya pedía entre 6 y 15 locutores.

## Decisión

Ofrecer una **identificación hecha por una persona que ha oído la grabación**, que sí vale
como prueba (a diferencia de los intervinientes, que son pista:
[[intervinientes-y-reglas-tras-el-7-x]], [[speaker-identification-descartado]]).

- Tras transcribir y guardar, el asistente **se detiene** y, por cada etiqueta con 3 o más
  intervenciones, enseña 5 frases con su minuto **repartidas por toda la sesión** (no las
  primeras: un cambio de voz entre tramos delata una etiqueta mezclada) y, si hay vídeo de
  YouTube, el enlace al segundo. Opciones: los 8 de `PERSONAS_VOZ` (nombre, cargo y apodos),
  «Público», «Varias personas mezcladas» y «No lo sé» (no se incluye y se infiere como
  siempre). Termina con un resumen y «¿Es correcto?».
- Va a `entrada.json` (`voces`) **antes** del bucle y se inyecta como
  `VOCES CONFIRMADAS POR LA SECRETARÍA` a los cuatro roles (`bloque_voces`, reglas en
  `INTERVINIENTES_SESION`). Además `aplicar_voces` las escribe en `identificacion_locutores`
  al terminar el bucle, con evidencia «Confirmada por la secretaría»: no se deja a la
  memoria del modelo.
- `--rehacer-informe` / la opción de rehacer del menú las reutilizan; si no hay (o se
  dijo «que lo decida el programa»), se vuelven a preguntar, y así se puede rehacer un pleno
  ya transcrito sin pagar la transcripción.
- Quién contesta: la secretaria, que reconoce las voces.

## Detalles que costaron

- La pregunta ocurre con `sys.stdout` sustituido por la `Consola`: el prompt de `input()`
  se quedaba en su buffer sin salir. `preguntar_voces` lo restaura mientras pregunta y
  silencia el latido «sigue trabajando» (`Consola.preguntando`).
- Una frase donde alguien se dirige a otra persona por su nombre **no** contradice una voz
  confirmada (se habla a los demás, no a uno mismo); solo una autopresentación como otra
  persona lo hace.

## Pendiente (versión 2)

Una página HTML con reproductor de audio que salte al segundo exacto, útil cuando no hay
vídeo de YouTube (audio unido o archivo local), que es el caso en que hoy solo se ve el
minuto. Para un audio unido de dos vídeos, el minuto del segundo vídeo es el mostrado menos
la duración del primero.

## Relacionado

[[diarizacion-como-andamiaje]], [[intervinientes-y-reglas-tras-el-7-x]],
[[speaker-identification-descartado]], [[asistente-para-la-funcionaria]],
[[guia-de-verificacion]], [[pipeline-plenos]]
