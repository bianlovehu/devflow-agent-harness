# 文件用途：按指定目标启动 API、前端或数据库开发服务。
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('api', 'web', 'db', 'status')]
    [string]$Target
)

. "$PSScriptRoot\env.ps1"

switch ($Target) {
    'api' { Invoke-Checked { uv run --locked uvicorn devflow.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir apps/api/src } }
    'web' {
        Push-Location -LiteralPath 'apps\web'
        try { Invoke-Checked { npm.cmd run dev } } finally { Pop-Location }
    }
    'db' { Invoke-Checked { docker compose up -d --wait --wait-timeout 120 db } }
    'status' {
        Invoke-Checked { docker compose ps }
        Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/health' | ConvertTo-Json -Depth 6
    }
}
