# 文件用途：只读代码证据 MCP stdio 服务；任务和租约由 Host 注入，所有调用再次授权。
import json
import os
import signal
import sys
import threading
import time
from uuid import UUID

import anyio
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from devflow.code import service
from devflow.code.mcp_contract import INPUTS, OUTPUTS, SERVER_NAME, SERVER_VERSION, tools
from devflow.code.tasks import bound_snapshot
from devflow.core.config import Settings
from devflow.core.errors import DomainError
from devflow.core.security import redact
from devflow.storage.artifact_store import ArtifactStore
from devflow.storage.database import create_database_engine
from devflow.storage.models import RunRecord


def authorize(session, run_id, token, repo_id, commit):
    run = session.get(RunRecord, run_id)
    now = session.scalar(select(func.clock_timestamp()))
    if (
        run is None
        or run.status != "running"
        or run.lease_token != token
        or run.lease_expires_at is None
        or run.lease_expires_at <= now
        or run.cancel_requested_at is not None
    ):
        raise DomainError(403, "mcp_task_denied", "代码服务的任务或租约已失效")
    if run.repo_id != repo_id:
        raise DomainError(403, "tool_repository_denied", "代码服务只能访问当前任务的仓库")
    return bound_snapshot(session, run, commit)


def build_server(engine, settings, store, run_id, token):
    async def list_tools(context, params):
        return ListToolsResult(tools=tools(os.getpid()))

    def execute(name, arguments, cancelled):
        if name not in INPUTS:
            raise DomainError(422, "unknown_tool", "MCP 工具不在只读白名单中")
        args = INPUTS[name].model_validate(arguments)
        with Session(engine) as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            sid = authorize(session, run_id, token, args.repo_id, args.commit)

            def guard():
                if cancelled.is_set():
                    raise DomainError(499, "mcp_cancelled", "代码证据调用已取消")
                with Session(engine) as check:
                    check.execute(text("SET TRANSACTION READ ONLY"))
                    authorize(check, run_id, token, args.repo_id, args.commit)

            if name == "repo_tree":
                result = service.tree(
                    session, args.repo_id, sid, args.path, args.offset, args.limit
                )
            elif name == "repo_search":
                result = service.search(
                    session,
                    args.repo_id,
                    sid,
                    args.query,
                    args.limit,
                    args.mode,
                    store,
                    settings,
                    guard,
                    timeout_seconds=max(0.05, settings.mcp_tool_timeout_seconds - 0.25),
                )
            else:
                result = service.read_file(
                    session, args.repo_id, sid, args.path, args.start_line, args.limit, store
                )
            guard()
            return OUTPUTS[name].model_validate(result).model_dump(mode="json")

    async def call_tool(context, params):
        cancelled = threading.Event()
        try:
            data = await anyio.to_thread.run_sync(
                execute, params.name, params.arguments or {}, cancelled, abandon_on_cancel=True
            )
            value, failed = {"ok": True, "data": data, "error": None}, False
        except (DomainError, ValidationError, SQLAlchemyError) as error:
            if isinstance(error, DomainError):
                status, code, message = error.status, error.code, error.message
            elif isinstance(error, ValidationError):
                status, code, message = 422, "invalid_tool_arguments", "MCP 工具参数不符合 schema"
            else:
                status, code, message = 503, "database_unavailable", "代码证据服务无法读取数据库"
            value, failed = (
                {
                    "ok": False,
                    "data": None,
                    "error": {"status": status, "code": code, "message": message},
                },
                True,
            )
        except BaseException:
            cancelled.set()
            raise
        value = redact(value)
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(value, ensure_ascii=False))],
            structured_content=value,
            is_error=failed,
        )

    return Server(
        SERVER_NAME,
        version=SERVER_VERSION,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
        get_tool_input_schema=lambda name: (
            INPUTS[name].model_json_schema() if name in INPUTS else None
        ),
    )


def main():
    # 不读取项目 .env，也不接受网络地址/任意路径作为工具参数。
    config = json.loads(os.environ["DEVFLOW_CODE_MCP_CONFIG"])
    run_id, token = UUID(config.pop("run_id")), UUID(config.pop("lease_token"))
    parent = config.pop("parent_pid")
    artifact_root = config.pop("artifact_root")
    settings = Settings(_env_file=None, **config)
    engine = create_database_engine(settings)
    store = ArtifactStore(__import__("pathlib").Path(artifact_root))
    server = build_server(engine, settings, store, run_id, token)

    def parent_watch():
        while True:
            time.sleep(1)
            if os.getppid() != parent:
                if sys.platform != "win32":
                    os.killpg(os.getpgrp(), signal.SIGTERM)
                os._exit(0)

    # Windows 虚拟环境可能经过 Python 重定向启动器，ppid 并非 Host；由 SDK Job Object 回收。
    if sys.platform != "win32":
        threading.Thread(target=parent_watch, daemon=True).start()

    async def run():
        async with stdio_server() as (reader, writer):
            await server.run(reader, writer, server.create_initialization_options())

    try:
        anyio.run(run)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
