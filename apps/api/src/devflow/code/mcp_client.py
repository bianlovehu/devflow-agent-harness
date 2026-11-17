# 文件用途：任务级 stdio MCP 客户端，独立异步生命周期、契约校验、有限等待与进程树清理。
import concurrent.futures
import json
import os
import sys
import threading
import time

import anyio
from anyio.from_thread import start_blocking_portal
from mcp import Client, MCPError
from mcp.client.stdio import StdioServerParameters
from mcp.types import CONNECTION_CLOSED, REQUEST_TIMEOUT, ToolListChangedNotification
from pydantic import ValidationError

from devflow.code.mcp_contract import (
    BACKEND,
    CONTRACT_VERSION,
    INPUTS,
    MAPPING,
    SERVER_NAME,
    SERVER_VERSION,
    fingerprint,
    tools,
    validate_result,
)
from devflow.core.config import PROJECT_ROOT
from devflow.core.errors import DomainError


def launch_parameters(worker, run_id, token):
    settings = worker.settings
    config = {
        key: getattr(settings, key)
        for key in (
            "postgres_host",
            "postgres_port",
            "postgres_db",
            "postgres_user",
            "code_rg_path",
            "mcp_tool_timeout_seconds",
        )
    }
    config.update(
        postgres_password=settings.postgres_password.get_secret_value(),
        run_id=str(run_id),
        lease_token=str(token),
        parent_pid=os.getpid(),
        artifact_root=str(worker.store.root),
    )
    # SDK 的默认环境只含系统运行项；显式设置项不包含模型或 GitHub 凭据。
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "devflow.code.mcp_server"],
        cwd=PROJECT_ROOT,
        env={
            "DEVFLOW_CODE_MCP_CONFIG": json.dumps(config),
            "DEVFLOW_PROJECT_ROOT": str(PROJECT_ROOT),
            "PYTHONUTF8": "1",
            "PYTHONUNBUFFERED": "1",
        },
    )


def validate_discovery(client, definitions, previous=None):
    info = client.server_info
    if (
        info is None
        or info.name != SERVER_NAME
        or info.version != SERVER_VERSION
        or fingerprint(definitions) != fingerprint(tools())
        or len(definitions) != 3
        or any(
            (tool.meta or {}).get("contract_version") != CONTRACT_VERSION for tool in definitions
        )
    ):
        raise DomainError(409, "mcp_contract_mismatch", "代码证据 MCP 身份或工具契约不兼容")
    result = {
        "server_name": info.name,
        "server_version": info.version,
        "contract_version": CONTRACT_VERSION,
        "protocol_version": client.protocol_version,
        "schema_sha256": fingerprint(definitions),
        "backend": BACKEND,
    }
    if previous and any(previous.get(key) != result[key] for key in result):
        raise DomainError(
            409, "mcp_contract_mismatch", "任务保存的 MCP 契约与当前服务不一致，仍可回放已有结果"
        )
    return result


def domain_cause(error):
    """SDK 的任务组会包装协议错误；保留已明确分类的业务/契约错误。"""
    if isinstance(error, DomainError):
        return error
    if isinstance(error, BaseExceptionGroup):
        for child in error.exceptions:
            found = domain_cause(child)
            if found:
                return found
    return None


