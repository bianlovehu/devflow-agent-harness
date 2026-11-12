<!-- 文件用途：说明项目各文件的职责及关键入口。 -->
# 项目文件用途索引

源码和支持注释的配置文件含一句用途说明；关键事务和调用处另有实现注释。
JSON、版本 pin、锁文件、diff 与日志保持标准原格式，避免破坏解析、补丁或证据行号。Alembic ini 使用 ASCII 注释，兼容 Windows 系统编码读取。
依赖目录、工具链、构建结果、运行制品和密钥文件不属于源码索引。

| 文件 | 用途 |
| --- | --- |
| [.editorconfig](../.editorconfig) | 统一编辑器的编码、缩进及 CRLF 行尾规则。 |
| [.env.example](../.env.example) | 列出服务端配置项及本地开发默认值，不包含真实密钥。 |
| [.gitattributes](../.gitattributes) | 固定仓库文本使用 CRLF，并标记二进制文件。 |
| [.gitignore](../.gitignore) | 忽略密钥、工具链、缓存、构建结果和运行数据。 |
| [.node-version](../.node-version) | 固定项目工具链版本，内容供安装器直接读取。 |
| [.python-version](../.python-version) | 固定项目工具链版本，内容供安装器直接读取。 |
| [README.md](../README.md) | 介绍项目范围、启动命令与开发验证方式。 |
| [alembic.ini](../alembic.ini) | 指定数据库迁移目录和 Python 模块搜索路径。 |
| [apps/api/migrations/env.py](../apps/api/migrations/env.py) | 加载业务模型，并配置在线与离线数据库迁移。 |
| [apps/api/migrations/script.py.mako](../apps/api/migrations/script.py.mako) | 为新迁移生成版本信息和升级、回滚函数模板。 |
| [apps/api/migrations/versions/0001_enable_pgvector.py](../apps/api/migrations/versions/0001_enable_pgvector.py) | 通过初始迁移启用 PostgreSQL 向量扩展。 |
| [apps/api/migrations/versions/0002_business_models_add_business_persistence_models.py](../apps/api/migrations/versions/0002_business_models_add_business_persistence_models.py) | 通过第二次迁移创建业务表、索引和关联约束。 |
| [apps/api/src/devflow/__init__.py](../apps/api/src/devflow/__init__.py) | 提供 DevFlow 应用版本号。 |
| [apps/api/src/devflow/artifact_store.py](../apps/api/src/devflow/artifact_store.py) | 按内容哈希保存及校验不可变的本地文本制品。 |
| [apps/api/src/devflow/config.py](../apps/api/src/devflow/config.py) | 读取服务端环境配置，并隐藏密钥等敏感字段。 |
| [apps/api/src/devflow/contracts.py](../apps/api/src/devflow/contracts.py) | 定义样例和 GitHub 共用的仓库、资源及来源状态契约。 |
| [apps/api/src/devflow/data_source.py](../apps/api/src/devflow/data_source.py) | 定义仓库读取协议，并选择文件或数据库数据源。 |
| [apps/api/src/devflow/database.py](../apps/api/src/devflow/database.py) | 创建数据库连接池，并为每个请求提供独立会话。 |
| [apps/api/src/devflow/errors.py](../apps/api/src/devflow/errors.py) | 统一业务错误响应，并避免暴露敏感输入和数据库详情。 |
| [apps/api/src/devflow/health.py](../apps/api/src/devflow/health.py) | 检测 API、数据库、向量扩展和迁移状态。 |
| [apps/api/src/devflow/import_fixtures.py](../apps/api/src/devflow/import_fixtures.py) | 校验并幂等导入样例仓库、资源快照及证据。 |
| [apps/api/src/devflow/main.py](../apps/api/src/devflow/main.py) | 组装 FastAPI 服务、业务路由及统一请求处理。 |
| [apps/api/src/devflow/model_probe.py](../apps/api/src/devflow/model_probe.py) | 显式执行一次最小 DeepSeek 连通测试，不参与日常轮询。 |
| [apps/api/src/devflow/models.py](../apps/api/src/devflow/models.py) | 定义业务数据库表、唯一约束与跨仓库关联约束。 |
| [apps/api/src/devflow/persistence_smoke.py](../apps/api/src/devflow/persistence_smoke.py) | 记录并核对真实 API 重启前后的会话、任务和证据。 |
| [apps/api/src/devflow/persistent_source.py](../apps/api/src/devflow/persistent_source.py) | 通过数据库读取仓库与当前有效的资源快照。 |
| [apps/api/src/devflow/repositories.py](../apps/api/src/devflow/repositories.py) | 提供运行配置和仓库资源的只读 HTTP 接口。 |
| [apps/api/src/devflow/workflow_api.py](../apps/api/src/devflow/workflow_api.py) | 提供会话、任务、事件和制品的 HTTP 接口。 |
| [apps/api/src/devflow/workflow_contracts.py](../apps/api/src/devflow/workflow_contracts.py) | 定义会话、消息、任务及证据接口的输入输出结构。 |
| [apps/api/src/devflow/workflows.py](../apps/api/src/devflow/workflows.py) | 以事务保存会话、消息、任务和固定版本的证据引用。 |
| [apps/api/tests/test_database_integration.py](../apps/api/tests/test_database_integration.py) | 使用真实 PostgreSQL 验证数据库就绪与向量运算。 |
| [apps/api/tests/test_health.py](../apps/api/tests/test_health.py) | 验证健康检查、依赖不可用状态和错误脱敏。 |
| [apps/api/tests/test_model_probe.py](../apps/api/tests/test_model_probe.py) | 用模拟响应验证模型探测次数、用量输出和密钥脱敏。 |
| [apps/api/tests/test_persistence_integration.py](../apps/api/tests/test_persistence_integration.py) | 在独立测试库验证迁移、事务、幂等、版本固定和并发写入。 |
| [apps/api/tests/test_repositories.py](../apps/api/tests/test_repositories.py) | 验证无密钥样例浏览、资源隔离及案例证据一致性。 |
| [apps/api/tests/test_workflow_units.py](../apps/api/tests/test_workflow_units.py) | 验证制品完整性、任务参数、请求来源和错误脱敏。 |
| [apps/web/.env.example](../apps/web/.env.example) | 列出前端服务端代理使用的后端地址。 |
| [apps/web/.npmrc](../apps/web/.npmrc) | 为当前前端项目指定 npm 官方源与依赖保存规则。 |
| [apps/web/.prettierignore](../apps/web/.prettierignore) | 排除不应由 Prettier 改写的依赖和生成文件。 |
| [apps/web/.prettierrc.json](../apps/web/.prettierrc.json) | 配置前端代码格式及 CRLF 行尾。 |
| [apps/web/AGENTS.md](../apps/web/AGENTS.md) | 提供当前前端目录的 Next.js 开发约定。 |
| [apps/web/eslint.config.mjs](../apps/web/eslint.config.mjs) | 配置 JavaScript、TypeScript、React 和 Next.js 静态检查。 |
| [apps/web/next.config.ts](../apps/web/next.config.ts) | 设置 Next.js 应用的运行选项。 |
| [apps/web/package-lock.json](../apps/web/package-lock.json) | 由 npm 维护的前端依赖锁文件，不手工插入注释。 |
| [apps/web/package.json](../apps/web/package.json) | 声明前端项目依赖与开发命令。 |
| [apps/web/postcss.config.mjs](../apps/web/postcss.config.mjs) | 为样式编译启用 Tailwind PostCSS 插件。 |
| [apps/web/src/app/api/backend/[...path]/route.ts](../apps/web/src/app/api/backend/[...path]/route.ts) | 将白名单内的只读业务请求转发到后端。 |
| [apps/web/src/app/api/health/route.ts](../apps/web/src/app/api/health/route.ts) | 代理后端健康检查，并返回明确的不可用状态。 |
| [apps/web/src/app/globals.css](../apps/web/src/app/globals.css) | 定义工作台布局、资源浏览和响应式页面样式。 |
| [apps/web/src/app/layout.tsx](../apps/web/src/app/layout.tsx) | 设置页面元数据，并挂载共享导航和查询状态。 |
| [apps/web/src/app/page.tsx](../apps/web/src/app/page.tsx) | 显示工程健康状态、仓库入口和开发进度。 |
| [apps/web/src/app/repositories/[repoId]/page.tsx](../apps/web/src/app/repositories/[repoId]/page.tsx) | 解析仓库及资源 URL 参数，并展示仓库工作区。 |
| [apps/web/src/app/repositories/page.tsx](../apps/web/src/app/repositories/page.tsx) | 显示仓库列表页面。 |
| [apps/web/src/components/providers.tsx](../apps/web/src/components/providers.tsx) | 提供可在页面间复用的 TanStack Query 客户端。 |
| [apps/web/src/components/repository-browser.tsx](../apps/web/src/components/repository-browser.tsx) | 浏览仓库、PR diff、CI 日志和项目资料原文。 |
| [apps/web/src/components/workspace-shell.tsx](../apps/web/src/components/workspace-shell.tsx) | 显示共享导航、数据来源及模型配置状态。 |
| [apps/web/src/lib/health.ts](../apps/web/src/lib/health.ts) | 定义前端使用的健康检查响应类型。 |
| [apps/web/src/lib/repositories.ts](../apps/web/src/lib/repositories.ts) | 导出由 OpenAPI 生成的仓库资源类型与统一请求函数。 |
| [apps/web/tsconfig.json](../apps/web/tsconfig.json) | 配置 TypeScript 类型检查和模块解析规则。 |
| [compose.yaml](../compose.yaml) | 启动带持久化数据卷的 PostgreSQL 和 pgvector。 |
| [docs/development-plan.md](../docs/development-plan.md) | 说明六周开发计划、各步产物和验收条件。 |
| [docs/file-guide.md](../docs/file-guide.md) | 说明项目各文件的职责及关键入口。 |
| [docs/step-01.md](../docs/step-01.md) | 记录工程骨架和运行环境的验收结果。 |
| [docs/step-02.md](../docs/step-02.md) | 记录演示数据、浏览界面及模型连通验证。 |
| [docs/step-03.md](../docs/step-03.md) | 记录数据持久化、迁移、幂等及重启验证。 |
| [evals/fixtures/expectations.json](../evals/fixtures/expectations.json) | 单独保存各案例的预期发现、证据位置与结论边界。 |
| [fixtures/README.md](../fixtures/README.md) | 说明样例工程、数据生成方式和参考标注边界。 |
| [fixtures/taskboard/ci-logs/201.txt](../fixtures/taskboard/ci-logs/201.txt) | 保存人工构造的 CI 原始日志，保留证据行号。 |
| [fixtures/taskboard/ci-logs/202.txt](../fixtures/taskboard/ci-logs/202.txt) | 保存人工构造的 CI 原始日志，保留证据行号。 |
| [fixtures/taskboard/ci-logs/203.txt](../fixtures/taskboard/ci-logs/203.txt) | 保存人工构造的 CI 原始日志，保留证据行号。 |
| [fixtures/taskboard/dataset.json](../fixtures/taskboard/dataset.json) | 供业务接口读取的样例数据，不包含评测参考答案。 |
| [fixtures/taskboard/documents/access-policy.md](../fixtures/taskboard/documents/access-policy.md) | 说明演示服务的任务访问约束与审查边界。 |
| [fixtures/taskboard/documents/architecture.md](../fixtures/taskboard/documents/architecture.md) | 说明演示服务的数据边界和输入契约。 |
| [fixtures/taskboard/documents/ci-runbook.md](../fixtures/taskboard/documents/ci-runbook.md) | 提供演示 CI 各失败阶段的排查方法。 |
| [fixtures/taskboard/documents/null-labels-postmortem.md](../fixtures/taskboard/documents/null-labels-postmortem.md) | 复盘演示中的空值标签处理问题与结论边界。 |
| [fixtures/taskboard/pull-requests/101.diff](../fixtures/taskboard/pull-requests/101.diff) | 保存人工 PR 的标准 Git diff，保留补丁原格式。 |
| [fixtures/taskboard/pull-requests/102.diff](../fixtures/taskboard/pull-requests/102.diff) | 保存人工 PR 的标准 Git diff，保留补丁原格式。 |
| [fixtures/taskboard/pull-requests/103.diff](../fixtures/taskboard/pull-requests/103.diff) | 保存人工 PR 的标准 Git diff，保留补丁原格式。 |
| [fixtures/taskboard/seed/.gitattributes](../fixtures/taskboard/seed/.gitattributes) | 固定演示仓库文本的 Git 行尾规则。 |
| [fixtures/taskboard/seed/README.md](../fixtures/taskboard/seed/README.md) | 说明演示 Python 工程的职责和测试入口。 |
| [fixtures/taskboard/seed/pyproject.toml](../fixtures/taskboard/seed/pyproject.toml) | 设置演示 Python 工程及其测试发现规则。 |
| [fixtures/taskboard/seed/taskboard/__init__.py](../fixtures/taskboard/seed/taskboard/__init__.py) | 标记 Taskboard 演示 Python 包。 |
| [fixtures/taskboard/seed/taskboard/config_check.py](../fixtures/taskboard/seed/taskboard/config_check.py) | 运行演示服务的启动配置检查。 |
| [fixtures/taskboard/seed/taskboard/service.py](../fixtures/taskboard/seed/taskboard/service.py) | 提供任务列表、标题和标签处理的演示业务逻辑。 |
| [fixtures/taskboard/seed/taskboard/settings.py](../fixtures/taskboard/seed/taskboard/settings.py) | 读取并校验演示服务所需的数据库配置。 |
| [fixtures/taskboard/seed/tests/test_service.py](../fixtures/taskboard/seed/tests/test_service.py) | 验证演示服务的访问边界、标签契约和标题格式。 |
| [fixtures/taskboard/snapshots/08e1a7f77ab3481e02b7b1b365a6db52746ccdb0/.gitattributes](../fixtures/taskboard/snapshots/08e1a7f77ab3481e02b7b1b365a6db52746ccdb0/.gitattributes) | 固定演示仓库文本的 Git 行尾规则。 |
| [fixtures/taskboard/snapshots/08e1a7f77ab3481e02b7b1b365a6db52746ccdb0/README.md](../fixtures/taskboard/snapshots/08e1a7f77ab3481e02b7b1b365a6db52746ccdb0/README.md) | 说明演示 Python 工程的职责和测试入口。 |
| [fixtures/taskboard/snapshots/08e1a7f77ab3481e02b7b1b365a6db52746ccdb0/pyproject.toml](../fixtures/taskboard/snapshots/08e1a7f77ab3481e02b7b1b365a6db52746ccdb0/pyproject.toml) | 设置演示 Python 工程及其测试发现规则。 |
| [fixtures/taskboard/snapshots/08e1a7f77ab3481e02b7b1b365a6db52746ccdb0/taskboard/__init__.py](../fixtures/taskboard/snapshots/08e1a7f77ab3481e02b7b1b365a6db52746ccdb0/taskboard/__init__.py) | 标记 Taskboard 演示 Python 包。 |
| [fixtures/taskboard/snapshots/08e1a7f77ab3481e02b7b1b365a6db52746ccdb0/taskboard/config_check.py](../fixtures/taskboard/snapshots/08e1a7f77ab3481e02b7b1b365a6db52746ccdb0/taskboard/config_check.py) | 运行演示服务的启动配置检查。 |
| [fixtures/taskboard/snapshots/08e1a7f77ab3481e02b7b1b365a6db52746ccdb0/taskboard/service.py](../fixtures/taskboard/snapshots/08e1a7f77ab3481e02b7b1b365a6db52746ccdb0/taskboard/service.py) | 提供任务列表、标题和标签处理的演示业务逻辑。 |
| [fixtures/taskboard/snapshots/08e1a7f77ab3481e02b7b1b365a6db52746ccdb0/taskboard/settings.py](../fixtures/taskboard/snapshots/08e1a7f77ab3481e02b7b1b365a6db52746ccdb0/taskboard/settings.py) | 读取并校验演示服务所需的数据库配置。 |
| [fixtures/taskboard/snapshots/08e1a7f77ab3481e02b7b1b365a6db52746ccdb0/tests/test_service.py](../fixtures/taskboard/snapshots/08e1a7f77ab3481e02b7b1b365a6db52746ccdb0/tests/test_service.py) | 验证演示服务的访问边界、标签契约和标题格式。 |
| [fixtures/taskboard/snapshots/6725207e6cfc27084147c1624a8f2da5f1dcf491/.gitattributes](../fixtures/taskboard/snapshots/6725207e6cfc27084147c1624a8f2da5f1dcf491/.gitattributes) | 固定演示仓库文本的 Git 行尾规则。 |
| [fixtures/taskboard/snapshots/6725207e6cfc27084147c1624a8f2da5f1dcf491/README.md](../fixtures/taskboard/snapshots/6725207e6cfc27084147c1624a8f2da5f1dcf491/README.md) | 说明演示 Python 工程的职责和测试入口。 |
| [fixtures/taskboard/snapshots/6725207e6cfc27084147c1624a8f2da5f1dcf491/pyproject.toml](../fixtures/taskboard/snapshots/6725207e6cfc27084147c1624a8f2da5f1dcf491/pyproject.toml) | 设置演示 Python 工程及其测试发现规则。 |
| [fixtures/taskboard/snapshots/6725207e6cfc27084147c1624a8f2da5f1dcf491/taskboard/__init__.py](../fixtures/taskboard/snapshots/6725207e6cfc27084147c1624a8f2da5f1dcf491/taskboard/__init__.py) | 标记 Taskboard 演示 Python 包。 |
| [fixtures/taskboard/snapshots/6725207e6cfc27084147c1624a8f2da5f1dcf491/taskboard/config_check.py](../fixtures/taskboard/snapshots/6725207e6cfc27084147c1624a8f2da5f1dcf491/taskboard/config_check.py) | 运行演示服务的启动配置检查。 |
| [fixtures/taskboard/snapshots/6725207e6cfc27084147c1624a8f2da5f1dcf491/taskboard/service.py](../fixtures/taskboard/snapshots/6725207e6cfc27084147c1624a8f2da5f1dcf491/taskboard/service.py) | 提供任务列表、标题和标签处理的演示业务逻辑。 |
| [fixtures/taskboard/snapshots/6725207e6cfc27084147c1624a8f2da5f1dcf491/taskboard/settings.py](../fixtures/taskboard/snapshots/6725207e6cfc27084147c1624a8f2da5f1dcf491/taskboard/settings.py) | 读取并校验演示服务所需的数据库配置。 |
| [fixtures/taskboard/snapshots/6725207e6cfc27084147c1624a8f2da5f1dcf491/tests/test_service.py](../fixtures/taskboard/snapshots/6725207e6cfc27084147c1624a8f2da5f1dcf491/tests/test_service.py) | 验证演示服务的访问边界、标签契约和标题格式。 |
| [fixtures/taskboard/snapshots/e06b47e7e6f566271f16f313082f37590eb885f6/.gitattributes](../fixtures/taskboard/snapshots/e06b47e7e6f566271f16f313082f37590eb885f6/.gitattributes) | 固定演示仓库文本的 Git 行尾规则。 |
| [fixtures/taskboard/snapshots/e06b47e7e6f566271f16f313082f37590eb885f6/README.md](../fixtures/taskboard/snapshots/e06b47e7e6f566271f16f313082f37590eb885f6/README.md) | 说明演示 Python 工程的职责和测试入口。 |
| [fixtures/taskboard/snapshots/e06b47e7e6f566271f16f313082f37590eb885f6/pyproject.toml](../fixtures/taskboard/snapshots/e06b47e7e6f566271f16f313082f37590eb885f6/pyproject.toml) | 设置演示 Python 工程及其测试发现规则。 |
| [fixtures/taskboard/snapshots/e06b47e7e6f566271f16f313082f37590eb885f6/taskboard/__init__.py](../fixtures/taskboard/snapshots/e06b47e7e6f566271f16f313082f37590eb885f6/taskboard/__init__.py) | 标记 Taskboard 演示 Python 包。 |
| [fixtures/taskboard/snapshots/e06b47e7e6f566271f16f313082f37590eb885f6/taskboard/config_check.py](../fixtures/taskboard/snapshots/e06b47e7e6f566271f16f313082f37590eb885f6/taskboard/config_check.py) | 运行演示服务的启动配置检查。 |
| [fixtures/taskboard/snapshots/e06b47e7e6f566271f16f313082f37590eb885f6/taskboard/service.py](../fixtures/taskboard/snapshots/e06b47e7e6f566271f16f313082f37590eb885f6/taskboard/service.py) | 提供任务列表、标题和标签处理的演示业务逻辑。 |
| [fixtures/taskboard/snapshots/e06b47e7e6f566271f16f313082f37590eb885f6/taskboard/settings.py](../fixtures/taskboard/snapshots/e06b47e7e6f566271f16f313082f37590eb885f6/taskboard/settings.py) | 读取并校验演示服务所需的数据库配置。 |
| [fixtures/taskboard/snapshots/e06b47e7e6f566271f16f313082f37590eb885f6/tests/test_service.py](../fixtures/taskboard/snapshots/e06b47e7e6f566271f16f313082f37590eb885f6/tests/test_service.py) | 验证演示服务的访问边界、标签契约和标题格式。 |
| [fixtures/taskboard/snapshots/e2874eff98064950c923278156a0e86e9880a635/.gitattributes](../fixtures/taskboard/snapshots/e2874eff98064950c923278156a0e86e9880a635/.gitattributes) | 固定演示仓库文本的 Git 行尾规则。 |
| [fixtures/taskboard/snapshots/e2874eff98064950c923278156a0e86e9880a635/README.md](../fixtures/taskboard/snapshots/e2874eff98064950c923278156a0e86e9880a635/README.md) | 说明演示 Python 工程的职责和测试入口。 |
| [fixtures/taskboard/snapshots/e2874eff98064950c923278156a0e86e9880a635/pyproject.toml](../fixtures/taskboard/snapshots/e2874eff98064950c923278156a0e86e9880a635/pyproject.toml) | 设置演示 Python 工程及其测试发现规则。 |
| [fixtures/taskboard/snapshots/e2874eff98064950c923278156a0e86e9880a635/taskboard/__init__.py](../fixtures/taskboard/snapshots/e2874eff98064950c923278156a0e86e9880a635/taskboard/__init__.py) | 标记 Taskboard 演示 Python 包。 |
| [fixtures/taskboard/snapshots/e2874eff98064950c923278156a0e86e9880a635/taskboard/config_check.py](../fixtures/taskboard/snapshots/e2874eff98064950c923278156a0e86e9880a635/taskboard/config_check.py) | 运行演示服务的启动配置检查。 |
| [fixtures/taskboard/snapshots/e2874eff98064950c923278156a0e86e9880a635/taskboard/service.py](../fixtures/taskboard/snapshots/e2874eff98064950c923278156a0e86e9880a635/taskboard/service.py) | 提供任务列表、标题和标签处理的演示业务逻辑。 |
| [fixtures/taskboard/snapshots/e2874eff98064950c923278156a0e86e9880a635/taskboard/settings.py](../fixtures/taskboard/snapshots/e2874eff98064950c923278156a0e86e9880a635/taskboard/settings.py) | 读取并校验演示服务所需的数据库配置。 |
| [fixtures/taskboard/snapshots/e2874eff98064950c923278156a0e86e9880a635/tests/test_service.py](../fixtures/taskboard/snapshots/e2874eff98064950c923278156a0e86e9880a635/tests/test_service.py) | 验证演示服务的访问边界、标签契约和标题格式。 |
| [infra/python-downloads.json](../infra/python-downloads.json) | 固定官方 Python 构建地址和校验值，供 uv 安装。 |
| [pyproject.toml](../pyproject.toml) | 配置 Python 项目依赖及 Ruff、pytest 规则。 |
| [scripts/build_fixtures.py](../scripts/build_fixtures.py) | 用固定 Git 身份和时间生成可复现的演示案例。 |
| [scripts/check-deepseek.ps1](../scripts/check-deepseek.ps1) | 显式触发一次 DeepSeek 最小连通检查。 |
| [scripts/check.ps1](../scripts/check.ps1) | 执行格式、静态检查、测试及可选的生产构建。 |
| [scripts/dev.ps1](../scripts/dev.ps1) | 按指定目标启动 API、前端或数据库开发服务。 |
| [scripts/env.ps1](../scripts/env.ps1) | 为当前终端加载项目专用工具链和缓存路径。 |
| [scripts/setup.ps1](../scripts/setup.ps1) | 安装锁定依赖，启动数据库并执行迁移和样例导入。 |
| [uv.lock](../uv.lock) | 由 uv 维护的 Python 依赖锁文件，不手工插入注释。 |
| [apps/web/scripts/generate-api.mjs](../apps/web/scripts/generate-api.mjs) | 从后端 OpenAPI 生成前端类型，并检查已提交类型是否过期。 |
| [apps/web/src/app/api/backend/[...path]/route.ts](../apps/web/src/app/api/backend/[...path]/route.ts) | 将受限的业务读取与任务创建请求交给统一后端代理。 |
| [apps/web/src/app/repositories/[repoId]/page.tsx](../apps/web/src/app/repositories/[repoId]/page.tsx) | 解析仓库及资源 URL 参数，并展示仓库工作区。 |
| [apps/web/src/app/runs/[runId]/page.tsx](../apps/web/src/app/runs/[runId]/page.tsx) | 解析任务直达地址并恢复工作台详情。 |
| [apps/web/src/app/runs/page.tsx](../apps/web/src/app/runs/page.tsx) | 解析仓库与会话筛选条件并打开分析工作台。 |
| [apps/web/src/components/analysis-form.tsx](../apps/web/src/components/analysis-form.tsx) | 从 PR 或 CI 创建会话与分析任务，并处理重试和文件模式限制。 |
| [apps/web/src/components/query-state.tsx](../apps/web/src/components/query-state.tsx) | 统一加载与错误提示，并遵守限流响应中的最早重试时间。 |
| [apps/web/src/components/run-workspace.tsx](../apps/web/src/components/run-workspace.tsx) | 展示可重开的会话、任务详情、已保存事件与固定版本证据。 |
| [apps/web/src/lib/api-client.ts](../apps/web/src/lib/api-client.ts) | 统一浏览器业务请求、错误码和请求标识，保留重试所需信息。 |
| [apps/web/src/lib/backend-proxy.ts](../apps/web/src/lib/backend-proxy.ts) | 按接口和方法限制代理范围，校验来源并保留任务请求的幂等语义。 |
| [apps/web/src/lib/generated/api.d.ts](../apps/web/src/lib/generated/api.d.ts) | 保存从 FastAPI OpenAPI 自动生成的接口类型，请勿手工修改。 |
| [apps/web/src/lib/run-submission.ts](../apps/web/src/lib/run-submission.ts) | 合并重复点击，并在请求结果未知时保留相同任务参数与幂等键。 |
| [apps/web/src/lib/workflows.ts](../apps/web/src/lib/workflows.ts) | 导出任务工作流类型，并完整读取会话消息与已保存事件。 |
| [apps/web/tests/api-client.test.mjs](../apps/web/tests/api-client.test.mjs) | 验证浏览器请求保留错误码与请求标识，并正确发送幂等键。 |
| [apps/web/tests/backend-proxy.test.mjs](../apps/web/tests/backend-proxy.test.mjs) | 验证业务代理的白名单、来源、查询透传及幂等响应边界。 |
| [apps/web/tests/run-submission.test.mjs](../apps/web/tests/run-submission.test.mjs) | 验证重复点击只发一次请求，未知结果重试复用幂等键。 |
| [docs/step-04-plan.docx](../docs/step-04-plan.docx) | 保存第4步前端主框架实施顺序与验收清单。 |
| [docs/step-04.md](../docs/step-04.md) | 记录前端主框架、任务创建和固定版本证据工作台的验收结果。 |
| [scripts/export_openapi.py](../scripts/export_openapi.py) | 离线导出 FastAPI 的 OpenAPI 契约，不启动服务或连接数据库。 |
| [apps/api/migrations/versions/0003_github_sync_state.py](../apps/api/migrations/versions/0003_github_sync_state.py) | 为仓库增加 GitHub 摘要同步状态，保留现有样例与历史任务。 |
| [apps/api/src/devflow/github_client.py](../apps/api/src/devflow/github_client.py) | 封装 GitHub 只读 HTTP、有限分页、限流退避和无令牌日志下载。 |
| [apps/api/src/devflow/github_source.py](../apps/api/src/devflow/github_source.py) | 持久化 GitHub 仓库摘要，并按登记范围读取 PR、Issue、CI 与 job 日志。 |
| [apps/api/tests/github_samples.py](../apps/api/tests/github_samples.py) | 提供可控的 GitHub API 响应，供只读适配器和数据库集成测试使用。 |
| [apps/api/tests/test_github_client.py](../apps/api/tests/test_github_client.py) | 验证 GitHub 只读请求、输入范围、有限分页、错误分类及令牌隔离。 |
| [apps/web/src/app/api/backend/[...path]/route.ts](../apps/web/src/app/api/backend/[...path]/route.ts) | 将受限的业务读取与任务创建请求交给统一后端代理。 |
| [apps/web/src/app/repositories/[repoId]/page.tsx](../apps/web/src/app/repositories/[repoId]/page.tsx) | 解析仓库及资源 URL 参数，并展示仓库工作区。 |
| [apps/web/src/app/runs/[runId]/page.tsx](../apps/web/src/app/runs/[runId]/page.tsx) | 解析任务直达地址并恢复工作台详情。 |
| [apps/web/src/components/github-job-logs.tsx](../apps/web/src/components/github-job-logs.tsx) | 仅在用户选择 job 后读取日志，并展示未就绪或过期错误。 |
| [apps/web/src/components/github-repository-form.tsx](../apps/web/src/components/github-repository-form.tsx) | 登记 GitHub 仓库并手动刷新摘要，所有外部请求保持只读。 |
| [apps/web/src/components/source-notices.tsx](../apps/web/src/components/source-notices.tsx) | 展示来源抓取时间、同步范围和不完整数据提示。 |
| [apps/web/src/lib/ci-status.ts](../apps/web/src/lib/ci-status.ts) | 根据真实 CI 状态生成标签，避免把运行中或无结论误判为失败。 |
| [apps/web/tests/ci-status.test.mjs](../apps/web/tests/ci-status.test.mjs) | 验证真实 CI 的运行中、成功、缺失结论和失败状态不会混淆。 |
| [docs/step-05.md](../docs/step-05.md) | 记录 GitHub 只读适配器、同步边界及真实网络验收结果。 |


