<!-- 文件用途：提供演示 CI 各失败阶段的排查方法。 -->
# CI 故障排查手册

这是演示用排查资料，日志均由项目人工编写。

## 安装阶段失败

若 pip 提示 No matching distribution found，应先核对依赖名、版本、索引和 Python 兼容性。安装尚未成功时，不能把后续测试结果当作已执行。

## 测试阶段失败

保留测试名、输入和堆栈行。TypeError: 'NoneType' object is not iterable 可说明代码遍历了 null，但仅凭最后一行不能排除其他原因，需要绑定对应代码版本。

## 配置阶段失败

DATABASE_URL is required 表示启动前缺少配置。应检查环境变量注入，不直接更改业务逻辑，也不要求输出数据库密码。

## 版本边界

同一 PR 的不同 CI 运行必须以 head_sha 区分，历史日志不能证明当前提交仍然失败。
