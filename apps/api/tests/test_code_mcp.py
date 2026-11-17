# 文件用途：真实 stdio MCP 协议、双重授权、契约及原子证据回放验收。
import json
import os
import time
import uuid
from unittest.mock import patch

import pytest
import test_persistence_integration as persistence
from devflow.analysis.tool_gateway import CodeTreeArgs, FileArgs, ToolGateway
from devflow.code.mcp_client import CodeMCPClient, launch_parameters
from devflow.code.mcp_contract import BACKEND, fingerprint, tools
from devflow.code.tasks import analysis_version, operation, prepare_run
from devflow.core.errors import DomainError
from devflow.storage.models import EvidenceRecord, RunEvidenceRecord, RunJournal, RunRecord
from devflow.workflows.worker import Worker
from sqlalchemy import func, select
from sqlalchemy.orm import Session

pytestmark = persistence.pytestmark


@pytest.fixture
def context(tmp_path):
    for ctx in persistence.context.__wrapped__(tmp_path):
        ctx.clients = []
        try:
            yield ctx
        finally:
            for client in ctx.clients:
                client.close()


def task(context):
    body = persistence.create_target(context)
    created = context.client.post("/api/v1/runs", json=body).json()
    worker = Worker(context.engine, context.settings, store=context.store)
    run_id, token = worker.claim(uuid.UUID(created["id"]))
    prepare_run(worker, run_id, token)
    with Session(context.engine) as session:
        run = session.get(RunRecord, run_id)
        version = analysis_version(session, run)
        assert run.configuration["code_backend"] == BACKEND
    head = version["resources"][0]["head_sha"]
    client = CodeMCPClient(worker, run_id, token)
    context.clients.append(client)
    before = time.monotonic()
    client.start()
    assert client.info["status"] == "connected", client.info
    print("MCP startup", round(time.monotonic() - before, 2))
    return worker, run_id, token, version, head, client


def test_real_stdio_three_tools_and_http_parity(context):
    worker, run_id, token, version, head, client = task(context)
    assert client.info["server_name"] == "devflow-code-evidence"
    assert client.info["schema_sha256"] == fingerprint(tools())
    assert client.info["protocol_version"] and client.info["pid"] != os.getpid()
    args = {"repo_id": "repo-taskboard", "commit": head}
    tree = client.call("list_code_tree", args)
    sid = tree["snapshot_id"]
    http = context.client.get(
        "/api/v1/repositories/repo-taskboard/code/tree", params={"snapshot_id": sid, "limit": 20}
    ).json()
    assert tree == http
    found = client.call("search_code", {**args, "query": "list_tasks"})
    hit = next(row for row in found["items"] if row["path"].startswith("tests/"))
    file = client.call(
        "read_file", {**args, "path": hit["path"], "start_line": hit["match_line"], "limit": 4}
    )
    http = context.client.get(
        "/api/v1/repositories/repo-taskboard/code/file",
        params={
            "snapshot_id": sid,
            "path": hit["path"],
            "start_line": hit["match_line"],
            "limit": 4,
        },
    ).json()
    assert file == http
    with Session(context.engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(EvidenceRecord)
                .join(RunEvidenceRecord, RunEvidenceRecord.evidence_id == EvidenceRecord.id)
                .where(RunEvidenceRecord.run_id == run_id, EvidenceRecord.path == hit["path"])
            )
            == 0
        )
    before = time.monotonic()
    client.close()
    print("MCP close", round(time.monotonic() - before, 2))


