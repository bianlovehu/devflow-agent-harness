# 文件用途：独立数据库验证代码快照、搜索跳转和任务补查回放。
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from devflow.analysis.tool_gateway import ToolGateway
from devflow.code import service
from devflow.code.tasks import operation, prepare_run
from devflow.core.errors import DomainError
from devflow.storage.models import (
    CodeFile,
    CodeSnapshot,
    EvidenceRecord,
    RepositoryRecord,
    RunEvidenceRecord,
    RunRecord,
)
from devflow.workflows.worker import Worker
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_persistence_integration import context as database_context
from test_persistence_integration import create_target


@pytest.fixture
def context(tmp_path):
    for ctx in database_context.__wrapped__(tmp_path):
        ctx.code_clients = []
        try:
            yield ctx
        finally:
            for client in ctx.code_clients:
                client.close()


def code_client(context, worker, run_id, token):
    from devflow.code.mcp_client import CodeMCPClient

    client = CodeMCPClient(worker, run_id, token)
    context.code_clients.append(client)
    client.start()
    assert client.info["status"] == "connected", client.info
    return client


pytestmark = pytest.mark.skipif(
    os.getenv("DEVFLOW_TEST_DATABASE") != "1", reason="需要独立 PostgreSQL 测试库"
)
BASE = "/api/v1/repositories/repo-taskboard/code"


def prepared(context):
    response = context.client.post(BASE + "/snapshots", json={})
    assert response.status_code == 202, response.text
    sid = uuid.UUID(response.json()["snapshot_id"])
    assert service.prepare(context.engine, context.settings, context.store, sid)
    status = context.client.get(BASE + f"/snapshots/{sid}").json()
    assert status["status"] == "ready", status
    return sid, status


def active_task(context):
    body = create_target(context)
    response = context.client.post("/api/v1/runs", json=body)
    assert response.status_code == 201, response.text
    worker = Worker(context.engine, context.settings, store=context.store)
    run_id, token = worker.claim(uuid.UUID(response.json()["id"]))
    prepare_run(worker, run_id, token)
    with Session(context.engine) as session:
        version = session.get(RunRecord, run_id).input_version
    commit = next(
        item["head_sha"] for item in version["resources"] if item["kind"] == "pull_request"
    )
    client = code_client(context, worker, run_id, token)
    gateway = ToolGateway(
        "repo-taskboard",
        [],
        {"input_version": version},
        code_access=lambda name, args: operation(
            worker, run_id, token, name, args, mcp_client=client
        ),
    )
    return worker, run_id, token, version, commit, gateway


def test_api_search_lines_immutability_and_isolation(context):
    sid, status = prepared(context)
    tree = context.client.get(BASE + f"/tree?snapshot_id={sid}").json()
    assert any(item["path"] == "taskboard" for item in tree["items"])
    found = context.client.post(
        BASE + "/search", json={"snapshot_id": str(sid), "query": "def list_tasks"}
    )
    assert found.status_code == 200, found.text
    hit = found.json()["items"][0]
    assert hit["path"] == "taskboard/service.py"
    file = context.client.get(
        BASE + "/file",
        params={"snapshot_id": str(sid), "path": hit["path"], "start_line": hit["match_line"]},
    ).json()
    assert "def list_tasks" in file["lines"][0]["text"]
    before = file["content_sha256"]
    with Session(context.engine) as session, session.begin():
        session.get(RepositoryRecord, "repo-taskboard").default_commit = "f" * 40
    after = context.client.get(
        BASE + "/file", params={"snapshot_id": str(sid), "path": hit["path"]}
    ).json()
    assert after["commit"] == status["commit"] and after["content_sha256"] == before
    assert context.client.get(f"/api/v1/repositories/other/code/snapshots/{sid}").status_code == 404
    assert not service.prepare(context.engine, context.settings, context.store, sid)


