$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$distDir = Join-Path $root "dist"
$buildDir = Join-Path $root "build"
$installerOutDir = Join-Path $root "installer_output"
$appInternalName = "finance_tool"

if (Test-Path $distDir) { Remove-Item $distDir -Recurse -Force }
if (Test-Path $buildDir) { Remove-Item $buildDir -Recurse -Force }
if (Test-Path $installerOutDir) { Remove-Item $installerOutDir -Recurse -Force }

$pyArgs = @(
    "-3.11",
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name", $appInternalName,
    "--distpath", "dist",
    "--workpath", "build",
    "--add-data", "db\schema.sql;db",
    "--add-data", "assets\app.ico;assets",
    "--icon", "assets\app.ico",
    "main.pyw"
)

& py $pyArgs

$builtExe = Join-Path $root "dist\$appInternalName\$appInternalName.exe"
if (!(Test-Path $builtExe)) {
    throw "Built executable not found: $builtExe"
}

$iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (!(Test-Path $iscc)) {
    $iscc = "C:\Program Files\Inno Setup 6\ISCC.exe"
}
if (!(Test-Path $iscc)) {
    $iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
}

if (!(Test-Path $iscc)) {
    throw "Inno Setup compiler not found: ISCC.exe"
}

& $iscc "installer.iss"

Write-Host ""
Write-Host "Installer output directory: $installerOutDir"
