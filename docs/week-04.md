<!-- 文件用途：记录第四周 RAG 演示版的实现、复现方法、验收证据与边界。 -->
# 第四周：加入 RAG，形成可演示版本

2026-11-02 完成第 13—16 步，交付本地 v0.1。此前编号“第 4 步”是前端工作台，本记录对应开发计划中“第 4 周：加入 RAG”。

## 实现与验收映射

| 步骤 | 已实现 | 主要证据 |
|---|---|---|
| 13 文档导入与版本 | 仓库内 UTF-8 Markdown/TXT、文本 PDF；5 MiB、50 页、100 万字符、512 块限制；上传原件 SHA256、来源、版本、解析/索引失败原因；同内容去重，同名更新；删除有效索引 | `knowledge.py`、`knowledge_api.py`、迁移 `0005_knowledge_rag`、`test_knowledge.py`、`test_week04_integration.py` |
| 14 本地向量与混合检索 | 固定 E5 ONNX int8 + tokenizer，CPU 推理、均值池化与 L2 归一化、query/passage 前缀；按模型及内容缓存向量；中文分词与英文标识符共用规则；pgvector 精确余弦召回 + PostgreSQL GIN 关键词召回各前 20，RRF(k=60) 返回最多 6 | `embeddings.py`、`prepare_rag.py`、检索调试页面、缓存与仓库隔离测试、本机 smoke 记录 |
| 15 Agent 接入 | `search_knowledge` 工具、`knowledge_qa` 任务；PR/CI 可选择加入资料；检索结果绑定到任务的不可变文档证据；报告校验已读证据 ID 和原文行号；无依据明确说明证据不足 | `worker.py`、`tool_gateway.py`、`reports.py`、真实/假模型演示报告 |
| 16 演示版 | 知识库上传、索引状态、版本和带行号文本预览；显示文档来源、PDF 页码、向量/关键词排序和融合分；问答及风险引用可展开；Markdown 导出；仓库到知识库和工作台导航 | `/knowledge`、仓库分析表单、报告页面、本记录三分钟脚本 |

## 初始化与复现

先按 README 完成 `setup.ps1`，确保数据库、依赖就绪。在项目根目录执行：

```powershell
. .\scripts\env.ps1
uv run --locked alembic upgrade head
uv run --locked python scripts/prepare_rag.py
# 只导入 4 份原有中文资料和 1 份英文策略，不创建分析任务、不调用模型 API
uv run --locked python scripts/week04_smoke.py --import-only
```

首次下载约 135 MB，文件放在被 Git 忽略的 `data/models/`。程序固定仓库、40 位 revision、模型和 tokenizer 的 SHA256。下载由显式准备命令执行，普通上传、检索、启动不会联网下载；缺失或损坏时给出准备提示。权重到位后可离线运行检索。