def test_queued_partial_missing_and_rg_unavailable(context):
    response = context.client.post(BASE + "/snapshots", json={}).json()
    sid = uuid.UUID(response["snapshot_id"])
    assert context.client.get(BASE + f"/tree?snapshot_id={sid}").status_code == 409
    settings = context.settings.model_copy(update={"code_max_files": 1})
    service.prepare(context.engine, settings, context.store, sid)
    with Session(context.engine) as session:
        assert session.get(CodeSnapshot, sid).status == "partial"
        skipped = session.scalar(
            select(CodeFile).where(
                CodeFile.snapshot_id == sid, CodeFile.skip_reason == "snapshot_budget"
            )
        )
        with pytest.raises(DomainError, match="snapshot_budget"):
            service.read_file(session, "repo-taskboard", sid, skipped.path, 1, 60, context.store)
        with pytest.raises(DomainError) as error:
            service.search(
                session,
                "repo-taskboard",
                sid,
                "a",
                20,
                "snippets",
                context.store,
                settings.model_copy(update={"code_rg_path": "missing-devflow-rg"}),
            )
        assert error.value.code == "code_search_unavailable"


def test_concurrent_prepare_request_is_idempotent(context):
    def create():
        with Session(context.engine) as session, session.begin():
            return service.request_snapshot(session, "repo-taskboard").id

    with ThreadPoolExecutor(max_workers=3) as pool:
        ids = list(pool.map(lambda _: create(), range(3)))
    assert len(set(ids)) == 1


def test_model_search_read_and_replay_same_evidence(context):
    worker, run_id, token, version, commit, gateway = active_task(context)
    args = {"repo_id": "repo-taskboard", "commit": commit, "query": "list_tasks", "mode": "paths"}
    result = gateway.execute("search_code", json.dumps(args))
    assert result["ok"], result
    assert gateway.observed == {}
    assert not gateway.evidence
    args["mode"] = "snippets"
    result = gateway.execute("search_code", json.dumps(args))
    assert result["ok"], result
    assert gateway.observed
    hit = next(item for item in result["data"]["items"] if item["path"].startswith("tests/"))
    search_observed = {key: list(value) for key, value in gateway.observed.items()}
    read_args = {
        "repo_id": "repo-taskboard",
        "commit": commit,
        "path": hit["path"],
        "start_line": hit["match_line"],
        "limit": 5,
    }
    file = gateway.execute("read_file", json.dumps(read_args))
    assert file["ok"], file
    with Session(context.engine) as session:
        count = session.scalar(
            select(func.count())
            .select_from(RunEvidenceRecord)
            .where(RunEvidenceRecord.run_id == run_id)
        )
    resumed = ToolGateway(
        "repo-taskboard",
        [],
        {"input_version": version},
        code_access=lambda name, args: operation(worker, run_id, token, name, args),
    )
    with patch("devflow.code.service.search", side_effect=AssertionError("禁止恢复重新搜索")):
        replay = resumed.execute("search_code", json.dumps(args))
    assert replay == result
    assert resumed.observed == search_observed
    with Session(context.engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(RunEvidenceRecord)
                .where(RunEvidenceRecord.run_id == run_id)
            )
            == count
        )
    denied = resumed.execute("search_code", json.dumps({**args, "commit": "f" * 40}))
    assert denied["error"]["code"] == "code_commit_denied"
    denied = resumed.execute("search_code", json.dumps({**args, "repo_id": "another"}))
    assert denied["error"]["code"] == "tool_repository_denied"


