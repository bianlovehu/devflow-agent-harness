# 文件用途：为当前终端加载项目专用工具链和缓存路径。
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:UV_CACHE_DIR = Join-Path $ProjectRoot '.cache\uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $ProjectRoot '.tools\python'
$env:UV_PYTHON_DOWNLOADS_JSON_URL = Join-Path $ProjectRoot 'infra\python-downloads.json'
$env:npm_config_cache = Join-Path $ProjectRoot '.cache\npm'
$env:npm_config_registry = 'https://registry.npmjs.org/'
$env:NEXT_TELEMETRY_DISABLED = '1'
$NodeVersion = (Get-Content -LiteralPath (Join-Path $ProjectRoot '.node-version') -Raw).Trim()
$LocalNodeDirectory = Join-Path $ProjectRoot ".tools\node-$NodeVersion-win-x64"
if (Test-Path -LiteralPath (Join-Path $LocalNodeDirectory 'node.exe')) {
    $env:PATH = "$LocalNodeDirectory;$env:PATH"
}

function Invoke-Checked {
    param([scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}
