# 文件用途：仅用fixture/fake验证完整部署、文档/报告/记忆及重启或备份后的持久性。
import argparse
import base64
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4


def request(base, path, body=None):
    raw = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if base.endswith("/api/backend"):
        path = path.removeprefix("/api/v1")
        origin = urlsplit(base)
        headers["Origin"] = f"{origin.scheme}://{origin.netloc}"
    req = Request(base + path, data=raw, headers=headers)
    with urlopen(req, timeout=180) as response:
        return json.load(response)


def sha(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def wait_run(api, run_id):
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        result = request(api, f"/api/v1/runs/{run_id}")
        if result["status"] not in {"queued", "running"}:
            if result["status"] != "succeeded":
                raise RuntimeError(f"Fixture run failed: {result.get('error_code')}")
            if result["result"]["provider"] != "fake":
                raise RuntimeError("Release smoke requires fake provider")
            return result
        time.sleep(1)
    raise TimeoutError("worker未在180秒内完成fixture任务")


def create(api):
    conversation = request(
        api,
        "/api/v1/conversations",
        {
            "repo_id": "repo-taskboard",
            "title": "本地运行持久性验收",
        },
    )
    common = {
        "repo_id": "repo-taskboard",
        "conversation_id": conversation["id"],
        "use_knowledge": True,
        "question": "核查所有者隔离与labels约束，引用固定证据。",
    }
    runs = []
    for task_type, target_id in [("pr_review", "102"), ("ci_debug", "202"), ("knowledge_qa", None)]:
        run = request(
            api, "/api/v1/runs", {**common, "task_type": task_type, "target_id": target_id}
        )
        completed = wait_run(api, run["id"])
        report = request(api, f"/api/v1/runs/{run['id']}/report")
        runs.append(
            {
                "id": run["id"],
                "task_type": task_type,
                "report_sha256": sha(report),
                "input_sha256": sha(completed["input_version"]),
            }
        )
    memory = request(api, f"/api/v1/runs/{runs[0]['id']}/memories", {"finding_index": 0})
    memory = request(api, f"/api/v1/memories/{memory['id']}/approve?repo_id=repo-taskboard", {})
    content = "# 发布验收文档\n发布验收标签 release-proof：文档、报告与记忆必须在恢复后保留。\n"
    document = request(
        api,
        "/api/v1/knowledge/upload",
        {
            "repo_id": "repo-taskboard",
            "filename": f"release-proof-{uuid4().hex}.md",
            "content_base64": base64.b64encode(content.encode()).decode(),
        },
    )
    if document["version"]["status"] != "ready":
        raise RuntimeError("真实本地向量索引未就绪")
    return {
        "runs": runs,
        "memory_id": memory["id"],
        "memory_summary": memory["summary"],
        "document_id": document["document_id"],
        "version_id": document["version"]["id"],
        "document_content_sha256": hashlib.sha256(content.encode()).hexdigest(),
    }


def verify(api, proof):
    for run in proof["runs"]:
        current = wait_run(api, run["id"])
        assert sha(current["input_version"]) == run["input_sha256"]
        assert sha(request(api, f"/api/v1/runs/{run['id']}/report")) == run["report_sha256"]
        evidence = request(api, f"/api/v1/runs/{run['id']}/evidence")
        assert evidence["items"], "固定证据必须保留"
        for item in evidence["items"]:
            artifact = request(
                api, f"/api/v1/artifacts/{item['artifact_id']}?repo_id=repo-taskboard"
            )
            assert artifact["content"] is not None
    memories = request(api, "/api/v1/memories?repo_id=repo-taskboard&limit=100")["items"]
    memory = next(m for m in memories if m["id"] == proof["memory_id"])
    assert memory["status"] == "approved" and memory["summary"] == proof["memory_summary"]
    doc = request(api, f"/api/v1/knowledge/{proof['document_id']}?repo_id=repo-taskboard")
    assert any(v["id"] == proof["version_id"] for v in doc["versions"])
    preview = request(
        api,
        f"/api/v1/knowledge/{proof['document_id']}/versions/{proof['version_id']}?repo_id=repo-taskboard",
    )
    normalized = preview["content"].replace("\r\n", "\n")
    assert hashlib.sha256(normalized.encode()).hexdigest() == proof["document_content_sha256"]
    found = request(
        api,
        "/api/v1/knowledge/search",
        {
            "repo_id": "repo-taskboard",
            "query": "发布验收标签 release-proof",
            "mode": "hybrid",
        },
    )
    assert any(h["document_id"] == proof["document_id"] for h in found["items"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--web", default="http://127.0.0.1:3000")
    parser.add_argument("--baseline", help="重启/恢复后核对既有proof，不创建新数据")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    proxy = args.web + "/api/backend"
    runtime = request(proxy, "/api/v1/runtime")
    if runtime["model"]["provider"] != "fake" or runtime["data_source"] != "fixture":
        raise SystemExit("Release smoke refuses non-fixture/non-fake deployment")
    assert request(args.api, "/api/v1/health")["status"] == "ok"
    assert request(args.web, "/api/health")["status"] == "ok"
    for path in ["/", "/repositories", "/runs", "/knowledge", "/memories"]:
        with urlopen(args.web + path, timeout=60) as response:
            assert response.status == 200
    proof = (
        json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        if args.baseline
        else create(proxy)
    )
    verify(proxy, proof)
    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError("输出已存在，避免覆盖验收证据")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\r\n"
    )
    print(f"Verified fixture PR/CI/QA, documents, memories and immutable evidence: {destination}")


if __name__ == "__main__":
    main()
