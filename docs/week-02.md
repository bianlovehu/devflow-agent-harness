<!-- 文件用途：记录第二周第5—8步的实现、逐项验收证据与当前限制。 -->
# 第二周交付：真实 GitHub 数据与可靠任务通道

目标来自 [六周计划](development-plan.md) 的第5—8步。模型分析属于第三周；本周执行结果统一标为模拟流程，不产出风险结论，不计入模型效果验收。

## 运行方式

先运行 setup 或 `alembic upgrade head`，再分别启动 `scripts/dev.ps1 api`、`scripts/dev.ps1 web`、`scripts/dev.ps1 worker`。当前迁移头为 `0004_worker_leases`。默认仍为 fixture/database；切换 GitHub 模式时 API 与 worker 必须读取同一份 `.env`，并同时重启。凭据只在服务端读取。

常驻 worker 默认一次执行一个任务，模拟阶段各等待3秒，租约30秒，每2秒续租，空队列每1秒轮询；可在环境变量中设置。启动多个 worker 会通过 `FOR UPDATE SKIP LOCKED` 互斥领取；事件和最终结果每次提交都校验随机租约令牌、running 状态和数据库时间。

## 第5步：GitHub 只读适配器

实现与接口细节见 [第5步记录](step-05.md)。支持地址校验、本地登记、最近20条 PR/CI 摘要、按需详情、正文 Issue 引用、job、日志与获取时间。分页和读取量有上限；限流冷却跨请求保留；不自动转为样例数据。API 错误保留错误码和 request ID，权限不足、限流、资源不可见及日志过期分别处理；GitHub 的404可能隐藏私有资源，提示保留此语义。

## 第6步：版本固定与证据

- 创建 GitHub 任务时只读本地同步摘要，记录 base/head 或 CI head/attempt，立即返回任务ID。worker 在 PR 文件列表读取前后校验两端 SHA，变化则 `input_changed`，不绑定混合证据。
- 文件读取只接受完整40位 SHA，逐级读取非递归 Git tree，拒绝链接、子模块、不安全路径和截断 tree；按 blob 大小及 Git SHA1 检查完整性。首批覆盖 Python、JS/TS、JSON/YAML/TOML/INI 等配置、Markdown和TXT，UTF-8文本每份至多256 KiB。
- 检查 patch 各 hunk 的行数与增删总数，缺失/截断时明确标记；base/head 可读时生成补充 diff。新增文件不取不存在的 base，删除文件不取不存在的 head，重命名按 previous_path 取 base。
- CI 使用固定 attempt 的 job 列表，日志绑定 run/attempt/job。外部文件和日志保留原始字节（`.bin`制品），不改写换行；字节 SHA256、行号、获取时间和证据ID进入数据库。前端以文本显示，原始字节仍可按哈希核验。
- 每次最多50个变更文件、20个job、8 MiB证据；文件数量超限、权限或不支持的文件形成检查范围缺口；总字节上限包含元数据，超过则采集失败，不绑定混合或截断制品。元数据制品保存 coverage/warnings。文件、diff、日志和样例文档均使用独立证据ID，可进一步引用行范围。
- 快照与绑定不可变；重试新建 run 并复用已有证据。历史读取只访问数据库与制品，不重新读取 GitHub。无仓库代码执行入口，无任意 shell 工具。

真实验收：公开仓库 `pallets/flask` PR **#6153**，run `6ee23bab-5840-455d-94f4-9ea1cef5694d`，base `d318b683471101618febed18996405ad26462110`，head `e4f64df12156a8a9030023835aa86ffdf95db1a5`。保存8条证据、11条事件，模拟流程成功。`CHANGES.rst`不在首批类型范围，coverage_complete 为 false，页面显示检查范围不完整；没有将这次读取描述为完整仓库审查。

## 第7步：持久化后台任务

- API原子保存问题、queued run和初始事件，`Idempotency-Key`重放同一请求，不再次写消息或启动任务；不同请求复用键返回409。
- 独立进程领取任务，保存owner、随机token、租约、心跳、开始/结束时间和attempt。每一步开始、证据绑定和最终写入均校验所有权。
- 取消queued任务立即结束；running任务先持久化取消请求，当前只读请求允许结束，但不进入下一步骤。取消与结果写入共用任务行锁，取消一旦提交就不能被成功覆盖。
- 失联租约过期由在线worker标记 `needs_attention/worker_lost`，不自动重做步骤。手动重试创建新run、保留原run，支持重试请求幂等。
- 模拟流程验证证据固定、制品完整性和持久化结果；错误、总时长超限、取消均有终态事件。

真实进程实验：仅终止本次QA进程PID30444。run `de9b7443-ca23-4862-af1e-1114f8eae8ab`在租约过期后变为 `needs_attention/worker_lost`；新worker领取其手动重试run `bf83ce42-66f8-4d03-afdf-d0126e140b59`并成功，输入版本完全一致。摘要保存在本地 `data/week02-worker-proof.json`。

## 第8步：SSE与任务时间线