def test_server_checks_scope_and_lease(context):
    worker, run_id, token, version, head, client = task(context)
    for arguments, code in [
        ({"repo_id": "another", "commit": head}, "tool_repository_denied"),
        ({"repo_id": "repo-taskboard", "commit": "f" * 40}, "code_commit_denied"),
    ]:
        with pytest.raises(DomainError) as error:
            client.call("list_code_tree", arguments)
        assert error.value.code == code
    with pytest.raises(DomainError):
        client.call(
            "read_file", {"repo_id": "repo-taskboard", "commit": head, "path": "../../.env"}
        )
    with Session(context.engine) as session, session.begin():
        session.get(RunRecord, run_id).cancel_requested_at = session.scalar(
            select(func.clock_timestamp())
        )
    from devflow.code.mcp_server import authorize

    with Session(context.engine) as session:
        with pytest.raises(DomainError) as error:
            authorize(session, run_id, token, "repo-taskboard", head)
        assert error.value.code == "mcp_task_denied"


def test_host_persists_evidence_and_offline_replay(context):
    worker, run_id, token, version, head, client = task(context)
    gateway = ToolGateway(
        "repo-taskboard",
        [],
        {"input_version": version},
        code_access=lambda name, args: operation(
            worker, run_id, token, name, args, mcp_client=client
        ),
    )
    args = {"repo_id": "repo-taskboard", "commit": head, "query": "list_tasks", "mode": "paths"}
    assert gateway.execute("search_code", json.dumps(args))["ok"]
    assert not gateway.observed and not gateway.evidence
    args["mode"] = "snippets"
    reply = gateway.execute("search_code", json.dumps(args))
    assert reply["ok"] and gateway.observed, reply
    expected_reads = dict(gateway.observed)
    client.close()
    from devflow.code.mcp_contract import SERVER_VERSION

    with patch(
        "devflow.code.mcp_client.CodeMCPClient.call",
        side_effect=AssertionError("离线回放不能调用服务"),
    ):
        replay = ToolGateway(
            "repo-taskboard",
            [],
            {"input_version": version},
            code_access=lambda name, params: operation(
                worker, run_id, token, name, params, mcp_client=client
            ),
        ).execute("search_code", json.dumps(args))
    assert replay == reply
    assert expected_reads
    assert client.records[-1]["source"] == "journal"
    assert client.records[-1]["server_version"] == SERVER_VERSION


@pytest.mark.parametrize(
    "mode,code",
    [
        ("schema", "mcp_contract_mismatch"),
        ("missing", "mcp_contract_mismatch"),
        ("start_exit", "mcp_start_failed"),
        ("start_timeout", "mcp_start_timeout"),
    ],
)
def test_real_startup_faults_have_explicit_status(context, mode, code):
    import sys
    from pathlib import Path

    worker, run_id, token, version, head, baseline = task(context)
    baseline.close()
    if mode == "start_timeout":
        worker.settings = worker.settings.model_copy(update={"mcp_startup_timeout_seconds": 0.3})
    parameters = launch_parameters(worker, run_id, token).model_copy(
        update={
            "command": sys.executable,
            "args": [str(Path(__file__).with_name("mcp_fault_server.py")), mode],
        }
    )
    client = CodeMCPClient(worker, run_id, token, parameters=parameters)
    context.clients.append(client)
    client.start()
    assert client.info["status"] == "unavailable"
    assert client.info["error_code"] == code, client.info
    with pytest.raises(DomainError) as error:
        client.call("list_code_tree", {"repo_id": "repo-taskboard", "commit": head})
    assert error.value.code == code


@pytest.mark.parametrize(
    "mode,code",
    [
        ("exit", "mcp_disconnected"),
        ("timeout", "mcp_timeout"),
        ("malformed", "mcp_result_invalid"),
        ("wire", "mcp_protocol_error"),
        ("changed", "mcp_contract_mismatch"),
    ],
)
def test_real_protocol_faults_stop_further_calls(context, mode, code):
    from pathlib import Path

    worker, run_id, token, version, head, baseline = task(context)
    baseline.close()
    worker.settings = worker.settings.model_copy(
        update={"mcp_tool_timeout_seconds": 0.3 if mode == "timeout" else 2}
    )
    parameters = launch_parameters(worker, run_id, token).model_copy(
        update={"args": [str(Path(__file__).with_name("mcp_fault_server.py")), mode]}
    )
    client = CodeMCPClient(worker, run_id, token, parameters=parameters)
    context.clients.append(client)
    client.start()
    assert client.info["status"] == "connected", client.info
    args = CodeTreeArgs(repo_id="repo-taskboard", commit=head)
    for _ in range(2):
        with pytest.raises(DomainError) as error:
            operation(worker, run_id, token, "list_code_tree", args, mcp_client=client)
        assert error.value.code == code, error.value
    assert client.records[-1]["source"] == "journal"
    assert client.info["status"] == "unavailable"


