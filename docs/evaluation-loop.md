<!-- 文件用途：说明固定评测、失败定位、改进和回归的运行方式及实测边界。 -->
# 评测与回归闭环

2026-11-11更新：本轮已授权真实分层基线和GPT语义复核，当前结果、失败归因及版本边界见[真实基线记录](real-baseline-report.md)。原已查看留出只作回归；发布封装已取消。

入口是 `python -m devflow.eval_cli`。它运行现有的 `AnalysisRunner`、只读 `ToolGateway` 和报告校验，保存逐题输出、实际读取区间、模型/工具 trace、失败原因和人工复核模板。默认使用离线假模型，不读取 `.env` 中的模型密钥，也不连接业务数据库。

固定集位于 `evals/devflow-v1/`：PR、CI、知识问答各 10 题。20 题开发集用于定位和改进，10 题留出集用于冻结改进后的检查。同一来源的变体，以及相互关联的 PR/CI/知识契约，都放在同一组。案例来自人工构造的独立小场景，不代表真实业务流量分布。

`inputs.json` 只包含问题和固定正文；`expectations.json` 保存预期结论、证据行段、禁止结论及允许不确定的边界。只有输入会交给模型。生成器是 `scripts/build_eval_dataset.py`；修改数据或评分规则后应更新版本，保留旧基线。

## 执行一轮闭环

在项目根目录加载工具链，然后运行开发集：

```powershell
. .\scripts\env.ps1
uv run --locked python -m devflow.eval_cli run --split dev --output data/evals/baseline
```

每个结果目录包含：

| 文件 | 用途 |
| --- | --- |
| `report.md` | 逐题检查结果、预期结论、禁止结论和下一步定位建议 |
| `results.json` | 数据集/评分器版本、模型、提示词、检索配置、Git 提交、工作树代码摘要和完整结果 |
| `cases/{case_id}.json` | 本题报告、固定证据及哈希、工具读取区间、请求/响应 trace、耗时与用量 |
| `failures.json` | 失败案例 ID、诊断标签、实际错误和人工失败复核，可直接驱动重跑 |
| `reviews.json` | 绑定本次运行及具体输出 SHA256 的人工语义复核模板 |
| `comparison.json` | 提供 `--baseline` 时生成的逐题改善、退步和遗留失败 |

先看 `failures.json`，再打开对应题的 JSON：

- `execution` / `schema`：检查错误码、最后一次调用和格式修正。
- `evidence_miss`：`read_by_tool=false` 表示应先查读取/检索；为 true 表示已读到但没有覆盖参考证据的引用。
- `false_positive` / `missed_issue`：核查 base/head 与业务契约，语义结论需人工确认。
- `citation`：核查证据身份、版本和已读区间。
- `wrong_stage` / `abstention`：核查日志阶段或材料不足时的表达。

改进代码、提示词或检索后，先重跑失败题，再执行同组完整回归：

```powershell
# 快速验证失败题，保留原始结果。
uv run --locked python -m devflow.eval_cli run --cases-from data/evals/baseline/failures.json --output data/evals/failure-rerun

# 同一组完整开发集：逐题比较，改善不能掩盖另一题的退步。
uv run --locked python -m devflow.eval_cli run --split dev --baseline data/evals/baseline --output data/evals/candidate
uv run --locked python -m devflow.eval_cli compare --baseline data/evals/baseline --current data/evals/candidate --output data/evals/comparison.json

# 开发改进冻结后，再看留出集；也可以显式运行全部 30 题。
uv run --locked python -m devflow.eval_cli run --split holdout --output data/evals/holdout
uv run --locked python -m devflow.eval_cli run --split all --output data/evals/all
```

指定题可重复使用 `--case`，例如 `--case pr-owner-fixed --case pr-null-unchanged`。基线与候选必须使用相同数据内容、评分器、模型/供应商、检索适配器和整组题目；不兼容的基线会在请求模型前拒绝。工作树代码、提示词、上下文配置可以变化，并分别记录。输出目录必须为空或尚不存在。

## 人工语义复核

本项目也可按用户指定由 GPT 承担复核角色，reviewer 必须如实记录为 GPT，不把模型复核写成真人评审。2026-11-09 已完成固定30题的 GPT 复核，并另审查9份历史 DeepSeek 真实报告；来源、逐题判断、失败原因与原始证据缺口见 [GPT语义复核记录](gpt-semantic-review-2026-11-09.md)。两批结果分别统计。

自动检查衡量报告结构、实际已读的引用范围、参考证据覆盖、正常 PR 误报、CI 阶段标签及拒答措辞。它不能判定“引用是否支持结论”“根因解释是否正确”或“所有预期问题是否都被识别”。参考证据覆盖和阶段标签只是代理指标，不作为语义准确率发布。

