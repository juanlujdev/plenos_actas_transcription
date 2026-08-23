---
type: source-summary
date_updated: 2026-08-23
---

# Reglas de recuento y decisiones sobre el acta (2026-08-23)

Conversación de trabajo del 2026-08-23, sin spec ni plan. Continúa
[[2026-08-22-primera-ejecucion-e2e-acta-oficial]]: allí el pipeline llegó al final por
primera vez y dejó tres objeciones sin resolver; aquí se leen **el acta generada, la
transcripción en crudo y el acta oficial del 11 de febrero** para decidir qué de aquello
era un error del modelo, qué un error del esquema y qué un error del auditor.

## Lo que se descubrió al contrastar con la transcripción

**1. El resultado del punto 1 SÍ consta: hubo desempate.** El análisis del día anterior
daba por hecho que el empate 3-3 había quedado sin resolver. La transcripción lo
desmiente en 00:17:19:

> *"Vale, pues entonces, ¿cómo queda para que sepamos? Eran 3 a 3, como el voto de la
> alcaldesa en este caso vale 2, se queda a 40 días."*

Y en 00:15:54: *"Y el voto de la alcaldesa, que desempata."* De modo que el
`resultado: "aprobado"` del generador era **correcto**, y la periodicidad de las sesiones
ordinarias quedó fijada en 40 días. Lo falso era la forma —"tres en contra" cuando nadie
votó en contra, y un `abstenciones: 0` inventado—, no el fondo. El acta generada, además,
ya narraba el desempate en el texto del punto.

**2. El auditor produjo un falso positivo.** Su tercera objeción decía que el informe
atribuía la propuesta de la "mini geolodría" a Joaquín Martínez. El JSON final dice
**Pedro José Martínez**, que es lo correcto; y la objeción señalaba `orden_del_dia[6]`
(punto 7º), donde esa frase ni aparece — está en el 6º. Ver
[[bucle-generador-auditor-corrector]].

**3. El acta se contradecía a sí misma en el punto 5.** El texto decía *"Consta en la
grabación un voto a favor y dos votos en contra, sin que se verbalice el recuento
completo"* y la frase compuesta por el render, justo detrás, afirmaba *"Se producen las
votaciones con un voto a favor y dos en contra"*. En la grabación (01:46:07) se oye por
qué: *"¿Votos a favor de la auditoría? Yo, uno. Y todos los demás, 4, 3, 4 y 5"*.

**4. Sergio de Fez Cerezuela asistió al pleno pese a la baja médica**, y hay discusión
expresa sobre ello (00:15:15). El informe hacía bien en listarlo entre los asistentes.
Queda resuelta la duda que dejó abierta la sesión anterior.

**5. El "aprobado" del punto 3 es una inferencia.** En 00:56:34 se oye *"Pues bueno, votos
a favor"* y en 00:56:51 ya están en el punto siguiente: nadie cuenta votos ni declara
resultado. El modelo dedujo "aprobado" porque la propuesta gustó. **Se decidió dejarlo
así** (ver decisiones).

## El acta oficial de febrero como árbitro

La pregunta "¿estructuramos las votaciones entre alternativas o las narramos?" se resolvió
leyendo lo que hace la secretaria en [[acta-oficial-11-febrero-2026]]: prosa siempre, cero
estructura, y ante un empate ni siquiera declara resultado. Eso descartó tocar el esquema.

## Los seis cambios propuestos y qué se decidió

| # | Propuesta | Decisión |
|---|---|---|
| 1 | Llevar la regla de recuentos también al generador | **Aplicado**, con el matiz de que una abstención verbalizada sí se cuenta |
| 2 | Recuento incompleto → los tres campos a `null` | **Aplicado**, conservando `resultado` y `modalidad` |
| 3 | Votaciones entre alternativas → recuentos a `null` + prosa | **Descartado**: el acta ya reflejaba bien el acuerdo |
| 4 | Excepción para escribir recuentos en `texto` | **Descartado**: dependía del 3 |
| 5 | Avisar de que hay dos concejales apellidados Martínez | **Aplicado** |
| 6 | `resultado` solo si se declara en la sesión | **Descartado** por el usuario |

Las tres decisiones de no hacer son del usuario y tienen consecuencia visible: con el 1
aplicado y el 3 descartado, el punto 1 del acta pasa a decir *"Se producen las votaciones
con tres votos a favor y tres en contra"* — sin el cero inventado y sin más cambios. Es,
palabra por palabra, la frase que escribió la secretaria en febrero para su propio empate.
Con el 6 descartado, el acta sigue afirmando "queda aprobado" en el punto 3 sin que la
grabación lo declare.

