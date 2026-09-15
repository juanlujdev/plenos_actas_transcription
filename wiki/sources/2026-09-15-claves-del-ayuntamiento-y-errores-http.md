---
type: source-summary
date_updated: 2026-09-15
---

# Las claves pasan a las cuentas del Ayuntamiento, y el log aprende a decir por qué falla

Conversación de trabajo del 2026-09-11 al 2026-09-15 (sin spec ni plan). Rama
`cambio_apikey_lorena`. Cierra el punto 1 de los pendientes de [[pipeline-plenos]]:
hasta ahora el pipeline gastaba saldo personal del desarrollador en cada ejecución.

## Qué hacía falta para cambiar de cuenta: nada de código

La pregunta de partida era si el cambio de cuenta exigía tocar el pipeline o configurar
algo en las plataformas. La respuesta la había dejado escrita la decisión de
[[asistente-para-la-funcionaria]]: las claves se leen de
`Configuración (no tocar)/configuracion.env` con `python-dotenv`, así que cambiar de
cuenta es editar un fichero de texto y **no hace falta reconstruir el `.exe`**. Esa
decisión se tomó en previsión de este día y es aquí donde se cobra.

Los dos ficheros a editar son independientes entre sí: el de la carpeta de pruebas del
Escritorio y el de `entrega/`. `construir_exe.ps1` copia al Escritorio **solo el `.exe`**,
nunca el `.env`.

## Lo único que sí había que mirar en las plataformas

- **OpenRouter — saldo.** `google/gemini-2.5-pro` es de pago y no tiene capa gratuita
  (ver [[pipeline-plenos]]): sin créditos comprados devuelve `402`.
- **OpenRouter — política de privacidad.** Es el ajuste no evidente: si la cuenta
  restringe el enrutado a proveedores que puedan entrenar con los datos, la petición
  falla con `404 No endpoints found matching your data policy` en vez de responder. Con
  la configuración por defecto funciona, pero es lo primero que mirar si una cuenta nueva
  no responde.
- **AssemblyAI — nada que activar.** `universal-3-5-pro` se pide en `speech_models` del
  cuerpo de la petición, no es un permiso de cuenta. Una cuenta nueva trae $50 de crédito
  sin tarjeta (~185 h de pregrabado) y concurrencia 5, que sobra para un audio al mes.
- **Ninguna allowlist de modelos por cuenta** en ninguna de las dos.

## La comprobación previa: un céntimo contra 0,40 $ y veinte minutos

Antes de lanzar el pleno se verificaron las claves con un script de usar y tirar que lee
el propio `configuracion.env` (sin pegar las claves en ninguna conversación) y hace tres
llamadas: `GET /api/v1/credits` de OpenRouter para ver el saldo, una completación de un
solo token a `gemini-2.5-pro` para probar enrutado y política de privacidad, y un `POST
/v2/transcript` real contra el audio de muestra de AssemblyAI, que es exactamente la
llamada que falla cuando el saldo está a cero.

Resultado: 30,00 $ de saldo en OpenRouter (0,00 gastados), el modelo respondiendo, y la
transcripción de prueba completada con diarización. Es la misma lógica de
[[persistir-lo-caro-antes-de-lo-fragil]] aplicada antes de empezar: comprobar lo barato
antes de gastar lo caro, en vez de descubrir a mitad de un pleno que falta saldo.

## El `.env` se queda con dos claves

`GROQ_API_KEY` y `ACTAS_DIR` salen de la plantilla de `construir_exe.ps1` y de los dos
ficheros existentes:

- **`GROQ_API_KEY`** no la puede usar el `.exe`. Groq solo entra si **falta** la clave de
  AssemblyAI (desde 2026-09-07 ya no es respaldo ante fallo, ver [[pipeline-plenos]]) y
  ese camino necesita `ffmpeg` para trocear, que no está en el PC del Ayuntamiento. Era
  una clave que no podía funcionar aunque estuviera bien escrita — y en la carpeta de
  pruebas llevaba meses con tres caracteres basura sin que nadie lo notara, precisamente
  porque nunca se lee.
- **`ACTAS_DIR`** vacío no hace nada: el asistente calcula la carpeta desde
  `sys.executable` y se asigna la variable él mismo. Sigue funcionando si algún día se
  añade a mano.

El criterio es el de todo el fichero: lo ve una persona que no sabe qué es una variable
de entorno, y una línea que no hace nada solo puede confundirla o invitarla a rellenarla.

## El registro decía el código HTTP, no el motivo

`raise_for_status()` compone su mensaje con el código, la razón HTTP y la URL, y
**descarta el cuerpo de la respuesta** — que es justo donde viajan
`"insufficient credits"` (OpenRouter) y `"Your current account balance is negative"`
(AssemblyAI). Un registro real del 2026-09-05, de cuando falló la clave de Groq, enseña
el problema entero:

```
requests.exceptions.HTTPError: 401 Client Error: Unauthorized for url:
https://api.groq.com/openai/v1/audio/transcriptions
```

Groq devolvió en el cuerpo un motivo claro y no aparece por ningún lado. Un fallo por
créditos se habría visto idéntico cambiando `401 Unauthorized` por `402 Payment Required`
(deducible) o por `400 Bad Request` de AssemblyAI (indistinguible de un audio corrupto o
un cuerpo mal formado).

`verificar_respuesta()` en `plenos_informe.py` sustituye a `raise_for_status()` en las
cinco llamadas que pueden quedarse sin saldo o sin clave: OpenRouter, y las tres de
AssemblyAI (subida, `POST /v2/transcript`, sondeo) más Groq. Adjunta hasta 300 caracteres
del cuerpo al mensaje y encadena con `from None` para no duplicar la excepción en el
registro. El `raise_for_status` del título de YouTube se queda como estaba: su `401` ya se
captura y se traduce, y no es una API de pago.

Importa aquí más que en otros proyectos porque **el log es el canal de diagnóstico**: la
funcionaria está a cientos de kilómetros y lo que envía cuando algo falla es ese fichero
(ver [[asistente-para-la-funcionaria]]). Un registro que dice *dónde* falló pero no *por
qué* obliga a un viaje de ida y vuelta que puede tardar días.

## La validación end-to-end

Se relanzó el pleno del 2026-09-03 completo con el `.exe` del Escritorio y las claves del
Ayuntamiento: correcto. Tres detalles del procedimiento que conviene recordar:

- **La opción 1 del menú es la única que valida la clave de AssemblyAI.** Siempre descarga
  y transcribe de nuevo; la opción 2 reutiliza la transcripción guardada y solo repetiría
  el bucle LLM.
- **No hay que borrar la carpeta del pleno anterior.** Todo se pisa por nombre, y los dos
  ficheros que podrían quedar obsoletos —`COMPROBAR ANTES DE SELLAR.txt` y
  `<fecha>-objeciones.json`— ya se borran solos si la corrida nueva no tiene objeciones.
- **El `.exe` del Escritorio y el de `entrega/` son el mismo fichero** (mismo SHA-256):
  `construir_exe.ps1` compila en `entrega/` y de ahí copia. Lo que se prueba es
  literalmente lo que se entrega.

## Relacionado

[[pipeline-plenos]], [[asistente-para-la-funcionaria]],
[[persistir-lo-caro-antes-de-lo-fragil]], [[por-que-plenos-en-local]]
