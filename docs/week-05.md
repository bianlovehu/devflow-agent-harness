<!-- 文件用途：记录第17—20步实现、故障恢复验收、记忆审核流程和可重复检查。 -->
# 第五周：上下文、长期记忆和恢复

验收日期：2026-11-04。第17—20步已实现。新增功能使用现有 PostgreSQL、制品存储和只读工具，不增加 GitHub 写权限。数据库迁移头为 `0006_context_memory`。

## 第17步：上下文预算与压缩

- 系统指令和当前请求独立保存；会话历史、近期消息、旧对话摘要、人工批准经验和工具/检索结果分层组装。任务消息序号固定历史读取范围，后来的用户问题不会进入已创建任务。
- 默认每次输入保守估算上限 **12,000 token**，默认输出上限 **2,000 token**。分别由 `CONTEXT_INPUT_TOKENS` 和 `MODEL_MAX_OUTPUT_TOKENS` 配置，已有 `.env` 的显式值继续生效。
- 超限时依次去重、从低排名检索证据开始裁剪正文、压缩旧工具结果、对旧对话做可复核的抽取式摘要。保留系统指令、当前问题、约束与未解决事项、消息/证据/制品 ID、版本和原始行号；assistant 工具调用与 tool 返回消息保持配对。
- 无法在预算内保留必要材料时，在发请求前返回 `budget_exceeded`。任务累计调用数、工具数、token 和原始截止时间继续由业务层控制。
- `run_journal` 和不可变 trace 制品保留脱敏后的压缩前材料与实际请求。报告中的“上下文与恢复记录”支持按调用查看，展示压缩前后估算、节省量、实际 prompt usage 和估算误差。
- 估算采用 ASCII 每3字符、非 ASCII 按 UTF-8 字节的保守规则，不声称与供应商 tokenizer 相同；中断后无法确认的 usage 不记为零，额外请求前按该次输入估算与输出上限预留预算。

对应验证：`test_context_budget.py`、`test_long_conversation_runs_with_constraints_and_original_material`。长历史真实经过压缩后继续完成 Agent 分析，关键 owner_id/null 约束与原始材料均可回查。

## 第18步：可审核的长期记忆

在报告发现项或带引用的知识回答下点击“提取经验”。真实供应商由模型提出候选，离线模式明确标记为规则演示。客户端不能直接提供或伪造来源；服务端从成功报告复制已校验的引用。

候选保存仓库、摘要、来源运行和引用、适用完整 SHA、有效期、提取模型与 usage、审核状态。默认有效期30天，默认绑定报告提交。用户可以编辑摘要、有效期与适用提交；留空提交表示经人工审核的仓库通用经验。编辑会重新进入待审核，保存后才能批准。

只有同仓库、已批准、未过期且版本匹配的条目才进入上下文，最多6条；新会话、恢复以及每次实际模型请求前都重新检查。未批准、撤销、过期、被替代或提交不匹配的经验不会自动注入。历史经验仍是不可信资料，不能覆盖工具权限，也不能代替当前代码证据。

审核页位于 `/memories`，支持来源报告、引用、编辑、批准、撤销和批准时替代旧经验。替代操作在同一仓库锁和事务内将旧条目标记为 `superseded`。来源报告与原始引用保持可追溯。

对应验证：`test_memory_approval_version_expiry_revoke_edit_and_restart`、`test_replacement_expiry_and_repository_isolation`、`test_revoked_memory_disappears_before_next_model_request`。数据库连接池销毁并重建后仍能召回已批准经验。

## 第19步：checkpoint 与恢复

