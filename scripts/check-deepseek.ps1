# 文件用途：显式触发一次 DeepSeek 最小连通检查。
. "$PSScriptRoot\env.ps1"

# Explicitly performs one small, billable request to the official DeepSeek API.
Invoke-Checked { uv run --locked python -m devflow.model_probe }
