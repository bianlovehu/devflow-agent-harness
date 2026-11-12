<!-- 文件用途：把当前已实现的架构选择连接到代码与可执行验证。 -->
# 架构决策索引

本页对应原第24步，仅说明当前实现，不宣称多用户、远端写操作或动态多Agent协作。

| 决策 | 原因与当前实现 | 可核验入口 |
| --- | --- | --- |
| PostgreSQL与pgvector承载业务状态和知识检索 | 仓库、文档版本、任务及证据的关联在同一数据库中校验；本地CPU产生向量，关键词与向量分别召回后以RRF合并，不需要另部署向量服务 | `models.py`、`knowledge.py:search_knowledge`、`eval_retrieval.py`；`test_week04_integration.py` |
| 业务状态和checkpoint分开 | 任务状态、租约和幂等业务写入使用业务表；LangGraph恢复中间状态保存在独立schema。checkpoint不充当业务完成记录，旧租约必须被隔离，避免恢复重复写入 | `checkpoint.py`、`worker.py`、迁移0006/0008；`test_week05_integration.py:test_real_process_crash_resumes_fixed_snapshot_without_duplicate_business_writes` |
| 固定版本与实际已读范围共同约束引用 | 文件、日志和文档来自任务采集时的不可变证据；版本变化不能改写旧报告。存在证据ID只证明身份，必须同时校验行号及工具实际读取，语义支持仍需GPT复核 | `workflows.py`、`tool_gateway.py`、`reports.py:validate_citations`、`evaluation.py`；`test_agent.py`、`test_fixed_files.py` |
| 数据库与文件制品共同持久化 | 数据库存身份、状态与内容哈希，较大文本保存为内容寻址文件；原始外部字节保留，按实际字节校验。只备份数据库不足以恢复报告原文 | `artifact_store.py`、`models.py:ArtifactRecord`；本机隔离验证`data/local-verification/20261111-native` |
| 普通服务不迁移、不下载权重 | 初始化可明确诊断和重跑，避免普通请求触发联网、DDL或竞争；bootstrap用锁串行迁移，固定权重显式准备并校验SHA | `bootstrap.py`、`embeddings.py`、`prepare_rag.py`；`test_release.py` |
| 预算使用共享账本 | 每次真实请求先原子预留，再依usage结算；不确定的中断调用保留预留，重启不重置总账。隔离评测数据不意味着隔离费用账户 | `budget.py`、`model_gateway.py`、`runtime_policy.py`；`test_budget_integration.py` |

上述文件均位于`apps/api/src/devflow`或`apps/api/tests`，准备脚本位于`scripts`。迁移文件位于`apps/api/migrations/versions`。选择带来的限制包括本地向量索引的CPU/内存开销、数据库与制品必须成对保存，以及引用校验无法自动证明语义正确。