def test_crash_before_commit_rolls_back_and_after_commit_replays(context):
    worker, run_id, token, version, commit, gateway = active_task(context)
    args = {
        "repo_id": "repo-taskboard",
        "commit": commit,
        "path": "taskboard/settings.py",
        "start_line": 1,
        "limit": 4,
    }
    with Session(context.engine) as session:
        initial = session.scalar(select(func.count()).select_from(EvidenceRecord))
    from devflow.code import tasks

    original = tasks.load_evidence
    with patch("devflow.code.tasks.load_evidence", side_effect=RuntimeError("crash before commit")):
        with pytest.raises(RuntimeError):
            gateway.execute("read_file", json.dumps(args))
    with Session(context.engine) as session:
        assert session.scalar(select(func.count()).select_from(EvidenceRecord)) == initial
    result = gateway.execute("read_file", json.dumps(args))
    assert result["ok"]
    with patch("devflow.code.service.read_file", side_effect=AssertionError("禁止重复读取")):
        resumed = ToolGateway(
            "repo-taskboard",
            [],
            {"input_version": version},
            code_access=lambda name, args: operation(worker, run_id, token, name, args),
        )
        assert resumed.execute("read_file", json.dumps(args)) == result
    assert original


@pytest.mark.parametrize("point", ["before_commit", "before_checkpoint"])
def test_real_subprocess_code_crash_and_new_worker_resume(context, point):
    import subprocess
    import sys
    from datetime import timedelta
    from pathlib import Path

    from devflow.analysis.tool_gateway import FileArgs
    from devflow.storage.models import RunJournal
    from devflow.workflows.worker import LeaseLost

    worker, run_id, token, version, commit, gateway = active_task(context)
    with Session(context.engine) as session, session.begin():
        run = session.get(RunRecord, run_id)
        run.configuration = {**run.configuration, "executor": "agent", "checkpoint_enabled": True}
        initial = session.scalar(
            select(func.count())
            .select_from(RunEvidenceRecord)
            .where(RunEvidenceRecord.run_id == run_id)
        )
    child = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("code_crash_worker.py")),
            context.database_name,
            str(context.store.root),
            str(run_id),
            str(token),
            commit,
            point,
        ],
        timeout=40,
        capture_output=True,
    )
    assert child.returncode == (73 if point == "before_commit" else 74), child.stderr.decode(
        errors="replace"
    )
    import time

    from test_code_mcp import process_alive

    server_pid = int(context.store.root.parent.joinpath("crash-mcp-pid.txt").read_text())
    until = time.monotonic() + 5
    while process_alive(server_pid) and time.monotonic() < until:
        time.sleep(0.05)
    assert not process_alive(server_pid), "崩溃的 Host 不能留下 MCP 服务"
    with Session(context.engine) as session, session.begin():
        count = session.scalar(
            select(func.count())
            .select_from(RunEvidenceRecord)
            .where(RunEvidenceRecord.run_id == run_id)
        )
        assert count == initial + (point != "before_commit")
        row = session.get(RunRecord, run_id)
        row.lease_expires_at = session.scalar(select(func.clock_timestamp())) - timedelta(seconds=1)
    resumed_worker = Worker(context.engine, context.settings, store=context.store)
    claimed = resumed_worker.claim(run_id)
    assert claimed and claimed[1] != token
    with pytest.raises(LeaseLost):
        operation(
            worker,
            run_id,
            token,
            "read_file",
            FileArgs(
                repo_id="repo-taskboard", commit=commit, path="taskboard/settings.py", limit=4
            ),
        )
    args = FileArgs(repo_id="repo-taskboard", commit=commit, path="taskboard/settings.py", limit=4)
    if point == "before_checkpoint":
        with patch(
            "devflow.code.service.read_file", side_effect=AssertionError("禁止回放重新读取")
        ):
            replay = operation(resumed_worker, run_id, claimed[1], "read_file", args)
    else:
        replay = operation(resumed_worker, run_id, claimed[1], "read_file", args)
    assert replay["version"] == commit and replay["lines"]
    with Session(context.engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(RunEvidenceRecord)
                .where(RunEvidenceRecord.run_id == run_id)
            )
            == initial + 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(RunJournal)
                .where(
                    RunJournal.run_id == run_id,
                    RunJournal.key.like("code-tool:%"),
                    ~RunJournal.key.like("%:mcp"),
                    ~RunJournal.key.like("%:error"),
                )
            )
            == 1
        )


