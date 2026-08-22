---
type: source-summary
date_updated: 2026-08-21
---

# Acta oficial de plenos: rellenar la plantilla del Ayuntamiento

Fuente: `docs/superpowers/specs/2026-08-21-acta-oficial-plenos-design.md` (2026-08-21,
estado: aprobado en brainstorming, pendiente de plan de implementación). Supera
parcialmente `2026-07-31-plenos-youtube-pipeline-design.md` — ver
[[2026-07-31-plenos-youtube-pipeline-design]].

## Resumen

[[pipeline-plenos]] deja de producir un "informe" con formato propio en PDF y pasa a
producir el **acta oficial del Ayuntamiento**, rellenando la plantilla Word que usa la
secretaría. El documento generado es un **borrador**: se envía por email a la secretaria,
y solo cuando ella lo aprueba, lo completa y lo sella se publica en la web.

## Material de partida

Tres ficheros aportados por el usuario: `MODELO_ACTAS_ORDINARIA.doc` y
`MODELO_ACTAS_EXTRAORDINARIA.doc` (plantillas vacías, Word 97 binario, convertidas a
`.docx` y versionadas en `scripts/plantillas/`), y
`20260512_Acta_Borrador Acta del 11 de febrero de 2026-1.pdf` — un acta real ya
redactada que sirve de **patrón de estilo**, no de entregable. Ambas plantillas son
estructuralmente idénticas (9 tablas); solo difieren en el número de expediente de
ejemplo y en que la extraordinaria añade un `Motivo:` vacío bajo el tipo de convocatoria.

## Decisiones tomadas

| Decisión | Elección | Motivo |
|---|---|---|
| Qué se publica en la web | El PDF sellado que devuelve la secretaria, no lo que genera el pipeline | El documento oficial es el que ella aprueba |
| Dónde cae lo generado | `uploads/actas/<fecha>/`, nunca `public/` | Todo lo que hay en `public/` se publica al hacer commit |
| Publicación | Comando aparte `--publicar <fecha> --pdf <ruta>` | Evita editar `plenos.json` a mano cada mes |
| Formato del borrador | `.docx` editable | La secretaria completa el expediente, las horas y lo que falte, y sella |
| Origen de las plantillas | Convertidas a `.docx`, guardadas en `scripts/plantillas/` | Word 97 no lo lee ninguna librería razonable de Python |
| Librería | `python-docx` (nueva dependencia, LOCAL — no va en `scripts/requirements.txt`, que es del bot de Telegram) | Lee las plantillas convertidas sin perder formato |
| Ordinaria o extraordinaria | Lo decide el modelo desde la grabación; si no consta, se aborta | Elegir plantilla a ciegas produciría un encabezado equivocado en un documento que se sella |
| Campos que no se oyen | `___________` (constante `HUECO`) | Principio anti-invención — ver [[via-de-escape-en-el-esquema]] — reforzado ahora por una persona que revisa antes de sellar |
| `plenos_render.py` (JSON→PDF) | Se borra | Su único consumidor era el documento publicado, que ahora es el acta sellada |
| Automatizar el envío del email | No, de momento | Se hará a mano hasta comprobar que el resultado es bueno |

## Arquitectura en dos pasos

```
python -u scripts/procesar_pleno.py --url "..." | --audio ... | --rehacer-informe <fecha>
    audio → ffmpeg → Groq whisper-large-v3 → transcripción
    → bucle Gemini generador→auditor→corrector → InformePleno (JSON)
    → plenos_acta.render_acta(informe) → uploads/actas/<fecha>/
          <fecha>-acta-<tipo>.docx        ← se envía por email
          <fecha>-transcripcion.md
          <fecha>-informe.json
          entrada.json                    ← título, video_id, video_url, resumen_corto

        ── email a la secretaria, revisión, sello (manual) ──

python scripts/procesar_pleno.py --publicar <fecha> --pdf "<acta sellada>"
    → public/plenos/<fecha>-pleno.pdf
    → public/plenos/<fecha>-transcripcion.md
    → entrada en public/data/plenos.json
    → commit manual → deploy
```

`entrada.json` existe para que `--publicar` no tenga que volver a pedir datos ni llamar a
ningún modelo.

## Cambios en el esquema (`scripts/plenos_informe.py`)