## 第二周新增文件

| 文件 | 用途 |
|---|---|
| `apps/api/migrations/versions/0004_worker_leases.py` | 任务租约、取消和结果字段迁移 |
| `apps/api/src/devflow/fixed_files.py` | 固定SHA的普通文本blob读取、路径和完整性检查 |
| `apps/api/src/devflow/evidence_capture.py` | PR/CI固定证据采集、范围缺口与数据库绑定 |
| `apps/api/src/devflow/worker.py` | 持久化分析/模拟worker、心跳、所有权隔离、取消与超时调用留痕 |
| `apps/api/src/devflow/event_stream.py` | 持久化事件到SSE的续传服务 |
| `apps/api/tests/test_fixed_files.py` | 固定文件、diff和原始日志字节测试 |
| `apps/api/tests/test_week02_integration.py` | 真实数据库的worker、证据与SSE故障测试 |
| `apps/web/src/components/run-progress.tsx` | 任务控制、SSE连接和时间线 |
| `apps/web/src/lib/event-sequence.ts` | 按序号去重和连续游标 |
| `apps/web/tests/event-sequence.test.mjs` | 历史/SSE合并和补查缺口测试 |
| `scripts/week02_smoke.py` | 可重复的样例/公开GitHub证据验收 |
| `docs/week-02.md` | 第二周逐项验收映射与限制 |