## Implementación

Las reglas comunes viven ahora en un bloque `RECUENTOS` que reciben **generador y
corrector** (antes solo el corrector, que era la causa del `0` inventado):

- `votacion` es un objeto o `null`, nunca una cadena.
- Un número solo se escribe si se oye.
- Recuento ininteligible **o incompleto** → los tres campos a `null`. *"Un recuento
  incompleto NO es un recuento."*
- `resultado` y `modalidad` se conservan si constan.
- Prohibido deducir restando de los asistentes, del reparto de la corporación o del
  sentido del debate.
- Las abstenciones cuentan como cualquier voto: si alguien dice que se abstiene, se
  cuenta; si nadie la menciona, `null`, nunca 0.

En `CORPORACION`, bajo los dos Martínez, un aviso de que el apellido solo no identifica a
ninguno de los dos y de que sin nombre de pila o etiqueta identificada la atribución es
"no identificado en la grabación".

## El fallo que destapó el cambio: `"sin votación"` como cadena

La primera ejecución con el bloque nuevo murió en el generador: escribió la **cadena**
`"sin votación"` en el campo `votacion`, que es objeto o `null`, en los tres puntos de
control. Tres ejecuciones anteriores no lo habían disparado.

Causa: el esquema tiene **dos vías de escape parecidas** para decir que no hubo votación
—`votacion: null` y `resultado: "sin votación"` dentro del objeto— y el bloque nuevo, que
insiste en `null` y en votaciones, empujó al modelo a mezclarlas. Arreglado en dos capas:
una viñeta al principio de `RECUENTOS` que lo dice explícitamente, y un `field_validator`
que normaliza a `null` las cadenas de ausencia (`"sin votación"`, `"no consta"`, vacía).
**Cualquier otra cadena sigue fallando** a propósito: convertir `"aprobado por
unanimidad"` en `null` afirmaría que no hubo votación cuando sí la hubo. No toca el JSON
Schema que viaja al modelo.

## El 504 reintentado, en vivo

La ejecución siguiente mostró por consola el reintento que se implementó el día anterior:

```
el proveedor cortó la respuesta (504: Upstream idle timeout exceeded);
esperando 2 min y reintentando...
```

Sobre el coste: el volcado del corte anterior traía `"cost": 0` junto a
`"upstream_inference_cost": 0.062`. **La petición cortada no se le factura al usuario**;
esos 0,062 $ son lo que Google le cobra a OpenRouter. Lo que se paga es el reintento que
sí devuelve contenido, o sea una llamada, no dos. Lo que el corte multiplica es el reloj:
el backoff de 2/4/8 minutos se heredó de los 429, donde la espera larga tiene sentido; un
timeout no es un cupo agotado y podría reintentarse mucho antes.

## Por qué no se vuelve a Google AI Studio

Se planteó si el problema desaparecería llamando a Gemini directamente. El error concreto
sí (es el proxy de OpenRouter el que corta), pero **la causa no**: el bucle de
razonamiento es del modelo, y con Google directo aparecería como un timeout de cliente o
un `DEADLINE_EXCEEDED`. Además haría falta abrir facturación con Google —lo que se evitó
al migrar—, se pierde el fallback de proveedor, y la petición fallida probablemente sí se
facturaría, porque no hay intermediario que la absorba.

La palanca que ataca la causa real es otra y no exige cambiar de proveedor: **ponerle
techo al razonamiento del auditor** (`reasoning: {max_tokens: N}`), que gasta casi toda su
salida razonando. No se hizo: recortarlo a ciegas degradaría las objeciones, que son lo
único que impide publicar un acta con datos inventados. Queda como el siguiente
experimento, barato de probar con `--rehacer-informe`.

## Tests

`scripts/test_plenos.py` gana 17 comprobaciones: que el bloque de recuentos llega al
generador, que exige `null` en recuentos incompletos, que una abstención verbalizada sí se
cuenta, que el resultado se conserva, que el aviso de los dos Martínez llega al generador
y al auditor, y nueve sobre la normalización de la cadena `"sin votación"` (incluida la
que fija que una cadena con contenido debe seguir fallando).

## Relacionado

[[pipeline-plenos]], [[2026-08-22-primera-ejecucion-e2e-acta-oficial]],
[[acta-oficial-11-febrero-2026]], [[via-de-escape-en-el-esquema]],
[[bucle-generador-auditor-corrector]], [[diarizacion-como-andamiaje]],
[[persistir-lo-caro-antes-de-lo-fragil]], [[2026-08-22-plenos-openrouter-gemini-pro]]
