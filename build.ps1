$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

# Keep the source tree free of __pycache__ folders during the build.
$env:PYTHONDONTWRITEBYTECODE = "1"

# Fail fast if the active Python environment does not match constraints.txt.
# Install the pinned set with: python -m pip install -c constraints.txt -e .[build]
python -B packaging_support\check_constraints.py
if ($LASTEXITCODE -ne 0) {
    throw "Fix the Python environment: python -m pip install -c constraints.txt -e .[build]"
}

$Version = (& python -B -c "import sys; sys.path.insert(0, 'src'); from pdf_toolbox.build_metadata import APP_VERSION; print(APP_VERSION)")
$AppName = "PDF Toolbox"
$ReleaseRoot = Join-Path $Root "release"
$DistStandaloneExe = Join-Path $Root "dist\$AppName.exe"
$ReleaseExe = Join-Path $ReleaseRoot "PDF-Toolbox-$Version.exe"

foreach ($FullPath in @(
    (Join-Path $Root "build"),
    (Join-Path $Root "dist"),
    $ReleaseExe
)) {
    if ((Test-Path -LiteralPath $FullPath) -and ($FullPath.StartsWith($Root))) {
        Remove-Item -LiteralPath $FullPath -Recurse -Force
    }
}

# One-file, windowed, UPX off (see pdf_toolbox_onefile.spec).
python -B -m PyInstaller --clean --noconfirm pdf_toolbox_onefile.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

if (-not (Test-Path -LiteralPath $DistStandaloneExe)) {
    throw "One-file build failed: $AppName.exe was not created."
}

New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null
Copy-Item -LiteralPath $DistStandaloneExe -Destination $ReleaseExe -Force

$SizeMb = [math]::Round((Get-Item -LiteralPath $ReleaseExe).Length / 1MB, 1)
Write-Host "Release created: $ReleaseExe ($SizeMb MB)"