本地 `data/week02-*-proof.json` 为验收产生的任务、版本、事件和制品哈希摘要，受Git忽略，不含凭据；`.cache/week02/`为临时进程日志与故障实验脚本。外部原始制品`.bin`保留源字节，不作为作者编辑的文本进行换行转换。

## 第三周新增文件

| 文件 | 用途 |
|---|---|
| `apps/api/src/devflow/model_gateway.py` | 阿里云/DeepSeek 模型入口、错误分类、usage 与测试假模型 |
| `apps/api/src/devflow/tool_gateway.py` | 当前任务范围内的只读工具、分页、日志错误块和重复调用检测 |
| `apps/api/src/devflow/agent.py` | LangGraph 循环、业务预算、一次修正与引用校验 |
| `apps/api/src/devflow/reports.py` | 报告 Pydantic schema、引用范围检查及安全 Markdown 草稿 |
| `apps/api/src/devflow/fake_model.py` | 仅使用可见工具片段的离线演示假模型 |
| `apps/api/tests/test_agent.py` | 模型参数、权限边界、引用、预算与图执行单元验证 |
| `apps/api/tests/test_week03_integration.py` | 六个样例、报告持久化/导出及失败/取消集成验证 |
| `apps/web/src/components/analysis-report.tsx` | 风险卡片、日志/代码引用展开、复制和下载草稿 |
| `scripts/week03_model_probe.py` | 显式真实模型工具调用与 JSON 小请求验收 |
| `scripts/week03_smoke.py` | 样例、真实 GitHub 或已采集公开快照的完整报告验收 |
| `docs/week-03.md` | 第9—12步实现、真实验收、复现方式和边界 |
| `docs/progress-report-2026-10-29.md` | 前3周完整性审查、修复验证、历史证据复核和当前进展 |

