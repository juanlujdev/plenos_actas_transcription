---
type: concept
date_updated: 2026-09-07
source_count: 1
---

# La guía de verificación: hacer barato comprobar el acta

El acta que produce [[pipeline-plenos]] es un borrador que alguien tiene que contrastar
contra la grabación antes de sellarla. Ese "alguien" es la funcionaria del Ayuntamiento, y
la grabación del pleno del 3 de septiembre de 2026 dura **3 horas y 29 minutos**.

Hasta 2026-09-07, el pipeline no le decía en qué minuto estaba nada. Verificar una frase
dudosa significaba rebuscar por toda la sesión, y lo que ocurre en la práctica cuando
verificar cuesta tanto es que **no se verifica y se sella igual**. Toda la arquitectura de
fiabilidad del proyecto —[[bucle-generador-auditor-corrector]],
[[via-de-escape-en-el-esquema]], la revisión humana de [[por-que-plenos-en-local]]— termina
apoyándose en ese último paso humano, y ese paso era el más caro de todos.

## Qué es

Un fichero `<fecha>-guia-de-verificacion.html` que se genera junto al acta, en la misma
carpeta, y se abre con doble clic en el navegador. Lo compone `plenos_guia.py`
**sin llamar a ningún modelo**: es un render determinista sobre el `informe.json` ya
guardado, igual que `plenos_acta.py` lo es para el `.docx`. Coste cero y regenerable tantas
veces como haga falta.

Contiene, por este orden:

1. **El mapa de voces** ([[diarizacion-como-andamiaje]]): qué persona hay detrás de cada
   etiqueta, con la cita que lo demuestra y su enlace al vídeo.
2. **Los puntos que conviene comprobar**: las objeciones que el auditor sostuvo hasta el
   final, cada una con dónde está, qué dice el acta, por qué se duda, qué se oye en la
   grabación y el minuto exacto.
3. **El orden del día completo**, punto por punto, con su acuerdo, su votación y su minuto.

Cada tiempo es un enlace `?t=<segundos>` a YouTube: un clic y el vídeo salta a ese momento.

## Por qué HTML y no un segundo `.docx`

Fue una decisión consciente, contra la petición literal del usuario, que pidió "un documento
gemelo". Dos razones, y la primera pesa mucho más:

- **Dos `.docx` casi idénticos en la misma carpeta acaban, antes o después, con el
  equivocado sellado o enviado por correo.** El acta es un documento con validez legal; la
  guía es una herramienta de trabajo interna. Confundirlos es un error caro y silencioso.
  Un HTML es inconfundible: nadie lo toma por el acta oficial.
- **En el navegador el tiempo es un enlace.** En Word habría que copiar el minuto y buscarlo
  a mano en YouTube, que es exactamente el trabajo que la guía existe para ahorrar.

La guía lleva además un encabezado que dice explícitamente que **no es el acta**, y la
pantalla final del asistente lo repite con esas mismas palabras
([[asistente-para-la-funcionaria]]).

## De dónde salen los minutos, y qué pasa cuando no salen

Ninguno se calcula ni se estima: todos vienen de datos que el pipeline ya tenía y no estaba
enseñando.

- La transcripción trae `[HH:MM:SS]` en cada intervención.
- `Votacion.timestamp` ya existía desde el rediseño del acta oficial.
- **`PuntoOrdenDia.timestamp` es nuevo** (2026-09-07): el momento en que empieza el debate
  de cada punto. Es el único sitio donde esta funcionalidad tocó los prompts — una regla
  calcada de la que ya pedía el timestamp de las votaciones.

Para una objeción, el minuto se busca en cascada: primero localizando la **cita literal** de
`Problema.evidencia` dentro de la transcripción (`localizar()`, que compara tal cual, luego
normalizando acentos y puntuación, y luego por fragmentos); si falla, el timestamp de la
votación del punto; si falla, el del punto.

Y si nada casa, **no se inventa un minuto**: esa línea simplemente no aparece. En un
documento cuyo propósito es verificar, un tiempo equivocado es peor que ninguno — es la
misma lógica de [[via-de-escape-en-el-esquema]] aplicada a la presentación.

