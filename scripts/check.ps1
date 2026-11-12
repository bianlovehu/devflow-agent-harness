# 文件用途：执行格式、静态检查、测试及可选的生产构建。
param([switch]$Build, [switch]$Integration)

. "$PSScriptRoot\env.ps1"

# 工程检查无论.env如何配置，都强制fake并暂时清空真实凭据；finally恢复调用终端。
$ProtectedNames = @('MODEL_PROVIDER', 'DASHSCOPE_API_KEY', 'DEEPSEEK_API_KEY', 'GITHUB_TOKEN', 'DEVFLOW_TEST_DATABASE')
$PreviousValues = @{}
foreach ($Name in $ProtectedNames) { $PreviousValues[$Name] = [Environment]::GetEnvironmentVariable($Name, 'Process') }
try {
    $env:MODEL_PROVIDER = 'fake'
    $env:DASHSCOPE_API_KEY = ''
    $env:DEEPSEEK_API_KEY = ''
    $env:GITHUB_TOKEN = ''
    Invoke-Checked { uv run --locked ruff check apps/api scripts }
    Invoke-Checked { uv run --locked ruff format --check apps/api scripts }
    $PreviousIntegration = $env:DEVFLOW_TEST_DATABASE
    try {
        if ($Integration) { $env:DEVFLOW_TEST_DATABASE = '1' }
        Invoke-Checked { uv run --locked pytest }
    } finally {
        $env:DEVFLOW_TEST_DATABASE = $PreviousIntegration
    }
    Push-Location -LiteralPath 'apps\web'
    try {
        Invoke-Checked { npm.cmd run api:check }
        Invoke-Checked { npm.cmd test }
        Invoke-Checked { npm.cmd run lint }
        Invoke-Checked { npm.cmd run typecheck }
        Invoke-Checked { npm.cmd run format:check }
        if ($Build) { Invoke-Checked { npm.cmd run build } }
    } finally {
        Pop-Location
    }
} finally {
    foreach ($Name in $ProtectedNames) { [Environment]::SetEnvironmentVariable($Name, $PreviousValues[$Name], 'Process') }
}
