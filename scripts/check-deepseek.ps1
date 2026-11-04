# 文件用途：显式检查当前模型供应商（支持阿里云）的最小连通性。
. "$PSScriptRoot\env.ps1"

# Explicitly performs a small, billable request to the configured provider.
Invoke-Checked { uv run --locked python -m devflow.model_probe }
