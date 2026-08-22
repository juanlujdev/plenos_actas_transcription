---
type: concept
date_updated: 2026-08-22
source_count: 2
---

# Por qué el pipeline de plenos se ejecuta a mano y no automatizado

Es la **divergencia mayor entre [[2026-07-31-plenos-youtube-pipeline-design]] y [[pipeline-plenos]]**. La spec diseñaba publicación totalmente automática; la implementación acabó siendo manual. No fue un recorte de alcance: la automatización se construyó entera, se probó y se eliminó.

## Lo que se construyó y luego se borró

Las tareas 4-7 del plan implementaron y commitearon: sondeo del feed RSS del canal (`parsear_feed`), gestión de estado con reintentos (`plenos_state.json`, `es_nuevo`, `registrar_fallo`, máx. 3 intentos), modo `--mode scan`, avisos de Telegram de éxito y error, el workflow `.github/workflows/plenos-scan.yml` con cron cada 2h, y el trigger correspondiente en `deploy.yml`. Todo eso se eliminó el 2026-08-08.

## Causa raíz

**YouTube bloquea a yt-dlp desde las IPs de datacenter de GitHub Actions.** El error exacto, obtenido tras instrumentar el código para exponer el `stderr` del subproceso:

> `ERROR: [youtube] 5UETzjDRRtw: Sign in to confirm you're not a bot. Use --cookies-from-browser or --cookies for the authentication.`

Desde la IP residencial del desarrollador, el mismo comando funciona sin problema.

**Cuidado con confundirlo con otro 403.** El 2026-08-22, desde esa misma IP residencial,
yt-dlp devolvió `HTTP Error 403: Forbidden` en todos los clientes de YouTube. No era este
bloqueo: la versión instalada (`2026.07.04`) había quedado desfasada frente a los cambios
de YouTube, y `pip install -U yt-dlp` lo resolvió. El bloqueo por IP de datacenter dice
literalmente *"Sign in to confirm you're not a bot"*; un 403 seco es otra cosa. La spec ya anticipaba este riesgo y proponía como plan B el secret `YT_COOKIES` con cookies de una cuenta de Google.

## Por qué se descartó el plan B de las cookies

Se llegó a preparar (perfil de Chrome aislado, cuenta secundaria, exportación en formato Netscape, workflow modificado para volcar el secret a fichero), pero se abandonó antes de usarlo por tres razones:

1. **Las cookies caducan y rotan.** Google las invalida por su cuenta; no hay forma de hacerlas permanentes. Cada caducidad significaría re-exportarlas y actualizar el secret.
2. **El fallo sería silencioso y diferido.** Con cron automático, cuando caducasen llegarían tres avisos de Telegram de error y el pleno quedaría marcado como fallido, requiriendo reproceso manual — es decir, el trabajo manual reaparece igual, pero en el peor momento.
3. **Riesgo para la cuenta.** Las cookies son credenciales de sesión completas; usarlas desde IPs de datacenter puede acarrear restricciones a esa cuenta de Google.

## Por qué la ejecución manual es aceptable aquí

- **Los plenos son mensuales.** Un comando al mes frente a mantener infraestructura, cookies y un cron que consume minutos de Actions en un repo privado.
- **El usuario ya controla todos los commits del proyecto** (ver la política de git de este repo), así que el paso manual encaja en un flujo que ya era manual.
- **Recupera la revisión humana previa**, que la spec había sacrificado conscientemente. Para un documento público sobre votaciones municipales eso es una mejora, no una pérdida: la propia spec listaba las "pruebas con audio real" como una de sus tres capas de garantía, y esta es justamente esa capa, hecha permanente.

## Alternativas evaluadas y descartadas

| Alternativa | Por qué no |
|---|---|
| Enviar el audio por Telegram al bot existente | La Bot API solo deja **descargar 20 MB**; un pleno de 4h son ~55 MB |
| Runner autoalojado de GitHub Actions | Funciona (IP residencial, sin cookies) pero exige un PC encendido y mantener el servicio |
| Carpeta compartida (Drive/OneDrive) con quien sube el vídeo | Viable y elimina YouTube del camino; es la evolución natural si algún día se quiere automatizar. La spec ya la dejaba apuntada como "fase final desacoplada" |

## Consecuencias en el resto del sistema

`deploy.yml` volvió exactamente a su estado anterior: sin el workflow de plenos en su lista de `workflow_run` y con el gate mirando solo `eventos.json` (ver [[gate-deploy-condicional]]). El pipeline de plenos **no participa en ningún disparo automático de deploy**: el commit manual a `main` dispara el deploy como cualquier otro push.

## Relacionado

[[pipeline-plenos]], [[2026-07-31-plenos-youtube-pipeline-design]], [[github-actions]], [[gate-deploy-condicional]], [[hostinger-deploy]]