模型采用 [Xenova 的 E5 ONNX 转换](https://huggingface.co/Xenova/multilingual-e5-small)，revision 为 `761b726dd34fb83930e26aab4e9ac3899aa1fa78`。前缀、池化和归一化遵循 [原始 multilingual-e5-small 模型说明](https://huggingface.co/intfloat/multilingual-e5-small)。分块使用同一 tokenizer 的完整 offset，默认 384 token、48 token 重叠，优先使用标题与段落边界；推理时另使用有 512 token 上限的 tokenizer，避免长文分块被提前截断。

启动 API、web、worker：

```powershell
# 三个终端分别运行，参照 README
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 api
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 web
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 worker
```

工作入口：[知识库](http://127.0.0.1:3000/knowledge?repo=repo-taskboard)、[样例仓库](http://127.0.0.1:3000/repositories/repo-taskboard)、[分析工作台](http://127.0.0.1:3000/runs?repo=repo-taskboard)。

完整演示数据可由脚本生成；它只领取自己创建的 run，不领取其他排队任务，可与常驻 worker 并行时发生领取竞争，因此建议生成期间先停止常驻 worker。

```powershell
# 真实本地向量 + 离线假模型；明确标识 fake，不产生模型 API 用量
uv run --locked python scripts/week04_smoke.py
# 显式使用 .env 配置的真实模型；本机使用 aliyun / deepseek-v4.1-flash
uv run --locked python scripts/week04_smoke.py --real --output data/week04-real-proof.json
# 可选：只验证知识问答 / PR 对照 / CI 链路
uv run --locked python scripts/week04_smoke.py --task knowledge_qa
```

脚本验证 3 个中文检索问题，其中包含英文策略的召回；生成知识问答、同一问题的直接 PR 分析和加入资料后的 PR 分析、CI #202 标签空值排障。任务和证据保存在数据库；JSON 摘要和 Markdown 草稿保存在 `data/`。真实模型调用记录、用量、检索排序、引用均可在任务与制品中核查。历史资料始终不替代固定提交代码或本次 CI 日志。

## 三分钟演示

| 时间 | 操作 | 展示重点 |
|---|---|---|
| 0:00—0:35 | 打开知识库，选择 `devflow-demo/taskboard`，预览 `access-policy.md` 和英文策略 | 来源为人工样例、当前版本、SHA256、原文行号；已有上传按钮与索引状态 |
| 0:35—1:00 | 输入“用户能否看到其他人的任务？”并检索；切换“仅关键词”再检索 | 中文问题能命中中文/英文资料；各召回排名、RRF 分和版本均可查。排序变化不等同于已证明整体效果提升 |
| 1:00—1:40 | 打开生成的知识问答任务，展开回答引用 | 模型通过工具检索后回答；原始文档、固定版本和行号可核查 |
| 1:40—2:20 | 打开 PR #102 的两份演示报告，或从相同问题表单分别关闭/开启 RAG | 直接分析依据固定代码；加入资料后能引用 AUTH-01 设计约束。无须把文档当作当前运行状态 |
| 2:20—3:00 | 打开 CI #202 报告，展开日志与历史复盘引用，再下载 Markdown | 当前日志与历史知识职责清楚；报告是建议，具备检查范围和未确认事项 |

另可上传自己的小型 `.md` 文档，再用同名文件更新；版本下拉可对照旧原文。删除会移除关联索引，后续检索不再使用该文档。重新上传可恢复同名文档并重建索引。

## 版本、失败和隔离语义

- 新任务保存当时的有效文档版本 ID；工具再与当前有效版本取交集。排队期间更新/删除时，不会静默换成新的正文，可能返回证据不足，需要重新创建任务。
- 检索成功后，引用绑定到任务证据和不可变制品；之后删除知识库文档不破坏已有报告核查。删除是退出有效知识库并移除索引，历史版本、原件和向量内容缓存为追溯保留，不是隐私擦除功能。
- 更新解析失败时保留此前成功索引的有效版本。若索引期间发生删除或更高版本已完成，旧索引结果不能恢复文档或覆盖新版本；失败记录保留原因。
- 同内容重复上传返回已有有效版本。若一个已有文档更新为另一文档已有的内容，则合并到已有文档并停用被替换正文，防止旧内容继续召回。
- 列表、预览、删除、检索均校验仓库及数据源。召回前先限定仓库、有效版本和模型版本，再排序与取前 20；不能先跨仓库召回后过滤。
- 模型与文档失败不返回 SQL、密钥或解析异常原文。文件名不作为存储路径；所有正文均作为不可信资料，前端只按文本展示，不执行 HTML。

## 检查与限制

自动检查入口包含后端格式/静态检查、单元与隔离 PostgreSQL 集成测试、OpenAPI 生成一致性、前端回归、lint、类型、格式和生产构建：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/check.ps1 -Integration -Build
```

新增测试覆盖长段落完整性与重叠、PDF 文本与页码、扫描件/加密/损坏错误、内容去重、有效版本切换、更新失败、删除索引与旧引用保留、仓库隔离、重复块向量缓存、并发更新/删除、排队任务版本固定、空库问答证据不足。默认测试使用可替换向量适配器与假模型，不下载权重或请求真实 API；本机 smoke 单独验证真实 ONNX 和阿里云模型。

当前索引在上传请求中同步完成，状态先提交为 `indexing`，失败保存为 `failed`。进程在索引期间终止可能留下 indexing 记录，可重新上传重试；尚未实现后台索引任务恢复。单个请求可能等待本地 CPU 推理，前端代理为知识库请求单独设置 180 秒超时。

PDF 仅支持文本提取，不做 OCR，也不承诺还原多栏阅读顺序。预览标注的是提取文本的行号，同时保留页码映射。当前向量检索使用 pgvector 精确扫描，面向小型本地资料库；尚无大规模延迟、Recall@6 或模型效果评测结论，向量最低相似度 0.75 只是当前实现的粗过滤。长期记忆、checkpoint 自动恢复和完整评测仍属于第 5—6 周。

## 本机验收记录（2026-11-02）

- `scripts/check.ps1 -Integration -Build` 全部通过：后端 184 项测试、前端 48 项测试；OpenAPI 生成一致、Ruff、ESLint、类型检查、Prettier 与生产构建通过。随后对最后的文件模式与资源过滤修正补跑 23 项相关测试，全部通过；迁移检查无差异，在线健康检查为 ok。
- 真实 ONNX 长文检查：含中文、英文、emoji 的长段落切成 17 块，最大 384 token，末段保留。浏览器中纯中文问题召回英文策略，英文策略的关键词排名为空、向量排名第 5，说明该条来自向量召回。
- 常驻 worker 验证：任务 `c6f8e78f-d67f-482d-9785-eb8b089a23b3` 经数据库排队，由独立 worker 领取并完成，HTTP 查询返回 succeeded，报告有文档引用；该项明确使用 fake，不请求真实模型。摘要位于 `data/week04-background-proof.json`。

本次真实模型记录如下，均为 `aliyun / deepseek-v4.1-flash`，摘要保存在 `data/week04-real-proof.json`：

| 演示 | 任务 | 模型/工具调用 | token 用量 |
|---|---|---|---|
| 知识问答 | [abc84a96](http://127.0.0.1:3000/runs/abc84a96-15eb-4898-9b3e-d1c5f8e1df15) | 3 / 2 | 22,893 |
| PR #102 直接分析 | [84b6fca0](http://127.0.0.1:3000/runs/84b6fca0-96bf-4062-aab5-459f7b7db738) | 4 / 10 | 22,827 |
| PR #102 加入资料 | [c9719d97](http://127.0.0.1:3000/runs/c9719d97-bb79-4508-8441-0fb9f9612da5) | 3 / 8 | 20,857 |
| CI #202 结合复盘 | [d1a6d487](http://127.0.0.1:3000/runs/d1a6d487-c9ed-465e-a4ad-d466faca1325) | 3 / 3 | 20,433 |

知识问答首次报告触发一次格式/引用修正，修正后通过校验；其余三项无需修正。这些是小样例功能演示，不能据此推断 RAG 总体节省 token 或提升准确率。PR 对照使用相同问题，仅切换是否加入资料。

验收截图保存在 `data/week04-knowledge.jpg`。下载的权重、运行数据、截图和服务日志都受 Git 忽略；源码、迁移、样例、锁文件与文档可正常提交。文本/代码文件使用 CRLF。