def test_search_limit_literal_unicode_and_line_mapping(context):
    from devflow.code.capture import blob_hash

    raw = ("\ufeff中文 .* -x\r\n" + "needle\r\n" * 30).encode()
    rows = [
        {
            "path": "CON.py",
            "kind": "file",
            "blob_sha": blob_hash(raw),
            "size_bytes": len(raw),
            "skip_reason": None,
        }
    ]
    coverage = {
        "inventory_complete": True,
        "eligible_complete": True,
        "saved_files": 1,
        "saved_bytes": len(raw),
        "entries": 1,
        "excluded": {},
        "omitted_count": 0,
    }
    sid = uuid.UUID(context.client.post(BASE + "/snapshots", json={}).json()["snapshot_id"])
    with patch("devflow.code.service.collect", return_value=(rows, {"CON.py": raw}, coverage)):
        service.prepare(context.engine, context.settings, context.store, sid)
    with Session(context.engine) as session:
        found = service.search(
            session,
            "repo-taskboard",
            sid,
            "needle",
            20,
            "snippets",
            context.store,
            context.settings,
        )
        assert found["truncated"] and found["truncation_reason"] == "result_limit"
        assert 0 < len(found["items"]) <= 20
        for query in ["中文", ".*", "-x"]:
            found = service.search(
                session,
                "repo-taskboard",
                sid,
                query,
                20,
                "snippets",
                context.store,
                context.settings,
            )
            assert found["items"][0]["match_line"] == 1
            assert found["items"][0]["lines"][0] == {"line": 1, "text": "中文 .* -x"}
        found = service.search(
            session, "repo-taskboard", sid, ".*not", 20, "snippets", context.store, context.settings
        )
        assert found["items"] == [] and found["search_complete"]


def test_old_tasks_and_prepare_failure_do_not_gain_new_versions(context):
    worker, run_id, token, version, commit, gateway = active_task(context)
    with Session(context.engine) as session, session.begin():
        row = session.get(RunRecord, run_id)
        row.input_version = {
            **row.input_version,
            "code_access": {
                "allowed_commits": [commit],
                "snapshots": [{"commit": commit, "status": "failed"}],
            },
        }
    denied = gateway.execute(
        "list_code_tree", json.dumps({"repo_id": "repo-taskboard", "commit": commit})
    )
    assert denied["error"]["code"] == "code_snapshot_not_ready"
    with Session(context.engine) as session, session.begin():
        row = session.get(RunRecord, run_id)
        version = dict(row.input_version)
        version.pop("code_access")
        row.input_version = version
    prepare_run(worker, run_id, token)
    denied = gateway.execute(
        "list_code_tree", json.dumps({"repo_id": "repo-taskboard", "commit": commit})
    )
    assert denied["error"]["code"] == "code_commit_denied"


