---
type: source-summary
date_updated: 2026-08-23
---

# Acta oficial del pleno del 11 de febrero de 2026

Documento del Ayuntamiento, no material generado: el borrador de acta que redactó la
Secretaría-Intervención para la sesión del 11 de febrero de 2026, firmado
electrónicamente en la sede (10 páginas, con capa de texto). Vive fuera del repositorio,
en `~/Downloads/Actas Enguidanos Plenos/`.

Es **el patrón de estilo de todo el acta que genera [[pipeline-plenos]]**: contra este
documento se validó el render en [[2026-08-21-acta-oficial-plenos-design]], y contra él se
resolvió el 2026-08-23 cómo debe escribirse una votación empatada
([[2026-08-23-reglas-de-recuento-y-decisiones-de-acta]]).

## Cómo escribe las votaciones

**Todas en prosa, dentro del relato del punto. No hay una sola tabla, casilla ni recuento
tabulado en las diez páginas.** El formulario `a_favor` / `en_contra` / `abstenciones` que
usa nuestro esquema no existe en el documento que redacta la secretaria: es un andamiaje
interno cuyo único destino es componer una frase.

Los acuerdos por unanimidad van integrados en la fórmula del acuerdo:

> *"el Pleno del Ayuntamiento, por unanimidad de los asistentes, ACUERDA: 1º) Mantener la
> adjudicación efectuada inicialmente del aprovechamiento de pastos…"*

Y ante un empate —la votación sobre el importe del aprovechamiento de biomasa— escribe
esto y nada más:

> *"D. Joaquín Martínez manifiesta que "las zonas de arriba le parecen bien y el resto lo
> tiene que ver", y su propuesta es que el importe sea a 10 euros la tonelada.* **Se
> producen las votaciones con tres votos a favor y tres en contra.***"*

El punto termina ahí. **No declara resultado**: ni "aprobado", ni "rechazado", ni
"resulta empate", ni menciona voto de calidad. Narra el recuento y calla. Es la decisión
de quien da fe: si de la sesión no salió un acuerdo declarado, el acta no lo fabrica.

Esa frase —*"Se producen las votaciones con tres votos a favor y tres en contra"*— es
literalmente la que compone `plenos_acta.frase_votacion`, porque el render se escribió
copiando este documento.

## Lo que aporta al pipeline

1. **Zanjó la duda sobre cómo representar un empate.** Se barajó añadir al esquema una
   estructura para votaciones entre alternativas; este documento demostró que el acta real
   no estructura nada, y la vía elegida fue la prosa. Ver
   [[via-de-escape-en-el-esquema]].
2. **Confirmó que el empate no es un caso exótico** en esta corporación: hay uno aquí (11
   de febrero, biomasa) y otro en el pleno del 7 de julio (periodicidad de los plenos).
   Dos de dos en las dos sesiones conocidas.
3. **Fija el registro**: presente de indicativo, tratamiento D./Dª/Sr./Sra., títulos de
   punto en mayúsculas con el sufijo `.-`, acuerdos desglosados en `1º)` / `PRIMERO.`,
   ruegos agrupados por quien los formula (*"Ruegos y preguntas formuladas por D. Joaquín
   Martínez:"*).

## Detalle de contexto

La sesión la preside el **Sr. Alcalde** (Sergio de Fez Cerezuela): es anterior a su baja
médica y a que Lorena Luján Chujfi ejerza la Alcaldía en funciones. De ahí que el
tratamiento sea masculino en todo el documento, mientras el pleno de julio exige "la Sra.
Alcaldesa" — el motivo por el que `plenos_informe.CORPORACION` tiene que decir quién
preside y hay que actualizarlo cuando eso cambie.

## Relacionado

[[pipeline-plenos]], [[2026-08-23-reglas-de-recuento-y-decisiones-de-acta]],
[[2026-08-21-acta-oficial-plenos-design]], [[via-de-escape-en-el-esquema]],
[[2026-08-22-primera-ejecucion-e2e-acta-oficial]]
