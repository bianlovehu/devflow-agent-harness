# 文件用途：运行演示服务的启动配置检查。
import os

from taskboard.settings import load_database_url


if __name__ == "__main__":
    load_database_url(dict(os.environ))
    print("Configuration ready")
