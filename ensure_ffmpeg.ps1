# Ensures ffmpeg\ffmpeg.exe + ffmpeg\ffprobe.exe in the repo (for `python gui/app.py`).
# NOT used by PyInstaller anymore — the installed .exe downloads FFmpeg on first run to AppData.
# Run from repo root: powershell -ExecutionPolicy Bypass -File ensure_ffmpeg.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$destDir = Join-Path $PSScriptRoot 'ffmpeg'
$ff = Join-Path $destDir 'ffmpeg.exe'
$fp = Join-Path $destDir 'ffprobe.exe'

if ((Test-Path -LiteralPath $ff) -and (Test-Path -LiteralPath $fp)) {
    Write-Host '[OK] ffmpeg\ already contains ffmpeg.exe and ffprobe.exe'
    exit 0
}

New-Item -ItemType Directory -Force -Path $destDir | Out-Null

$url = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'
$zip = Join-Path $env:TEMP ("gc_ffmpeg_dl_{0}.zip" -f [Guid]::NewGuid().ToString('N'))
$extract = Join-Path $env:TEMP ("gc_ffmpeg_x_{0}" -f [Guid]::NewGuid().ToString('N'))

try {
    Write-Host '[INFO] Downloading FFmpeg (BtbN win64 GPL, ~100MB)...'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing

    Write-Host '[INFO] Extracting...'
    Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force

    $top = Get-ChildItem -LiteralPath $extract -Directory -ErrorAction Stop | Select-Object -First 1
    if (-not $top) { throw 'Archive has no top-level folder' }
    $bin = Join-Path $top.FullName 'bin'
    if (-not (Test-Path -LiteralPath $bin)) { throw "No bin folder under $($top.Name)" }

    $srcFf = Join-Path $bin 'ffmpeg.exe'
    $srcFp = Join-Path $bin 'ffprobe.exe'
    if (-not (Test-Path -LiteralPath $srcFf)) { throw 'ffmpeg.exe not found in archive' }
    if (-not (Test-Path -LiteralPath $srcFp)) { throw 'ffprobe.exe not found in archive' }

    Copy-Item -LiteralPath $srcFf -Destination $ff -Force
    Copy-Item -LiteralPath $srcFp -Destination $fp -Force
    Write-Host '[OK] Copied ffmpeg.exe and ffprobe.exe into ffmpeg\'
    exit 0
}
catch {
    Write-Host "[ERROR] $($_.Exception.Message)"
    exit 1
}
finally {
    Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $extract) {
        Remove-Item -LiteralPath $extract -Recurse -Force -ErrorAction SilentlyContinue
    }
}
