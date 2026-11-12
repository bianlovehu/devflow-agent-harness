# 文件用途：供容器检查API就绪、worker实际轮询/租约心跳与数据库依赖；不请求模型。
import argparse
import json
import os
import time
from pathlib import Path
from urllib.request import urlopen

from devflow.config import get_settings
from devflow.database import create_database_engine
from devflow.health import inspect_health


def worker_heartbeat():
    filename = os.environ.get("DEVFLOW_WORKER_HEARTBEAT")
    if filename:
        target = Path(filename)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"pid": os.getpid(), "at": time.time()}), encoding="utf-8", newline="\r\n"
        )
        temporary.replace(target)


def check_worker(filename, *, maximum_age=15):
    value = json.loads(Path(filename).read_text(encoding="utf-8"))
    if not 0 <= time.time() - value["at"] <= maximum_age:
        return False
    # SIG0仅在POSIX是非破坏性的进程检查；Windows不可用os.kill模拟。
    if os.name == "posix":
        os.kill(value["pid"], 0)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("service", choices=["api", "worker"])
    args = parser.parse_args()
    try:
        if args.service == "api":
            with urlopen("http://127.0.0.1:8000/api/v1/health", timeout=5) as response:
                ready = response.status == 200 and json.load(response)["status"] == "ok"
        else:
            ready = check_worker(os.environ["DEVFLOW_WORKER_HEARTBEAT"])
            engine = create_database_engine(get_settings())
            try:
                ready = ready and inspect_health(engine).status == "ok"
            finally:
                engine.dispose()
    except (OSError, ValueError, KeyError):
        ready = False
    raise SystemExit(0 if ready else 1)


if __name__ == "__main__":
    main()
