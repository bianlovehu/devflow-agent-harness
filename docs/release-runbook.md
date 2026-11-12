<!-- 文件用途：候选版本的显式准备、完整启动、无费用演示、备份和空项目恢复步骤。 -->
# 候选版本启动手册

> 2026-11-11：发布封装、镜像分发和跨机器验收已取消。本文保留历史部署记录；本轮使用[本地运行手册](local-runbook.md)，不继续下文的发布封装流程。

当前为本轮候选实现，完成验证前以[检查表](release-checklist.md)中的证据状态为准。

要求：Linux containers 的 Docker Engine/Desktop 与 Compose v2（支持 additional_contexts），以及执行准备/验收脚本用的 Python 3.11+。构建访问镜像仓库、PyPI、npm；首次准备权重访问固定的 Hugging Face 文件。运行fixture模式不需要GitHub或模型密钥。具体资源实测在完成干净环境验证后登记。

从源码包解压到新目录后：

```powershell
# 仅此显式准备步骤下载或复用已校验权重，不导入模型服务凭据。
python scripts/prepare_model_assets.py
docker compose build
docker compose up -d --wait --wait-timeout 240
```

默认地址为http://127.0.0.1:3000、API http://127.0.0.1:8000。所有宿主端口只绑定回环地址。init服务负责一次性迁移、样例导入及真实本地向量索引；API/worker启动不执行迁移、不下载依赖或权重。PostgreSQL及checkpoint在postgres_data卷，文档原件、报告trace和证据在app_data卷；向量权重随镜像只读保存。普通重启不会清除这些数据。

默认容器始终为fixture/fake，即使开发机.env配置了真实模型。显式部署真实模式时设置DEPLOY_MODEL_PROVIDER=aliyun、DASHSCOPE_API_KEY、DASHSCOPE_BASE_URL及DASHSCOPE_MODEL；真实GitHub另外设置DEPLOY_DATA_SOURCE=github和GITHUB_TOKEN。凭据只由服务端读取，不进入前端镜像或浏览器。现有报价策略只允许已核查的供应商/地域/模型组合；不自动提高200元预算或180元停止线。

初始化失败先看`docker compose logs init`。配置或密钥调整后执行`docker compose up -d --force-recreate api worker`。日常启动不要手工在API、worker中分别执行Alembic。需要升级schema时显式执行`docker compose run --rm init`，成功后再重建API/worker。

## 三分钟fixture演示

1. 打开仓库，选择Taskboard PR #102，展示固定base/head与所有者过滤删除。
2. 创建分析，展示worker进度、证据行号、报告与Markdown草稿；说明这是离线演示，不执行仓库代码、不发布评论。
3. 打开CI #202，展示安装失败和“测试被跳过”的证据，区分历史labels复盘与当前失败。
4. 在知识库查看已索引中英文资料，提问AUTH-01与labels契约，打开不可变引用。
5. 从PR发现提取经验并批准，展示版本/审核约束；重启后重新打开原报告、文档和记忆。

可自动保存同一链路与持久性证据：

```powershell
python scripts/release_smoke.py --output data/release/create.json
docker compose restart api worker web
docker compose up -d --wait --wait-timeout 240
python scripts/release_smoke.py --baseline data/release/create.json --output data/release/restarted.json
```

## 一致备份与恢复演练

备份脚本暂时停止API/worker写入者，保存数据库和app_data，再启动写入者。先确认没有Compose之外的服务连接同一库写入。脚本不把二进制备份经PowerShell文本管道传输。

```powershell
python scripts/release_backup.py backup --project devflow --directory data/backups/candidate-1
```

恢复仅允许不同的新项目、空数据库和空app_data，拒绝覆盖业务数据。先为新项目配置不同宿主端口（例如POSTGRES_PORT=15433、API_PORT=18001、WEB_PORT=13001），保留同一候选镜像，然后：

```powershell
python scripts/release_backup.py restore --project devflow-restored --directory data/backups/candidate-1
python scripts/release_smoke.py --api http://127.0.0.1:18001 --web http://127.0.0.1:13001 --baseline data/release/create.json --output data/release/restored.json
```

只有同一批run、文档版本、已批准记忆、原始证据和内容哈希都一致，恢复才算通过。不要对日常项目执行`down -v`。候选源码包使用`python scripts/package_release.py --output data/releases/candidate.tar.gz`封装真实工作树，包含原有未提交内容和逐文件哈希，排除密钥与运行数据，不修改Git暂存状态。
