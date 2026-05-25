# Build completo: incrementa version en installer.iss, compila con PyInstaller y genera
# el instalador con Inno Setup. Si iscc.exe no esta instalado, lo descarga e instala.
$ErrorActionPreference = 'Stop'

# ── 1. Localizar iscc.exe (antes de tocar nada, fail-fast) ────────────────────
function Find-Iscc {
    $cmd = Get-Command iscc -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\iscc.exe",
        "$env:ProgramFiles\Inno Setup 6\iscc.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\iscc.exe"
    )) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

$iscc = Find-Iscc
if (-not $iscc) {
    Write-Host "Inno Setup no encontrado. Descargando e instalando..."
    $tmp = Join-Path $env:TEMP 'innosetup_install.exe'
    Invoke-WebRequest -Uri 'https://jrsoftware.org/download.php/is.exe' -OutFile $tmp -UseBasicParsing
    Write-Host "Instalando Inno Setup (silencioso)..."
    Start-Process $tmp -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-' -Wait
    Remove-Item $tmp -Force
    $iscc = Find-Iscc
    if (-not $iscc) {
        Write-Error "Inno Setup instalado pero iscc.exe no encontrado. Reinicia el terminal e intenta de nuevo."
        exit 1
    }
    Write-Host "Inno Setup instalado: $iscc"
}

# ── 2. Bump version en installer.iss ─────────────────────────────────────────
$iss = Join-Path $PSScriptRoot 'installer.iss'
$content = [IO.File]::ReadAllText($iss)

$m = [regex]::Match($content, '(?m)^#define AppVersion\s+"(\d+\.\d+)(?:\.(\d+))?"')
if (-not $m.Success) {
    Write-Error "No se encontro '#define AppVersion' en installer.iss"
    exit 1
}

$base     = $m.Groups[1].Value
$buildNum = if ($m.Groups[2].Value -ne '') { [int]$m.Groups[2].Value + 1 } else { 1 }
$newVer   = "$base.$buildNum"

$content = [regex]::Replace($content, '(?m)^#define AppVersion\s+"[\d.]+"', "#define AppVersion   `"$newVer`"")
[IO.File]::WriteAllText($iss, $content, (New-Object Text.UTF8Encoding $false))
Write-Host "Version actualizada: $newVer"

# ── 3. Build completo via build.bat (PyInstaller + iscc) ─────────────────────
$root = Split-Path $PSScriptRoot -Parent
$env:NOPAUSE = '1'
try {
    cmd /c "`"$root\build\build.bat`""
    $ec = $LASTEXITCODE
} finally {
    Remove-Item Env:NOPAUSE -ErrorAction SilentlyContinue
}

exit $ec
