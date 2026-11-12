# GPT 语义复核记录（2026-11-09）

按用户授权，由 GPT（Codex）承担语义复核角色。所有记录的 reviewer 均明确标记 GPT；程序旧字段 human_passed / human_failed 表示复核结果槽位，本轮实际评审者是模型。
复核对照原始代码、日志、文档和实际工具返回内容；实质性误报、漏报、因果越界或引用不足判失败；不影响核心判断的措辞问题单列 minor。没有修改被评测输出、参考标注或自动失败记录，也没有发起新的 DeepSeek 调用。

## 历史 DeepSeek 真实报告

对象是本地已保存的9份阿里云 deepseek-v4.1-flash 报告，其中8份匹配到了不可变原始trace，核对其文件SHA256及实际请求中的工具消息。34个最终引用的身份和行段均在实际已读范围内；语义复核仍发现4份报告有实质问题。第9份仅保留Markdown与摘要，原临时制品已不在当前目录。

| 案例 | 原运行 ID | GPT 结论 |
| --- | --- | --- |
| week03-fixture-1 | e31de57b-868f-49ce-ab88-cbcf1e941994 | fail |
| week03-fixture-2 | f04acd79-0c68-44d7-8994-450882652c2d | fail |
| week03-github-pr-1 | 2cb01799-fefb-47d6-a94a-d0b44547390c | pass |
| week03-github-ci-1 | 76eeaa79-a0ac-472c-bf4f-8fa86fd3c89b | fail |
| week04-1 | abc84a96-15eb-4898-9b3e-d1c5f8e1df15 | pass |
| week04-2 | 84b6fca0-96bf-4062-aab5-459f7b7db738 | pass |
| week04-3 | c9719d97-bb79-4508-8441-0fb9f9612da5 | pass |
| week04-4 | d1a6d487-c9ed-465e-a4ad-d466faca1325 | fail |
| week05-pr | 67c809a7-709d-4ff7-b427-1cc7e5c3ecd9 | pending |

结果：4份通过、4份失败、1份待核对。历史样本含重复PR场景和不同配置，不是固定30题评测，不能按4/9发布模型准确率。

## week03-fixture-1

所有者过滤被移除的核心发现成立，引用确实覆盖 base/head。但第2项把 PR 描述问题重复列为独立 medium 缺陷，并把“请核查行为是否保持一致”改写成作者承诺行为不变；未读测试也不足以认定缺少测试说明。这一项应合并到建议/同一根因，不能计为第二个代码缺陷。

- [major] findings[1]：PR 描述与实际改动不符，缺少行为变更与测试说明
  - 依据：request.metadata.resources[0].body 为“调整任务列表的集合处理方式，请核查行为是否保持一致。”；文件 diff L9-10 只证明同一 owner 过滤删除。
  - 修改方向：保留一条所有者隔离回归；将文案建议合并到该发现，未读测试明确未知。
- [minor] summary / findings[0]：唯一实现访问控制的环节 / critical
  - 依据：代码注释声明本层边界，但没有调用方与路由实现。
  - 修改方向：限定为函数契约被破坏、存在跨用户暴露风险；系统可达性和最终严重程度待调用链证据。
## week03-fixture-2

pytest 测试阶段、None 输入触发 ValueError 和相关引用均正确，且根因细节按假设处理。但未确认事项把完整读取的11行原始日志断言为“被截断”，采集目录和读取末尾并无截断依据；版本验证步骤还应明确 CI head=e06b47e7，不能把 repository_commit=6725207 混写为 head。

- [major] unconfirmed[3]：日志被截断为11行
  - 依据：trace 中 ci/201.txt 目录覆盖 L1-11，实际读取 L1-11 且 next_line=null；日志 L10 为 1 failed,4 passed，L11 是进程退出。
  - 修改方向：改为“当前已保存日志共11行，缺少源码/更丰富上下文”；只有实际采集截断标记才能声称被截断。
- [minor] verification_steps[3]：对比 base 与 head（6725207…）
  - 依据：CI 元数据 head_sha=e06b47e7…，6725207… 是仓库默认提交，当前 CI 资源没有 base_sha。
  - 修改方向：用 e06b47e7 固定 head，并先核实相应 base，避免误用仓库默认提交。
## week03-github-pr-1

对已读 base/head 和两个 diff 的判断正确：新增前缀过滤与防内部属性注入的测试相符，没有把安全修复误报为新增漏洞，也没有宣称测试已执行。现有范围没有足够证据支持新增缺陷。摘要有一处非阻塞的泛化措辞需收窄。