@pytest.mark.parametrize("task_type,target", [("pr_review", "102"), ("ci_debug", "201")])
def test_controlled_model_follows_search_read_cite_chain(context, task_type, target):
    from devflow.analysis.agent import AnalysisRunner
    from devflow.analysis.model_gateway import ModelReply, tool_call

    body = create_target(context, task_type, target)
    created = context.client.post("/api/v1/runs", json=body).json()
    worker = Worker(context.engine, context.settings, store=context.store)
    run_id, token = worker.claim(uuid.UUID(created["id"]))
    prepare_run(worker, run_id, token)
    with Session(context.engine) as session:
        run = session.get(RunRecord, run_id)
        version, config = run.input_version, run.configuration
        original_resources = list(version["resources"])
    head = next(resource["head_sha"] for resource in version["resources"])
    query = "list_tasks" if task_type == "pr_review" else "DATABASE_URL"

    class CrossFileModel:
        provider = "fake"
        name = "controlled-cross-file"

        def complete(self, messages, tools, **kwargs):
            results = [
                json.loads(item["content"])["data"] for item in messages if item["role"] == "tool"
            ]
            if not results:
                return tool_call(
                    "search_code",
                    {"repo_id": "repo-taskboard", "commit": head, "query": query},
                    "search",
                )
            if len(results) == 1:
                hit = (
                    next(
                        item
                        for item in results[0]["items"]
                        if item["path"].startswith("tests/")
                        if task_type == "pr_review"
                    )
                    if task_type == "pr_review"
                    else results[0]["items"][0]
                )
                return tool_call(
                    "read_file",
                    {
                        "repo_id": "repo-taskboard",
                        "commit": head,
                        "path": hit["path"],
                        "start_line": hit["match_line"],
                        "limit": 4,
                    },
                    "read",
                )
            fragment = results[-1]
            citation = {
                "evidence_id": fragment["id"],
                "start_line": fragment["start_line"],
                "end_line": fragment["end_line"],
            }
            report = {
                "report_version": "2",
                "task_type": task_type,
                "summary": "已补查固定提交中的相关测试或配置，未推断未确认的调用关系。",
                "findings": [],
                "answer_evidence": [citation],
                "failure_stage": "未知" if task_type == "ci_debug" else None,
                "verification_steps": ["按引用核对当前配置与测试。"],
                "suggestions": [],
                "unconfirmed": [],
                "scope": ["仅覆盖实际读取的固定材料。"],
                "boundary_claims": [],
            }
            return ModelReply(
                {"role": "assistant", "content": json.dumps(report, ensure_ascii=False)}
            )

    client = code_client(context, worker, run_id, token)
    gateway = ToolGateway(
        "repo-taskboard",
        [],
        {"input_version": version},
        code_access=lambda name, args: operation(
            worker, run_id, token, name, args, mcp_client=client
        ),
    )
    config = {**config, "report_review": {"enabled": False}}
    result = AnalysisRunner(
        CrossFileModel(), gateway, task_type, "核对未修改调用方或测试", config
    ).run()
    assert result["model_calls"] == 3 and result["tool_calls"] == 2
    assert result["report"]["answer_evidence"]
    assert result["report"]["evidence_facts"]["reads"]
    with Session(context.engine) as session:
        assert session.get(RunRecord, run_id).input_version["resources"] == original_resources


def test_search_timeout_is_not_empty_success(context):
    import subprocess
    import sys

    sid, _ = prepared(context)
    original = subprocess.Popen
    children = []

    def slow_search(args, **kwargs):
        assert kwargs["shell"] is False and "--fixed-strings" in args
        child = original([sys.executable, "-c", "import time; time.sleep(10)"], **kwargs)
        children.append(child)
        return child

    with Session(context.engine) as session:
        with (
            patch("devflow.code.service.subprocess.Popen", side_effect=slow_search),
            patch("devflow.code.service.SEARCH_SECONDS", 0.5),
        ):
            result = service.search(
                session, "repo-taskboard", sid, "a", 20, "snippets", context.store, context.settings
            )
    assert result["truncated"] and not result["search_complete"]
    assert result["truncation_reason"] == "timeout"
    assert children and all(child.poll() is not None for child in children)


# 默认代码浏览只读数据库；任何远端连接都必须由显式拉取触发。
def test_cached_browse_without_snapshots_does_not_create_or_download(context):
    with patch(
        "devflow.repositories.github_client.GitHubClient.get",
        side_effect=AssertionError("浏览不能联网"),
    ):
        for _ in range(2):
            reply = context.client.get(BASE + "/snapshots")
            assert reply.status_code == 200 and reply.json()["snapshot"] is None
    with Session(context.engine) as session:
        assert session.scalar(select(func.count()).select_from(CodeSnapshot)) == 0