`InformePleno` gana `tipo_sesion` (`Literal["ordinaria", "extraordinaria", "no consta"]`,
el `"no consta"` aborta la generación del acta), `motivo_convocatoria`, `hora_inicio`,
`hora_fin`, `presidente`, `asistentes` y `ausentes`. `PuntoOrdenDia` gana
`parte: Literal["resolutiva", "control"]` y renombra `debate` a `texto` (prosa de acta con
las intervenciones incorporadas y el acuerdo desglosado si lo hay); `votacion` se
mantiene estructurado a propósito, para que el render componga la frase en letra sin que
el generador escriba recuentos dentro de `texto` — dos fuentes del mismo dato serían un
riesgo de contradicción. `ruegos_y_preguntas` pasa de `list[str]` a `list[BloqueRuegos]`
(`formulados_por` + `puntos`), porque el acta los agrupa por quien los formula.

**Se eliminan** `Intervencion` y el campo `intervenciones` (las intervenciones ahora van
dentro de cada punto, no en una sección aparte) y `resumen_ejecutivo` (sin destino: el
PDF de informe que lo consumía se borra). `resumen_corto` se queda — lo consume
`--publicar` a través de `entrada.json` para la tarjeta de la web.

## Cambios en los prompts

Ver [[bucle-generador-auditor-corrector]] para el mecanismo; esta spec le añade el estilo
de acta municipal: presente de indicativo, tratamiento formal (D., Dª, Sr. Alcalde),
intervenciones introducidas con "Toma la palabra el Sr. concejal D. ...", títulos en
mayúsculas, acuerdos desglosados en PRIMERO./SEGUNDO., y el criterio de reparto entre
parte resolutiva y actividad de control. Al auditor hay que decirle explícitamente que
esas fórmulas y ese tratamiento **no son afirmaciones inventadas** — el mismo problema, y
la misma solución, que ya obligó a pasarle el listado de la corporación (ver
[[bucle-generador-auditor-corrector]]).

## Render (`scripts/plenos_acta.py`, nuevo)

Sin LLM. Elige la plantilla según `tipo_sesion` y rellena por posición: expediente
(siempre `HUECO`, nunca el número de ejemplo de la plantilla), tipo y motivo de
convocatoria, fecha y duración en formato legible, presidente si consta, el párrafo de
apertura con asistentes/ausentes, los puntos de cada parte en su tabla, los ruegos
agrupados, y la fórmula de cierre (que la plantilla no trae pero el acta real sí, con
horas y fecha en letra). Necesita un conversor número→letra de 0 a 99, escrito a mano en
vez de traer una dependencia — igual que ya se hacía con las cifras de recuentos, ahora
también cubre horas, minutos, días y el año.

## Pruebas y validación

`scripts/test_plenos.py` cubre número→letra, reparto de puntos por `parte`, ruegos
agrupados, frase de votación con recuentos a `null` (nunca imprime un cero no dicho — ver
[[via-de-escape-en-el-esquema]]), elección de plantilla por `tipo_sesion` y que
`--publicar` sobre una fecha ya presente actualiza la fila en vez de duplicarla.

La spec preveía como validación final `--rehacer-informe 2026-07-07` sobre el pleno de
julio ya transcrito, y revisión del `.docx` resultante contra el acta del 11 de febrero.
Esa validación end-to-end (que exige `GEMINI_API_KEY`) quedó pendiente del usuario; la
Task 5 que ingiere esta fuente sí validó el render de forma aislada, con un informe de
prueba construido a mano, y encontró y corrigió dos defectos tipográficos reales (raya en
"Secretaria – Interventora" y mayúsculas en la celda "Presidida por") — ver
`.superpowers/sdd/2026-08-21-acta-oficial-plenos/validacion-estilo.md`.

## Fuera de alcance

Envío automático del email a la secretaria; automatizar el paso de publicación tras el
visto bueno; la carpeta de secretaría (Drive/OneDrive) que dejó pendiente
[[2026-07-31-plenos-youtube-pipeline-design]] — ver el punto 4 de "Pendiente para pasar a
producción" en [[pipeline-plenos]], que esta spec resuelve por otra vía (email + sellado
manual, no una carpeta compartida).

## Entidades y conceptos relacionados

[[pipeline-plenos]], [[2026-07-31-plenos-youtube-pipeline-design]],
[[bucle-generador-auditor-corrector]], [[via-de-escape-en-el-esquema]],
[[por-que-plenos-en-local]]
