# 文件用途：离线导出 FastAPI 的 OpenAPI 契约，不启动服务或连接数据库。
import json

from devflow.main import app

if __name__ == "__main__":
    print(json.dumps(app.openapi(), ensure_ascii=True, sort_keys=True))