def test_manual_pull_pins_cached_version_and_same_commit_never_downloads_again(context):
    pulled = context.client.post(BASE + "/pull", json={})
    assert pulled.status_code == 202, pulled.text
    first = pulled.json()
    sid = uuid.UUID(first["snapshot_id"])
    assert service.prepare(context.engine, context.settings, context.store, sid)
    original = context.client.get(
        BASE + "/file", params={"snapshot_id": str(sid), "path": "taskboard/service.py"}
    ).json()
    with patch("devflow.code.service.collect", side_effect=AssertionError("同一提交不能重新下载")):
        for _ in range(2):
            assert context.client.get(BASE + "/snapshots").json()["snapshot"]["snapshot_id"] == str(
                sid
            )
        assert context.client.post(BASE + "/pull", json={}).status_code == 200
        assert not service.prepare(context.engine, context.settings, context.store, sid)
    next_commit = "08e1a7f77ab3481e02b7b1b365a6db52746ccdb0"
    assert next_commit != first["commit"]
    with Session(context.engine) as session, session.begin():
        session.get(RepositoryRecord, "repo-taskboard").default_commit = next_commit
    # 仓库摘要更新，不改变上次手动拉取并发布的浏览版本。
    assert context.client.get(BASE + "/snapshots").json()["snapshot"]["snapshot_id"] == str(sid)
    next_row = context.client.post(BASE + "/pull", json={}).json()
    assert next_row["commit"] == next_commit
    assert service.prepare(
        context.engine, context.settings, context.store, uuid.UUID(next_row["snapshot_id"])
    )
    assert (
        context.client.get(BASE + "/snapshots").json()["snapshot"]["snapshot_id"]
        == next_row["snapshot_id"]
    )
    assert (
        context.client.get(
            BASE + "/file", params={"snapshot_id": str(sid), "path": "taskboard/service.py"}
        ).json()
        == original
    )


def test_failed_manual_update_keeps_last_published_version(context):
    row = context.client.post(BASE + "/pull", json={}).json()
    sid = uuid.UUID(row["snapshot_id"])
    service.prepare(context.engine, context.settings, context.store, sid)
    with Session(context.engine) as session, session.begin():
        session.get(RepositoryRecord, "repo-taskboard").default_commit = "f" * 40
    failed = context.client.post(BASE + "/pull", json={}).json()
    service.prepare(
        context.engine, context.settings, context.store, uuid.UUID(failed["snapshot_id"])
    )
    assert (
        context.client.get(BASE + "/snapshots", params={"commit": "f" * 40}).json()["snapshot"][
            "status"
        ]
        == "failed"
    )
    assert context.client.get(BASE + "/snapshots").json()["snapshot"]["snapshot_id"] == str(sid)


def test_repository_summary_refresh_preserves_code_workspace_pointer(context):
    from devflow.repositories.github_source import GitHubRepositorySource
    from github_samples import FakeGitHub

    fake = FakeGitHub()
    with Session(context.engine) as session:
        source = GitHubRepositorySource(session, context.settings, client=fake)
        repo = source.add_repository("owner/project")
        row = service.request_snapshot(session, repo.id, repo.default_commit)
        row.status = "ready"
        row.manifest_sha256 = "c" * 64
        service.select_for_browsing(session, row, requested=True)
        session.commit()
        saved_id = row.id
        source.refresh(repo.id)
        assert service.cached_snapshot(session, repo.id).id == saved_id
        assert session.get(RepositoryRecord, repo.id).sync_state["code_workspace"][
            "snapshot_id"
        ] == str(saved_id)


def test_github_pull_resolves_current_default_branch_only_on_manual_request(context):
    from devflow.repositories.github_source import GitHubRepositorySource
    from github_samples import FakeGitHub

    fake = FakeGitHub()
    with Session(context.engine) as session:
        repo = GitHubRepositorySource(session, context.settings, client=fake).add_repository(
            "owner/project"
        )
        fake.calls.clear()
        assert service.cached_snapshot(session, repo.id) is None
        assert fake.calls == []
        row = service.pull_latest(session, repo.id, context.settings, client_factory=lambda _: fake)
        assert row.commit_sha == "a" * 40
        assert fake.calls == ["/repos/owner/project", "/repos/owner/project/commits/main"]
        session.commit()