## 第四周新增文件

| 文件 | 用途 |
|---|---|
| `apps/api/migrations/versions/0005_knowledge_rag_add_versioned_knowledge_and_hybrid_.py` | 文档、版本、向量块、GIN 关键词索引与内容向量缓存 |
| `apps/api/src/devflow/embeddings.py` | 固定模型/tokenizer 校验、本地 CPU ONNX 推理与归一化 |
| `apps/api/src/devflow/knowledge.py` | 文档解析、token 分块、事务版本切换、删除与混合检索 |
| `apps/api/src/devflow/knowledge_api.py` | 知识库上传、状态、版本、预览、删除与检索调试 API |
| `apps/api/tests/test_knowledge.py` | PDF/文本边界、分块完整性与分词规则 |
| `apps/api/tests/test_week04_integration.py` | 版本/去重/删除、仓库隔离、缓存、并发与问答证据 |
| `apps/web/src/app/knowledge/page.tsx` | 知识库页面入口与仓库参数 |
| `apps/web/src/components/knowledge-workspace.tsx` | 资料维护、索引状态、来源预览、排序调试与问答入口 |
| `fixtures/knowledge/owner-policy.en.md` | 用于中文问题召回英文资料的人工样例策略 |
| `scripts/prepare_rag.py` | 显式下载和校验固定版本模型 |
| `scripts/week04_smoke.py` | 真实本地向量、离线或真实模型的 PR/CI/问答演示验证 |
| `docs/week-04.md` | 第13—16步验收、三分钟演示与当前限制 |

