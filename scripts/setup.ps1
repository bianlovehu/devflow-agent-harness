# 文件用途：安装锁定依赖，启动数据库并执行迁移和样例导入。
param([switch]$SkipDatabase)

. "$PSScriptRoot\env.ps1"

foreach ($Tool in @('uv', 'git')) {
    if (-not (Get-Command $Tool -ErrorAction SilentlyContinue)) {
        throw "Install $Tool first; see README.md."
    }
}

$CurrentNodeVersion = if (Get-Command node -ErrorAction SilentlyContinue) { & node --version } else { '' }
if ($CurrentNodeVersion -ne $NodeVersion) {
    [System.IO.Directory]::CreateDirectory((Join-Path $ProjectRoot '.tools')) | Out-Null
    $ArchiveName = "node-$NodeVersion-win-x64.zip"
    $ArchivePath = Join-Path $ProjectRoot ".tools\$ArchiveName"
    Write-Host "Downloading project-local Node.js $NodeVersion..."
    Invoke-WebRequest -Uri "https://nodejs.org/dist/$NodeVersion/$ArchiveName" -OutFile $ArchivePath
    $Checksums = (Invoke-WebRequest -Uri "https://nodejs.org/dist/$NodeVersion/SHASUMS256.txt").Content
    $ExpectedHash = ($Checksums -split "`n" | Where-Object { $_.TrimEnd().EndsWith($ArchiveName) }) -split '\s+' | Select-Object -First 1
    if ((Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedHash) {
        throw 'Node.js archive SHA256 mismatch.'
    }
    Expand-Archive -LiteralPath $ArchivePath -DestinationPath (Join-Path $ProjectRoot '.tools') -Force
    $env:PATH = "$LocalNodeDirectory;$env:PATH"
}

# 仅首次复制示例配置，重复初始化保留用户已经填写的密钥。
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
if (-not (Test-Path -LiteralPath 'apps\web\.env.local')) {
    Copy-Item -LiteralPath 'apps\web\.env.example' -Destination 'apps\web\.env.local'
}
$PythonVersion = (Get-Content -LiteralPath '.python-version' -Raw).Trim()
Invoke-Checked { uv python install $PythonVersion --no-registry }
Invoke-Checked { uv sync --locked }
Push-Location -LiteralPath 'apps\web'
try { Invoke-Checked { npm.cmd ci --no-audit --no-fund } } finally { Pop-Location }

if (-not $SkipDatabase) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Install Docker Desktop first.' }
    Invoke-Checked { docker compose up -d --wait --wait-timeout 120 db }
    Invoke-Checked { uv run --locked alembic upgrade head }
    Invoke-Checked { uv run --locked python -m devflow.import_fixtures }
}
Write-Host 'Setup complete. Start API and web in separate terminals using scripts/dev.ps1.'
