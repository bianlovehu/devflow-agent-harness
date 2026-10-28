# 文件用途：记录并核对真实 API 重启前后的会话、任务和证据。
"""Create/read a persistent demo record without running a model or worker."""

import argparse
import json
import uuid
from urllib.request import Request, urlopen

from devflow.config import PROJECT_ROOT

PROOF = PROJECT_ROOT / "data" / "step-03-proof.json"
BASE_URL = "http://127.0.0.1:8000/api/v1"


def request(path: str, body=None, key=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Idempotency-Key"] = key
    payload = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    with urlopen(Request(BASE_URL + path, data=payload, headers=headers), timeout=15) as response:
        return json.load(response)


def create() -> None:
    # 保存真实 HTTP 写入结果，供服务重启后的独立核验使用。
    if PROOF.exists():
        verify()
        return
    conversation = request(
        "/conversations", {"repo_id": "repo-taskboard", "title": "第 3 步持久化验收"}
    )
    run = request(
        "/runs",
        {
            "repo_id": "repo-taskboard",
            "conversation_id": conversation["id"],
            "task_type": "pr_review",
            "target_id": "102",
            "question": "这是持久化验收记录，等待后续 worker 接入，不调用模型。",
        },
        key="step-03-proof-" + uuid.uuid4().hex,
    )
    record = {
        "conversation": conversation,
        "run": run,
        "evidence": request(f"/runs/{run['id']}/evidence"),
        "artifacts": request(f"/runs/{run['id']}/artifacts"),
    }
    PROOF.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    PROOF.write_bytes(text.replace("\n", "\r\n").encode())
    print(
        json.dumps(
            {"status": "created", "conversation_id": conversation["id"], "run_id": run["id"]}
        )
    )


def verify() -> None:
    # 重新读取数据库中的任务及制品，与重启前保存的版本逐项比较。
    record = json.loads(PROOF.read_text(encoding="utf-8"))
    run_id = record["run"]["id"]
    assert request("/conversations/" + record["conversation"]["id"]) == record["conversation"]
    assert request("/runs/" + run_id) == record["run"]
    assert request(f"/runs/{run_id}/evidence") == record["evidence"]
    assert request(f"/runs/{run_id}/artifacts") == record["artifacts"]
    events = request(f"/runs/{run_id}/events")["items"]
    assert events[0]["event_type"] == "run.queued" and events[0]["sequence"] == 1
    messages = request(f"/conversations/{record['conversation']['id']}/messages")["items"]
    assert any(message["id"] == record["run"]["message_id"] for message in messages)
    for artifact in record["artifacts"]["items"]:
        result = request(f"/artifacts/{artifact['id']}?repo_id=repo-taskboard")
        assert result["artifact"] == artifact and result["content"]
    print(
        json.dumps(
            {
                "status": "verified",
                "conversation_id": record["conversation"]["id"],
                "run_id": run_id,
                "pinned_version_unchanged": True,
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "verify"])
    args = parser.parse_args()
    if args.action == "create":
        create()
    else:
        verify()


if __name__ == "__main__":
    main()