class CodeMCPClient:
    def __init__(self, worker, run_id, token, *, deadline=None, parameters=None):
        self.worker, self.run_id, self.token = worker, run_id, token
        self.deadline = deadline or time.monotonic() + 600
        self.parameters = parameters or launch_parameters(worker, run_id, token)
        self.info = {
            "backend": BACKEND,
            "contract_version": CONTRACT_VERSION,
            "status": "not_connected",
        }
        self.records = []
        self._ready = threading.Event()
        self._portal_context = self._portal = self._owner_future = None
        self._send = None
        self._failure = None
        self._stopping = False

    def guard(self):
        self.worker.guard(self.run_id, self.token)
        if time.monotonic() >= self.deadline:
            raise DomainError(504, "mcp_timeout", "代码证据调用达到任务时限")

    def emit(self, name, payload):
        self.worker._event(
            self.run_id,
            self.token,
            name,
            payload,
            key=f"mcp:{name}:{len(self.records)}:{self.worker.owner}",
        )

    def fail(self, error):
        self._failure = error
        self.info.update(status="unavailable", error_code=error.code, error_message=error.message)

    async def protocol_message(self, message):
        if isinstance(message, Exception):
            error = DomainError(502, "mcp_protocol_error", "代码证据 MCP 协议消息异常")
        elif isinstance(message, ToolListChangedNotification):
            error = DomainError(
                409, "mcp_contract_mismatch", "代码证据 MCP 工具契约在任务中发生变化"
            )
        else:
            return
        self.fail(error)
        self.emit("mcp.unavailable", {"label": "代码证据服务不可用；已有材料仍可分析", **self.info})
        if self._send is not None:
            try:
                self._send.send_nowait((None, None, None, None))
            except (anyio.WouldBlock, anyio.ClosedResourceError, anyio.BrokenResourceError):
                pass

    async def _owner(self):
        try:
            from sqlalchemy.orm import Session

            from devflow.storage.models import RunRecord

            with Session(self.worker.engine) as session:
                configuration = session.get(RunRecord, self.run_id).configuration
                if configuration.get("mcp_contract_version") != CONTRACT_VERSION:
                    raise DomainError(
                        409, "mcp_contract_mismatch", "本任务记录的 MCP 契约版本不兼容"
                    )
            async with Client(
                self.parameters,
                cache=None,
                message_handler=self.protocol_message,
                input_required_max_rounds=0,
                read_timeout_seconds=self.worker.settings.mcp_startup_timeout_seconds,
            ) as client:
                definitions = (await client.list_tools()).tools
                previous = self.worker._journal_read(self.run_id, "mcp:contract")
                identity = validate_discovery(client, definitions, previous)
                self.worker._journal_write(self.run_id, self.token, "mcp:contract", identity)
                self.info.update(
                    identity, status="connected", pid=(definitions[0].meta or {}).get("pid")
                )
                self._send, receive = anyio.create_memory_object_stream(1)
                self._ready.set()
                async with receive:
                    async for name, arguments, timeout, future in receive:
                        if name is None:
                            break
                        try:
                            with anyio.fail_after(timeout):
                                reply = await client.call_tool(
                                    name, arguments, read_timeout_seconds=timeout
                                )
                            value = validate_result(name, reply.structured_content, reply.is_error)
                            future.set_result(value)
                        except DomainError as error:
                            # 业务拒绝不破坏连接；不兼容结果则终止本任务后续协议调用。
                            if error.code.startswith("mcp_") and error.code != "mcp_task_denied":
                                self.fail(error)
                            future.set_exception(error)
                            if self._failure:
                                break
                        except Exception as error:
                            if isinstance(error, TimeoutError) or (
                                isinstance(error, MCPError) and error.code == REQUEST_TIMEOUT
                            ):
                                mapped = DomainError(504, "mcp_timeout", "代码证据 MCP 调用超时")
                            elif isinstance(error, (RuntimeError, ValidationError)):
                                mapped = DomainError(
                                    502, "mcp_result_invalid", "代码证据服务返回不符合契约的结果"
                                )
                            elif isinstance(error, MCPError) and error.code != CONNECTION_CLOSED:
                                mapped = DomainError(
                                    502, "mcp_protocol_error", "代码证据 MCP 协议消息异常"
                                )
                            else:
                                mapped = DomainError(
                                    503, "mcp_disconnected", "代码证据 MCP 服务连接中断"
                                )
                            mapped.__cause__ = error
                            self.fail(mapped)
                            if not future.done():
                                future.set_exception(mapped)
                            break
        except BaseException as error:
            if isinstance(error, anyio.get_cancelled_exc_class()):
                return
            if not self._stopping and self._failure is None:
                self.fail(
                    domain_cause(error)
                    or DomainError(
                        503, "mcp_start_failed", "代码证据 MCP 服务无法启动或完成协议协商"
                    )
                )
        finally:
            self._ready.set()

    def start(self):
        if self._portal is not None or self._failure is not None:
            return
        started = time.monotonic()
        end = min(self.deadline, started + self.worker.settings.mcp_startup_timeout_seconds)
        self.guard()
        self.emit("mcp.connecting", {"label": "连接代码证据服务", "transport": "stdio"})
        self.info["status"] = "connecting"
        self._portal_context = start_blocking_portal()
        self._portal = self._portal_context.__enter__()
        self._owner_future = self._portal.start_task_soon(self._owner)
        try:
            while not self._ready.wait(0.05):
                self.guard()
                if self._failure:
                    self._owner_future.cancel()
                    break
                if time.monotonic() >= end:
                    self.fail(DomainError(504, "mcp_start_timeout", "连接代码证据 MCP 服务超时"))
                    self._owner_future.cancel()
                    break
            if time.monotonic() >= end and self._failure is None:
                self.fail(DomainError(504, "mcp_start_timeout", "连接代码证据 MCP 服务超时"))
                self._owner_future.cancel()
            self.info["startup_ms"] = round((time.monotonic() - started) * 1000)
            if self._failure:
                self.emit(
                    "mcp.unavailable",
                    {"label": "代码证据服务不可用；已有材料仍可分析", **self.info},
                )
            else:
                self.emit("mcp.connected", {"label": "代码证据服务已连接", **self.info})
        except BaseException:
            self.close()
            raise

    def call(self, name, arguments):
        try:
            if name not in MAPPING:
                raise DomainError(422, "unknown_tool", "MCP 工具不在白名单中")
            INPUTS[MAPPING[name]].model_validate(arguments)
        except ValidationError as error:
            raise DomainError(422, "invalid_tool_arguments", "MCP 工具参数不符合 schema") from error
        self.guard()
        self.start()
        if self._failure:
            raise self._failure
        if self._owner_future.done() or self._send is None:
            error = DomainError(503, "mcp_disconnected", "代码证据 MCP 服务已退出")
            self.fail(error)
            raise error
        future = concurrent.futures.Future()
        end = min(self.deadline, time.monotonic() + self.worker.settings.mcp_tool_timeout_seconds)
        try:
            self._portal.call(
                self._send.send,
                (MAPPING[name], arguments, max(0.001, end - time.monotonic()), future),
            )
        except Exception as cause:
            error = DomainError(503, "mcp_disconnected", "代码证据 MCP 服务连接已关闭")
            self.fail(error)
            raise error from cause
        try:
            while True:
                self.guard()
                if self._failure:
                    self._owner_future.cancel()
                    raise self._failure
                remaining = end - time.monotonic()
                if remaining <= 0:
                    error = DomainError(504, "mcp_timeout", "代码证据 MCP 调用超过时限")
                    self.fail(error)
                    self._owner_future.cancel()
                    raise error
                try:
                    return future.result(timeout=min(0.05, remaining))
                except concurrent.futures.TimeoutError:
                    continue
        except BaseException:
            if not future.done():
                self._owner_future.cancel()
            raise

    def record(
        self,
        name,
        args,
        *,
        replay=False,
        error=None,
        elapsed_ms=0,
        result_chars=0,
        metadata=None,
        result=None,
    ):
        record = {
            **(metadata or self.info),
            "tool": MAPPING.get(name, name),
            "arguments": args.model_dump(),
            "duration_ms": elapsed_ms,
            "result_chars": result_chars,
            "source": "journal" if replay else "protocol",
            "status": "replayed" if replay else self.info["status"],
            "error_code": error.code if error else None,
            "error_message": error.message if error else None,
            "returned_ranges": [
                {key: item[key] for key in ("id", "path", "version", "start_line", "end_line")}
                for item in (
                    (result or {}).get("items", []) if name == "search_code" else [result or {}]
                )
                if item.get("id") and item.get("lines")
            ],
        }
        self.records.append(record)
        if error and self.info["status"] == "unavailable" and not replay:
            self.emit(
                "mcp.unavailable", {"label": "代码证据服务不可用；已有材料仍可分析", **self.info}
            )
        self.emit(
            "mcp.replayed" if replay else "mcp.call_failed" if error else "mcp.call_completed",
            {
                "label": "回放已保存代码证据"
                if replay
                else "代码证据补查失败"
                if error
                else "代码证据补查完成",
                **record,
            },
        )
        return record

    def close(self):
        self._stopping = True
        if self._owner_future is not None and not self._owner_future.done():
            self._owner_future.cancel()
        if self._portal_context is not None:
            self._portal_context.__exit__(None, None, None)
            self._portal_context = None
        if self.info.get("status") == "connected":
            self.info["status"] = "closed"
            from devflow.workflows.worker import LeaseLost, RunCancelled, RunTimedOut

            try:
                self.emit("mcp.closed", {"label": "代码证据服务已关闭", **self.info})
            except (LeaseLost, RunCancelled, RunTimedOut):
                # 已完成进程回收；失去租约/取消后不再为旧执行者写事件。
                pass

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.close()
