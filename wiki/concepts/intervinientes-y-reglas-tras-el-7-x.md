---
type: concept
date_updated: 2026-10-08
source_count: 1
---

# Intervinientes, reproches y datos dudosos: lo que cambió tras el 7 de octubre

El 7-X se leyó el acta del 3-IX en el pleno y varios concejales señalaron errores. Contrastadas
sus quejas con la grabación (`2026-09-03-transcripcion.md`), las justificadas apuntaban a
cuatro fallos de fondo y uno de forma. Todos se atacaron en [[bucle-generador-auditor-corrector]]
y en código, no con un cuarto agente ([[revisor-final-descartado]]).

| Fallo observado | Cambio |
|---|---|
| «Acusaciones mutuas» donde solo una parte insultó | Regla 16 quater (atribuir quién dijo qué a quién; «mutuas» solo con cita de cada lado) + objeción del auditor |
| Dato inventado desde un fragmento confuso («regulación de acceso») | Regla 6 bis + objeción «datos sin frase clara» |
| Respuesta del equipo de gobierno perdida en los ruegos | Regla 14 bis (solo si es concluyente) |
| Lugares mal oídos («visera» por «pesquera») | `TOPONIMOS` → regla 20 y keyterms de AssemblyAI |
| «Teniente alcalde» vs «alcaldesa» | `normalizar_cargos` en `plenos_acta.py`, determinista |
| Voces sin identificar | El asistente pregunta intervinientes y apodos (`INTERVINIENTES_SESION`) |

## Por qué los intervinientes son una pista y no una prueba

Misma razón que [[speaker-identification-descartado]]: una lista de nombres empuja al modelo a
asignarlos todos. Por eso el bloque no prueba asistencia, no rellena el mapa de voces
([[diarizacion-como-andamiaje]]) y un apodo ambiguo no identifica a nadie. Sirve para
reconocer «Nando» o «Chari» cuando alguien los nombra, y para dar el nombre correcto a
AssemblyAI antes de que lo destroce.

## Decisión sobre el cargo de quien preside

Se pidió «Lorena alcaldesa, Sergio concejal». Se mantuvo **Teniente de Alcalde por
delegación** (el nombramiento real; ver el gotcha de `PRESIDENCIA` en CLAUDE.md): Fernando
pidió unificar la forma, no un cargo concreto. Cualquier cambio se hace solo en `PRESIDENCIA`
y `CORPORACION`.

## Qué NO se cambió

Modelo (`google/gemini-2.5-pro`) y troceado de la transcripción. Partir el pleno rompería el
mapa de voces y la regla de turnos alternos, que necesitan la sesión entera; 213 KB caben de
sobra en contexto.

## Segunda vuelta (2026-10-08): lo que el modelo siguió dejando pasar

El acta regenerada con estas reglas resolvió «visera», Las Chorreras/La Playeta, «mutuas» y
la forma de nombrar a Lorena, pero introdujo errores peores: el acta del 7 de julio
«rechazada» con un recuento de 3-2-2, el pleno fechado el 30 de septiembre, la pregunta de
un vecino atribuida a un concejal cuya etiqueta lo mezclaba, y «tenso enfrentamiento» pese a
estar vetado en el generador y en el auditor. Respuesta: **código, no más prompt**.
`incoherencias()` (acuerdo/votación, resultado/recuento, calificaciones vetadas) se suma al
auditor; `Votacion` deduce el resultado de un recuento completo; `fijar_fecha` impone la
fecha de quien procesa. En prompt solo se añadieron las señales de público dentro de una
etiqueta de concejal (DIARIZACION) y los verbos que califican (16 quater c).

Por qué el auditor no lo vio y una revisión dirigida sí: ver la explicación en
[[bucle-generador-auditor-corrector]] — un único pase sobre 200 KB, sin hipótesis previa,
con el mismo modelo que redactó y un prompt cargado de excepciones de «no señales».


## Tercera vuelta (2026-10-10): otro modelo como auditor y más control en código

Decisiones, todas medidas contra el acta del 3-IX con `quejas_pleno.py`:

- **Auditor = Sonnet 5.5 (`MODELO_AUDITOR`), redactor y corrector = Gemini.** Un modelo que se
  revisa a sí mismo repite sus puntos ciegos. Probado en vivo sobre el informe del 3-IX: el
  auditor nuevo objetó el acuerdo «rechazar» con 3-2-2, la pregunta del vecino atribuida a un
  concejal y los «tenso» que no dijo nadie. Coste medido: ~0,3 $ por llamada (110 k tokens de
  entrada, 10 k de salida, ~70 s). No se envía `temperature` (Sonnet 5.5 da 400); sí
  `reasoning.enabled`.
- **Auditor de atribuciones**, una vez, siempre. Se descartó dispararlo solo con etiquetas
  marcadas «voces mezcladas»: la etiqueta que cargó con la pregunta del vecino no lo estaba.
- **`citas_no_halladas` y `toponimos_parecidos`** en `incoherencias()`. Una cita entre comillas
  es literal y se comprueba con pares de palabras; un topónimo casi igual a uno de la lista se
  marca. Limitación documentada: un lugar que no esté en `TOPONIMOS` no se ve.
- **`quejas_pleno.py`**: cada queja justificada es un caso comprobable; sobre el informe viejo
  del 3-IX marca las 8 que seguían en pie (fecha, punto 1, «Hoya de las Vejas», «tenso
  enfrentamiento», «amenaza con promover»…).
- Descartado: auditar por tramos de transcripción (rompe el mapa de voces, que necesita la
  sesión entera) y cambiar el modelo del generador.

### Cuarta vuelta (2026-10-10): Opus 5.5 y recuentos protegidos

Prueba real del bucle con Sonnet 5.5: 10 de 11 quejas del 3-IX resueltas, pero el auditor pidió
anular el recuento 3-4 del punto 3 y el 7 a favor del 4 porque los decía una etiqueta marcada
«mezclada», y el corrector los borró. Probado el mismo informe con Opus 5.5 (una sola muestra):
no repite ese falso positivo y encuentra además apodos de particulares en el acta. `MODELO_AUDITOR`
pasa a Opus 5.5. Dos defensas independientes del modelo: una línea en los prompts del auditor y
del de atribuciones («una etiqueta mezclada no invalida un recuento»), y `restaurar_recuentos`
en el bucle, que devuelve los recuentos completos que el corrector borre y deja un aviso
entre los pendientes. Sigue abierto: la regla de «etiqueta contaminada» marca B, D, E y F
como mezcladas y deja a Joaquín fuera de casi todo el acta (decisión pendiente).
