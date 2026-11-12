<!-- 文件用途：当前Windows电脑的本地启动、显式初始化、无费用演示和排障。 -->
# 本地运行手册

2026-11-11范围调整：本轮只做本地运行和真实评测闭环。发布封装、镜像分发及跨机器验收已取消；已有部署文件保留。[第22—24步核对表](release-checklist.md)登记实现、证据与缺口。

## 准备与初始化

先启动Docker Desktop，等待`docker info`成功。本地只需要Docker中的数据库，API、worker和前端在本机运行。

```powershell
cd D:\DevFlow
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1
. .\scripts\env.ps1
# 显式准备固定版本、SHA256的本地E5权重，已有文件只校验。
uv run --locked python scripts/prepare_rag.py
# 日常迁移和幂等初始化的统一入口。
uv run --locked python -m devflow.bootstrap --seed --knowledge
```

setup保留已有配置并安装锁定依赖，只启动db服务。bootstrap串行迁移、幂等导入样例，`--knowledge`建立向量索引；API/worker不迁移。开发新迁移可用Alembic生成命令，应用迁移统一用bootstrap。

首次准备需要访问Node/Python发布源、PyPI、npm、Docker仓库和Hugging Face固定文件。本地E5量化模型及tokenizer约135 MB，版本和SHA固定于`embeddings.py`。模型缺失时知识索引明确失败，不通过普通请求隐式下载。工具及依赖版本分别见`.python-version`、`.node-version`、`uv.lock`和前端`package-lock.json`。

## 本地服务

分别打开三个项目目录终端。fixture演示在API和worker两个终端都显式覆盖fake，不改写`.env`。

```powershell
# 终端1
$env:MODEL_PROVIDER='fake'
$env:DATA_SOURCE='fixture'
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1 api
```

```powershell
# 终端2
$env:MODEL_PROVIDER='fake'
$env:DATA_SOURCE='fixture'
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1 worker
```

```powershell
# 终端3
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1 web
```

工作台为`http://127.0.0.1:3000`，API为`http://127.0.0.1:8000`。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/dev.ps1 status
```

status检查db、API数据库/vector/迁移就绪、前端代理和worker轮询心跳。仅`/health/live`成功不代表完整就绪。worker心跳默认写`data/worker-heartbeat.json`，超过15秒失效，文件存在本身不证明进程存活。

真实分析只用根目录`.env`的服务端供应商、模型与凭据。关闭fake演示服务，清除终端的MODEL_PROVIDER覆盖后重启API/worker；前端不配置密钥。普通浏览及健康检查不调用模型，创建真实分析或提取任务会产生费用。共享预算200元、停止线180元不因重启或评测重置。

## 三分钟fixture演示

1. 打开PR #102，展示固定base/head与所有者过滤变更。
2. 创建分析，展示worker进度、报告、证据行号和Markdown草稿。
3. 分析CI #202，区分安装失败、测试跳过及历史复盘。
4. 在知识库询问AUTH-01约束，打开回答引用的固定文档版本。
5. 从PR发现提取并批准记忆，重启API/worker/前端，重新打开原报告、文档和记忆。

fake演示只验收工程链路，语义质量由真实基线独立报告。日常数据同时依赖`devflow_postgres_data`与项目`data/artifacts`，备份需同时保留；不要对日常项目执行`down -v`。

## 无费用检查

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1 -Integration -Build
```

入口临时强制fake并清空真实凭据，结束后恢复调用进程环境。检查全部Python脚本的Ruff、后端测试、OpenAPI契约、前端测试/静态检查及构建。集成检查前需按上文显式准备本地E5，真实本地检索不调用收费模型。数据库集成测试只创建和清理自己随机命名的库，含真实子进程中断恢复。完整本机服务的隔离启动、重启与持久性验证：

```powershell
. .\scripts\env.ps1
uv run --locked python scripts/local_smoke.py --directory data/local-verification/new-local-check
```

目录必须为空且位于项目data内，默认使用API 18000与前端13000；可通过--api-port/--web-port指定其他空闲端口。脚本建立自己的随机库和独立制品目录，结束后清理自己创建的进程与数据库，保留证据文件。实测见[本地验证记录](local-verification-20261111.md)。不要启动日常真实worker代替fake验证，以免领取已有真实队列任务。

## 排障和资源

| 现象 | 处理 |
| --- | --- |
| Docker named pipe不存在 | 启动Docker Desktop，等待`docker info`成功，再执行`docker compose up -d --wait db` |
| API存活但就绪503 | 查数据库/vector/migration状态，显式执行bootstrap |
| 一直queued | 确认worker在线、与API连接同一库且模型模式一致，检查心跳和日志 |
| embedding_not_ready | 显式执行prepare_rag.py；检查本地文件与SHA |
| 前端代理失败 | 检查`apps/web/.env.local`的BACKEND_URL和API端口，重启前端 |
| 真实模式启动拒绝 | 检查服务端Key、官方HTTPS地址与已登记报价，不在网页填写密钥 |
| 模型网络错误/费用未知 | 保留trace和未知用量预留，排查后仅继续未执行评测题 |

2026-11-10隔离容器空闲内存观测约API135 MiB、worker95 MiB、前端62 MiB、数据库52 MiB；这是历史容器观测，不是本机开发最低配置。Next编译、ONNX索引和集成测试会额外使用内存。
