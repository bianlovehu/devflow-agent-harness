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
| [apps/api/src/devflow/contracts.py](../apps/api/src/devflow/contracts.py) | 定义仓库、PR、CI 和文档的接口数据结构。 |
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
| [apps/web/src/lib/repositories.ts](../apps/web/src/lib/repositories.ts) | 定义资源接口类型，并封装统一的只读数据请求。 |
| [apps/web/tsconfig.json](../apps/web/tsconfig.json) | 配置 TypeScript 类型检查和模块解析规则。 |
| [compose.yaml](../compose.yaml) | 启动带持久化数据卷的 PostgreSQL 和 pgvector。 |
| [docs/development-plan.md](../docs/development-plan.md) | 说明六周开发计划、各步产物和验收条件。 |
| [docs/file-guide.md](../docs/file-guide.md) | 说明项目各文件的职责。 |
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