使用锁定版本的 `langgraph-checkpoint-postgres`，每个 run UUID 是独立 `thread_id`；业务会话历史仍保存在消息表。checkpoint 表位于独立 `devflow_checkpoints` schema，图以 `durability="sync"` 保存步骤状态，业务迁移管理 schema 生命周期，库自身 setup 管理内部表版本。实现依据 [LangGraph checkpointer 文档](https://docs.langchain.com/oss/python/langgraph/checkpointers) 和 [故障恢复与幂等文档](https://docs.langchain.com/oss/python/langgraph/fault-tolerance)。

业务表继续管理任务状态、租约、心跳、递增事件和恢复次数。checkpoint 每次写入也持有任务行锁并校验租约，旧 worker 不能在租约被接管后提交 checkpoint、journal 或最终结果。`run_journal` 对图节点和已完成读取工具提供幂等记录，恢复不重复已经完成的工具业务事件，最终报告与会话回复在同一事务中写入一次。

在线 worker 自动回收新 Agent 任务的过期租约，**最多自动恢复一次**。恢复复用原 run、输入快照、证据绑定和制品哈希，重新校验制品；缺失时进入待处理，不重新采集最新版本代替。再次失联、恢复失败或原始时限已过进入 `needs_attention`。用户仍可按原证据手动重试，重试是独立新 run。模拟和早期没有 checkpoint 标记的任务仍按原规则进入待处理。

恢复记录包括 `recovery_count`、`run.recovery_queued`、`run.resumed`、额外模型调用数、已知恢复 usage 和 `unknown_usage_calls`。模型请求发出前持久化计数；请求中途被杀时，供应商可能已经计费但未返回 usage，因此不承诺模型请求只发生一次。

验收不是在进程内模拟异常：`crash_worker.py` 启动独立真实 worker 子进程并以 `os._exit(73)` 强制退出，再使租约过期并启动新 worker。三个场景均完成恢复：

| 中断位置 | 恢复行为 | 核查点 |
|---|---|---|
| 工具结果持久化后、图节点 checkpoint 前 | 复用该结果，继续其余工具 | 已完成工具不重复执行，事件不重复 |
| 第二次模型请求过程中 | 从工具完成状态继续，重新发起模型请求 | 中断调用 usage 标记未知，增加恢复调用记录 |
| 报告保存前 | 从已完成图和 journal 取回报告 | 不再次请求模型，只保存一次最终报告与会话回复 |

另验证第二次租约失联停止自动恢复、旧令牌写入被拒、恢复遇缺失制品进入待处理。

## 第20步：安全边界与草稿

- 仓库代码、diff、Issue、文档、日志、会话历史和记忆都作为不可信资料处理。服务端工具白名单与仓库/版本限制继续生效；模型请求发布评论会得到 `unknown_tool`。
- 已知 GitHub Token、`sk-` 密钥、AWS access key、Bearer 和常见配置密钥格式在模型输入、工具响应、trace/journal 和 API JSON 输出中脱敏，保留换行与行号。本地不可变原始制品仍按原始哈希校验；不把脱敏展示误称为原始字节。
- 报告按 React 文本节点呈现，不执行模型 HTML；导出的模型字段继续转义 Markdown 元字符。草稿编辑器仅编辑当前页面内容，复制和下载都采用编辑后的草稿；切换运行会重新初始化草稿，并展示固定提交。
- PR 报告打开时通过只读 API 检查当前 head SHA，可手动重新检查；变化后标记旧结论。读取失败明确显示未完成核查，旧报告仍能打开。
- 前端代理只放行新增的本地记忆、上下文和版本检查接口，保留 Origin、参数与请求体限制。没有 GitHub 写接口。

## 真实模型验收

`uv run --locked python scripts/week05_smoke.py --real` 使用临时独立数据库和人工样例 PR #102，调用已配置的阿里云 `deepseek-v4.1-flash` 完成报告与候选提取。报告3次模型调用共 **16,865 token**，候选经验提取 **732 token**。候选包含 owner_id/actor_id 隔离的适用条件与建议，来源复制自报告中的已校验引用。

随后验证待审核条目不召回、批准后新会话召回、数据库重连、提交不匹配排除和撤销。新会话的组装验证使用明确标注的离线假模型，避免为同一工程边界增加真实请求。脱敏摘要与报告分别保存在 `data/week05-real-proof.json`、`data/week05-real-proof.md`；这些本地验收输出受 Git 忽略，临时数据库在退出时清理。

## 复现与使用

完整检查 `.\scripts\check.ps1 -Integration -Build` 已通过：后端 **202项**（含真实 PostgreSQL 隔离测试）、前端 **54项**，以及 Ruff、OpenAPI 类型同步、ESLint、TypeScript、Prettier 和 Next.js 生产构建。新增及编辑文件通过 CRLF 换行检查，`git diff --check` 无异常。

```powershell
. .\scripts\env.ps1
uv sync --locked
uv run --locked alembic upgrade head
# 完整工程检查，包含隔离 PostgreSQL 集成测试和前端生产构建
.\scripts\check.ps1 -Integration -Build
# 不调用真实模型的独立记忆流程验收
uv run --locked python scripts/week05_smoke.py
# 显式调用 .env 中真实供应商；使用临时测试库，不向 GitHub 写入
uv run --locked python scripts/week05_smoke.py --real
```

升级后重新启动 API、worker 和前端。打开已完成的报告，选择某个发现项“提取经验”，在“长期记忆”中编辑并批准，再创建同仓库同版本的新会话查看召回。查看报告的“上下文与恢复记录”可核对每次压缩与请求；草稿可直接编辑、复制和下载。

## 当前限制

记忆是最多6条的仓库/提交筛选，不做语义检索或自动事实认证；人工批准仍需要审阅证据。抽取式摘要保留识别出的约束句与来源指针，必要约束无法装入预算时明确停止。脱敏覆盖已知格式，不能识别任意自定义秘密。默认30天有效期通过读取时过滤实现，不依赖定时清理。

草稿修改保存在当前页面，刷新前应复制或下载。首次请求发出后立即崩溃的模型 usage 只能标记未知；checkpoint 不提供外部模型计费的 exactly-once 保证。第6周的固定效果评测、部署与求职材料尚未完成。
