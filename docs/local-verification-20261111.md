<!-- 文件用途：记录本机源码进程的隔离验证与工程检查证据。 -->
# 本地验证记录（2026-11-11）

本轮不封装发布版本。验证运行在当前Windows电脑，数据库为已有PostgreSQL/pgvector服务；仅创建随机隔离库，原始制品保存到独立目录。日常数据库与制品不被重置。

```powershell
. .\scripts\env.ps1
uv run --locked python scripts/local_smoke.py --directory data/local-verification/20261111-native
```

结果已通过，记录位于`data/local-verification/20261111-native/verification.json`，创建和重启结果分别为`created.json`、`restarted.json`，三个服务日志在同目录。

- API、worker、前端均直接从源码在本机启动，不构建应用镜像。
- 环境明确固定fixture/fake，真实供应商和GitHub凭据在子进程中置空。
- 新随机数据库通过bootstrap迁移至0008，幂等导入fixture和5份知识文档；模型文件仅复用显式准备的本地E5。
- 完成PR、CI、知识问答、记忆提取/批准与文档上传索引，所有业务请求通过前端代理。
- 停止并重新创建三个服务进程，核对同一批run ID、报告/输入哈希、原始证据、文档版本与已批准记忆。
- 前后主账本相同：结算3.689716元、未知预留0.169460元；本机fake验证未新增真实模型费用。
- 结束时仅终止脚本持有的子进程、删除本脚本随机创建的数据库，保留日志和独立制品。日常数据库继续运行。

完整工程检查入口为`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1 -Integration -Build`。首次本轮执行通过253个后端测试、56个前端测试、OpenAPI、Ruff、ESLint、TypeScript、Prettier及Next构建。后续新增隔离制品路径测试与提示词改进后，相关66项测试通过；完整最终检查已通过254项后端测试、56项前端测试及全部契约/静态/构建检查；日志与结构化记录保存在`data/local-verification/20261111-checks/checks.log`和`verification.json`。

故障检查的具体入口：

| 要求 | 测试入口 |
| --- | --- |
| 真实子进程中断及checkpoint恢复、不重复写入 | `test_week05_integration.py:test_real_process_crash_resumes_fixed_snapshot_without_duplicate_business_writes` |
| 二次失联、原证据缺失不能改用新证据 | `test_week05_integration.py:test_second_worker_loss_stops_and_missing_artifacts_do_not_recapture`及`test_missing_snapshot_artifact_on_recovery_fails_without_fresh_capture` |
| 排队取消、执行中取消、旧租约隔离 | `test_week02_integration.py`对应cancel/lease测试 |
| SSE断线续传及终态竞争 | `test_week02_integration.py`对应sse/stream测试，前端`event-sequence.test.mjs`及`backend-proxy.test.mjs` |
| 记忆批准、撤销、过期及下一次模型调用前失效 | `test_week05_integration.py`对应memory/revoked测试 |
| 普通任务不执行checkpoint建表、缺模型不下载 | `test_release.py` |

托管GitHub Actions没有在本轮执行；已有工作流不能当作云端通过记录。历史容器备份恢复记录在`data/release`及`data/backups`保留，本轮验证不将它们标为最终发布验收。

最终源码另在data/local-verification/20261111-native-final完成两轮本机进程验证，增加检查新worker PID心跳及隔离ModelCharge记录数为0。主账本当时有并行真实评测，前后差额不归因于fake演示。其后工具行数/压缩次序修正新增58项针对性测试通过，最终统一检查记录在data/local-verification/20261111-tool-fixes，不覆盖前一轮日志。

工具修复后完整检查首次258通过/1失败：原分页测试假定请求创建顺序等于时间戳顺序，未固定时间。现固定首组时间及第二组并列时间，仍验证时间与UUID排序；相关3项通过，259项后端、56项前端与全部契约/静态/构建复验通过。失败原日志保留20261111-tool-fixes，复验日志及摘要在20261111-tool-fixes-recheck。当前冻结源码再经20261111-final-fixes验证两次本机启动、重启与相同报告/文档/记忆/证据，并确认隔离模型费用记录为0。CI检查job显式准备固定E5后才跑真实本地检索测试；托管Actions仍未执行。