## 第五周新增文件

| 文件 | 用途 |
|---|---|
| `apps/api/migrations/versions/0006_context_memory_add_reviewed_memories_and_recovery_.py` | 记忆、恢复 journal、恢复次数和 checkpoint schema |
| `apps/api/src/devflow/context_budget.py` | 分层输入预算、按次序压缩与来源/约束保留 |
| `apps/api/src/devflow/memory.py` | 模型候选提取、人工审核、版本/有效期过滤与替代事务 |
| `apps/api/src/devflow/memory_api.py` | 长期记忆本地提取、列表、编辑、批准和撤销接口 |
| `apps/api/src/devflow/checkpoint.py` | PostgreSQL checkpointer 与持有租约的写入校验 |
| `apps/api/src/devflow/security.py` | 已知令牌脱敏与统一 API JSON 展示边界 |
| `apps/api/tests/test_context_budget.py` | 压缩顺序、工具配对、约束与来源、权限和脱敏验证 |
| `apps/api/tests/test_week05_integration.py` | 记忆、长对话、恢复、版本变化和原始制品验证 |
| `apps/api/tests/crash_worker.py` | 三个持久化边界强制退出的独立验收进程 |
| `apps/web/src/app/memories/page.tsx` | 长期记忆工作台入口 |
| `apps/web/src/components/memory-workspace.tsx` | 报告提取经验、审核、编辑、撤销与替代 |
| `apps/web/src/components/context-history.tsx` | 压缩估算、usage、恢复次数与原始材料查看 |
| `scripts/week05_smoke.py` | 临时数据库中的离线/真实模型记忆完整流程验收 |
| `docs/week-05.md` | 第17—20步实现、验收记录与边界 |

