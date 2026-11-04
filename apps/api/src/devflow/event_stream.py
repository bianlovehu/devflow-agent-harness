# 文件用途：从已提交事件生成带序号的 SSE，短会话轮询支持断线续传且不取消任务。
import asyncio
import json
import time

from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from devflow.models import RunEventRecord, RunRecord
from devflow.security import redact
from devflow.workflow_contracts import RunEventResponse
from devflow.workflows import TERMINAL


def event_batch(engine, run_id, after):
    # 每轮单独打开并关闭事务，不在长连接期间占用数据库连接或旧快照。
    with Session(engine) as session:
        # 先读状态再读事件：若结束发生在两次查询之间，下轮仍会补取终态事件。
        # 反过来会出现旧事件列表配上新终态，过早发送 end 而遗漏最后一次提交。
        run = session.get(RunRecord, run_id)
        rows = session.scalars(
            select(RunEventRecord)
            .where(RunEventRecord.run_id == run_id, RunEventRecord.sequence > after)
            .order_by(RunEventRecord.sequence)
            .limit(100)
        ).all()
        return [
            RunEventResponse.model_validate(row).model_dump(mode="json") for row in rows
        ], run.status


def sse_frame(event: dict) -> str:
    data = json.dumps(redact(event), ensure_ascii=False, separators=(",", ":"))
    return f"id: {event['sequence']}\nevent: run_event\ndata: {data}\n\n"


async def stream_events(request, engine, run_id, after, *, max_seconds=45, poll_seconds=0.25):
    cursor = after
    started = last_heartbeat = time.monotonic()
    yield "retry: 1500\n\n"
    while not await request.is_disconnected():
        rows, status = await run_in_threadpool(event_batch, engine, run_id, cursor)
        for event in rows:
            cursor = event["sequence"]
            yield sse_frame(event)
        if len(rows) == 100:
            continue
        if status in TERMINAL:
            yield f"event: end\ndata: {json.dumps({'status': status, 'after': cursor})}\n\n"
            return
        now = time.monotonic()
        if now - started >= max_seconds:
            # 结束一个传输会话后 EventSource 自动携带 Last-Event-ID 重连。
            yield ": reconnect\n\n"
            return
        if now - last_heartbeat >= 10:
            yield ": keepalive\n\n"
            last_heartbeat = now
        await asyncio.sleep(poll_seconds)
