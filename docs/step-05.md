<!-- 文件用途：记录 GitHub 只读适配器、同步边界及真实网络验收结果。 -->
# 第 5 步 GitHub 只读适配器验收

日期：2026-10-28（Asia/Shanghai）

状态：第5步已完成。可添加GitHub仓库、同步有限摘要、按需读取PR文件和同仓库Issue引用、CI及job步骤，并按job请求日志。第6步继续完成真实来源的版本固定和证据制品；本步实时预览不作为已固定分析证据。

## 数据与接口

迁移0003_github_sync_state为repositories增加可空的JSONB同步状态，保存仓库抓取时间及PR、CI摘要的抓取时间、范围和警告。已有样例、会话、任务和证据表不改写。GitHub仓库使用github-{GitHub数字ID}作为本地标识，重复添加不创建重复仓库，样例和GitHub读取按来源隔离。

新增接口：

```text
POST /api/v1/repositories
POST /api/v1/repositories/{repo_id}/refresh
GET  /api/v1/repositories/{repo_id}/ci-runs/{run_id}/jobs/{job_id}/logs
```

既有仓库、PR、CI列表和详情接口复用同一业务契约。POST仅改变本地登记与同步状态，对GitHub的请求全部为GET。运行配置只返回github_configured布尔值，不返回Token。

初次或手动刷新同步最近更新的20条PR及最近20条CI摘要，列表只读本地缓存。变更文件与job通过有限分页读取；分页链接仅用来判断下一页，后续请求仍使用固定API路径。文件最多300条，job最多200条，达到上限会标记不完整。缺少diff、全文或日志不会用空的完整内容伪装。

PR详情读取正文中最多5条同仓库Issue引用，明确标记body_reference。外仓库引用不触发访问，正文、标题、diff与日志都作为纯文本展示，不执行其中内容。手工关联和全部关闭关系不属于当前范围。

## 超时与错误

GitHub请求采用2026-03-10 REST API版本，API主机固定为api.github.com。单次网络超时30秒，单次业务读取总时长60秒，代理给仓库读取保留70秒窗口。网络及5xx最多重试2次，鉴权和参数错误直接返回。

| 情况 | 错误码 | 行为 |
| --- | --- | --- |
| 未配置Token但资源要求认证 | github_authentication_required | 提示配置相应只读权限 |
| Token无效或过期 | github_authentication_failed | 不自动重试 |
| 权限不足 | github_forbidden | 提示仓库范围与权限 |
| 资源不存在或不可见 | github_not_found | 保留GitHub的404含义，不猜测私有资源是否存在 |
| 主限流或次限流 | github_rate_limited | 返回429、Retry-After及倒计时 |
| job未完成或日志未准备 | github_logs_not_ready | 提示稍后读取 |
| job存在但日志404或410 | github_logs_unavailable | 返回410，说明过期或不可用 |
| 请求总时间耗尽 | github_timeout | 返回504并结束读取 |

冷却状态按主机和令牌摘要在API进程内共享；冷却结束前，新客户端也不向该主机发请求。认证令牌不写入冷却缓存。上游权限失败时，仓库摘要保留上一次成功数据与抓取时间，并携带新的警告。

日志先核验job属于当前仓库和run。签名跳转仅允许HTTPS及GitHub日志存储域名，外部下载不携带Authorization。每次响应最多4MiB，前端日志最多显示前2000行。Token只从服务端环境读取，不使用系统Git凭据或浏览器登录状态。

## 真实网络与页面验收

匿名读取公开仓库pallets/flask，登记到本地数据库的标识为github-596892。没有将已登录Git账号的凭据复制到应用。

| 验收 | 实际结果 |
| --- | --- |
| 仓库登记与摘要 | 20条PR、20条CI，无同步警告 |
| PR详情 | PR6168，读取12个变更文件，未达到分页上限 |
| PR输入版本 | HEAD为7689f98403e2c0b0bc8d1031e60f8cff2620e86a |
| CI详情 | run40606945025，completed和success，第1次尝试 |
| job读取 | 读取到1个job及其步骤 |
| 日志权限 | 匿名读取job122548688051日志得到403，页面显示github_forbidden及request_id |
| 界面来源 | 显示GitHub、抓取时间、同步范围及真实成功状态 |
| 数据隔离 | 样例模式仍只显示样例；GitHub仓库、缓存和既有任务独立保留 |

真实日志成功下载尚未使用Token验证；已用模拟HTTP验证签名跳转、无令牌外部下载、404/410和未就绪日志。公开仓库元数据可读不代表每个日志端点也允许匿名访问。

浏览器使用独立8001/3001端口检查真实读取，默认3000/8000样例服务和`.env`模式配置保留。临时服务在验收后关闭。新建与刷新HTTP流程使用隔离数据库及受控GitHub响应验证，标准使用方式见README的GitHub只读模式。

## 自动验证与工程约定

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1 -Integration -Build
```

87项后端测试通过，其中41项覆盖GitHub客户端的地址校验、分页、限流、只读请求、超时、日志与令牌隔离，另有真实数据库的登记幂等、来源隔离、失败后保留摘要及HTTP资源读取测试。38项前端测试通过，验证新增代理范围、Retry-After透传和CI状态映射。Ruff、OpenAPI差异检查、ESLint、TypeScript、Prettier和生产构建通过。

新增迁移文件后，健康检查会重新读取迁移头，避免旧进程缓存导致误报待迁移。

新增或修改的文本使用CRLF。源码包含一句文件用途说明，来源校验、限流、签名下载和持久化关键处加中文注释。前端集合和业务类型继续从OpenAPI派生。

下一步是第6步：按PR的base/head SHA读取文件，固定日志job和尝试版本，保存制品与EvidenceRef，使真实GitHub任务也能回看分析时的材料。

## 接口依据

GitHub官方文档：[PR与变更文件](https://docs.github.com/en/rest/pulls/pulls)、[工作流运行](https://docs.github.com/en/rest/actions/workflow-runs)、[job与日志](https://docs.github.com/en/rest/actions/workflow-jobs)、[重试与限流](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api)、[错误排查](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api)。