def test_contract_mismatch_recovery_allows_only_old_results(context):
    worker, run_id, token, version, head, client = task(context)
    args = FileArgs(
        repo_id="repo-taskboard", commit=head, path="tests/test_service.py", start_line=1, limit=3
    )
    original = operation(worker, run_id, token, "read_file", args, mcp_client=client)
    client.close()
    with Session(context.engine) as session, session.begin():
        row = session.get(RunJournal, (run_id, "mcp:contract"))
        row.payload = {**row.payload, "schema_sha256": "incompatible"}
    restored = CodeMCPClient(worker, run_id, token)
    context.clients.append(restored)
    restored.start()
    assert restored.info["error_code"] == "mcp_contract_mismatch"
    assert operation(worker, run_id, token, "read_file", args, mcp_client=restored) == original
    with pytest.raises(DomainError) as error:
        operation(
            worker,
            run_id,
            token,
            "read_file",
            args.model_copy(update={"start_line": 5}),
            mcp_client=restored,
        )
    assert error.value.code == "mcp_contract_mismatch"


def test_launch_does_not_inherit_model_credentials(context):
    worker, run_id, token, version, head, client = task(context)
    config = launch_parameters(worker, run_id, token)
    content = json.dumps(config.env)
    assert (
        "DASHSCOPE" not in content and "DEEPSEEK" not in content and "GITHUB_TOKEN" not in content
    )
    assert config.args == ["-m", "devflow.code.mcp_server"]
    assert "run_id" not in config.args and "lease_token" not in config.args


def process_alive(pid):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def test_close_reaps_real_server_process(context):
    worker, run_id, token, version, head, client = task(context)
    pid = client.info["pid"]
    assert process_alive(pid)
    client.close()
    assert not process_alive(pid)


def test_server_rejects_extra_arguments_via_real_protocol(context):
    # 原始 SDK Client 绕过 Host 参数校验，证明 Server 独立拒绝。
    import anyio
    from mcp import Client

    worker, run_id, token, version, head, client = task(context)
    client.close()
    parameters = launch_parameters(worker, run_id, token)

    async def check():
        async with Client(parameters) as raw:
            try:
                result = await raw.call_tool(
                    "repo_tree",
                    {"repo_id": "repo-taskboard", "commit": head, "host_path": "C:/Windows"},
                )
            except Exception as error:
                assert "invalid" in str(error).lower() or "additional" in str(error).lower()
            else:
                assert result.is_error

    anyio.run(check)


def test_raw_server_rechecks_expired_lease_and_bound_snapshot(context):
    from datetime import timedelta

    import anyio
    from devflow.code.mcp_contract import validate_result
    from mcp import Client

    worker, run_id, token, version, head, client = task(context)
    client.close()

    async def check():
        async with Client(launch_parameters(worker, run_id, token)) as raw:
            args = {"repo_id": "repo-taskboard", "commit": head}
            with Session(context.engine) as session, session.begin():
                row = session.get(RunJournal, (run_id, "code-prepared"))
                row.payload = {"snapshots": []}
            reply = await raw.call_tool("repo_tree", args)
            with pytest.raises(DomainError) as error:
                validate_result("repo_tree", reply.structured_content, reply.is_error)
            assert error.value.code == "code_snapshot_not_ready"
            with Session(context.engine) as session, session.begin():
                row = session.get(RunRecord, run_id)
                row.lease_expires_at = session.scalar(select(func.clock_timestamp())) - timedelta(
                    seconds=1
                )
            reply = await raw.call_tool("repo_tree", args)
            with pytest.raises(DomainError) as error:
                validate_result("repo_tree", reply.structured_content, reply.is_error)
            assert error.value.code == "mcp_task_denied"

    anyio.run(check)


