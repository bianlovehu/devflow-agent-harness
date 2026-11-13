# 记忆效果固定对照集

32条同仓库合成历史经验（含2条故意误批准的错误经验）、8个问题。inputs.json 为模型可见输入，expectations.json 为独立召回/断言标注。合成批准仅写入每次运行随机创建的隔离数据库，不写业务记忆；全部有来源run和固定序号。

```powershell
. .\scripts\env.ps1
# 只测真实本地E5和生产召回，不调用付费模型
uv run --locked python -m devflow.eval_memory --output data/memory-retrieval-new
# 三组同一真实回答模型，所有请求经过主库共享预算账本
uv run --locked python -m devflow.eval_memory --real --output data/memory-comparison-new
```

先准备本地E5模型并升级主库预算账本；输出目录必须为空。每组相同输入上限12,000、输出上限1,800、单次90秒，固定种子73轮换执行顺序，不填充输入、不自动重试失败调用。每个问题每组一次，共24次真实调用；模型、阈值、代码哈希和数据哈希记录在 results.json。语料建索引与检索都用生产代码和固定E5权重，关键词/向量仅对审核、仓库、有效期及版本过滤后的集合评分。来源UUID和到期时间因隔离库运行而变化，不影响排序；相关性同分按固定记忆UUID排序。

results.json 保存原始请求、回答、usage、命中说明、相关召回和错误经验暴露；report.md 为自动统计；review.json 为逐条解释复核模板。--real 未启用时，答案质量与真实输入token为空，不能当作回答实验。request_id 对应模型响应标识；付费请求通过 source=memory-comparison 的共享账本记录。

2026-11-13 的24次真实调用及非盲解释复核仅保存在本地 runs/20261113，不随 Git 提交；新检出仓库可用上述命令重新生成运行记录。未对测试结果调改断言标注，开发集校准的首轮失败记录保存在 calibration.json。该集没有独立留出或多次重复，不支持推断生产收益；无记忆和最近6条均为有效对照。不能将相关召回提升等同于答案质量提升。
