---
type: source-summary
date_updated: 2026-08-21
---

# Convocatoria oficial y ajustes posteriores al rediseño del acta

**Fuente:** conversación de trabajo del 2026-08-21, posterior a implementar
[[2026-08-21-acta-oficial-plenos-design]]. No tiene spec ni plan propios: son decisiones
tomadas y ejecutadas en la misma sesión, ingeridas para que no se pierda el porqué.

Cubre cinco cambios sobre [[pipeline-plenos]], todos con los tests en verde y sin escribir
nada en `public/` ni en `uploads/`.

## 1. Quién preside: Lorena Luján Chujfi, en funciones

El rediseño del acta dejó abierta una contradicción entre fuentes del propio proyecto: la
spec llamaba "presidenta" a Lorena Luján Chujfi, mientras `plenos_informe.CORPORACION`
daba a Sergio de Fez Cerezuela como Alcalde-Presidente y a ella como Concejala.

**Resuelto por el usuario:** Sergio de Fez es el Alcalde, está **de baja médica**, y Lorena
Luján ejerce sus funciones. El pleno del 7 de julio de 2026 lo presidió ella.

Consecuencias implementadas:

- `CORPORACION` recoge la baja y la Alcaldía en funciones.
- Las reglas 7 y 8 del `PROMPT_GENERADOR` tratan a quien preside por su cargo y en su
  género — *"la Sra. Alcaldesa"*, nunca *"el Sr. Alcalde"* —, y el ejemplo del
  `PROMPT_AUDITOR` va acorde para que no marque la fórmula como afirmación inventada.
- Se añadió un guardarraíl explícito en el propio bloque `CORPORACION`: ese dato sirve
  para el **tratamiento**, no para rellenar el campo `presidente` ni para atribuir
  intervenciones. Sin él, el modelo podía dar por hecho quién preside aunque la grabación
  no lo dijera, rompiendo [[via-de-escape-en-el-esquema]].

Esto además **cierra el hallazgo aparcado** durante la implementación del rediseño: la
plantilla oficial trae precargado `LORENA LUJÁN CHUJFI` en la celda "Presidida por", y
conservarlo cuando `presidente` es `null` —lo que decide la spec— es correcto, porque es
quien preside de verdad.

## 2. La convocatoria oficial como fuente

Idea del usuario: el Ayuntamiento redacta el orden del día antes de cada sesión, con los
títulos exactos y los números de expediente. Pasárselo al modelo resuelve de golpe títulos,
numeración y referencias administrativas.

Se implementó como `--convocatoria <pdf>`. El desarrollo completo, con las dos
consecuencias no obvias, está en [[convocatoria-como-fuente]].

## 3. La fecha del CLI rellena el hueco

`procesar_pleno` recibe una `fecha` autoritativa (de `--fecha`, del título del vídeo, o de
la entrada guardada). Si el modelo no oye la fecha en la grabación, ahora se rellena con
ella antes de renderizar. **Solo rellena el `null`; nunca pisa una fecha que sí conste en
la grabación.**

Motivo: se le estaba pidiendo a la secretaria que rellenase a mano un `___________` que la
herramienta ya conocía con certeza. No debilita [[via-de-escape-en-el-esquema]] porque el
dato no lo inventa el modelo.

## 4. La web deja de hablar de "informes"

`src/components/pages/AyuntamientoPage.jsx` seguía describiendo el documento viejo: título
*"Informes de los plenos"*, botón *"Informe PDF ↓"*, descarga `Informe-pleno-<fecha>.pdf`,
y una nota que decía *"Resumen automático de cada sesión a partir de la grabación. El
documento oficial es el acta aprobada por el Pleno."*

Tras el rediseño, el fichero detrás de ese enlace **es** el acta sellada, así que la nota
le decía al vecino que un documento con validez legal era un resumen automático no oficial.
Ni la spec ni el plan miraron el frontend; lo detectó la revisión final de la rama.

Ahora: *"Actas de los plenos"*, botón *"Acta PDF ↓"*, y la nota dice que el acta está
*"revisada, completada y sellada por la Secretaría-Intervención del Ayuntamiento"*.
**Deliberadamente no dice "aprobada por el Pleno"**: la aprobación ocurre en la sesión
siguiente, y lo que se publica es el acta sellada, no necesariamente ya aprobada.

## 5. El bucle narra su progreso

El bucle podía estar varios minutos en silencio y, si el auditor se atascaba, no había
forma de verlo. Ahora cada rol anuncia qué hace y qué encuentra: ver
[[bucle-generador-auditor-corrector]].

## Relacionado

[[pipeline-plenos]], [[convocatoria-como-fuente]], [[bucle-generador-auditor-corrector]],
[[via-de-escape-en-el-esquema]], [[2026-08-21-acta-oficial-plenos-design]]
