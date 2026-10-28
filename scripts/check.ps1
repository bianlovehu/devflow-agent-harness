# 文件用途：执行格式、静态检查、测试及可选的生产构建。
param([switch]$Build, [switch]$Integration)

. "$PSScriptRoot\env.ps1"

Invoke-Checked { uv run --locked ruff check apps/api scripts/build_fixtures.py }
Invoke-Checked { uv run --locked ruff format --check apps/api scripts/build_fixtures.py }
$PreviousIntegration = $env:DEVFLOW_TEST_DATABASE
try {
    if ($Integration) { $env:DEVFLOW_TEST_DATABASE = '1' }
    Invoke-Checked { uv run --locked pytest }
} finally {
    $env:DEVFLOW_TEST_DATABASE = $PreviousIntegration
}
Push-Location -LiteralPath 'apps\web'
try {
    Invoke-Checked { npm.cmd run lint }
    Invoke-Checked { npm.cmd run typecheck }
    Invoke-Checked { npm.cmd run format:check }
    if ($Build) { Invoke-Checked { npm.cmd run build } }
} finally {
    Pop-Location
}
