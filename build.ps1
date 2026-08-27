$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Version = (& python -c "import sys; sys.path.insert(0, 'src'); from pdf_toolbox.build_metadata import APP_VERSION; print(APP_VERSION)")
$AppName = "PDF Toolbox"
$ReleaseRoot = Join-Path $Root "release"
$ReleaseDir = Join-Path $ReleaseRoot "PDF-Toolbox-v$Version"
$DistAppDir = Join-Path $Root "dist\$AppName"
$DistStandaloneExe = Join-Path $Root "dist\$AppName.exe"
$ReleaseAppDir = Join-Path $ReleaseDir $AppName
$ReleaseStandaloneExe = Join-Path $ReleaseDir "$AppName.exe"
$ReleaseStandaloneCopyExe = Join-Path $ReleaseRoot "PDF-Toolbox-v$Version-Standalone.exe"
$ZipPath = Join-Path $ReleaseRoot "PDF-Toolbox-v$Version-Windows.zip"

foreach ($FullPath in @(
    (Join-Path $Root "build"),
    (Join-Path $Root "dist"),
    $ReleaseDir,
    $ZipPath
)) {
    if ((Test-Path -LiteralPath $FullPath) -and ($FullPath.StartsWith($Root))) {
        Remove-Item -LiteralPath $FullPath -Recurse -Force
    }
}

python -m PyInstaller --clean --noconfirm pdf_toolbox.spec

if (-not (Test-Path -LiteralPath (Join-Path $DistAppDir "$AppName.exe"))) {
    throw "Build failed: $AppName.exe was not created."
}

New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
Copy-Item -LiteralPath $DistAppDir -Destination $ReleaseAppDir -Recurse
Copy-Item -LiteralPath (Join-Path $Root "README.md") -Destination $ReleaseDir

if (Test-Path -LiteralPath (Join-Path $Root "LICENSE")) {
    Copy-Item -LiteralPath (Join-Path $Root "LICENSE") -Destination $ReleaseDir
}

python -m PyInstaller --clean --noconfirm pdf_toolbox_onefile.spec

if (-not (Test-Path -LiteralPath $DistStandaloneExe)) {
    throw "One-file build failed: $AppName.exe was not created."
}

Copy-Item -LiteralPath $DistStandaloneExe -Destination $ReleaseStandaloneExe -Force
Copy-Item -LiteralPath $DistStandaloneExe -Destination $ReleaseStandaloneCopyExe -Force

$ZipCreated = $false
foreach ($Attempt in 1..3) {
    try {
        Start-Sleep -Seconds 1
        Compress-Archive -LiteralPath $ReleaseDir -DestinationPath $ZipPath -Force
        $ZipCreated = $true
        break
    }
    catch {
        if ($Attempt -eq 3) {
            Write-Warning "ZIP creation skipped because Windows kept a build file locked: $($_.Exception.Message)"
        }
    }
}

Write-Host "Release created:"
Write-Host "  $ReleaseStandaloneExe"
Write-Host "  $ReleaseStandaloneCopyExe"
Write-Host "  $ReleaseAppDir"
if ($ZipCreated) {
    Write-Host "  $ZipPath"
}
