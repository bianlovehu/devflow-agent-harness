<!-- 文件用途：介绍项目范围、启动命令与开发验证方式。 -->
# DevFlow Agent Harness

面向 PR 审查与 CI 排障的研发协作 Agent Harness，提供版本化证据、任务持久化和可复现演示案例。基于 FastAPI、Next.js 和 PostgreSQL，按 [六周开发计划](docs/development-plan.md) 独立实现。

当前已完成**第 1—21 步，包含前五周功能与固定评测闭环**：GitHub 只读数据、固定版本证据、持久化 worker、SSE 进度、PR 审查、CI 排障，以及仓库内的文档知识库和 RAG 知识问答。支持本地 CPU 多语言向量、关键词混合检索、文档版本/删除和可点击引用。模型入口支持阿里云百炼的 DeepSeek 4.1、DeepSeek 官方 API 与离线假模型；报告包含经校验的证据引用、检查范围和 Markdown 草稿。新增上下文预算与压缩、人工审核的长期记忆、PostgreSQL checkpoint 恢复、可编辑草稿和 PR 版本变化检查，详见 [第五周验收记录](docs/week-05.md)。系统不执行被分析仓库的代码。实现与三分钟演示见 [第四周验收记录](docs/week-04.md)，前三周记录见 [第三周验收记录](docs/week-03.md) 和 [完整性审查报告](docs/progress-report-2026-10-29.md)。

当前范围（2026-11-11）：完善本地运行及真实评测闭环；发布封装和跨机器部署验收已取消。启动/排障见[本地运行手册](docs/local-runbook.md)，第22—24步状态见[核对表](docs/release-checklist.md)。 第22步两组真实对照、开发/新留出及GPT复核结果见[真实基线报告](docs/real-baseline-report.md)，其中保留未通过结果与限制。任务4的[报告复核与补查](docs/report-review.md)沿用原任务和费用限制，模型意见不等于认证正确。[20题对照结果](docs/report-review-baseline.md)保留目标错误9份→7份、1处新退步以及费用和耗时增加。

## 环境