def test_legacy_task_keeps_internal_backend(context):
    worker, run_id, token, version, head, client = task(context)
    client.close()
    with Session(context.engine) as session, session.begin():
        row = session.get(RunRecord, run_id)
        row.configuration = {
            k: v
            for k, v in row.configuration.items()
            if k not in {"code_backend", "mcp_contract_version"}
        }
    with patch(
        "devflow.code.mcp_client.CodeMCPClient.call",
        side_effect=AssertionError("旧任务不能切换MCP"),
    ):
        result = operation(
            worker,
            run_id,
            token,
            "list_code_tree",
            CodeTreeArgs(repo_id="repo-taskboard", commit=head),
        )
    assert result["items"] and result["commit"] == head


def test_host_rejects_forged_code_hash_and_body(context):
    worker, run_id, token, version, head, client = task(context)
    args = FileArgs(repo_id="repo-taskboard", commit=head, path="tests/test_service.py", limit=3)
    valid = client.call("read_file", args.model_dump())
    valid["lines"][0]["text"] = "forged"
    with patch.object(client, "call", return_value=valid):
        with pytest.raises(DomainError) as error:
            operation(worker, run_id, token, "read_file", args, mcp_client=client)
    assert error.value.code == "mcp_result_invalid"
    assert client.info["status"] == "unavailable"


def test_cancelled_host_closes_child(context):
    from devflow.workflows.worker import RunCancelled

    worker, run_id, token, version, head, client = task(context)
    pid = client.info["pid"]
    with Session(context.engine) as session, session.begin():
        session.get(RunRecord, run_id).cancel_requested_at = session.scalar(
            select(func.clock_timestamp())
        )
    with pytest.raises(RunCancelled):
        try:
            client.call("list_code_tree", {"repo_id": "repo-taskboard", "commit": head})
        finally:
            client.close()
    assert not process_alive(pid)


@pytest.mark.parametrize("interrupt", ["timeout", "cancel"])
def test_active_call_reaps_server_and_real_ripgrep(context, tmp_path, interrupt):
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path

    from devflow.workflows.worker import RunCancelled

    worker, run_id, token, version, head, baseline = task(context)
    baseline.close()
    worker.settings = worker.settings.model_copy(update={"mcp_tool_timeout_seconds": 2})
    marker = tmp_path / "children.json"
    params = launch_parameters(worker, run_id, token).model_copy(
        update={
            "args": [str(Path(__file__).with_name("mcp_fault_server.py")), "orphan", str(marker)]
        }
    )
    client = CodeMCPClient(worker, run_id, token, parameters=params)
    context.clients.append(client)
    client.start()
    assert client.info["status"] == "connected", client.info

    def invoke():
        try:
            client.call("list_code_tree", {"repo_id": "repo-taskboard", "commit": head})
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(invoke)
        deadline = time.monotonic() + 2
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists()
        children = json.loads(marker.read_text())
        assert all(process_alive(pid) for pid in children.values())
        if interrupt == "cancel":
            with Session(context.engine) as session, session.begin():
                session.get(RunRecord, run_id).cancel_requested_at = session.scalar(
                    select(func.clock_timestamp())
                )
        with pytest.raises(RunCancelled if interrupt == "cancel" else DomainError) as error:
            future.result(timeout=10)
        if interrupt == "timeout":
            assert error.value.code == "mcp_timeout"
    assert all(not process_alive(pid) for pid in children.values())