人工逐题对照原文和参考标注，在 `reviews.json` 填写 `verdict`（`pass` / `fail`）、`reviewer`、`notes`。失败时还需选择 `failure_tags`：`missed_issue`、`false_positive`、`wrong_root_cause`、`unsupported_claim`、`bad_answer` 或 `other`。未完成的题保留 `pending`。然后生成单独的已复核结果：

```powershell
uv run --locked python -m devflow.eval_cli review --run data/evals/candidate --reviews data/evals/candidate/reviews.json --output data/evals/candidate-reviewed
```

复核不覆盖原始运行，也不抹掉自动失败。新输出必须重新复核；旧运行人工通过、新运行待复核，会在比较中标为 `semantic_review_lost`，避免误称质量继续达标。即使不改输出，复核也只能绑定模板指定的运行和 SHA256。

`run` / `review` 退出码：0 为自动检查和全部人工复核通过，1 为存在自动或人工失败，2 为参数/输入错误，3 为自动检查通过但语义复核未完成。`compare` 的 0 仅表示没有新增退步，1 表示存在退步；仍失败和待复核的数量始终单独显示。

## 模型和检索边界

显式添加 `--provider configured` 才使用 `.env` 中配置的模型，继续经过主库共享预算预留/结算；真实请求会产生用量。默认 fake 为有限规则演示，不会识别所有 30 题。失败调用保留已知 usage，未知用量单独计数；目录价估算不是服务商账单。

知识问答使用固定文档快照的内存关键词适配器（`snapshot-keyword-v1`，共用生产分词规则），验证 Agent 检索调用、引用和材料不足时的处理。它不验证 PostgreSQL/pgvector 混合检索，也不提供生产 Recall@6。关键词与混合检索、压缩前后两组效果实验仍属于第 22 步后续工作，当前没有真实模型效果结论。

确定性工程回归独立于效果评测，统一入口为：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1 -Integration
```

权限在 `test_agent.py` / `test_github_client.py`，取消和重连在 `test_week02_integration.py`，真实进程恢复与记忆撤销在 `test_week05_integration.py`，文档删除与历史引用在 `test_week04_integration.py`。`test_evaluation.py` 验证来源隔离、答案不进入模型、引用诊断、失败调用用量、复核绑定和回归门禁。普通检查不调用真实模型。

## 2026-11-05 实测

本轮用离线假模型完成了“评测 → 失败定位 → 修改 → 失败重跑 → 完整回归”：

| 范围 | 改进前自动通过 | 改进后自动通过 | 结果 |
| --- | --- | --- | --- |
| 20 题开发集 | 12/20 | 14/20 | 两题误报消除，逐题新增退步为 0，仍失败 6 题 |
| 原始 8 道失败题 | 0/8 | 2/8 | 修复题通过，其余失败继续保留 |
| 冻结后全部 30 题 | 未执行 | 18/30 | 开发集 14/20，留出集 4/10；语义全部待人工复核 |

发现的问题是离线假模型会扫描 base 中已被修复的缺陷、以及 head 中未变更的旧代码，进而误报新增风险。修正为只比较已完整读取的 base/head 正文，并仅把 head 新增或替换行作为规则候选；diff 的行号不会混入文件正文。

`pr-owner-fixed` 和 `pr-null-unchanged` 的 `false_positive` 消失。仍失败的开发题包含分页遗漏、除零、CI 错误行引用不足和规则尚不支持的 lint/OOM/DNS；留出集还暴露了租户缓存、时区、其他 CI 根因与知识检索覆盖缺口。留出结果未用于本轮调参。这些结果说明流程能够暴露并保留失败，不能用作真实模型准确率。

完整本地制品在 `data/evals/loop-baseline-v1/`、`loop-regression-v1/`、`loop-failures-rerun-v1/` 和 `loop-all-v1/`。初始执行在评分器开发期间采集；最终基线用相同定稿评分规则对保存的原始输出重新评分，没有重新调用旧模型。`rescored` 字段保留原始运行 ID、原始结果摘要和评分器摘要。可随源码核查的精简记录见 [`evals/regressions/2026-11-05.json`](../evals/regressions/2026-11-05.json)。

验证：`scripts/check.ps1 -Integration` 通过后端全量245项（包含当时21项评测测试）、前端56项、OpenAPI一致性、Ruff、ESLint、TypeScript及Prettier检查。随后补充复核命令完整链路与同标签不同证据的回归测试，评测专项23项全部通过。修改和新增的文本文件均校验为CRLF。