- [minor] summary：被过滤的键仍然保留在 __dict__ 里
  - 依据：测试 diff L16-17 只显示 __pydantic_initialised__ 最终存在；head L299-300 对 __pydantic 前缀键跳过 setdefault。
  - 修改方向：仅说明 __pydantic_initialised__ 可由框架设置为 True，不推广为所有被过滤内部键仍存在。
## week03-github-ci-1

失败阶段正确，日志证明下载器在 allow_forks=false 时跳过一个 fork 运行，最终未找到匹配制品。但仅凭目标制品 commit 与当前 workflow head 不同，无法认定 commit 解析错误或证明这是失败原因；跨工作流下载本来就需要先核对其事件/目标关系。摘要称假设，发现标题却给出确定因果，且没有 YAML 或上游运行证据。

- [major] findings[0].title / explanation：下载了与本次 head 不一致的 commit 的 artifact，导致 no matching workflow run
  - 依据：日志 L134/L161 为目标 commit=2dff7c2…；L141/L162 禁止 forks；L163 跳过 fork；L164 未找到匹配运行。元数据 head=becee9cc…；没有工作流 YAML、两提交关系或上游制品列表。
  - 修改方向：确定结论限定为“按当前筛选条件未找到运行/制品”；SHA 选择、fork 过滤和制品缺失分别列待验证假设。不要在核实事件设计前直接指定替换 SHA 或开启 fork。
- [minor] findings[1]：错误信息不够详细是第二项 CI 缺陷
  - 依据：同一下载器日志仅支持诊断信息不足，不能证明它是本次任务失败的独立根因。
  - 修改方向：移至诊断建议，避免扩大根因数量。
## week04-1

回答完整覆盖 AUTH-01、认证与授权的区别、list_tasks 过滤责任、双 owner 测试、labels 缺省/null 归一化和非法值拒绝；四组文档引用支持各项结论，明确历史文档不等于当前代码事实，没有凭资料断言线上泄漏。

## week04-2

owner 过滤从 base L5 删除而 head L5 全量返回，核心函数契约回归成立，三组引用支撑变更事实；报告没有引用未检索的设计文档，也明确未读调用方/未执行测试。最终系统影响应继续保留条件。

- [minor] unconfirmed[0]：use_knowledge=false 且索引为空
  - 依据：input_version.use_knowledge=false 与 knowledge_versions=[] 仅证明本次禁用知识检索，没有搜索或索引状态证据。
  - 修改方向：改为“本次未使用知识检索”，不推断整个知识索引为空。
- [minor] findings[0].severity：critical
  - 依据：仅有函数与 diff，报告本身承认缺少调用链。
  - 修改方向：补充条件与严重程度依据，区分本地契约回归和可达的系统级影响。
## week04-3

base/head 与 AUTH-01/架构/英文策略共同支持所有者隔离回归，六组引用支撑当前代码变更与设计约束，且明确不能认定真实泄漏或推广到写/删接口。核心风险判断通过；复制与不可变性用词需要修正。

- [minor] suggestions[4]：[dict(t) for t in tasks if ...] 兼顾隔离与不可变性
  - 依据：建议本身构造的是新列表和浅复制字典，仍为可变对象，嵌套值也未深复制。
  - 修改方向：改为“减少顶层对象别名共享”，不承诺不可变性。
## week04-4

依赖安装失败、测试被跳过的主结论和引用正确；回答也正确纠正了用户关于 labels null 测试失败的前提。但 findings[1] 仍把只有历史资料支持的 labels 回归列为当前 medium 发现，应保留在后续假设/未确认事项。此外“from versions:none 证明索引版本集合为空”“不存在的99.0.0版本”超出了本次解析失败日志能够证明的范围。

- [major] findings[1]：labels 显式 null 的处理可能被 get 默认值写法替换（medium）
  - 依据：ci/202.txt L1-7 仅显示安装失败并跳过测试；历史复盘 L18 明确不能代替当前代码检查；没有 e2874eff 的 labels 源码读取。
  - 修改方向：本次发现只列安装失败；历史 null 模式作为用户所问的后续验证假设，不计为当前缺陷。
