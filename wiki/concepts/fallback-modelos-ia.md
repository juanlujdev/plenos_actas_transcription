---
type: concept
date_updated: 2026-09-08
source_count: 3
---

# Elección y fallback de modelos de IA

Este pipeline usa dos proveedores de IA con políticas distintas: uno para transcribir el
audio y otro para redactar el acta. Ninguno de los dos se elige por disponibilidad — se
eligieron por capacidad, y se pagan.

> Esta página nació compartida con el bot de agenda de `enguidanos_web`, que usa modelos
> gratuitos con fallback entre ellos. Al separarse los proyectos (2026-09-08) se quedó
> aquí solo la mitad que aplica a las actas. La política del bot, opuesta a esta, vive en
> la wiki de aquel repositorio.

## Redacción del acta: `google/gemini-2.5-pro` vía OpenRouter, sin alternativa

El pipeline migró a OpenRouter el 2026-08-22 (ver
[[2026-08-22-plenos-openrouter-gemini-pro]]): del SDK `google.genai` contra Google AI
Studio a `requests` contra OpenRouter, con `google/gemini-2.5-pro`. El motivo fue que el
modelo `pro` tiene **cupo 0** en la capa gratuita de Google, y se quería ese modelo sin
abrir facturación con Google. Es el primer sitio del proyecto donde se paga por token.

El modelo está **fijo en `plenos_informe.MODELO`**, no configurable por entorno: es una
decisión de calidad, no un parámetro de despliegue.

**No hay modelo de respaldo, y es deliberado.** Un acta se sella y queda como documento
oficial del Ayuntamiento, se genera una vez al mes y no hay con qué compararla salvo la
grabación. Un modelo peor "pero disponible" no es un apaño aceptable. Ante un 429, el
bucle espera 2, 4 y 8 minutos y **reintenta el mismo modelo** en vez de saltar a otro:
puede permitírselo porque nadie está mirando la pantalla.

La salida se pide con `json_schema` en modo `strict`, no con `json_object`: el esquema
pydantic es parte del contrato, no una validación posterior. Ver
[[via-de-escape-en-el-esquema]].

## Transcripción: AssemblyAI con Groq como respaldo

El 2026-08-22 la transcripción pasó a AssemblyAI (ver
[[2026-08-22-plenos-assemblyai-diarizacion]]). Es el único fallback del proyecto que cruza
**proveedores distintos con capacidades distintas**: AssemblyAI `universal-3-5-pro` diariza
y admite el audio entero (tope 5 GB / 10 h); Groq `whisper-large-v3` es gratis pero exige
trocear con ffmpeg (25 MB por fichero) y no dice quién habla.

Se conservó a petición explícita del usuario, como red de seguridad para no perder una
grabación, asumiendo que la rama de respaldo produce una transcripción **peor** —no
equivalente—: sin locutores, el acta pierde las atribuciones que
[[diarizacion-como-andamiaje]] permite.

La condición es simple: si hay `ASSEMBLYAI_API_KEY` se usa AssemblyAI, y solo se cae a
Groq si falta o si la petición falla.

## Restricciones que no se pueden relajar

- **El modelo de redacción no se degrada.** Ni a `flash`, ni a un `:free`, ni "solo esta
  vez". Si `gemini-2.5-pro` no está disponible, se espera.
- **Temperatura 0 y máximo 3 vueltas** del bucle generador→auditor→corrector. Las vueltas
  están topadas porque cada una cuesta dinero y porque el auditor puede contradecirse; qué
  pasa entonces está en [[bucle-generador-auditor-corrector]].
- **`_espera_tras_error` respeta el `retry-after` de los 429 de Groq**, con tope de 65
  minutos. El cupo horario de la capa gratuita puede pedir esperas largas, y abortar ahí
  significaría perder la transcripción de un pleno entero.
- **Los errores de configuración (`401`, `400`) se propagan sin reintento.** No tiene
  sentido esperar ocho minutos por un problema de credenciales.

## Relacionado

[[pipeline-plenos]], [[bucle-generador-auditor-corrector]], [[diarizacion-como-andamiaje]],
[[via-de-escape-en-el-esquema]], [[2026-08-22-plenos-openrouter-gemini-pro]],
[[2026-08-22-plenos-assemblyai-diarizacion]], [[persistir-lo-caro-antes-de-lo-fragil]]