## Qué buscar en el acta: el fallo que solo se vio usándolo

La primera versión mostraba, como frase a comprobar, el campo `afirmacion_dudosa` del
auditor. La funcionaria intentó buscarla en Word y no la encontró, y lo dijo: *"¿qué se
supone que tengo que comprobar y cómo lo busco?"*.

La causa: `afirmacion_dudosa` es **la descripción que hace el revisor**, no el texto literal
del acta. El auditor escribe *"La explicación sobre la denuncia por prevaricación la da un
interviniente no identificado"*; el acta dice *"A petición del Pleno, un interviniente no
identificado en la grabación explica que la queja se fundamenta..."*. Parecidas, pero no
buscables.

De ahí `buscar_en_acta()`: extrae la frase **literal del informe** que ella puede pegar en el
buscador de Word, verificando siempre que existe de verdad en el texto. Primero busca un
fragmento entrecomillado de la objeción que aparezca tal cual; si no, la frase del acta que
más comparta con la duda; y si ninguna da confianza, no ofrece nada y la manda a leer el
punto entero.

Ese último caso importa: **mandarla a buscar una frase que no está en el acta es peor que no
darle ninguna**, porque quema la confianza en el resto de la guía.

Al implementarlo aparecieron dos fallos que ningún test escrito de antemano habría cazado, y
que solo se vieron al probar contra el pleno real:

- La primera versión puntuaba por número bruto de palabras compartidas, y elegía una frase
  larga que solo coincidía por casualidad en **el nombre del concejal mal atribuido** —
  justo el error que se estaba persiguiendo. Se corrigió puntuando por proporción.
