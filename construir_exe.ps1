# Construye la carpeta que se copia al PC del Ayuntamiento.
# Uso:  powershell -ExecutionPolicy Bypass -File scripts\construir_exe.ps1
$ErrorActionPreference = "Stop"

$raiz    = Split-Path -Parent $PSScriptRoot
$destino = Join-Path $raiz "entrega\Actas de Plenos del Ayuntamiento"
$config  = Join-Path $destino "Configuración (no tocar)"

pyinstaller --onefile --console --noconfirm `
    --name "Generar acta de un pleno" `
    --distpath $destino `
    --workpath (Join-Path $raiz "build") `
    --specpath (Join-Path $raiz "build") `
    --paths (Join-Path $raiz "scripts") `
    --add-data "$(Join-Path $raiz 'scripts\plantillas');plantillas" `
    --hidden-import plenos_informe `
    --hidden-import plenos_acta `
    --exclude-module matplotlib `
    --exclude-module IPython `
    --exclude-module rich `
    (Join-Path $raiz "scripts\asistente_plenos.py")

New-Item -ItemType Directory -Force -Path (Join-Path $config "registros") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $destino "Actas generadas") | Out-Null

Copy-Item (Join-Path $raiz "scripts\asistente\LEEME.txt") `
          (Join-Path $destino "LÉEME - Cómo generar un acta.txt") -Force

# Las claves no se pisan nunca: si ya hay un configuracion.env, se respeta.
$env_file = Join-Path $config "configuracion.env"
if (-not (Test-Path $env_file)) {
    # Out-File -Encoding utf8 mete BOM siempre en Windows PowerShell 5.1, y
    # python-dotenv sin utf-8-sig pierde la primera clave del fichero si lleva BOM.
    # Se escribe sin BOM para que la primera clave se lea bien tal cual, y de paso
    # coincide con lo que hace falta si algún día se lee sin utf-8-sig.
    $contenido = @"
ASSEMBLYAI_API_KEY=
OPENROUTER_API_KEY=
GROQ_API_KEY=
ACTAS_DIR=
"@
    [System.IO.File]::WriteAllText($env_file, $contenido, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Creado $env_file - RELLENA LAS CLAVES antes de entregarlo."
}

# yt-dlp oficial: se baja la última versión al construir y luego se actualiza solo
# en el PC del Ayuntamiento con "yt-dlp -U".
$yt = Join-Path $config "yt-dlp.exe"
if (-not (Test-Path $yt)) {
    Invoke-WebRequest -Uri "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" `
                      -OutFile $yt
}

Write-Host ""
Write-Host "Listo: $destino"