## 统一运行限制与项目预算

| 文件 | 用途 |
|---|---|
| `apps/api/src/devflow/runtime_policy.py` | 服务端限额、带来源与版本的保守报价及 Decimal 计费 |
| `apps/api/src/devflow/budget.py` | 主库预算账户、并发预留、幂等结算与未知用量保留 |
| `apps/api/src/devflow/budget_api.py` | 只读预算摘要和运行关联费用接口 |
| `apps/api/migrations/versions/0007_runtime_budget_add_shared_model_cost_ledger.py` | 项目预算账户及逐请求账本迁移 |
| `apps/api/tests/test_runtime_policy.py` | 配置上限、工具指纹、连续循环及恢复计数 |
| `apps/api/tests/test_budget_integration.py` | 金额边界、并发、异常、跨入口计费及进程恢复 |
| `apps/api/tests/budget_samples.py` | 模型适配器单测使用的显式假账本 |
| `apps/api/tests/budget_crash_worker.py` | 收费请求边界的隔离进程强制退出实验 |
| `apps/web/src/components/budget-summary.tsx` | 项目预算与运行费用的只读展示 |
| `docs/runtime-budget.md` | 当前策略、计费方法、限制与验证说明 |

## 固定评测与回归

| 文件 | 用途 |
|---|---|
| `evals/devflow-v1/inputs.json` | 按来源分组的30题固定输入，仅此部分可进入模型 |
| `evals/devflow-v1/expectations.json` | 预期结论、参考证据、禁止结论与不确定边界 |
| `scripts/build_eval_dataset.py` | 可复现生成固定评测集 |
| `apps/api/src/devflow/eval_runner.py` | 固定快照、关键词适配器和实际Agent执行，无参考答案输入 |
| `apps/api/src/devflow/evaluation.py` | 数据校验、自动诊断、人工复核绑定、报告与逐题回归 |
| `apps/api/src/devflow/eval_cli.py` | 评测、失败题重跑、复核与基线比较命令 |
| `apps/api/tests/test_evaluation.py` | 来源与答案隔离、诊断、复核、版本和回归门禁测试 |
| `evals/regressions/2026-11-05.json` | 首轮闭环的配置摘要、逐题结果与改善记录 |
| `docs/evaluation-loop.md` | 复现步骤、退出码、实际结果和未验收边界 |

