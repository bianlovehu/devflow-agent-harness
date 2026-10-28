<!-- 文件用途：记录工程骨架和运行环境的验收结果。 -->
# 第 1 步：环境与工程骨架验收

日期：2026-10-26（Asia/Shanghai）

状态：已完成第 1 步。业务数据和 Agent 能力按第 2 步起继续实现。

## 已交付

- Git 仓库初始化，主分支 main；CRLF、EditorConfig、忽略文件和服务端环境变量示例。
- 项目专用 Python 3.11.17 与 Node.js 24.22.1，不依赖系统 Python 3.11.0 / Node 21。
- FastAPI 健康检查、SQLAlchemy 连接入口、Pydantic Settings 配置。
- PostgreSQL 17.10 + pgvector 0.8.2，镜像固定到已验证的 SHA256 摘要，端口仅监听 127.0.0.1。
- Alembic 迁移环境与初始迁移 0001_enable_pgvector，数据库使用持久化数据卷。
- Next.js App Router、TypeScript、Tailwind、TanStack Query 基础布局。
- 首页实时展示 API、数据库、向量扩展和迁移状态，支持手动检测及 15 秒刷新。
- 前端服务端健康检查代理，支持后端不可用与数据库不可用的错误展示。
- uv.lock、package-lock.json、Ruff、ESLint 10、Prettier 与统一初始化/开发/检查脚本。
- 上一个对话的完整计划保存在 development-plan.md。

## 验证结果

| 检查 | 结果 |
| --- | --- |
| 在新的 PowerShell 进程执行 setup.ps1 | 通过：锁定依赖安装、容器健康与迁移 |
| 新终端执行 check.ps1 -Integration -Build | 通过 |
| pytest | 4 passed；包括真实 PostgreSQL/pgvector 集成检查 |
| Python 更新为 3.11.17 后重跑测试 | 4 passed，无警告 |
| Ruff lint / format | 通过 |
| ESLint / TypeScript / Prettier | 通过 |
| Next.js 生产构建 | 通过，生成首页和健康检查代理 |
| 数据库停机时 API 存活检查 | HTTP 200 |
| 数据库停机时完整健康检查 | HTTP 503 |
| 数据库恢复后完整健康检查 | HTTP 200，四项均 ok |
| 实际浏览器首页 | 四项服务全部已就绪，已修正窄窗口导航换行 |
| 自建文本和锁文件行尾 | 已归一为 CRLF 并检查 |
| Git 忽略检查 | .env、工具链、缓存、依赖、构建和本地数据不进入版本控制 |

数据库集成检查不仅测试连接，还执行了 vector 欧氏距离运算；停启后迁移版本和扩展仍可读取。

## 启动入口

在项目根目录：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 api
# 另一个终端
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev.ps1 web
```

首页：http://127.0.0.1:3000

API 文档：http://127.0.0.1:8000/api/docs

本次验收后前后端及数据库保持运行；重启电脑后按上述命令启动即可。

## 取舍和已知限制

- **Python 补丁版本：** [Python 3.11.18](https://www.python.org/downloads/release/python-31118/) 于 2026-10-25 发布，仅提供源码。截至本次核验，Astral 官方 Windows 独立构建最新为 3.11.17，因此固定使用 3.11.17，并在 infra/python-downloads.json 保存官方下载 URL 与 SHA256。后续独立构建发布后再更新 pin。没有把 3.11.17 宣称为 Python 官方最新发布版本。
- **工具链元数据：** 本机 uv 0.11.3 内置索引停留在 3.11.15；项目保存的官方元数据使它仍能下载固定的 3.11.17。安装脚本不注册新 Python 到 Windows 注册表。
- **npm 源：** 机器全局 npm 源指向证书过期的旧镜像；仅在项目 .npmrc 和脚本环境中指定官方源，不改全局配置。
- **前端 lint：** 使用 ESLint 10 + Next.js 官方插件 + TypeScript/React Hooks 插件，避免完整配置集所带旧插件的 peer dependency 冲突。[官方插件配置说明](https://nextjs.org/docs/app/api-reference/config/eslint)
- **迁移权限：** 本地开发使用 Compose 创建的数据库所有者执行扩展迁移；接入其他数据库时需预先授权安装 vector 扩展。
- **当前平台：** 自动工具链安装面向 Windows x64。前后端应用代码和锁文件保留后续 Linux 部署的入口，完整容器化服务在第 23 步完成。
- **下一步范围：** 仓库/PR/CI 样例、业务表、worker、GitHub、模型、检索与长期记忆尚未实现；首页相关入口明确显示待开发。

初始迁移回滚保留 vector 扩展，避免误删可能被共享使用的数据库能力。
