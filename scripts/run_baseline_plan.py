# 文件用途：以独立、限额小批次推进固定真实基线，观察到费用/供应商失败便停止，不重置账本。
import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=["analysis", "context", "stability"], required=True)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--dataset", default="evals/devflow-v1")
    parser.add_argument("--split", choices=["dev", "holdout"], default="dev")
    parser.add_argument("--freeze")
    parser.add_argument(
        "--resume-after-stop", help="显式确认已排查的停止原因，仅继续未执行题，不重跑失败题"
    )
    args = parser.parse_args()
    directory = Path(args.directory)
    directory.mkdir(parents=True, exist_ok=True)
    state_path = directory / "state.json"
    if args.resume_after_stop:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("stop_reason") != args.resume_after_stop:
            parser.error("确认原因与当前停止原因不一致")
        state.setdefault("stop_history", []).append(
            {
                "reason": state.pop("stop_reason"),
                "acknowledged_at": datetime.now(UTC).isoformat(),
                "action": "continue pending jobs; retain failed outputs and unknown reservations",
            }
        )
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\r\n",
        )
    while True:
        command = [
            sys.executable,
            "-m",
            "devflow.baseline_cli",
            "--real",
            "--suite",
            args.suite,
            "--directory",
            str(directory),
            "--dataset",
            args.dataset,
            "--split",
            args.split,
            "--limit",
            "6",
            "--batch-cap-cny",
            "5",
        ]
        if args.freeze:
            command += ["--freeze", args.freeze]
        with (directory / "execution.log").open("a", encoding="utf-8", newline="\r\n") as log:
            completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        state_path = directory / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        count, total = len(state.get("completed", [])), len(state.get("jobs", []))
        print(
            json.dumps(
                {
                    "suite": args.suite,
                    "completed": count,
                    "planned": total,
                    "budget": state.get("budget_latest"),
                    "stop_reason": state.get("stop_reason"),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        if completed.returncode != 0:
            raise SystemExit(completed.returncode)
        if count == total and total:
            break


if __name__ == "__main__":
    main()
