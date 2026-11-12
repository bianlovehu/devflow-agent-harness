# 文件用途：本机源码API/worker/前端的fake隔离启动、重启与持久性演示，不使用应用镜像。
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

from devflow.budget import get_budget_ledger
from devflow.config import PROJECT_ROOT, get_settings
from devflow.database import create_database_engine
from devflow.eval_cli import provenance
from devflow.evaluation import write_json
from devflow.models import ModelCharge
from sqlalchemy import func, select, text


def wait_ready(url, processes, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for name, process in processes.items():
            if process.poll() is not None:
                raise RuntimeError(f"{name}已退出，请查看隔离目录日志")
        try:
            with urlopen(url, timeout=3) as response:
                value = json.load(response)
                if response.status == 200 and value["status"] == "ok":
                    return value
        except (OSError, URLError, ValueError):
            pass
        time.sleep(0.5)
    raise TimeoutError(f"就绪检查超时: {url}")


def stop(processes):
    for process in reversed(list(processes.values())):
        if process.poll() is None:
            if os.name == "nt":
                # 只终止本脚本持有且仍运行的Popen进程树，不按名称查杀用户服务。
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                process.terminate()
            process.wait(timeout=15)
    processes.clear()


def main():
    parser = argparse.ArgumentParser(description="本机fake隔离演示与重启验证")
    parser.add_argument("--directory", required=True)
    parser.add_argument("--api-port", type=int, default=18000)
    parser.add_argument("--web-port", type=int, default=13000)
    args = parser.parse_args()
    directory = Path(args.directory).resolve()
    if directory.exists() and any(directory.iterdir()):
        parser.error("目录必须不存在或为空，防止覆盖已有记录")
    if not directory.is_relative_to((PROJECT_ROOT / "data").resolve()):
        parser.error("隔离记录必须保存在项目data内")
    if args.api_port == args.web_port:
        parser.error("API与前端端口必须不同")
    for port in [args.api_port, args.web_port]:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    node = shutil.which("node")
    if not node:
        parser.error("先通过scripts/env.ps1载入项目Node")
    directory.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    budget_before = get_budget_ledger().summary()
    database = "devflow_local_" + uuid4().hex
    environment = {
        **os.environ,
        "POSTGRES_DB": database,
        "MODEL_PROVIDER": "fake",
        "DATA_SOURCE": "fixture",
        "FIXTURE_STORAGE": "database",
        "ANALYSIS_EXECUTOR": "agent",
        "SIMULATION_STEP_SECONDS": "0",
        "DASHSCOPE_API_KEY": "",
        "DEEPSEEK_API_KEY": "",
        "GITHUB_TOKEN": "",
        "DEVFLOW_ARTIFACT_ROOT": str(directory / "artifacts"),
        "DEVFLOW_WORKER_HEARTBEAT": str(directory / "worker-heartbeat.json"),
        "WEB_ORIGIN": f"http://127.0.0.1:{args.web_port}",
        "BACKEND_URL": f"http://127.0.0.1:{args.api_port}",
        "PYTHONUTF8": "1",
        "NEXT_TELEMETRY_DISABLED": "1",
    }
    admin = create_database_engine(settings).execution_options(isolation_level="AUTOCOMMIT")
    processes, logs, stages = {}, [], []
    created = False

    def run(command):
        subprocess.run(command, cwd=PROJECT_ROOT, env=environment, check=True)

    def start():
        started_at = time.time()
        commands = {
            "api": [
                sys.executable,
                "-m",
                "uvicorn",
                "devflow.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.api_port),
            ],
            "worker": [sys.executable, "-m", "devflow.worker"],
            "web": [
                node,
                str(PROJECT_ROOT / "apps/web/node_modules/next/dist/bin/next"),
                "dev",
                "--hostname",
                "127.0.0.1",
                "--port",
                str(args.web_port),
            ],
        }
        for name, command in commands.items():
            log = (directory / f"{name}.log").open("a", encoding="utf-8", newline="\r\n")
            logs.append(log)
            processes[name] = subprocess.Popen(
                command,
                cwd=PROJECT_ROOT / "apps/web" if name == "web" else PROJECT_ROOT,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        health = {
            "api": wait_ready(environment["BACKEND_URL"] + "/api/v1/health", processes),
            "web": wait_ready(environment["WEB_ORIGIN"] + "/api/health", processes),
        }
        # CLI检查新鲜轮询心跳和相同隔离数据库的完整健康状态。
        for _ in range(30):
            heartbeat_path = Path(environment["DEVFLOW_WORKER_HEARTBEAT"])
            if heartbeat_path.exists():
                heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))
                if heartbeat["pid"] == processes["worker"].pid and heartbeat["at"] >= started_at:
                    break
            time.sleep(0.5)
        run([sys.executable, "-m", "devflow.healthcheck", "worker"])
        stages.append({"pids": {n: p.pid for n, p in processes.items()}, "health": health})

    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database}"'))
        created = True
        run([sys.executable, "-m", "devflow.bootstrap", "--seed", "--knowledge"])
        start()
        common = [
            sys.executable,
            "scripts/release_smoke.py",
            "--api",
            environment["BACKEND_URL"],
            "--web",
            environment["WEB_ORIGIN"],
        ]
        run([*common, "--output", str(directory / "created.json")])
        stop(processes)
        start()
        run(
            [
                *common,
                "--baseline",
                str(directory / "created.json"),
                "--output",
                str(directory / "restarted.json"),
            ]
        )
        budget_after = get_budget_ledger().summary()
        isolated = create_database_engine(settings.model_copy(update={"postgres_db": database}))
        try:
            with isolated.connect() as connection:
                assert connection.scalar(select(func.count()).select_from(ModelCharge)) == 0
        finally:
            isolated.dispose()
        write_json(
            directory / "verification.json",
            {
                "status": "passed",
                "mode": "native source processes; fixture/fake; isolated database and artifacts",
                "database": database,
                "artifacts": environment["DEVFLOW_ARTIFACT_ROOT"],
                "stages": stages,
                "provenance": provenance(),
                "budget_before": budget_before,
                "budget_after": budget_after,
                "isolated_model_charge_count": 0,
                "budget_note": "主账本可能有同时运行的真实评测；本隔离演示为fake且无模型费用记录",
                "python": sys.version,
                "node": subprocess.check_output([node, "--version"], text=True).strip(),
            },
        )
        print(f"PASS: {directory / 'verification.json'}", flush=True)
    finally:
        stop(processes)
        for log in logs:
            log.close()
        if created:
            assert database.startswith("devflow_local_") and len(database) == 46
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{database}" WITH (FORCE)'))
        admin.dispose()


if __name__ == "__main__":
    main()
