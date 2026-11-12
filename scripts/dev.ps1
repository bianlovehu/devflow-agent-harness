# 文件用途：按指定目标启动 API、前端或数据库开发服务。
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('api', 'web', 'db', 'status', 'worker')]
    [string]$Target
)

. "$PSScriptRoot\env.ps1"

switch ($Target) {
    'api' { Invoke-Checked { uv run --locked uvicorn devflow.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir apps/api/src } }
    'worker' {
        if (-not $env:DEVFLOW_WORKER_HEARTBEAT) {
            $env:DEVFLOW_WORKER_HEARTBEAT = Join-Path $ProjectRoot 'data\worker-heartbeat.json'
        }
        [System.IO.Directory]::CreateDirectory((Split-Path -Parent $env:DEVFLOW_WORKER_HEARTBEAT)) | Out-Null
        Invoke-Checked { uv run --locked python -m devflow.worker }
    }
    'web' {
        Push-Location -LiteralPath 'apps\web'
        try { Invoke-Checked { npm.cmd run dev } } finally { Pop-Location }
    }
    'db' { Invoke-Checked { docker compose up -d --wait --wait-timeout 120 db } }
    'status' {
        Invoke-Checked { docker compose ps }
        Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/health' | ConvertTo-Json -Depth 6
        Invoke-RestMethod -Uri 'http://127.0.0.1:3000/api/health' | ConvertTo-Json -Depth 6
        if (-not $env:DEVFLOW_WORKER_HEARTBEAT) {
            $env:DEVFLOW_WORKER_HEARTBEAT = Join-Path $ProjectRoot 'data\worker-heartbeat.json'
        }
        Invoke-Checked { uv run --locked python -m devflow.healthcheck worker }
    }
}
