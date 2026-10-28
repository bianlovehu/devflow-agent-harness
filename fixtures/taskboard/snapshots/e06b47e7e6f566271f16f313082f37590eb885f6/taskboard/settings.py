# 文件用途：读取并校验演示服务所需的数据库配置。
def load_database_url(environ: dict[str, str]) -> str:
    # 配置缺失时明确失败，避免服务带着错误连接信息继续启动。
    value = environ.get("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is required")
    return value
