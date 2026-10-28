<!-- 文件用途：介绍项目范围、启动命令与开发验证方式。 -->
# DevFlow Agent Harness

面向 PR 审查与 CI 排障的研发协作 Agent Harness，提供版本化证据、任务持久化和可复现演示案例。基于 FastAPI、Next.js 和 PostgreSQL，按 [六周开发计划](docs/development-plan.md) 独立实现。

当前已完成**第 1—3 步：工程骨架、演示案例和业务数据持久化**。默认从 PostgreSQL 浏览样例仓库、PR、CI 和资料，并通过 API 保存会话、消息、任务、事件及证据版本。DeepSeek 配置已接通；分析工作台、worker、Agent、RAG 和记忆将按计划继续实现。

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

然后分别打开两个终端：

```powershell
cd D:\DevFlow
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 api
```

```powershell
cd D:\DevFlow
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 web
```

- 工作台：http://127.0.0.1:3000
- 样例仓库：http://127.0.0.1:3000/repositories
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
uv run --locked alembic upgrade head
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
evals/fixtures/        与业务输入分离的 6 个案例参考标注
scripts/               初始化、开发启动、样例生成与检查入口
docs/                  开发计划与步骤验收记录
compose.yaml           PostgreSQL 17 + pgvector，持久化数据卷
pyproject.toml          Python 项目配置与 Ruff/pytest 配置
```

业务接口使用 `/api/v1` 前缀。前端通过自身的 `/api/health` 服务端代理访问 API，不将后端凭据暴露给浏览器。健康检查执行有超时的数据库查询，既检查连接，也检查扩展与迁移状态；错误响应不包含连接密码或 SQL 异常原文。

迁移 `0001_enable_pgvector` 负责启用扩展，并创建 Alembic 版本记录；第 3 步再添加业务表。回滚初始迁移会保留可能被共享使用的 vector 扩展。

## 常见问题

- **Docker named pipe 不存在：** 启动 Docker Desktop，确认使用 Linux containers，然后执行 `docker info`。
- **端口 5432 已占用：** 修改根目录 `.env` 中 `POSTGRES_PORT`，重新创建 db 容器并重启 API。
- **数据库已连接但扩展/迁移待配置：** 执行 `uv run --locked alembic upgrade head`。
- **修改数据库密码后连接失败：** 既有数据卷保留原密码，修改 `.env` 不会自动变更数据库内的用户密码。
- **后端地址变化：** 修改 `apps/web/.env.local` 中的 `BACKEND_URL`，重启前端。
- **初始化下载失败：** 确认上述发布源可访问后重跑脚本；已有配置和数据库卷会保留。

验收与限制见 [第 1 步记录](docs/step-01.md) 、[第 2 步记录](docs/step-02.md) 和 [第 3 步记录](docs/step-03.md)。普通浏览与自动测试不调用真实模型。

## 样例数据与数据源

默认使用 DATA_SOURCE=fixture 和 FIXTURE_STORAGE=database，无需外部密钥即可浏览数据库中已导入的样例。显式设置 FIXTURE_STORAGE=files 可进行离线只读浏览。页面和响应均标明 fixture；真实 GitHub 适配器在第 5 步实现，当前选择 DATA_SOURCE=github 会返回明确的未就绪错误。

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

## DeepSeek 服务端配置

仅在根目录 .env 中填写 DEEPSEEK_API_KEY；DEEPSEEK_MODEL 默认是 deepseek-flash。不要把密钥放入前端环境变量或源码。修改配置后重启 API。

显式的连通测试会向 DeepSeek 官方接口发送一次最多 8 个输出 token 的小请求：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-deepseek.ps1
```

该命令只显示验证状态、模型名和 usage，不打印密钥或服务端错误原文。页面顶部的「密钥已配置」仅表示配置存在；日常健康检查、样例浏览和普通测试不发出模型请求。完整 Agent 分析将在后续步骤接入。


## 数据持久化与代码阅读

数据库迁移完成后，重复导入样例不会新增同一条记录：

```powershell
. .\scripts\env.ps1
uv run --locked alembic upgrade head
uv run --locked python -m devflow.import_fixtures
uv run --locked alembic check
```

会话、消息、任务及其固定版本证据使用 PostgreSQL 保存；大文本制品位于被 Git 忽略的 data/artifacts。验收写入接口可在 API 文档中查看。当前只创建 queued 记录，执行器尚未接入，不会自动调用模型。

代码阅读入口：[文件用途索引](docs/file-guide.md)、[业务模型](apps/api/src/devflow/models.py)、[事务服务](apps/api/src/devflow/workflows.py)、[第 3 步验收](docs/step-03.md)。源码与可注释配置含用途说明，关键实现处另有中文注释。