- 事件先随业务事务提交，再由独立短数据库会话读取。每轮先读任务状态再读事件，避免查询间终态提交导致遗漏结束事件。序号在锁定run行后递增；事件正文带run ID、sequence、类型、时间与payload。
- `GET /runs/{id}/stream`发送SSE `id`、`run_event`和终态`end`，支持 `Last-Event-ID`与`after`；每批最多100条，终态前清空剩余事件。每10秒心跳，45秒切换传输会话，浏览器自动续传。
- Next.js代理直接透传流和浏览器取消信号，不缓冲为JSON，不透传Cookie或Authorization。浏览器断开只关闭传输，不调用取消API。
- 前端先读完整历史，再从连续游标订阅；按run ID与sequence合并，历史补查不能覆盖新事件。每5秒补查作为SSE不可用时的后备，任务详情亦轮询恢复状态。
- 时间线显示入队、开始、工具、阶段、错误、取消与结束，保留原事件详情。停止与按原证据重试都有独立按钮。

真实HTTP实验经 `127.0.0.1:3000/api/backend`，run `50cb1daa-f2eb-447b-b6ff-2573a1d1cb8e`：先接收事件1并断开，携带Last-Event-ID=1重新连接，得到2—9，合并与数据库1—9完全相同。后台约24秒持续执行并多次续租，最终成功。摘要在 `data/week02-http-proof.json`。

真实浏览器实验：run `e400d86f-53bd-4973-9c51-631296b8606b`执行中刷新后恢复时间线；关闭页面再打开时已完成，9条事件无重复，控制台无错误。停止另一个排队任务得到run `503c0be7-e4be-4792-a835-2b3a74b3bacf`，只保留入队、取消请求、已取消三条事件。running阶段取消另由真实数据库并发测试验证。

## 验收映射

| 计划要求 | 可核查证据 |
|---|---|
| 真实仓库与来源错误 | `test_github_client.py`、第5步真实读取记录、上述Flask任务 |
| 固定SHA及旧版本不变 | `test_fixed_files.py`、`test_github_worker_pins_artifacts_and_old_run_survives_pr_changes` |
| diff补取、新增/删除/重命名 | `test_diff_completeness`、`test_capture_supplements_missing_patch_and_detects_moving_pr`、三种文件状态测试 |
| 日志原文/job/哈希 | `test_ci_capture_uses_fixed_attempt_and_original_log_bytes`、CI数据库证据测试 |
| 不执行外部代码 | `FixedFileReader`仅GET tree/blob；worker固定两个只读工具，没有shell注册 |
| 立即返回、持久化与幂等 | 创建接口及既有事务/并发集成测试；真实浏览器重试任务 |
| 并发领取、心跳、过期隔离 | `test_concurrent_workers_claim_once_and_finish_persisted_simulation`、旧token拒绝测试、真实进程实验 |
| 排队/执行中取消、失败、超时 | `test_week02_integration.py`的取消、缺失制品和timeout测试 |
| 先保存事件与批量续传 | `test_sse_replays_every_persisted_event_after_cursor_across_batches`（超过200条） |
| 刷新/断开不取消、无重复遗漏 | 浏览器实测、实际HTTP续传、`event-sequence.test.mjs` |

验证结果：后端123项测试通过，前端42项测试通过，OpenAPI契约检查、Ruff、ESLint、TypeScript、Prettier与生产构建通过；最新加强的版本更新验收另行通过。项目166个文本文件的CRLF检查及 `git diff --check` 通过。

统一命令：`powershell -ExecutionPolicy Bypass -File scripts/check.ps1 -Integration -Build`。另有 `scripts/week02_smoke.py` 可在本地数据卷重复生成样例或真实GitHub证据证明（运行前停止常驻worker，避免同时领取）。

## 已知限制

1. 执行器为simulation，尚无模型报告、LangGraph/checkpoint、RAG或长期记忆。模拟succeeded只表示证据与通道流程完成。
2. 默认配置保留fixture/database；仓库实时预览不等于任务固定证据。真实Token仍由用户在服务端显式配置；公开PR实测不证明私有仓库或受限日志可读。成功的日志下载/持久化由可控HTTP和真实数据库测试覆盖。
3. PR采集前后SHA检查拒绝常见变更竞态；GitHub文件列表无ref参数，极短时间内改走又回到相同SHA的列表竞态不能提供平台级原子快照保证。保存的全文仍来自各自固定SHA，并校验Git blob。
4. 自动恢复属于第19步；没有存活worker时，租约过期状态直到下次worker启动才会更新。中止网络请求可能等待当前GET超时，取消后不启动下一个步骤。
5. 二进制、非UTF-8、RST等未支持类型、不可达的fork提交、超大文件或超过采集规模会保留缺口。CI没有任何可读取日志时进入待处理，仍保存元数据和原因。
6. 文件先原子落盘再提交数据库；事务回滚可能留下未引用制品，尚未实现垃圾回收，不影响已绑定证据。历史证据缺失/篡改会明确报错。

协议依据：[Git Trees](https://docs.github.com/en/rest/git/trees)、[Git Blobs](https://docs.github.com/en/rest/git/blobs)、[Actions运行与attempt](https://docs.github.com/en/rest/actions/workflow-runs)、[SSE续传字段](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)。
