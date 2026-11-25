---
type: source-summary
date_updated: 2026-11-25
---

# Corporación, presidencia y plantillas configurables (spec, plan e implementación)

Fuentes: `docs/superpowers/specs/2026-11-23-corporacion-configurable-design.md` (spec),
`docs/superpowers/plans/2026-11-23-corporacion-configurable.md` (plan) y la sesión de
trabajo del 2026-11-23 al 2026-11-25 que los ejecutó. Rama `test_cambio_gobierno`, 14
commits locales sin merge ni push (`cc86608..055c30a`). Concepto resultante:
[[corporacion-configurable]].

## Motivo

Una moción de censura cambió el equipo de gobierno de Enguídanos. Hasta entonces la
corporación, quién preside y las plantillas `.docx` estaban en constantes de código, así
que cada moción, elección o cambio de concejal obligaba a llamar al desarrollador y
reconstruir el `.exe` ([[asistente-para-la-funcionaria]]). El objetivo es que la
funcionaria lo mantenga desde el propio asistente.

## Lo que decidió el usuario

- Editor guiado dentro del asistente con un `corporacion.json` validado (enfoque A). Se
  descartaron una hoja Excel/CSV, porque los errores saldrían con la transcripción ya
  pagada, y un `corporacion.py` editado por el desarrollador, porque no resuelve nada.
- **Quién preside es un dato de la corporación y no se pregunta en cada pleno.** Al principio
  se pensó preguntarlo en cada acta y se descartó. Si un día preside otra persona, se cambia
  en el menú o lo corrige la secretaria en el borrador.
- Las plantillas solo cambian textos o membrete; la estructura se mantiene.
- Fuera de alcance: las actas de la moción de censura y de las sesiones constitutivas (Mesa
  de Edad, las redacta la secretaria a mano), el secretario accidental y la consulta del
  saldo de AssemblyAI/OpenRouter (AssemblyAI no tiene API de saldo; OpenRouter exige
  management key o límite de gasto).
- Se mantiene una parte pequeña de costes: lo que suele costar un pleno antes de lanzarlo y
  lo que ha costado al terminar.
- Ningún pleno se había procesado después de la moción, así que la semilla (la corporación
  anterior) es la correcta para todos los plenos existentes.

## Lo que se construyó

- `corporacion.py` + `corporacion_inicial.json`: modelo pydantic, validación con mensajes
  llanos y textos derivados (tratamientos, fórmulas de presidencia, bloque para el prompt,
  menú de voces, keyterms, resumen, aviso de presidencia).
- Los prompts de los cuatro roles son estáticos y la corporación viaja en el mensaje
  (`cabecera_mensaje`). Se quitaron los nombres reales de los ejemplos y del esquema JSON.
  Ver [[bucle-generador-auditor-corrector]].
- `plenos_acta.py` rellena «Presidida por» y la fila de la Secretaria desde la corporación,
  `normalizar_cargos` depende de `hay_alcaldesa` y las plantillas se pueden sustituir
  (`PLANTILLAS_PROPIAS`, `validar_plantilla`).
- Cada pleno guarda su corporación en `entrada.json` (`corporacion_del_pleno`).
- Opción 3 del asistente: ver, alta, cambio, baja, nueva corporación tras elecciones,
  presidencia, Secretaria y plantillas, con resumen y confirmación antes de guardar y copia
  en `historial/`.
- `costes.py`: coste habitual (media de los plenos guardados) y coste real.
- CLAUDE.md, wiki y `.exe` actualizados.

## Lo que corrigieron las revisiones

Cada tarea pasó una revisión independiente, y al final se revisó la rama entera:

- Los apodos no llegaban al modelo («Chari» = Mª Rosario) y la detección de apellidos
  compartidos fallaba con partículas («de Fez», «de la Torre»).
- «Nueva corporación» perdía todo lo tecleado si se repetía un nombre. Ahora el nombre
  repetido se rechaza al escribirlo y se puede corregir o quitar a una persona antes de
  guardar.
- Un coste que la API no devuelve salía como 0,00 $ y arrastraba la media. Ahora se muestra
  «no disponible».
- La plantilla extraordinaria se aceptaba como ordinaria. Ahora se comprueba la celda «Tipo
  Convocatoria».
- No se veía quién iba a figurar presidiendo antes de lanzar un pleno. Ahora sale el aviso
  «Preside: …».
- Los keyterms de AssemblyAI llevaban «Mª». Ahora llevan «María», porque el reconocedor
  nunca escribe la abreviatura.

## Pendiente

- **Regresión con el pleno del 3-IX** (`--rehacer-informe 2026-09-03` y
  `python quejas_pleno.py 2026-09-03`, ~5 $). Bloquea la entrega del `.exe` a la
  funcionaria. No se ha podido hacer en el PC de desarrollo: el pleno no está y no hay
  claves.
- La corporación posterior a la moción hay que meterla con la opción 3 antes del primer
  pleno. El `.exe` arranca con la semilla.
- Validar con la secretaria la fórmula de presidencia «por ausencia».
- La rama sigue sin integrar: el usuario eligió dejarla como está.
