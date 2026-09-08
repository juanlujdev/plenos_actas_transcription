---
type: concept
date_updated: 2026-09-07
source_count: 1
---

# El asistente para la funcionaria: empaquetar sin reescribir

[[pipeline-plenos]] lo ejecuta a mano el desarrollador desde su PC, con `python -u
procesar_pleno.py --url "..."` ([[por-que-plenos-en-local]]). El objetivo de
`asistente_plenos.py` no es sustituir ese pipeline, sino envolverlo: que la
funcionaria del Ayuntamiento genere el borrador del acta con un doble clic y tres
preguntas, sin terminal, sin Python instalado y sin ver una línea de jerga técnica. Los
prompts, los esquemas, el bucle y el render del `.docx` no se tocan.

## Por qué PyInstaller `--onefile` y no Python embebido ni instalador

El PC del Ayuntamiento no tiene Python, ni pip, ni permisos de administrador
garantizados. Se descartaron dos alternativas:

- **Carpeta portable con Python embebido + `.bat`**: funciona, pero son decenas de
  ficheros sueltos que se rompen en cuanto alguien mueve el `.bat` sin el resto. Queda
  como plan B si los antivirus dan guerra con el `.exe`.
- **Instalador (Inno Setup)**: una herramienta más que mantener para un beneficio nulo
  cuando el uso es mensual y el doble clic ya resuelve el problema.

`--onefile` lleva dentro el intérprete y todas las librerías; el PC de destino solo
necesita Windows 64 bits, internet y una carpeta con permiso de escritura. El riesgo
asumido es el falso positivo típico de antivirus en el primer arranque con ejecutables
`--onefile`, documentado en el LÉEME de la funcionaria para que no bloquee el primer uso.

## Por qué las claves viven en un fichero de texto, no en variables de entorno del sistema

`cargar_configuracion()` lee `Configuración (no tocar)/configuracion.env` con
`python-dotenv` en vez de esperar que las claves estén ya en el entorno de Windows.
Durante las pruebas el pipeline gasta las claves personales del desarrollador
(AssemblyAI y OpenRouter, de pago). Cuando se validen, se sustituirán por claves del
Ayuntamiento **editando ese fichero con el Bloc de notas**, sin recompilar el `.exe` ni
tocar el Registro de Windows. Compilar las claves dentro del ejecutable habría atado
cada cambio de cuenta a una reconstrucción y a redistribuir un `.exe` nuevo; ponerlas en
variables de entorno del sistema habría exigido a alguien sin conocimientos técnicos
manipular el Panel de control. Un `.env` es editable por cualquiera con un doble clic.

Si falta una clave, `main()` lo comprueba al arrancar y no deja avanzar con un
`KeyError` a mitad de la transcripción: dice *"El programa todavía no está
configurado. Avisa a Juan Luján"*, con el detalle técnico solo en el log.

## Por qué `yt-dlp.exe` viaja aparte y se autoactualiza

El resto de dependencias (`pydantic`, `python-docx`, los prompts) se congelan dentro
del `.exe` a propósito: cambiarlas es decisión del desarrollador y exige reconstruir.
`yt-dlp` es la excepción deliberada. La wiki ya documenta que YouTube rompe yt-dlp
cada pocos meses — el 403 del 2026-08-22 fue justo una versión desfasada, no el
bloqueo por IP de datacenter de [[por-que-plenos-en-local]] —, y en el PC del
Ayuntamiento no habrá quien lo detecte ni lo arregle: no hay terminal, no hay pip, y
la funcionaria no sabe qué es una versión de un paquete.

Por eso `yt-dlp.exe` (el binario oficial independiente) va suelto en
`Configuración (no tocar)/`, y `actualizar_descargador()` ejecuta `yt-dlp -U` antes de
cada descarga: unos segundos, una vez al mes. Si la actualización falla (sin
internet, antivirus), se anota en el log y se sigue con la versión que haya, en vez
de bloquear la ejecución por un fallo en un paso que es puro margen de seguridad.
`descargar_audio` resuelve el comando en tiempo de ejecución — el `yt-dlp.exe`
incluido si el proceso está `sys.frozen`, o `sys.executable -m yt_dlp` si corre desde
el repo — porque dentro de un `.exe`, `sys.executable` es el propio ejecutable, y
relanzarlo a sí mismo como si fuera Python sería un error distinto.

## Por qué el registro se lo queda todo y la pantalla solo lo traducido

