---
type: concept
date_updated: 2026-08-29
source_count: 1
---

# Por qué no hay un cuarto agente revisor del acta

Al leer el `.docx` del pleno del 19 de mayo aparecieron cuatro defectos de **texto** —duplicidad de fórmulas, redundancia, comillas mezcladas, ortografía— y se planteó añadir un **revisor final** al [[bucle-generador-auditor-corrector]]: un cuarto rol que corrigiese la forma del texto ya consolidado. Se descartó. Lo que se hizo en su lugar: **cambiar los prompts** del generador y del corrector, y resolver la tipografía **en código**.

## Lo que sí se descubrió por el camino

**Ampliar el corrector no era una opción**, aunque fuese la primera candidata. El corrector es condicional:

```python
# plenos_informe.py
while problemas and vueltas < MAX_VUELTAS:
    informe = corregir(...)
```

Si el auditor da el visto bueno a la primera —cosa que ya ha pasado en ejecuciones reales— **el corrector no se ejecuta nunca**. Colgar de él un paso obligatorio de revisión habría producido un acta revisada unas veces sí y otras no, sin que nada lo indicara. Cualquier responsabilidad incondicional tiene que vivir fuera del `while`.

## Por qué tampoco el agente nuevo

1. **Los defectos eran autoinfligidos por los prompts.** La regla 11 del generador ya prohibía escribir el acuerdo dentro de `texto`, y aun así el modelo cerró el punto 2º con *"se da el punto por aprobado"* antes de la fórmula jurídica. Y la regla 14 **obligaba** a que `texto` llevara "SIEMPRE varios párrafos": en el punto 5º, que se despachaba en una frase, el modelo fabricó la segunda —*"No se presentan escritos"* detrás de *"La Presidencia informa de que no se han presentado escritos"*— para cumplirla. Añadir un agente que limpie después lo que una regla mal formulada produce cada vez es pagar dos veces por el mismo error.
2. **Habría sido el único paso que nadie audita.** El auditor corre antes que él por definición. Un modelo con licencia para borrar frases de un documento que se sella, y sin nadie detrás que verifique lo que borró, es la peor pieza posible en este pipeline.
3. **La tipografía no necesita un modelo.** Unificar comillas es una sustitución determinista; pedírsela a un LLM cuesta ~0,06 $ y 80-190 s por ejecución y abre superficie de invención a cambio de nada. Vive en `plenos_acta.comillas()`, que además la **garantiza**: el modelo ya había escrito el mismo paraje con comillas dobles en `texto` y simples en `acuerdo` del mismo punto, teniendo la regla delante.
4. **La ortografía casi no tenía defectos que justificaran la pasada.** El barrido de las ~5.500 palabras del acta del 19 de mayo encontró exactamente dos cosas: `Las Chorreras` / `las Chorreras` alternando, y `ENGUIDANOS` sin tilde en el título del punto 4 — que viene copiado literalmente de la convocatoria por la regla 21, así que "corregirlo" habría chocado con una fuente autorizada.

## Lo que se pierde, y se asumió

Un cambio de prompt es una garantía **probabilística**; un paso de revisión con su puerta determinista habría sido una garantía **verificable**, y habría producido el informe de correcciones (original → corregido → regla) que un documento oficial agradece. Se asume a cambio de no meter un modelo sin supervisión al final de la cadena. La comprobación sigue siendo humana: la lista de pendientes por consola y la lectura de la secretaria.

El corolario práctico es el de siempre en este bucle, en su otra dirección: **una regla de forma que le pides al corrector la necesita también el generador**, o el defecto se reproduce en cada ejecución. Por eso el criterio tipográfico, la prohibición de la fórmula coloquial y la de la redundancia entraron en los dos prompts a la vez. El auditor no los recibe a propósito: su prompt le dice explícitamente que no señale problemas de estilo, y dárselos quemaría vueltas.

## Relacionado

[[bucle-generador-auditor-corrector]], [[pipeline-plenos]], [[acta-oficial-11-febrero-2026]], [[via-de-escape-en-el-esquema]]