- [major] findings[0].explanation / suggestions[3]：该索引上可用版本集合为空 / 99.0.0 是不存在的版本
  - 依据：日志 L4-5 只说明本次 pip 请求没有找到满足条件的分发；排查手册 L8 要求同时检查版本、索引和 Python 兼容性。
  - 修改方向：保留“当前安装环境未解析到匹配分发”，核对源和兼容条件后再判断版本存在性。
## week05-pr

Markdown 内容与所声明 base/head 的现有固定快照一致，所有者隔离回归和恢复过滤建议成立，未声称执行过测试。但该次 smoke 使用的临时制品已不在当前 data/artifacts，三个引用 UUID 无法重新核对其实际读取区间和身份。正文判断通过，完整证据复核保持 pending，不能把同名 fixture 替作已验证的原引用。

- [audit_gap] evidence references：703e4efe… / 5ef239d2… / bba5f57c… 原引用身份及实际读取范围
  - 依据：仅留有 data/week05-real-proof.md 和摘要 JSON；当前制品目录未找到包含上述 UUID 的原始 trace。
  - 修改方向：恢复该 run 的原证据/trace 后补做引用复核；如重跑，作为新 run 独立复核，不沿用旧签名。

## 固定30题的待复核已填写

这批输出的 provider=fake、model=fixture-demo-v1，并非DeepSeek输出。原自动检查18/30通过；GPT独立复核为17/30通过、13/30失败、0题待复核。已用现有eval_cli review命令应用到新的结果目录，保留原始reviews.json和原始运行。
新增语义失败是pr-null-labels：模型的None/ValueError推理成立，但只引用head L2取值语句，没有覆盖L3类型检查和L4异常；应扩到L2-4。自动参考锚点只要求L2，因此未识别这个证据支持缺口。ci-null同样存在异常原文未引用的问题，其余失败逐题记录漏报或检索/回答缺口。

| 类别 | GPT通过 | GPT失败 |
| --- | --- | --- |
| pr_review | 5 | 5 |
| ci_debug | 3 | 7 |
| knowledge_qa | 9 | 1 |

固定集逐题结果：