El pipeline imprime cientos de líneas pensadas para el desarrollador: sondeos de
AssemblyAI, vueltas del bucle generador→auditor→corrector, rutas internas, trazas.
Enseñárselas a la funcionaria sería ruido que no sabría interpretar; ocultarlas sin
guardarlas dejaría sin diagnóstico el día que algo falle, con ella a cientos de
kilómetros del desarrollador. La clase `Consola` resuelve las dos necesidades a la vez
sustituyendo `sys.stdout`: cada línea se escribe entera en un fichero de registro y,
si `traducir()` reconoce el patrón, también su versión amable en pantalla. Lo que no
se traduce no desaparece — sigue en el log —, solo no se muestra.

Es la misma idea que [[persistir-lo-caro-antes-de-lo-fragil]] aplicada a la
comunicación en vez de a los datos: lo caro de reconstruir (qué pasó exactamente
durante la ejecución) se guarda completo; lo frágil de exponer (jerga técnica a
alguien sin contexto para interpretarla) se filtra. Cuando algo falla, el mensaje en
pantalla es una frase y la ruta del log; el log es lo que ella envía al desarrollador.

## Por qué la funcionaria genera pero no publica

El asistente no toca git en ningún caso, y su menú no ofrece `--rehacer-acta` ni
`--rehacer-informe`, que son herramientas del desarrollador. El reparto de papeles es
explícito en la spec: ella genera el borrador y lo envía; la secretaria lo revisa, lo
completa y lo sella.

> Cuando se escribió esto, el reparto tenía un tercer tramo: el desarrollador, con el PDF
> sellado en la mano, ejecutaba `--publicar` para subir el acta a la web del municipio.
> Esa publicación se retiró el 2026-09-08 al separarse el proyecto. La frontera que
> importa sigue siendo la misma y ahora es más simple: el asistente genera, las personas
> revisan, y nada se publica automáticamente. Ampliar su alcance a publicar habría significado darle acceso a un
repo git y a credenciales que no le corresponden para una tarea que ocurre una vez al
mes.

## Por qué la fecha la escribe ella a mano

`extraer_fecha()` puede deducir una fecha del título del vídeo, y el asistente la
ofrece como valor por defecto aceptable con un simple Enter. Pero no se acepta sin
confirmación ni se usa si no hay Enter: la fecha aparece en el nombre de la carpeta
del borrador y en el encabezado de un documento que se va a sellar, y un error de
un dedo ahí — o un título de vídeo mal formado que `extraer_fecha` interprete mal —
no se detecta hasta que alguien lo nota en un documento oficial. Es la aplicación del
mismo principio que rige el tipo de sesión en el resto del pipeline: cuando el coste
de acertar mal es escribir un dato falso en un acta municipal, no se automatiza lo
que se puede confirmar con una pregunta.

## Lo que enseñó la primera ejecución real (2026-09-07)

Nueve tareas, cada una implementada por un agente y revisada por otro, produjeron un
asistente que pasaba 339 tests y **cuyo camino largo estaba roto de forma determinista**.
Lo encontró la revisión final de toda la rama, no ninguna de las nueve puertas de calidad
por tarea: ninguna recorría una ejecución completa.

Merece la pena tenerlo presente al añadir cosas aquí: **los fallos de este programa no
están en las piezas, están en las costuras**, y solo aparecen ejecutándolo entero contra un
pleno de verdad.

### El error que ninguna prueba unitaria podía ver

`procesar_pleno._hay_color()` llama a `sys.stdout.isatty()` para decidir si pinta colores.
Durante `ejecutar_pipeline`, `sys.stdout` es la `Consola` del asistente, que no tenía ese
método. Resultado: **toda** ejecución completa moría con `AttributeError` en la última
instrucción del pipeline — después de pagar la transcripción, después de gastar el bucle de
LLM y **con el `.docx` ya correctamente escrito en disco**. La funcionaria veía "Ha ocurrido
un problema y no he podido terminar el acta" con el acta terminada en la carpeta.

`pantalla_final` no llegaba a ejecutarse nunca, así que los tres finales, el
`COMPROBAR ANTES DE SELLAR.txt` y el aviso de que es un borrador eran **código muerto en
producción**.

