# 只读代码证据 MCP

DevFlow 的新 PR/CI 分析任务默认使用官方 Python SDK `mcp==2.3.0`，通过真实 `stdio` 子进程访问固定提交的代码。浏览器继续使用原 HTTP 代码接口；模型仍通过 Function Calling 请求现有工具网关，不直接连接 MCP。

```text
模型 → ToolGateway → 任务级 MCP Client → stdio Server → code.service
                        ↓ 校验固定版本、正文及哈希
                   证据关联 + RunJournal 原子提交 → 返回模型
```

## 启动与依赖

执行 `uv sync --locked` 并按原流程启动 API、worker、前端即可。无需手工启动 MCP 服务或开放新端口。worker 在代码快照准备完成后、第一次模型调用前启动独立服务进程，任务完成、取消或异常退出后关闭连接。没有可用快照时只使用原有证据，并在报告注明检查范围受限。

```dotenv
# 启动含协议协商和工具发现，范围 0.1～10 秒
MCP_STARTUP_TIMEOUT_SECONDS=10
# 单次协议调用，范围 0.1～5 秒；同时受任务剩余时间限制
MCP_TOOL_TIMEOUT_SECONDS=5
CODE_RG_PATH=rg
```

本地需要 ripgrep，可通过 `CODE_RG_PATH` 指定可执行文件。普通 GitHub Actions 测试任务现在也安装 ripgrep 并检查版本。原镜像已安装固定版本，无需新增队列或数据库迁移。准备快照不调用模型；`scripts/check.ps1 -Integration -Build` 强制使用假模型。

## 工具契约与访问范围

| 模型工具 | MCP 工具 | 作用 |
| --- | --- | --- |
| `list_code_tree` | `repo_tree` | 按目录分页列举任务固定快照，最多 20 项 |
| `search_code` | `repo_search` | 字面量搜索，最多 20 个匹配片段或路径 |
| `read_file` 的新补查 | `repo_read` | 读取固定文件片段，最多 100 行 |

输入复用严格 Pydantic schema（拒绝额外参数），输出采用严格 schema 的 `ok/data/error` 包络。公开 HTTP 与 MCP 共用 `code.service`；提交、快照 ID、清单/文件哈希、覆盖信息和行号语义相同。模型已绑定文件证据的读取仍可在 Host 本地完成；目录与仅路径搜索不算正文已读。

服务固定名称 `devflow-code-evidence`、版本 `1.0.0`、契约 `code-evidence-v1`。Host 比较服务身份、完整工具白名单、规范化输入/输出 schema SHA-256；服务返回的描述不会变成系统提示词。实际协商的协议版本随 SDK 记录，不写死成预设协议版本。

服务每次调用独立校验任务运行状态、当前租约、取消状态、仓库、完整提交和任务绑定的快照。路径只用来查快照清单，不能指定宿主机文件。数据库每个会话执行 `SET TRANSACTION READ ONLY`；服务没有下载、模型、代码执行、数据库写入工具。子进程只得到数据库、制品根目录、ripgrep 和任务授权所需配置，不加载项目 `.env`，不传模型或 GitHub 密钥。

这些是应用内权限约束，不是操作系统沙箱。数据库连接配置通过私有子进程环境传入，不能记录环境内容。诊断写 stderr，stdout 只用于 MCP 消息。SDK 使用独立进程组或 Windows Job Object 清理进程树；POSIX 另有父进程死亡检查。

## 证据与恢复

新任务配置保存 `code_backend=mcp-stdio-v1`、契约版本；旧任务缺少该字段时保持内部函数路径。不会在恢复时升级执行方式。

- 先查 `code-tool:<规范化请求哈希>`；成功结果和终止错误均可回放，不依赖服务在线。
- 新结果由 Host 核对仓库、提交、快照、文件哈希和实际原文。服务本身不建立证据。
- 证据关联、裁剪后最终结果和服务身份在同一事务提交，提交时检查 worker 租约；只有返回的正文行记为已读。
- 事务前退出安全重读同一快照；事务后或 checkpoint 前退出直接回放相同结果、证据 ID 和版本。
- `mcp:contract` 保存实际服务、协议和 schema 哈希；恢复进程必须匹配。契约不兼容仍能回放旧结果，不能按新契约继续补查。
- 服务不可用时不会回退到内部函数，不会用新分支替代旧材料。制品缺失/损坏明确报错，不重新下载来掩盖问题。
- 同一任务不自动重连或重试协议失败；关闭 SDK 协议结果缓存和自动补输入循环，回放统一使用 journal。畸形协议消息或收到工具契约变更通知时停止新补查。模型可继续用已有材料；复核阶段失败保留原报告并增加未确认说明。

## 观测和排障

任务时间线以中文显示连接、失败、补查、回放和关闭事件。工具详情保留服务版本、协议、契约哈希、耗时、结果长度、实际返回证据行范围和错误码；trace 也保存这些字段。`GET /api/v1/runtime` 的 `code_mcp` 只说明配置能力，状态为 `not_connected`，不冒充已经建立连接。实际状态以各任务事件为准。

| 错误码 | 含义及处理 |
| --- | --- |
| `mcp_start_failed` / `mcp_start_timeout` | 子进程启动或协商失败/超时；检查当前虚拟环境、SDK 锁版本和 worker 日志 |
| `mcp_contract_mismatch` | 服务身份、工具或保存的契约不一致；已有结果可回放，原任务不继续新补查 |
| `mcp_disconnected` / `mcp_timeout` | 服务退出或调用超时；保留已有证据，不自动重试 |
| `mcp_result_invalid` | 输出 schema、来源、哈希或正文不符；停止后续协议补查 |
| `mcp_task_denied` | 任务停止、取消或租约过期；旧进程不能继续读取 |
| `tool_repository_denied` / `code_commit_denied` | 仓库或提交超出本任务权限 |
| `code_snapshot_not_ready` | 未绑定可用固定快照；不会改用后来的材料 |
| `code_file_skipped` / `artifact_missing` / `artifact_corrupt` | 文件不在可读范围或制品异常，检查清单和制品存储 |
| `code_search_unavailable` / `code_search_timeout` | ripgrep 缺失或搜索投影准备超时 |

搜索进程在已有时间预算内受控；执行中超时会返回 `truncated=true`、`truncation_reason=timeout`，不能把不完整搜索解释成没有匹配。

## 验证入口

`test_mcp_contract.py` 验证 schema 和白名单；`test_code_mcp.py` 用官方 SDK 和真实子进程验证协议、HTTP 一致性、授权、异常、回放和清理；`test_code_integration.py` 验证受控假模型搜索/读取/引用和真实进程中断恢复；`test_report_review.py` 验证复核服务失败保留报告。

完整检查：`scripts/check.ps1 -Integration -Build`。这些测试只修改随机隔离测试库与临时制品，不发起付费模型请求、不修改 GitHub。

参考：[官方 Python SDK](https://github.com/modelcontextprotocol/python-sdk)、[MCP 架构](https://modelcontextprotocol.io/docs/learn/architecture)。

本次本地结果和仍需处理的运行事项见 [2026-11-17 验收记录](code-evidence-mcp-verification-20261117.md)。
