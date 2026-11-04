<!-- 文件用途：记录第三周第9—12步的实现、可复核验收和边界。 -->
# 第三周：PR 审查和 CI 排障

完成日期：2026-10-29（Asia/Shanghai）。承接第二周现有工作区，实现第9—12步。用户指定采用阿里云百炼 API，模型为 `deepseek-v4.1-flash`；真实请求使用用户提供的北京工作空间 Base URL，密钥仅存于被 Git 忽略的根目录 `.env`。

## 第9步：模型入口

- `model_gateway.py` 统一消息、工具 schema、超时、非思考模式、usage 和错误分类，兼容阿里云/DeepSeek 官方接口。阿里云端点限定官方 HTTPS 主机和兼容模式路径，禁止跟随重定向；不向前端返回密钥。
- 模型 HTTP 请求不自动重试；401/403、402、429、网络/服务端错误、输出格式错误分别记录。JSON/报告校验失败最多修正一次，修正也占用模型和 token 预算。
- `ScriptedModel` 供回归注入；`FixtureModel` 仅用于 fixture 演示，依靠实际工具返回片段，不读取 `evals/`。真实 GitHub 分析不会静默切换到假模型。
- `week03_model_probe.py` 显式验证真实模型选工具、消费工具结果、返回并校验 JSON。阿里云实测成功，两次小请求、一次工具调用，共394 tokens。普通浏览、健康检查和自动化测试不访问真实模型。

## 第10步：只读工具网关

固定白名单：`get_pr`、`read_evidence`、`read_file`、`get_ci`、`read_log`、`get_linked_issues`、`search_knowledge`。最后一个明确返回 `knowledge_not_ready`，第四周再接 RAG。

网关只读取当前任务绑定的制品，参数由 Pydantic 校验；仓库 ID、完整提交、路径、证据 ID 和行号均在服务端检查。未知工具和跨仓库请求返回结构化错误。证据目录与正文分离，目录不算已读证据。参数最多8000字符，单次结果最多12000字符，正文按最多100行和7000字符返回原始行号、下一页位置及全文制品 ID。超长单行明确报错。相同参数复用结果并记录 duplicate，仍计入任务工具次数。

工具执行不访问任意 URL、shell 或 GitHub 写 API。远端只读采集沿用第二周适配器的超时、有限重试和限流；工具阶段使用已固定的本地材料。PR 可采集同 head 的 CI 与同仓库关联 Issue，fixture PR 同样固定相关 CI 快照。CI 优先采集失败 job，保留 run attempt/job 身份与全文指针。大范围/缺失日志仍保留采集缺口。

## 第11步：LangGraph 与 PR 审查

`context → model → tools → model/结束` 采用实际安装并锁定的 LangGraph。业务预算、取消与租约检查放在图外，模型不能扩大权限或预算。每个模型调用、工具调用及用量写入现有持久化事件时间线。模型请求预留输入与输出预算，达到次数、时长或 token 限额时终止。

报告固定包含摘要、风险项、严重程度、证据、建议、未确认事项及检查范围；CI 额外包含失败阶段和验证步骤。只有当前任务实际返回过的证据行段才允许成为最终引用。不存在、越界或未读引用会触发至多一次修正，仍失败则不给出有效报告。

任务配置保存系统提示词、提示词版本、结果 schema、模型/供应商/端点、预算及应用代码 SHA256。请求/响应、工具定义与 usage 保存为哈希制品，成功/失败事件提供 trace artifact ID；不记录 API Key 或鉴权响应头。报告服务端补充实际读取范围与采集缺口。

## 第12步：CI 报告与交互

`pr_review` 与 `ci_debug` 共用持久化任务入口。日志按错误关键词提取上下文，仍使用原始日志行号，可切换逐行补查。没有日志时进入待处理，不能只凭元数据捏造根因。

工作台展示严重程度卡片、失败阶段、验证步骤、建议、未确认事项、范围、用量及时间线。引用可展开原始代码/日志并高亮；可停止任务、按原证据重试、复制和下载 Markdown 草稿。所有生成内容标为分析建议；React 作为文本渲染，Markdown 导出转义 HTML/链接等结构字符。

## 真实验收

以下任务均由阿里云 `deepseek-v4.1-flash` 运行，报告、证据与调用记录已保存在本地数据库和 `data/`。未发评论、提交 review、修改代码或重跑 GitHub CI。

