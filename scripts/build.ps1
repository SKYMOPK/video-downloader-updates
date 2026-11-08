param([switch]$SkipTests, [string]$Compiler = "")
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$releaseIdentity = Get-Content -LiteralPath 'app\release.json' -Raw | ConvertFrom-Json
$appVersion = $releaseIdentity.version
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    uv sync --frozen
    if ($LASTEXITCODE -ne 0) { throw '無法建立開發環境' }
}
if (-not $SkipTests) {
    & .venv\Scripts\python.exe -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw '測試失敗，停止建置' }
}
& .venv\Scripts\python.exe scripts\verify_tools.py
if ($LASTEXITCODE -ne 0) { throw '依賴完整性檢查失敗' }
$priorPath = $env:PATH
try {
    # Exclude unrelated host software's DLL directories from dependency scanning.
    $pythonBase = & .venv\Scripts\python.exe -c 'import sys; print(sys.base_prefix)'
    $env:PATH = "$projectRoot\.venv\Scripts;$pythonBase;$env:WINDIR\System32;$env:WINDIR"
    & .venv\Scripts\pyinstaller.exe --noconfirm --onefile --windowed --name app-updater --paths $projectRoot --distpath build\updater-dist --workpath build\updater-work --specpath build scripts\apply_update.py
    if ($LASTEXITCODE -ne 0) { throw '更新程式封裝失敗' }
    & .venv\Scripts\pyinstaller.exe --noconfirm VideoDownloader.spec
    if ($LASTEXITCODE -ne 0) { throw '封裝失敗' }
} finally {
    $env:PATH = $priorPath
}
Copy-Item -LiteralPath 'README.md','THIRD_PARTY_NOTICES.md','requirements-lock.txt' -Destination 'dist\VideoDownloader'
Copy-Item -LiteralPath 'docs' -Destination 'dist\VideoDownloader' -Recurse -Force
& .venv\Scripts\python.exe scripts\package_update.py
if ($LASTEXITCODE -ne 0) { throw '完整更新包產生失敗' }
if (-not $Compiler) {
    $candidates = @("$projectRoot\build-tools\Inno\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe")
    $Compiler = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if ($Compiler) {
    & $Compiler "/DAppVersion=$appVersion" installer.iss
    if ($LASTEXITCODE -ne 0) { throw '安裝套件建置失敗' }
} else {
    Write-Output '可攜版已產生於 dist\VideoDownloader；安裝包需 Inno Setup 6，使用 -Compiler 指定 ISCC.exe'
}