## 本地运行与真实基线（2026-11-11）

- docs/local-runbook.md：本地启动、就绪检查、fake演示与排障。
- docs/release-checklist.md：原22—24步状态，发布事项标注取消。
- docs/local-verification-20261111.md：源码进程隔离启动/重启与检查证据。
- docs/architecture-decisions.md：架构选择、实现和测试索引。
- scripts/local_smoke.py：本机源码进程的隔离fake演示，不构建镜像。
- scripts/baseline_report.py：汇总usage、引用、检索与绑定输出哈希的GPT复核。
- evals/reviews/gpt-real-dev-v2-20261111.json：40次真实开发结果的逐题GPT复核。

- docs/real-baseline-report.md：改进前后、两组对照、重复采样、新留出及费用的最终报告。

### 第2版报告：事实、推测和建议

- `apps/api/src/devflow/report_v2.py`：新报告格式、工具记录的读取范围、同因合并，以及历史线索与当前问题的区分。
- `apps/api/tests/test_report_v2.py`：四类历史结论错误、直接引用、建议计数和旧报告兼容检查。
- `apps/web/src/lib/report-presentation.ts`：按三类分组，保留每项在原报告中的位置。
- `docs/report-rules.md`：用直白说法说明报告内容、证据限制，以及引用检查与结论复核的区别。
- evals/freezes/development-20261111.json：新留出创建前的开发冻结。
- evals/devflow-novel-holdout-20261111：冻结后新建的9题及标注/来源记录。
- evals/reviews/gpt-real-dev-v4-20261111.json、gpt-context-v3-20261111.json、gpt-stability-v3-20261111.json、gpt-novel-holdout-20261111.json：73条冻结版本的GPT逐题复核。
