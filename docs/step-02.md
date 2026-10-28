<!-- 文件用途：记录演示数据、浏览界面及模型连通验证。 -->
# 第 2 步：可控演示案例验收

日期：2026-10-26（Asia/Shanghai）

状态：完成样例数据、统一只读接口和浏览界面。同时按用户授权配置并实测 DeepSeek 连通性。

## 数据清单

所有业务数据均由项目人工构造，不对应真实 GitHub 仓库、用户或生产事故。

| 类型 | 内容 |
| --- | --- |
| Python 工程 | Taskboard，任务列表、标题处理、可选标签及配置检查 |
| PR #101 | 正常的标题连续空格规范化 |
| PR #102 | 移除所有者过滤，产生跨用户任务读取风险 |
| PR #103 | dict.get 默认值不能覆盖显式 null，导致合法输入被类型检查拒绝 |
| CI #201 | PR #103 的空值标签测试失败，实际错误为 ValueError |
| CI #202 | 指定的人工构造依赖版本无法解析，测试未开始 |
| CI #203 | 缺少 DATABASE_URL，集成测试未开始 |
| 项目资料 | 架构说明、访问策略、CI 排查手册、空值回归复盘，共 4 份 |
| 标注 | 6 个案例，分别给出预期发现、固定版本证据行及不应得出的结论 |

复盘资料提到历史 TypeError，而当前 PR #103 会先被类型检查以 ValueError 拒绝。这一差异是刻意保留的核查案例，不能用历史资料替代当前提交证据。

## 文件与生成方式

- fixtures/taskboard/seed/：可运行的 Python 基础工程。
- fixtures/taskboard/snapshots/：基础提交及 3 个 PR HEAD 的完整快照。
- fixtures/taskboard/pull-requests/：由 Git 生成的 diff。
- fixtures/taskboard/ci-logs/：3 份带固定时间的人工日志。
- fixtures/taskboard/documents/：4 份资料原文。
- fixtures/taskboard/dataset.json：API 使用的公开样例数据。
- evals/fixtures/expectations.json：独立存放的参考标注，业务 API 不读取。
- scripts/build_fixtures.py：固定提交身份和时间，在项目缓存临时 Git 仓库中生成上述材料。

Git 提交 ID 来自真实的本地 Git 提交，属于人工构造数据，不能当作真实 GitHub 提交。生成器不会连接远端，也不会修改 DevFlow 主仓库的提交历史。临时仓库清理前检查绝对路径，并处理 Windows Git 对象只读属性。

文本文件保存为 CRLF。dataset 中的源码、日志与文档字符串按 LF 规范化；content_sha256、log_sha256 和文档 version 均是规范化 UTF-8 文本的 SHA256。

## 界面与接口

入口：http://127.0.0.1:3000/repositories

仓库页面支持：

- PR、CI、项目资料三个分类，刷新时保留 URL 中选中的资源。
- PR diff、BASE/HEAD 版本、完整文件和行号。
- CI 日志、失败阶段、关联 PR、HEAD 和内容哈希。
- 项目资料完整原文、行号与版本哈希。
- 加载、空数据、错误和重试状态。
- 页面顶部和资源元数据中的明确样例标识。

业务接口统一使用 /api/v1：

```text
GET /runtime
GET /repositories
GET /repositories/{repo_id}
GET /repositories/{repo_id}/pull-requests
GET /repositories/{repo_id}/pull-requests/{number}
GET /repositories/{repo_id}/ci-runs
GET /repositories/{repo_id}/ci-runs/{run_id}
GET /repositories/{repo_id}/documents
GET /repositories/{repo_id}/documents/{document_id}
```

Pydantic 契约与 RepositoryDataSource 协议约定了同一套读取接口。DATA_SOURCE=fixture 使用离线数据。设置 github 后返回清晰的 503，直到第 5 步实现真实适配器；不会偷偷返回样例数据。不存在的仓库或资源返回 404。

前端只经自己的只读代理访问这些业务路径，未暴露文件读取或任意远端请求能力。

## DeepSeek 接入

用户提供的密钥已写入被 Git 忽略的根目录 .env，未写入示例、源码、页面、样例数据或验收记录。

- 模型：deepseek-flash，官方 HTTPS 端点。
- 实测：一次请求成功，返回预期 OK；输入 9 tokens、输出 1 token、合计 10 tokens。
- 探测关闭思考模式，输出上限 8 tokens，不重试。
- runtime 只返回是否配置和模型名称，绝不返回密钥。
- 浏览样例、刷新健康状态和普通自动测试均不调用真实模型。
- 完整的工具调用、usage 持久化、任务预算与 Agent 分析仍按第 9 步及后续计划实现。

手动再次验证会产生一次小额 API 调用：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-deepseek.ps1
```

参考：[DeepSeek 官方接入文档](https://api-docs.deepseek.com/)。

## 验证

- API 与模型探测测试：20 项通过（包含真实数据库集成检查）。
- 示例 Python 工程：5 项基础测试通过。
- 数据生成重复执行：dataset 字节哈希与提交 SHA 保持一致。
- 测试核对快照、源码哈希、日志哈希、资料版本与 6 个案例的证据行。
- 无密钥 fixture 浏览测试通过；测试断言不会请求模型。
- 未实现的真实模式返回 503；未知仓库/资源不返回其他仓库内容。
- PR 权限缺失、null 回归和正常修改的实际行为与标注一致。
- Ruff、ESLint、TypeScript、Prettier 和 Next.js 生产构建通过。
- 实际浏览器完成仓库 → PR diff → HEAD 文件 → CI 日志 → 资料原文验收。
- 项目文本使用 CRLF；.env 忽略规则和源文件/浏览器制品密钥检查通过。

## 当前边界

本步骤从版本化 JSON 读取样例，没有新增业务数据库表。文档尚未向量化，尚未创建或执行 Agent 任务，也未接入真实 GitHub。资料查看只显示文本，不执行 HTML。

下一步是第 3 步：建立仓库、会话、运行任务、事件、证据和制品的数据模型，并实现迁移与幂等的样例导入。
