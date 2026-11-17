# 文件用途：通过真实 MCP 协议注入退出、延迟及契约/结果错误。
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import anyio
from devflow.code.mcp_contract import SERVER_NAME, SERVER_VERSION, tools
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, ToolListChangedNotification

CHILDREN = []


async def main():
    mode = sys.argv[1]
    wire_fd = os.dup(sys.stdout.fileno()) if mode == "wire" else None
    if mode == "start_exit":
        return

    async def listing(context, params):
        if mode == "start_timeout":
            await anyio.sleep(30)
        values = tools(os.getpid())
        if mode == "schema":
            values[0].input_schema = {"type": "object"}
        if mode == "missing":
            values.pop()
        return ListToolsResult(tools=values)

    async def calling(context, params):
        if mode == "wire":
            os.write(wire_fd, b"invalid-json\n")
            await anyio.sleep(30)
        if mode == "changed":
            # 故障注入：在当前请求通道宣告契约变化（正常静态服务不会发送）。
            await context.session.send_notification(
                ToolListChangedNotification(), related_request_id=context.request_id
            )
            await anyio.sleep(30)
        if mode == "orphan":
            child = subprocess.Popen(
                [shutil.which("rg"), "--fixed-strings", "--", "needle", "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
            CHILDREN.append(child)
            Path(sys.argv[2]).write_bytes(
                json.dumps({"server": os.getpid(), "rg": child.pid}).encode()
            )
            await anyio.sleep(60)
        if mode == "exit":
            os._exit(19)
        if mode == "timeout":
            await anyio.sleep(30)
        value = {"ok": True, "data": {"unexpected": "malformed"}, "error": None}
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(value))], structured_content=value
        )

    server = Server(
        SERVER_NAME, version=SERVER_VERSION, on_list_tools=listing, on_call_tool=calling
    )
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(main)