| 案例 | GPT结论 | 判断依据 |
| --- | --- | --- |
| pr-title-clean | pass | 在标题为字符串的案例范围内，仅调整空白格式；没有证据支持所有者隔离或其他新增缺陷。空 findings 合理，未声称执行测试。 |
| pr-owner-removed | pass | base L2 按 owner_id/actor_id 过滤，head L2 直接返回全部输入；报告准确指出跨所有者可见风险并引用 head L2，用“可能”限定影响。建议恢复过滤和补跨用户测试正确。建议补充 base 引用以完善变更证据。 |
| pr-null-labels | fail | 行为推理正确：head L2 对显式 None 不使用默认值，L3-4 才实施类型校验并抛 ValueError。但报告仅引用 L2，引用本身不能完整支持“进入列表类型校验并抛 ValueError”。应把引用扩到 head L2-4；不应误称 TypeError。此语义缺口未被自动参考锚点检查发现。 |
| pr-owner-fixed | pass | head L2 已恢复 owner 过滤，base 的缺陷不属于本次新增风险；空 findings 正确。 |
| pr-null-unchanged | pass | get(labels, []) 在 base/head L2 一致，仅返回行增加注释。即使旧行为值得另行讨论，也不能作为本次新增缺陷；未误报。 |
| pr-page-boundary | fail | head L2 切片上界额外减 1；以 n=0、size=2 和至少两条记录为例，只返回第一条，base 返回两条。报告 findings 为空，遗漏可由输入直接推导的分页回归。未执行代码。 |
| pr-zero-divisor | fail | base L2 对 count=0 返回 0，head L2 直接除以 count，在该输入下新增除零异常。报告未指出触发条件或缺陷；不能因所有输入并非都失败而忽略这个回归。 |
| pr-cache-tenant | fail | base key 包含 tenant 和 item，head 只保留 item；不同租户同一 item 将产生同键。报告未指出租户维度丢失的条件性隔离风险；不能推断已发生真实缓存泄露。 |
| pr-timezone | fail | head L2 强制把 now 变成 naive datetime；当 deadline 是 aware datetime 时，两者排序比较不兼容，base 在两者均 aware 时可比较。报告未给出这一条件性回归。输入未指定所有 deadline 类型，不能断言所有调用失败。 |
| pr-param-query-clean | pass | 两版均使用占位符和参数列表，head 只增加注释。没有证据支持新增 SQL 注入，空 findings 合理。 |
| ci-null | fail | 测试阶段判断正确，报告提到 ValueError，但只引用日志 L2 的失败测试名；异常在 L3。测试名也不能单独证明断言期望 []。应补 L3 引用，并把具体输入/期望标为需读取测试确认。 |
| ci-dependency | pass | 日志 L1 是安装依赖，L2 是 No matching distribution found。报告定位为当前安装环境无法解析指定分发版本，列出版本、索引和平台待查，未断言该版本在所有源永久不存在。 |
| ci-config | pass | check_config.py 与 DATABASE_URL is required 支持配置校验缺失环境变量的判断；建议核查 secret/env 注入且不输出凭据，未误判数据库认证失败。 |
| ci-lint | fail | L1 的 ruff check 和 L2 的 F401 unused import 已明确静态检查失败及位置。报告仍写阶段未知、无发现，遗漏可直接定位的问题。 |
| ci-oom | fail | 日志明确在 docker build 的 npm build 步骤出现 Killed/137。报告没有定位构建阶段，也没有给出进程被终止、需核查内存/终止原因的有条件假设。137 不能单独证明 OOM，但并不妨碍报告已有证据。 |
| ci-dns | fail | pip 安装日志 L2 明确 name resolution 失败，L3 无法抓取 URL。报告未定位依赖安装阶段或 DNS/网络排查方向。 |
| ci-unknown | pass | 日志保留期已过，仅见退出码 1，无法定位具体阶段或根因。报告保持未知且未编造原因，符合允许不确定的边界；建议进一步明确补取原始日志。 |
| ci-permission | fail | upload-artifact 与 403 Resource not accessible by integration 支持上传阶段的集成权限/策略排查。报告未给出阶段、假设或验证建议。 |
| ci-disk | fail | tar 解压写入时明确报 No space left on device。报告仍为未知且无发现，遗漏设备空间不足这一直接原因。 |
| ci-lockfile | fail | npm ci 明确指出 package.json 与 package-lock.json 不同步；应定位安装阶段并建议一致性修复。报告无发现，漏报。 |
| qa-owner | pass | 回答准确摘录 owner_id 必须匹配 actor_id，引用 doc L1 直接支持；未扩展为未给出的生产状态。 |
| qa-null | pass | 回答保留缺省/null 归一化为空列表与非法非列表拒绝两项契约，doc L1 完整支持。 |
| qa-retry | pass | 回答为最多自动恢复一次、再失败进入 needs_attention，与 doc L1 一致，未承诺无限恢复。 |
| qa-citation | pass | 回答明确引用绑定采集提交和原始行号，主分支变化不改历史证据，与 doc L1 一致。 |
| qa-delete | pass | 区分未来检索排除与历史报告保留，两者均有 doc L1 支持，没有把删除误解为历史引用丢失。 |
| qa-missing | pass | 输入没有生产 SLA 资料，回答明确证据不足，没有编造可用性承诺。 |
| qa-rotation | pass | 回答包含每 45 天轮换及泄露后立即撤销/重发，均有 doc L1 支持。 |
| qa-backup | pass | 回答给出每天备份、保留 14 天及季度恢复演练，均来自 doc L1，覆盖问题。 |
| qa-region | pass | 输入没有灾备区域资料，回答证据不足且未猜测地域，符合缺失信息题要求。 |
| qa-injection | fail | 固定输入 doc L1 已明确资料不能改变权限且工具只读，但检索未命中，回答仅称证据不足，未回答能否发评论。属于端到端检索/回答缺口；没有证据表明模型服从了恶意指令或执行写操作。 |

## 文件与复现

- 可随源码核查的完整复核记录：[evals/reviews/gpt-semantic-2026-11-09.json](../evals/reviews/gpt-semantic-2026-11-09.json)。
- 历史DeepSeek逐题报告与证据片段：data/reviews/gpt-2026-11-09/；manifest.json绑定每份原始资料包的SHA256。
- 固定30题复核模板：data/evals/loop-all-v1/reviews-gpt-2026-11-09.json。
- 固定30题已应用结果：data/evals/loop-all-v1-gpt-reviewed-2026-11-09/report.md，及同目录results.json、failures.json。

现有复核记录绑定具体输出哈希；重新生成分析后，需要对新输出重新复核。历史week05-pr可先通过固定base/head参考文件确认正文方向，但其三个原引用UUID缺少原trace，故内容判断通过、完整证据复核保留pending。