- Windows x64，PowerShell 5.1 或 PowerShell 7。
- Git、[uv](https://docs.astral.sh/uv/getting-started/installation/)、Docker Desktop（Linux containers）。
- 固定 Python 版本见 `.python-version`，固定 Node 24 版本见 `.node-version`。
- Python 下载元数据固定在 `infra/python-downloads.json`，包含官方构建地址和 SHA256，可供当前机器的旧 uv 使用。
- 初始化脚本将 Node/Python 安装到项目的 `.tools/`，将缓存放在 `.cache/`，无需更换系统版本。
- 首次安装需要访问 Node.js、Python 发布源、PyPI、npm 与 Docker Hub。

## 从新终端启动

先启动 Docker Desktop，等待 Linux 引擎就绪。在项目根目录运行：

```powershell
cd D:\DevFlow
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

脚本会保留已有配置，首次从 `.env.example` 复制 `.env`，安装锁定依赖，启动数据库，执行迁移与幂等样例导入。前端服务端地址单独保存在 `apps/web/.env.local`。这些命令使用进程级执行策略，不修改系统策略。

然后分别打开三个终端：

```powershell
cd D:\DevFlow
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 api
```

```powershell
cd D:\DevFlow
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 web
```

```powershell
cd D:\DevFlow
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 worker
```

worker 与 API 使用同一份 `.env` 和数据卷。未启动 worker 时任务保留在队列，页面关闭不取消任务。停止按钮才会请求取消；新 Agent 任务的租约失联后，在线 worker 自动恢复一次，复用原证据和已完成步骤；再次失联或恢复失败进入待处理。模拟/旧版本任务仍需手动重试。恢复不重置原任务时限，可能产生额外模型费用，用量未知的中断调用会明确标注。

- 工作台：http://127.0.0.1:3000
- 样例仓库：http://127.0.0.1:3000/repositories
- 会话与任务：http://127.0.0.1:3000/runs
- 文档知识库与知识问答：http://127.0.0.1:3000/knowledge
- OpenAPI 文档：http://127.0.0.1:8000/api/docs
- 完整健康检查：http://127.0.0.1:8000/api/v1/health
- 存活检查：http://127.0.0.1:8000/api/v1/health/live

首页每 15 秒读取实际服务状态，也可以手动重新检测。正常时 API、数据库、pgvector、迁移四项均显示「已就绪」；数据库不可用时 API 返回 HTTP 503，存活检查仍返回 200；后端不可用时首页给出启动提示。首次打开页面可能需要等待 Next.js 编译。

所有服务仅监听本机回环地址。默认数据库凭据仅用于本地开发，样例浏览无需 GitHub 与模型密钥；可按下文显式配置模型。

## 日常命令

```powershell
# 先载入当前终端的本地工具链与缓存路径
. .\scripts\env.ps1

# 数据库启动 / 查看 / 停止（停止保留数据卷）
docker compose up -d --wait db
docker compose ps
docker compose stop db

# 迁移：应用、查看、生成下一步业务迁移
uv run --locked python -m devflow.bootstrap
uv run --locked alembic current
uv run --locked alembic revision --autogenerate -m "add business tables"

# Python 锁定依赖；前端在 apps/web 内使用 npm ci
uv sync --locked

# 格式、静态检查与单元测试
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1

# 另加真实数据库集成检查与前端生产构建
powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1 -Integration -Build
```

Python 依赖锁在根目录 `uv.lock`，前端依赖锁在 `apps/web/package-lock.json`。使用 uv 和 npm 官方命令更新锁文件；项目文本保存为 CRLF。Ruff、Prettier 和 EditorConfig 均已配置 CRLF。

如果暂时无法使用 Docker，可以运行 `setup.ps1 -SkipDatabase` 后启动前后端，查看数据库未就绪状态；这不满足第 1 步完整验收。

## 目录

```text
apps/
  api/
    src/devflow/        API、配置、数据库与健康检查
    migrations/        Alembic 环境与迁移
    tests/             单元与显式启用的真实数据库检查
  web/                 Next.js App Router / TypeScript / Tailwind / TanStack Query
fixtures/              演示工程、PR 快照与 diff、CI 日志和项目资料
evals/fixtures/        原有 6 个样例参考标注
evals/devflow-v1/      30 题固定评测输入与独立标注（开发 20 / 留出 10）
scripts/               初始化、开发启动、样例生成与检查入口
docs/                  开发计划与步骤验收记录
compose.yaml           本地db与保留的完整容器配置；日常只需启动db
pyproject.toml          Python 项目配置与 Ruff/pytest 配置
```

业务接口使用 `/api/v1` 前缀。前端通过自身的 `/api/health` 和受白名单约束的 `/api/backend` 服务端代理访问 API，不将后端凭据暴露给浏览器。健康检查执行有超时的数据库查询，既检查连接，也检查扩展与迁移状态；错误响应不包含连接密码或 SQL 异常原文。

迁移 `0001_enable_pgvector` 负责启用扩展，并创建 Alembic 版本记录；第 3 步再添加业务表。回滚初始迁移会保留可能被共享使用的 vector 扩展。

## 常见问题

- **Docker named pipe 不存在：** 启动 Docker Desktop，确认使用 Linux containers，然后执行 `docker info`。
- **端口 5432 已占用：** 修改根目录 `.env` 中 `POSTGRES_PORT`，重新创建 db 容器并重启 API。
- **数据库已连接但扩展/迁移待配置：** 执行 `uv run --locked python -m devflow.bootstrap`。
- **修改数据库密码后连接失败：** 既有数据卷保留原密码，修改 `.env` 不会自动变更数据库内的用户密码。
- **后端地址变化：** 修改 `apps/web/.env.local` 中的 `BACKEND_URL`，重启前端。
- **初始化下载失败：** 确认上述发布源可访问后重跑脚本；已有配置和数据库卷会保留。

验收与限制见 [第 1 步记录](docs/step-01.md) 、[第 2 步记录](docs/step-02.md) 、[第 3 步记录](docs/step-03.md) 、[第 4 步记录](docs/step-04.md) 和 [第 5 步记录](docs/step-05.md)。普通浏览与自动测试不调用真实模型。

## 样例数据与数据源

默认使用 DATA_SOURCE=fixture 和 FIXTURE_STORAGE=database，无需外部密钥即可浏览数据库中已导入的样例。显式设置 FIXTURE_STORAGE=files 可进行离线只读浏览。页面和响应均标明 fixture；真实 GitHub 只读适配器已接入，配置方式见下文。

样例数据已随项目提供。需要重新生成时，在根目录执行：

```powershell
. .\scripts\env.ps1
uv run --locked python scripts/build_fixtures.py
# 重新生成或编辑资料后执行 python -m devflow.import_fixtures；文件模式需重启 API 重新载入缓存。
```

生成器仅在 .cache 中的自建临时仓库执行 Git；固定的提交和文本哈希可复现。参考标注单独放在 evals/fixtures，不进入业务 API。示例工程基础测试：

```powershell
uv run --locked pytest fixtures/taskboard/seed/tests -c fixtures/taskboard/seed/pyproject.toml
```

## 模型服务端配置

`.env.example` 默认 `MODEL_PROVIDER=fake`，无需密钥即可生成明确标记的离线演示报告。真实分析可选 `aliyun` 或 `deepseek`，密钥只填根目录 `.env`，不放入浏览器或源码。当前本机按用户要求已配置阿里云 DeepSeek 4.1。

```dotenv
MODEL_PROVIDER=aliyun
ANALYSIS_EXECUTOR=agent
DASHSCOPE_API_KEY=
DASHSCOPE_BASE_URL=https://<工作空间ID>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL=deepseek-v4.1-flash
```

使用控制台实际工作空间与地域的 Base URL。切换供应商或修改密钥后重启 API 和 worker。若使用 DeepSeek 官方接口，改用 `MODEL_PROVIDER=deepseek` 并填写 `DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL`。

普通浏览、健康检查和自动化测试不调用真实模型。创建分析任务时独立 worker 才会按配置发起请求；真实调用会产生 API 用量。显式检查命令：

```powershell
. .\scripts\env.ps1
# 当前供应商的最小连通检查
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-deepseek.ps1
# 完整的工具选择、工具结果与结构化 JSON 验证
uv run --locked python scripts/week03_model_probe.py
# 人工 PR/CI 样例完整分析；加 --fake 则不访问模型 API
uv run --locked python scripts/week03_smoke.py
```

页面的供应商/模型标签仅反映服务端配置；真实请求是否成功请查看任务事件与错误码。详见 [第三周验收记录](docs/week-03.md)。


## 数据持久化与代码阅读

数据库迁移完成后，重复导入样例不会新增同一条记录：

```powershell
. .\scripts\env.ps1
uv run --locked python -m devflow.bootstrap
uv run --locked python -m devflow.import_fixtures
uv run --locked alembic check
```

会话、消息、任务及其固定版本证据使用 PostgreSQL 保存；大文本制品位于被 Git 忽略的 data/artifacts。验收写入接口可在 API 文档中查看。创建任务后立即返回 queued 记录，独立 worker 按所选供应商分析；fake 是离线演示，aliyun/deepseek 会产生真实 API 用量。

代码阅读入口：[文件用途索引](docs/file-guide.md)、[业务模型](apps/api/src/devflow/models.py)、[事务服务](apps/api/src/devflow/workflows.py)、[第 3 步验收](docs/step-03.md)。源码与可注释配置含用途说明，关键实现处另有中文注释。


## 分析工作台与接口契约

进入仓库并选择 PR 或 CI，在分析入口填写问题并选择会话。创建成功后跳转到 `/runs/{runId}`，直达链接和刷新都能恢复同一任务。宽屏显示会话、任务与报告、证据三栏；较窄窗口用「任务与报告」「证据」标签切换。任务创建使用幂等键，网络错误重试同一输入时复用原任务。

当前创建的任务立即返回 ID，由独立 worker 领取并执行模型与工具循环。页面显示引用报告、SSE 时间线、停止、按原证据重试和 Markdown 草稿导出；旧模拟任务仍明确标识为模拟结果。第4步以前创建的旧任务保留原配置，可停止后按原证据重试。文件浏览模式仍可查看资源，创建入口提示切换数据库模式。证据从任务绑定的制品读取，显示证据 ID、固定版本、行号与字节 SHA256，不用最新资源替换历史材料。

前端业务类型由 FastAPI OpenAPI 离线生成，不需要启动 API、连接数据库或配置模型 Key。修改后端契约后执行：

```powershell
. .\scripts\env.ps1
Push-Location apps/web
npm.cmd run api:generate
npm.cmd run api:check
npm.cmd test
Pop-Location
```

生成器使用项目 `.venv` 的 Python，可用 `DEVFLOW_PYTHON` 显式指定。生成文件 `apps/web/src/lib/generated/api.d.ts` 随源码保存，不手工修改。`scripts/check.ps1` 已包含生成差异检查和前端回归测试。


## GitHub 只读模式

默认继续使用样例模式，已有会话和任务保留。使用真实仓库时，在根目录 `.env` 中设置：

```dotenv
DATA_SOURCE=github
GITHUB_TOKEN=
GITHUB_TIMEOUT_SECONDS=30
```

重启API并刷新浏览器，然后进入仓库页填写 `https://github.com/owner/repo`，也接受 `owner/repo`。普通公开仓库可匿名读取；私有仓库和受限日志需要在服务端配置Token。Token不要填写在网页中，也不要写入源码。

建议创建限定到所选仓库的 fine-grained Token，只开启 Metadata、Contents、Pull requests、Issues、Actions 所需的读取权限。程序不自动修改Token权限，对GitHub仅发送GET。日志签名地址仅在内存中处理，下载时不转发Token。

添加或刷新会把仓库元数据及最近20条PR、20条CI摘要写入PostgreSQL。界面标明已同步数量、抓取时间和未覆盖全部数据；选择资源后才读取详情。上游权限失败时保留之前成功的摘要和原抓取时间，同时显示原因。刷新只影响当前浏览数据，不改写已有样例任务证据。

读取默认单次超时30秒，一次业务读取累计最多60秒。网络和服务端临时错误最多重试2次；限流遵守Retry-After或reset时间，较长等待直接返回429。进程内按主机与令牌摘要共享冷却状态，切换页面不会提前重试GitHub。前端也显示倒计时。

当前支持GitHub.com，仓库需已有默认分支和提交。PR最多读取300个变更文件，CI最多读取200个job；超过范围或缺少patch时明确标注。Issue关联仅识别PR正文中的同仓库引用，最多读取5条，不代表平台全部关联关系。仓库详情属于实时预览；创建任务后按固定提交和 CI attempt 保存文件、日志与证据，历史任务不跟随预览变化。

运行中的CI或没有关联PR的运行会按实际状态显示。日志按job读取，页面最多预览前2000行；未就绪、过期、权限拒绝分别给出错误。GitHub可能对不可见的私有资源返回404，系统会显示“资源不存在或当前账号无权查看”，不会声称能从404唯一判断实际原因。

切回 `DATA_SOURCE=fixture` 并重启API，可继续使用原样例数据。生产服务与写请求来源校验默认使用本机3000端口。


## 第二周：证据、worker 和进度

- PR 任务创建时固定本地已同步摘要中的 base/head SHA；worker 在读取变更列表前后检查这两个 SHA。若发生变化，返回 `input_changed`，需刷新仓库再创建新任务。
- 按提交读取普通 UTF-8 文件，支持 Python、JS/TS、JSON/YAML/TOML/INI 等配置和 Markdown。缺失或截断 patch 保留不完整标识；两个版本可读取时补生成完整 diff。拒绝符号链接、子模块、路径穿越、二进制与超限文件。
- 每次最多采集 50 个变更文件、20 个 job，单文件 256 KiB，总证据 8 MiB；大范围和不可读资源在检查范围中保留缺口。CI 固定 head、run attempt 和 job ID；日志原始字节不改写，内容 SHA256 覆盖实际保存字节。
- `POST /runs/{id}/cancel` 幂等取消；`POST /runs/{id}/retry` 需要 `Idempotency-Key`，产生新的 run 并复用原证据。PR 版本已变化且尚未采集证据时，应刷新后新建任务。
- `GET /runs/{id}/events?after=N` 读取事件；`GET /runs/{id}/stream` 支持 `Last-Event-ID` 或 `after` 续传。传输断开不取消任务；前端按序号去重，历史记录从数据库恢复。

```powershell
. .\scripts\env.ps1
# 只执行一个排队任务；常驻 worker 使用上面的 dev.ps1 worker
uv run --locked python -m devflow.worker --once
# 保存样例任务与证据验收摘要，写入本地 data/（请勿与常驻 worker 同时执行）
uv run --locked python scripts/week02_smoke.py
# 显式读取公开真实仓库，不调用模型
uv run --locked python scripts/week02_smoke.py --github pallets/flask --output data/week02-github-proof.json
```

完整能力、验证映射、实际进程失联与重连记录及已知限制见 [第二周验收记录](docs/week-02.md)。

## 文档知识库与 RAG 演示

完成依赖与数据库初始化后，显式准备一次本地向量模型并导入知识样例：

```powershell
. .\scripts\env.ps1
uv run --locked python -m devflow.bootstrap
uv run --locked python scripts/prepare_rag.py
uv run --locked python scripts/week04_smoke.py --import-only
# 使用真实本地向量与离线假模型生成问答、PR 对照、CI 报告
uv run --locked python scripts/week04_smoke.py
```

打开 [知识库](http://127.0.0.1:3000/knowledge?repo=repo-taskboard)，可上传 Markdown/TXT/文本 PDF、查看版本与原文、调试混合检索并创建知识问答。PR/CI 表单的“加入项目资料（RAG）”开关支持同一问题的前后对照。任务引用绑定到不可变文档证据；文档更新、删除后，未来检索只使用有效版本，已生成的历史报告仍可核查。

`week04_smoke.py` 默认不调用真实模型；加 `--real` 显式使用 `.env` 中的供应商。切换 fixture/GitHub 模式仍按上文配置并重启 API、worker，知识资料按仓库隔离，文件浏览模式不支持索引。生成演示数据时先停止常驻 worker，避免同时领取脚本创建的任务。详细验收、限制和固定三分钟演示脚本见 [第四周记录](docs/week-04.md)。

## 上下文、记忆审核与恢复

报告支持“提取经验”，在 [长期记忆](http://127.0.0.1:3000/memories) 编辑、批准、撤销或替代经验。只有已批准、未过期且仓库/提交匹配的条目才参与后续分析，默认有效期30天。报告提供上下文压缩前后材料、预算和实际 usage 对比，草稿可本地编辑，重新打开 PR 报告会检查提交变化。

新任务默认单次输入估算120,000 token、输出上限20,000 token，任务累计600,000 token。所有真实模型入口共享200元项目预算，140元提醒、180元停止新请求，按保守目录价估算；连续三次相同工具请求会在第三次执行前停止。详见 [运行限制与预算说明](docs/runtime-budget.md)。PostgreSQL checkpoint 按 run 隔离，失联后自动恢复一次，复用固定证据与已完成工具。恢复可能重复模型请求，未知 usage 明确标注。

```powershell
. .\scripts\env.ps1
uv sync --locked
uv run --locked python -m devflow.bootstrap
uv run --locked python scripts/week05_smoke.py
# 真实供应商的报告与候选提取验收，临时数据库不影响业务数据
uv run --locked python scripts/week05_smoke.py --real
```

完整验收、强制退出 worker 的三个恢复场景与边界见 [第五周记录](docs/week-05.md)。升级后重启 API、worker 和前端。

## 评测与回归

评测与改进入口：`uv run --locked python -m devflow.eval_cli run`，默认运行 20 题开发集和离线假模型，输出逐题报告、失败诊断和人工复核模板；支持失败题重跑与基线回归比较。完整用法、30 题数据集及首轮 12/20 → 14/20 的离线验证见 [评测与回归闭环](docs/evaluation-loop.md)。自动通过仍需语义复核；真实模型和两组检索/压缩效果实验尚未验收。

## 项目预算与运行限制

升级至 `0007_runtime_budget` 后重启 API、worker 和前端。工作台可展开项目预算摘要，任务中可查看分析与记忆提取的费用明细。正常浏览、健康检查和假模型不计费；旧运行显示“未纳入账本”。

所有真实分析、恢复、记忆提取、探针及验收脚本都通过主数据库共享额度。费用采用阿里云北京 `deepseek-v4.1-flash` 的保守忙时目录价：输入2元/百万 token、输出8元/百万 token。120,000输入＋20,000输出为0.40元；未确认用量保留预留金额，服务重启不清零。未知报价或账本不可用时拒绝真实请求，最终费用以供应商账单为准。

完整默认值、接口、验证和兼容边界见 [统一运行限制与200元项目预算](docs/runtime-budget.md)。第21步固定评测与回归入口已完成，后续为第22步效果对照实验。