| 案例 | 任务 ID | 结果 |
|---|---|---|
| 人工 PR #102 | `e31de57b-868f-49ce-ab88-cbcf1e941994` | 成功，引用 base/head 与 diff 定位移除 owner 筛选 |
| 人工 CI #201 | `f04acd79-0c68-44d7-8994-450882652c2d` | 成功，分析 null 标签测试的 ValueError |
| [公开 pydantic PR #14103](https://github.com/pydantic/pydantic/pull/14103) | `2cb01799-fefb-47d6-a94a-d0b44547390c` | 最终提示词v2成功，检查固定文件与 diff，未确认新缺陷；4次模型、7次工具调用，共33360 tokens |
| [公开失败 CI 40847897235](https://github.com/pydantic/pydantic/actions/runs/40847897235) | `76eeaa79-a0ac-472c-bf4f-8fa86fd3c89b` | v2成功，job `123359802431` 的165行日志指向 artifact 下载步骤无匹配 run；4次模型、6次工具，共33094 tokens |

公开 PR 固定 base `0453f38e7e3f309894a6e7fc5848eef5e945a8c5`、head `8724553d50d506b25d17968df0eb384d5dee32cf`；CI 固定 head `becee9cc0ef8132e854762448fde76aa56608c6b`、attempt 1。上述公共案例通过已授权 GitHub 连接器 GET 取得真实元数据、文件和日志，再绑定到同一业务任务执行器；文件导入前校验 Git blob SHA，制品另存 SHA256。连接器返回的是解码文本，不能据此声称验证了下载响应的原始网络字节。

**采集限制如实记录：**首次直接用匿名 GitHub 适配器采集 PR 的任务 `0fe649d3-9d36-4049-8e98-7bf3cc492fdb` 因匿名配额耗尽失败，记录了冷却提示。随后使用用户已连接的 GitHub 只读账号取得快照完成上述分析。生产应用直读受限日志仍需服务端配置合适的 GitHub 只读 Token；连接器账号没有写入应用 `.env`。快照导入仅是显式 CLI 验收入口，不宣称网页可复用连接器凭据。

证明文件：`data/week03-aliyun-fixture-proof.json`、`data/week03-github-pr-connector-v2-proof.json`、`data/week03-github-ci-connector-v2-proof.json`。公开采集快照和生成的 Markdown 同在 `data/`，均被 Git 忽略。早期v1报告保留为历史任务，最终v2提示词进一步要求不强报风格偏好、重复根因或未证实推测。

## 回归与复现

```powershell
. .\scripts\env.ps1
# 默认无外部调用的单元/集成/生产构建检查
powershell -ExecutionPolicy Bypass -File scripts/check.ps1 -Integration -Build
# 显式的真实模型工具调用与 JSON 检查（会产生 API 用量）
uv run --locked python scripts/week03_model_probe.py
# 离线假模型的两个演示任务
uv run --locked python scripts/week03_smoke.py --fake --output data/week03-fake-proof.json
# 用当前供应商执行人工样例分析（会产生 API 用量）
uv run --locked python scripts/week03_smoke.py
# 直接读取公开仓库，须按当前已同步列表选择目标；API 限流与权限仍生效
uv run --locked python scripts/week03_smoke.py --github owner/repo --pr 123 --ci 456
# 已采集公开快照的显式复验（仍调用真实模型）
uv run --locked python scripts/week03_smoke.py --snapshot data/week03-ci-connector-snapshot.json
```

回归覆盖所有6个 fixture 案例、正常 PR 不强报风险、未知/跨仓库工具、非法路径/提交、分页/超长结果、重复调用、模型401/402/429/服务错误、阿里云参数、坏引用、最多一次修正、预算终止、报告持久化/导出和模型返回后取消。第二周并发、租约、证据和 SSE 测试继续保留。

最终统一验收通过：后端155项、前端43项测试；Ruff/格式、OpenAPI一致性、ESLint、TypeScript、Prettier与 Next.js 生产构建全部通过。浏览器实测报告加载、引用展开显示原始行号、Markdown下载成功；下载文件5937字节、CRLF且无孤立LF。代码/文本换行和 `git diff --check` 另行检查。

## 当前边界

- 尚未接入 RAG、长期记忆和 checkpoint 自动恢复，分别按第四/五周计划实现；失联任务继续进入待处理。
- 报告是待核验建议。引用校验能保证来源和行号有效，不能自动证明模型推理正确；不将模型的泛化建议等同于已复现缺陷。
- 停止会阻止下一次模型/工具调用和结果提交；已发出的只读请求等待当前超时结束，已发生的模型用量无法撤回。
- 为保证没有密钥也能演示，`.env.example` 默认 fake；本机按用户要求显式采用 aliyun。真实仓库不会静默降级到 fixture/fake。

协议依据：[阿里云 DeepSeek API](https://help.aliyun.com/zh/model-studio/deepseek-api)、[DeepSeek Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)、[JSON Output](https://api-docs.deepseek.com/guides/json_mode/)、[LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)。

## 完整性审查补充（2026-10-29）

后续独立审查补齐模型异常/用量、取消和超时留痕、剩余总时长、日志错误块分页及正文未读提示。后端回归增至170项，前端43项与生产构建通过；4个历史真实验收任务的报告、引用和制品再次核验一致。详见[当前进展报告](progress-report-2026-10-29.md)。