La lección no es "faltaba `isatty`", es que **la `Consola` no cumplía el contrato de un
fichero de texto** y el pipeline es código ajeno que puede tocar cualquiera de sus miembros.
Se le añadieron también `encoding` y `writelines`, y un test que ejecuta `_banner` dentro de
`ejecutar_pipeline` con una `Consola` real: es el único que habría cazado esta clase de
fallo, y cuesta cuatro líneas.

### Fallos de empaquetado que no se ven desde el repo

- **La carpeta de entrega estaba en `dist/`**, que es donde Vite construye la web de este
  mismo repositorio y que Vite **limpia en cada build**. El primer despliegue se habría
  llevado por delante el ejecutable y el `configuracion.env` con las claves. Ahora vive en
  `entrega/`, en `.gitignore`.
- **Los acentos salían rotos** ("todavÃ­a", "LujÃ¡n") con el codepage regional de Windows: el
  programa forzaba UTF-8 en `sys.stdout` pero no en la consola. Se arregló en el código
  (`SetConsoleOutputCP(65001)`) y no documentando un `chcp 65001` que nadie iba a escribir.
  Verificado desde una consola nueva real, que arranca en codepage **850**, no 1252.
- **El `configuracion.env` generado llevaba BOM.** `Out-File -Encoding utf8` en Windows
  PowerShell 5.1 lo mete siempre, y `python-dotenv` pegaba esos tres bytes al nombre de la
  **primera** clave, así que `ASSEMBLYAI_API_KEY` no cargaba nunca — pero `OPENROUTER_API_KEY`
  sí. El ejecutable habría dicho "no está configurado" con la clave escrita delante. Y como
  el Bloc de notas también guarda con BOM, habría vuelto en cuanto alguien pegara las claves
  del Ayuntamiento. Arreglado en los dos lados: se escribe sin BOM y se lee con `utf-8-sig`.
- **La opción "Ver las instrucciones" estaba rota solo dentro del `.exe`**: la búsqueda del
  fichero comparaba en mayúsculas y la `É` de `LÉEME` no casa con `E`. Desde el repo
  funcionaba.

### La transcripción no se degrada a un transcriptor peor

En la primera ejecución real, la subida de 197 MB a AssemblyAI se cortó a los cuatro minutos
(`SSLEOFError`: la conexión partida a mitad de transferencia, no un problema de credenciales
ni de saldo). El pipeline cayó entonces a la rama de respaldo de Groq, que no tenía clave, y
reventó con un 401 tras nueve minutos de trabajo perdidos.

Dos cambios, y el segundo es una decisión de fondo:

- **La subida se reintenta** (cuatro intentos, esperas de 30 s, 1 min y 2 min, reabriendo el
  fichero cada vez: el cuerpo ya consumido no se puede reenviar). Un pleno son 100-200 MB
  por una línea doméstica; que la conexión se parta no es excepcional, es lo normal cada
  tantas ejecuciones. El sondeo también tolera cortes, porque tirar una transcripción que el
  servidor ya está haciendo —y que ya se ha pagado— no tiene sentido.
- **Si hay clave de AssemblyAI, ya no se cae a Groq.** Groq no diariza, y sin diarización no
  hay [[diarizacion-como-andamiaje]] ni mapa de voces; además exige trocear con `ffmpeg`,
  que no está en el PC del Ayuntamiento. Degradar en silencio a un transcriptor peor en un
  documento que se sella es peor que parar y decirlo.

### Cómo se le dicen las cosas

El pipeline imprime cientos de líneas para el desarrollador. El asistente las manda **todas**
al registro y traduce a pantalla una decena de marcadores conocidos; lo que no reconoce, no
se enseña. Tres detalles que salieron de pensar en ella y no en el programa:

- El **latido cada minuto** existe porque veinte minutos de consola muda parecen un programa
  colgado, y lo que hace cualquiera ante un programa colgado es cerrarlo — que es lo único
  que de verdad rompe el proceso.
- El aviso de duración se dejó **en mayúsculas** aunque un test del plan exigía minúsculas:
  se ajustó el test, no el texto. Sacrificar el énfasis que evita que cierre la ventana para
  contentar a una comprobación es invertir las prioridades.
- Los mensajes de fallo dicen siempre **si la transcripción está a salvo**, porque es lo
  único caro y lo que decide si ella cree haber perdido veinte minutos.

## Relacionado

[[pipeline-plenos]], [[guia-de-verificacion]], [[diarizacion-como-andamiaje]],
[[por-que-plenos-en-local]], [[persistir-lo-caro-antes-de-lo-fragil]]
