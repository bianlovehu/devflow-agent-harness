<!-- 文件用途：说明样例工程、数据生成方式和参考标注边界。 -->
# 人工构造的演示数据

taskboard/seed 是一个可运行的轻量 Python 工程。taskboard/documents 保存后续 RAG 用的设计、访问策略、CI 手册和故障复盘。

运行以下命令生成固定的 Git 提交、PR diff、代码快照、CI 日志与 dataset.json：

```powershell
. .\scripts\env.ps1
uv run --locked python scripts/build_fixtures.py
```

Git 操作只发生在项目 .cache/fixture-build 下新建的临时仓库，不连接远端。提交身份和时间固定；快照、diff、SHA 与日志可以重复生成。所有文本使用 CRLF。

每个案例的预期发现、证据位置和不应得出的结论，单独保存在 evals/fixtures/expectations.json。业务 API 不读取该文件，防止把参考答案混入后续 Agent 输入。

样例数据没有真实 GitHub URL、真实用户、真实凭据或真实事故。API 和页面均标记 data_source=fixture。应用不会运行这个示例工程；只有开发者主动执行测试时才会运行自建测试代码。
