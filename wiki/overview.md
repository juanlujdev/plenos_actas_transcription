# Overview del proyecto

Este proyecto convierte la grabación de cada sesión plenaria del Ayuntamiento de
Enguídanos en el borrador del **acta oficial**, rellenando la plantilla Word que usa la
secretaría. El flujo es: audio (YouTube o fichero local) → transcripción diarizada con
AssemblyAI `universal-3-5-pro` (Groq `whisper-large-v3` como respaldo) → bucle
`gemini-2.5-pro` vía OpenRouter validado contra esquemas pydantic → relleno determinista
del `.docx`, sin LLM. Todo el detalle está en [[pipeline-plenos]].

El acta generada es un **borrador**. Se envía por email a la secretaria, que lo completa,
lo revisa y lo sella. El pipeline termina ahí: no publica nada en ninguna web y no toca
git. Para ayudarla a revisarlo se genera junto al acta una guía de verificación en HTML
con los minutos enlazados a la grabación ([[guia-de-verificacion]]).

Su historia es instructiva. Nació en julio de 2026 dentro del repositorio de la web
municipal `enguidanos_web`, diseñado y construido entero como pipeline automático con
cron —espejo del sistema de agenda por Telegram que ya existía allí—, y esa automatización
se **eliminó** tras la primera prueba real: YouTube bloquea las descargas desde las IPs de
datacenter de GitHub Actions, y mantener cookies vivas resultaba más costoso que ejecutar
un comando al mes ([[por-que-plenos-en-local]]). El resultado es el opuesto al de aquel
sistema en cuanto a infraestructura, pero comparte con él la convicción de fondo: nada
sale sin que una persona lo confirme. El 2026-09-08 el proyecto se separó a su propio
repositorio y las actas dejaron de publicarse en la web del municipio.

Su fiabilidad descansa en cuatro ideas, y son lo más reutilizable que tiene:

- [[bucle-generador-auditor-corrector]] — tres roles LLM y un `while` determinista que
  verifica el acta contra la transcripción, con salida cuando el auditor se contradice a
  sí mismo.
- [[via-de-escape-en-el-esquema]] — el esquema nunca debe forzar al modelo a inventar; un
  campo que no consta vale `"no consta"`, y solo hay una forma de decirlo.
- [[diarizacion-como-andamiaje]] — la etiqueta de locutor es una voz, no una identidad:
  cuándo puede propagarse a toda la sesión y el día que esa propagación falló.
- [[persistir-lo-caro-antes-de-lo-fragil]] — lo que cuesta dinero se escribe en disco
  antes de llamar a lo que puede fallar, para que ningún fallo obligue a pagar dos veces.

Dos fuentes alimentan cada acta y mandan en cosas distintas: la convocatoria oficial
manda en la forma (títulos, numeración, expedientes, tipo de sesión) y la grabación manda
en el fondo (qué se debatió y qué se votó) — ver [[convocatoria-como-fuente]]. Un punto
convocado del que la grabación no habla no se redacta: escribir lo previsto como si
hubiera ocurrido sería una invención con pinta de oficial.

Desde septiembre de 2026 el pipeline lo ejecuta directamente una funcionaria del
Ayuntamiento, mediante un ejecutable empaquetado con PyInstaller que envuelve el mismo
código sin duplicarlo ([[asistente-para-la-funcionaria]]). Eso convierte cada cambio en el
código en un cambio que hay que reempaquetar: un `.exe` sin reconstruir hace que ella
pruebe la versión anterior y su feedback no sirva.
