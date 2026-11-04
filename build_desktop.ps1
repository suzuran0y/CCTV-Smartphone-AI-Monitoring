param([string]$Python = "$PSScriptRoot\.local-validation\desktop-build-env\Scripts\python.exe")
$ErrorActionPreference = 'Stop'
$outputRoot = Join-Path $PSScriptRoot ('.local-validation\desktop-build-' + (Get-Date -Format 'yyyyMMdd-HHmmssfff'))
Push-Location -LiteralPath $PSScriptRoot
try {
    & $Python -I -m PyInstaller --name Sentinel --onedir --windowed --noupx `
        --workpath (Join-Path $outputRoot 'work') --distpath (Join-Path $outputRoot 'dist') --specpath $outputRoot `
        --icon "$PSScriptRoot/assets/sentinel-camera.ico" --add-data "$PSScriptRoot/assets/sentinel-camera.ico:assets" `
        --add-data "$PSScriptRoot/version.properties:." --add-data "$PSScriptRoot/app/web/templates:app/web/templates" `
        --add-data "$PSScriptRoot/app/web/static:app/web/static" --add-data "$PSScriptRoot/app/desktop/templates:app/desktop/templates" `
        --add-data "$PSScriptRoot/app/desktop/static:app/desktop/static" --collect-all webview `
        "$PSScriptRoot/sentinel_desktop.py"
    if ($LASTEXITCODE -ne 0) { throw 'Sentinel Desktop build failed.' }
    Write-Output (Join-Path $outputRoot 'dist\Sentinel\Sentinel.exe')
} finally {
    Pop-Location
}