- El separador de frases tomaba "Sra.", "D.", "Dª" y "Excma." por final de frase, y las
  citas salían cortadas por la mitad ("Teniente de Alcalde, Dª Lorena Luján Chujfi" sin "La
  Sra." delante).

## Lo que no cabe en el acta pero sí en la guía

La secretaria pidió poder recoger los temas paralelos que salen en el debate, y a la vez
dijo que no hacía falta que la IA los añadiera al acta. Las dos cosas a la vez solo son
posibles si el pipeline se los enseña **sin escribirlos en el documento que se sella**:

- En el acta no caben porque un acta numera lo convocado, y un epígrafe inventado para
  ellos sería una invención con pinta de oficial — el mismo riesgo de
  [[convocatoria-como-fuente]] leído al revés.
- Pero si se podan en silencio, ella no puede sintetizarlos: tendría que buscarlos en tres
  horas y media de vídeo, que es justo el trabajo que dijo que no puede hacer.

De ahí `asuntos_no_convocados` (regla 16 ter del generador): una síntesis de una o dos
frases por tema, el punto en cuyo debate surge y su timestamp. La guía los pinta en su
propia sección, cada uno con su minuto enlazado, encabezada por el aviso de que **no están
en el acta**. `plenos_acta.py` no lee ese campo, así que el `.docx` no puede cambiar por
esto ni aunque el modelo se ponga generoso.

Es la misma división de trabajo que el resto de la guía: el pipeline localiza, la persona
decide.

## Los tres ficheros tienen que contar lo mismo

Cada pleno produce tres documentos que hablan del mismo contenido: el acta `.docx`, la guía
`.html` y el aviso `COMPROBAR ANTES DE SELLAR.txt`.

Al principio los dos primeros los componía el pipeline y el tercero lo escribía el
asistente, que solo corre cuando la funcionaria usa el menú. Resultado inmediato: tras
mejorar cómo se nombran los puntos, `--rehacer-acta` dejó el acta y la guía al día y el
`.txt` siguió diciendo `orden_del_dia[2].texto`. **El fichero que ella lee justo antes de
sellar contradecía a los otros dos.**

Desde 2026-09-07 los tres se generan en el mismo sitio (`_componer_guia`, dentro de
`procesar_pleno.py`), así que `--rehacer-acta` los deja siempre coherentes. Es una variante
del mismo principio de [[persistir-lo-caro-antes-de-lo-fragil]]: lo que debe ir junto, se
escribe junto.

`escribir_comprobaciones` **borra** el `.txt` cuando ya no quedan objeciones, en vez de
dejar el de la ejecución anterior. Un aviso viejo que contradice al documento nuevo es peor
que no tener aviso.

## Un try/except por fichero, no uno para los tres

Generarlos juntos no basta: hay que poder fallar por separado. En la corrida del pleno del
3 de septiembre de 2026 la guía del pase anterior estaba abierta mientras se generaba la
nueva, Windows dio `PermissionError` al reescribir el HTML, y como `_componer_guia` envolvía
la guía y el `.txt` en el **mismo** try, el `.txt` no llegó a escribirse. El asistente lo
reescribió entonces por su cuenta con `objeciones=()`, cayendo al camino degradado de
`_avisos_legibles`: el aviso volvió a decir `orden_del_dia[0]` sin frase que buscar ni
minuto que oír — exactamente lo que las dos secciones anteriores existen para evitar. El
acta y el informe estaban perfectos; solo se perdió la ayuda para comprobarlos.

Desde entonces cada fichero tiene su propio try, y el `.txt` va primero porque no depende de
la guía para nada. Y cuando el HTML está bloqueado se escribe con la hora en el nombre
(`-guia-de-verificacion-1438.html`) en vez de perderse: reejecutar con la guía anterior
abierta no es un descuido raro, es lo que se hace al comparar dos pases.

Es el mismo principio de [[persistir-lo-caro-antes-de-lo-fragil]] leído al revés: lo que
puede fallar no debe poder arrastrar a lo que no ha fallado.

## Las objeciones se persisten en disco

`Problema` vivía solo en memoria durante el bucle y se imprimía por consola. Eso tenía dos
consecuencias malas: `--rehacer-acta` regeneraba la guía **sin su sección más valiosa**, y
si el render del `.docx` fallaba tras un bucle de LLM ya pagado, la lista de objeciones se
perdía para siempre aunque hubiera costado lo mismo que el resto del informe.

Desde 2026-09-07 se guardan en `<fecha>-objeciones.json` en el mismo momento que el
`informe.json` y antes de componer nada — [[persistir-lo-caro-antes-de-lo-fragil]] otra vez,
con el mismo razonamiento que puso la transcripción antes del bucle.

## Traducir las rutas internas del auditor

`Problema.seccion` viene como una ruta del esquema: `orden_del_dia[2].texto`,
`ruegos_y_preguntas[2]`. Se estaba imprimiendo tal cual, y la funcionaria no tiene forma de
saber que eso es el punto 3 del acta.

`_ruta_legible()` las traduce usando el `numero` y el `titulo` reales del informe:

| Lo que devuelve el auditor | Lo que ve ella |
|---|---|
| `orden_del_dia[2].texto` | `Punto 3º) SOLICITUD ASISTENCIA JURÍDICA... — en el relato del debate` |
| `orden_del_dia[4].acuerdo` | `Punto 5º) APROBACIÓN... — en el acuerdo` |
| `ruegos_y_preguntas[2]` | `Punto 10º) RUEGOS Y PREGUNTAS — intervención 3` |
| `identificacion_locutores[3]` | `Mapa de voces — etiqueta D` |
| `asistentes` | `Lista de asistentes` |

El título es **el mismo que aparece en el acta**, así que sirve para buscarlo con Ctrl+F. Si
el índice viene fuera de rango o la raíz no se reconoce, la ruta se deja tal cual: perder la
información sería peor que enseñar algo feo.

La cita de `evidencia` se limpia también de las marcas de la transcripción
(`[00:22:20] Interviniente B:`), que son ruido para ella; el tiempo no se pierde porque va
aparte, en su propia línea con el enlace.

## Relacionado

[[pipeline-plenos]], [[asistente-para-la-funcionaria]], [[diarizacion-como-andamiaje]],
[[persistir-lo-caro-antes-de-lo-fragil]], [[via-de-escape-en-el-esquema]],
[[bucle-generador-auditor-corrector]], [[por-que-plenos-en-local]]
