# 文件用途：以租约和心跳执行持久化只读分析或模拟任务，支持取消、预算与模型调用留痕。
import argparse
import logging
import signal
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from devflow.agent import AnalysisRunner
from devflow.artifact_store import ArtifactStore
from devflow.checkpoint import postgres_checkpointer
from devflow.config import get_settings
from devflow.database import create_database_engine
from devflow.errors import DomainError
from devflow.evidence_capture import bind_capture, capture_github
from devflow.fake_model import FixtureModel
from devflow.github_client import GitHubClient
from devflow.model_gateway import DeepSeekModel
from devflow.models import (
    ArtifactRecord,
    EvidenceRecord,
    MessageRecord,
    RepositoryRecord,
    ResourceSnapshot,
    RunEvidenceRecord,
    RunJournal,
    RunRecord,
)
from devflow.security import redact
from devflow.tool_gateway import ToolGateway
from devflow.workflows import append_message, append_run_event, run_evidence

logger = logging.getLogger("devflow.worker")


class LeaseLost(Exception):
    pass


class RunCancelled(Exception):
    pass


class RunTimedOut(Exception):
    pass


class Worker:
    def __init__(
        self,
        engine,
        settings,
        store=None,
        *,
        client_factory=GitHubClient,
        owner=None,
        model_factory=None,
        embedder_factory=None,
    ):
        self.engine = engine
        self.settings = settings
        self.store = store or ArtifactStore()
        self.client_factory = client_factory
        self.model_factory = model_factory
        self.embedder_factory = embedder_factory
        self.owner = owner or "worker-" + uuid.uuid4().hex
        self.stop = threading.Event()

    def _owned(self, session, run_id, token, *, check_stop=True):
        run = session.scalar(select(RunRecord).where(RunRecord.id == run_id).with_for_update())
        now = session.scalar(select(func.clock_timestamp()))
        if (
            run is None
            or run.status != "running"
            or run.lease_token != token
            or run.lease_expires_at is None
            or run.lease_expires_at <= now
        ):
            raise LeaseLost()
        if check_stop:
            if self.stop.is_set():
                raise LeaseLost()
            if run.cancel_requested_at is not None:
                raise RunCancelled()
            if now >= run.started_at + timedelta(
                seconds=run.configuration["budget"]["timeout_seconds"]
            ):
                raise RunTimedOut()
        return run, now

    def reap_expired(self):
        # 仅新版本 Agent 任务自动恢复一次；模拟/历史任务仍进入待处理。
        with Session(self.engine) as session, session.begin():
            runs = session.scalars(
                select(RunRecord)
                .join(RepositoryRecord)
                .where(
                    RunRecord.status == "running",
                    RunRecord.lease_expires_at <= func.clock_timestamp(),
                    RepositoryRecord.data_source == self.settings.data_source,
                )
                .with_for_update(of=RunRecord, skip_locked=True)
            ).all()
            for run in runs:
                recover = (
                    not run.cancel_requested_at
                    and run.recovery_count == 0
                    and run.configuration.get("checkpoint_enabled")
                    and run.configuration.get("executor") == "agent"
                )
                run.status = (
                    "queued"
                    if recover
                    else "cancelled"
                    if run.cancel_requested_at
                    else "needs_attention"
                )
                run.error_code = None if recover or run.cancel_requested_at else "worker_lost"
                run.error_message = (
                    None
                    if recover or run.cancel_requested_at
                    else "自动恢复次数已用尽或旧任务无 checkpoint，请检查后手动重试"
                )
                if recover:
                    run.recovery_count += 1
                else:
                    run.finished_at = session.scalar(select(func.clock_timestamp()))
                run.lease_token = None
                run.lease_owner = None
                run.lease_expires_at = None
                append_run_event(
                    session,
                    run.id,
                    "run.recovery_queued" if recover else "run." + run.status,
                    {
                        "status": run.status,
                        "error_code": run.error_code,
                        "recovery_count": run.recovery_count,
                    },
                )
            return len(runs)

    def claim(self, run_id=None):
        self.reap_expired()
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            run = session.scalar(
                select(RunRecord)
                .join(RepositoryRecord)
                .where(
                    RunRecord.status == "queued",
                    RunRecord.cancel_requested_at.is_(None),
                    RunRecord.configuration["executor"].astext.in_(["simulation", "agent"]),
                    RunRecord.id == run_id if run_id is not None else True,
                    RepositoryRecord.data_source == self.settings.data_source,
                )
                .order_by(RunRecord.created_at, RunRecord.id)
                .with_for_update(of=RunRecord, skip_locked=True)
                .limit(1)
            )
            if run is None:
                return None
            now = session.scalar(select(func.clock_timestamp()))
            run.status = "running"
            run.attempt += 1
            run.lease_token = uuid.uuid4()
            run.lease_owner = self.owner
            run.started_at = run.started_at or now
            run.heartbeat_at = now
            run.lease_expires_at = now + timedelta(seconds=self.settings.worker_lease_seconds)
            append_run_event(
                session,
                run.id,
                "run.resumed" if run.recovery_count else "run.started",
                {
                    "status": "running",
                    "attempt": run.attempt,
                    "executor": run.configuration.get("executor"),
                    "recovery_count": run.recovery_count,
                },
            )
            return run.id, run.lease_token

    def heartbeat(self, run_id, token):
        with Session(self.engine) as session, session.begin():
            run, now = self._owned(session, run_id, token, check_stop=False)
            run.heartbeat_at = now
            run.lease_expires_at = now + timedelta(seconds=self.settings.worker_lease_seconds)

    def guard(self, run_id, token):
        with Session(self.engine) as session, session.begin():
            self._owned(session, run_id, token)

    def _event(self, run_id, token, event_type, payload, key=None):
        with Session(self.engine) as session, session.begin():
            self._owned(session, run_id, token)
            key = key or f"event:{event_type}:{payload.get('stage', '')}:{payload.get('tool', '')}"
            if session.get(RunJournal, (run_id, key)) is None:
                append_run_event(session, run_id, event_type, redact(payload))
                session.add(RunJournal(run_id=run_id, key=key, payload={"emitted": True}))

    def _journal_read(self, run_id, key):
        with Session(self.engine) as session:
            record = session.get(RunJournal, (run_id, key))
            return record.payload if record else None

    def _journal_write(self, run_id, token, key, value):
        with Session(self.engine) as session, session.begin():
            self._owned(session, run_id, token, check_stop=False)
            record = session.get(RunJournal, (run_id, key))
            if record is None:
                session.add(RunJournal(run_id=run_id, key=key, payload=redact(value)))
            else:
                record.payload = redact(value)

    def _wait(self, run_id, token):
        end = time.monotonic() + self.settings.simulation_step_seconds
        while time.monotonic() < end:
            self.guard(run_id, token)
            self.stop.wait(min(0.2, max(0, end - time.monotonic())))
        self.guard(run_id, token)

    def _finish(self, run_id, token, status, *, result=None, code=None, message=None):
        with Session(self.engine) as session, session.begin():
            run, now = self._owned(session, run_id, token, check_stop=False)
            # 取消与最终提交共用同一任务行锁，取消一旦提交，结果不能覆盖取消。
            if run.cancel_requested_at is not None:
                status, code, message, result = "cancelled", None, None, None
            elif now >= run.started_at + timedelta(
                seconds=run.configuration["budget"]["timeout_seconds"]
            ):
                status, code, message, result = "failed", "timeout", "任务达到总时长限制", None
            if status == "failed" and run.recovery_count:
                status = "needs_attention"
            run.status = status
            run.result = result
            if status == "succeeded" and result and result.get("kind") == "analysis_report":
                import json

                append_message(
                    session,
                    run.conversation_id,
                    json.dumps(
                        {
                            "run_id": str(run.id),
                            "report": result["report"],
                            "input_version": run.input_version,
                        },
                        ensure_ascii=False,
                    ),
                    role="assistant",
                )
            run.error_code = code
            run.error_message = message
            run.finished_at = now
            run.lease_token = run.lease_owner = run.lease_expires_at = None
            append_run_event(
                session,
                run_id,
                "run." + status,
                {
                    "status": status,
                    "error_code": code,
                    "executor": run.configuration.get("executor"),
                },
            )

    def _analyze(self, run_id, token):
        import json

        with Session(self.engine) as session:
            run = session.get(RunRecord, run_id)
            repo = session.get(RepositoryRecord, run.repo_id)
            configuration = {**run.configuration, "recovering": run.recovery_count > 0}
            items = []
            for evidence in run_evidence(session, run_id):
                artifact = session.get(ArtifactRecord, evidence.artifact_id)
                items.append(
                    {
                        "id": str(evidence.id),
                        "artifact_id": str(artifact.id),
                        "path": evidence.path,
                        "version": evidence.version,
                        "source_type": evidence.source_type,
                        "start_line": evidence.start_line,
                        "end_line": evidence.end_line,
                        "content": self.store.read_text(artifact.storage_key, artifact.sha256),
                    }
                )
            snapshots = []
            for resource in run.input_version["resources"]:
                if resource.get("snapshot_id"):
                    snapshot = session.get(ResourceSnapshot, uuid.UUID(resource["snapshot_id"]))
                    payload = snapshot.payload
                    # 避免把完整代码/日志塞进初始消息，正文只能通过工具按预算读取。
                    metadata = payload.get("metadata", payload)
                    snapshots.append(
                        {
                            "kind": snapshot.kind,
                            "external_id": snapshot.external_id,
                            **{
                                key: metadata[key]
                                for key in (
                                    "title",
                                    "body",
                                    "name",
                                    "status",
                                    "conclusion",
                                    "base_sha",
                                    "head_sha",
                                    "run_attempt",
                                    "related_ci",
                                )
                                if key in metadata and len(str(metadata[key])) <= 3000
                            },
                            "related_ci": payload.get("related_ci", []),
                        }
                    )
            task_type = run.task_type
            input_version = run.input_version
            question = session.get(MessageRecord, run.message_id).content
            current_message = session.get(MessageRecord, run.message_id)
            history = [
                {"id": str(m.id), "role": m.role, "content": m.content}
                for m in session.scalars(
                    select(MessageRecord)
                    .where(
                        MessageRecord.conversation_id == run.conversation_id,
                        MessageRecord.sequence < current_message.sequence,
                    )
                    .order_by(MessageRecord.sequence)
                ).all()
            ]
            from devflow.memory import recall_memories, run_version

            memories = recall_memories(session, run.repo_id, run_version(run.input_version))
            recovery_count = run.recovery_count
            repo_id, source = run.repo_id, repo.data_source
            # 采集证据已消耗的时间不能在进入模型循环时被重新分配。
            now = session.scalar(select(func.clock_timestamp()))
            deadline = (
                time.monotonic()
                + (
                    run.started_at
                    + timedelta(seconds=configuration["budget"]["timeout_seconds"])
                    - now
                ).total_seconds()
            )
        model_settings = self.settings.model_copy(
            update={
                "model_provider": configuration["provider"],
                "deepseek_model": configuration["model"],
                "dashscope_model": configuration["model"],
                "dashscope_base_url": configuration["base_url"],
                "model_timeout_seconds": configuration["model_timeout_seconds"],
            }
        )
        if self.model_factory:
            model = self.model_factory(model_settings)
        elif configuration["provider"] == "fake":
            if source != "fixture":
                raise DomainError(
                    422, "model_configuration_error", "真实 GitHub 分析需要配置真实模型供应商"
                )
            model = FixtureModel()
        else:
            model = DeepSeekModel(model_settings)

        def guard():
            self.guard(run_id, token)

        def emit(name, payload):
            self._event(
                run_id,
                token,
                name,
                payload,
                key=f"agent:{runner.model_calls}:{runner.tool_calls}:{name}",
            )

        @contextmanager
        def fence():
            with Session(self.engine) as session, session.begin():
                self._owned(session, run_id, token, check_stop=False)
                yield

        def recheck_memories():
            # 恢复与每次发起模型请求前重查审核状态，撤销/过期不会继续随旧消息注入。
            with Session(self.engine) as session:
                valid = recall_memories(session, repo_id, run_version(input_version))
            runner.memories = valid
            runner.active_memories = valid

        def knowledge_search(query):
            from devflow.embeddings import get_embedder
            from devflow.knowledge import repository_lock, search_knowledge

            with Session(self.engine) as session, session.begin():
                # 先计算召回，绑定前重新检查租约和有效版本，避免索引期间长期持有任务锁。
                found = search_knowledge(
                    session,
                    repo_id,
                    query,
                    version_ids=input_version.get("knowledge_versions", []),
                    embedder_factory=self.embedder_factory or get_embedder,
                )
                self._owned(session, run_id, token)
                repository_lock(session, repo_id)
                from devflow.knowledge import active_versions

                active = {str(v) for v in active_versions(session, repo_id)}
                found["items"] = [v for v in found["items"] if v["version_id"] in active]
                evidence_items = []
                for item in found["items"]:
                    evidence = session.get(EvidenceRecord, uuid.UUID(item["evidence_id"]))
                    artifact = session.get(ArtifactRecord, evidence.artifact_id)
                    if session.get(RunEvidenceRecord, (run_id, evidence.id)) is None:
                        session.add(
                            RunEvidenceRecord(
                                run_id=run_id, evidence_id=evidence.id, repo_id=repo_id
                            )
                        )
                    evidence_items.append(
                        {
                            "id": str(evidence.id),
                            "artifact_id": str(artifact.id),
                            "source_type": "document",
                            "path": evidence.path,
                            "version": evidence.version,
                            "start_line": evidence.start_line,
                            "end_line": evidence.end_line,
                            "content": self.store.read_text(artifact.storage_key, artifact.sha256),
                        }
                    )
                    item["id"] = str(evidence.id)
                    item["lines"] = [
                        {"line": item["start_line"] + i, "text": text}
                        for i, text in enumerate(item.pop("content").splitlines())
                    ]
                found["_evidence"] = evidence_items
                event_key = f"knowledge:{runner.model_calls}:{runner.tool_calls}"
                if session.get(RunJournal, (run_id, event_key)) is None:
                    append_run_event(
                        session,
                        run_id,
                        "knowledge.retrieved",
                        redact(
                            {
                                "query": query,
                                "items": [
                                    {k: v for k, v in item.items() if k != "lines"}
                                    for item in found["items"]
                                ],
                                "model_key": found["model_key"],
                            }
                        ),
                    )
                    session.add(RunJournal(run_id=run_id, key=event_key, payload={"emitted": True}))
                return found

        gateway = ToolGateway(
            repo_id,
            items,
            {"resources": snapshots, "input_version": input_version},
            guard=guard,
            emit=emit,
            knowledge_search=knowledge_search,
        )
        runner = AnalysisRunner(
            model,
            gateway,
            task_type,
            question,
            configuration,
            guard=guard,
            emit=emit,
            timeout_seconds=deadline - time.monotonic(),
            history=history,
            memories=memories,
            journal_read=lambda key: self._journal_read(run_id, key),
            journal_write=lambda key, value: self._journal_write(run_id, token, key, value),
            thread_id=str(run_id),
            before_model=recheck_memories,
        )
        self._event(
            run_id, token, "stage.started", {"stage": "analysis", "label": "模型与工具分析"}
        )
        try:
            with postgres_checkpointer(self.engine, fence) as checkpointer:
                runner.checkpointer = checkpointer
                result = runner.run()
        finally:
            # 取消或超时也保留已发生的调用；仍强制校验租约，不允许旧 worker 写入。
            trace = json.dumps(runner.trace, ensure_ascii=False, indent=2)
            key, digest, size = self.store.put_text(trace)
            with Session(self.engine) as session, session.begin():
                self._owned(session, run_id, token, check_stop=False)
                artifact = session.scalar(
                    select(ArtifactRecord).where(
                        ArtifactRecord.repo_id == repo_id, ArtifactRecord.sha256 == digest
                    )
                )
                if artifact is None:
                    artifact = ArtifactRecord(
                        repo_id=repo_id,
                        sha256=digest,
                        size_bytes=size,
                        media_type="application/json",
                        storage_key=key,
                    )
                    session.add(artifact)
                    session.flush()
                trace_id = str(artifact.id)
                event_key = f"event:trace:{run.attempt}"
                if session.get(RunJournal, (run_id, event_key)) is None:
                    append_run_event(
                        session,
                        run_id,
                        "analysis.trace_saved",
                        {
                            "artifact_id": trace_id,
                            "model_calls": runner.model_calls,
                            "tool_calls": runner.tool_calls,
                            "total_tokens": runner.total_tokens,
                            "attempt": run.attempt,
                        },
                    )
                    session.add(RunJournal(run_id=run_id, key=event_key, payload={"emitted": True}))
        # 服务端补充不可省略的检查范围，不能仅靠模型自报覆盖率。
        result["report"]["scope"] = result["report"]["scope"][:29]
        result["report"]["scope"].append(
            f"服务端记录：绑定证据 {len(gateway.evidence)} 条，"
            f"实际读到 {len(gateway.observed)} 条；"
            "未执行仓库代码或测试。"
        )
        if not gateway.observed:
            result["report"]["unconfirmed"] = result["report"]["unconfirmed"][:19]
            result["report"]["unconfirmed"].append(
                "服务端记录：未读取任何证据正文，仅取得目录或工具错误；无法据此确认风险或排除缺陷。"
            )
        complete = all(
            resource.get("coverage_complete", True) for resource in input_version["resources"]
        )
        if not complete:
            result["report"]["unconfirmed"] = result["report"]["unconfirmed"][:19]
            result["report"]["unconfirmed"].append(
                "采集范围不完整，请核查固定输入中的 warnings 和元数据制品。"
            )
        result.update(
            {
                "trace_artifact_id": trace_id,
                "input_version": input_version,
                "coverage_complete": complete,
                "recovery_count": recovery_count,
                "recovery_model_calls": sum(
                    1 for call in runner.trace["calls"] if call.get("recovery")
                ),
                "recalled_memories": [m["id"] for m in runner.memories],
                "unknown_usage_calls": sum(
                    1 for call in runner.trace["calls"] if "usage" not in call
                ),
                "recovery_usage": {
                    key: sum(
                        call.get("usage", {}).get(key, 0)
                        for call in runner.trace["calls"]
                        if call.get("recovery")
                    )
                    for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                },
            }
        )
        self._event(
            run_id, token, "stage.completed", {"stage": "analysis", "label": "报告与引用已校验"}
        )
        self._finish(run_id, token, "succeeded", result=result)

    def execute(self, run_id, token):
        pulse_stop = threading.Event()

        def pulse():
            while not pulse_stop.wait(min(2, self.settings.worker_lease_seconds / 3)):
                try:
                    self.heartbeat(run_id, token)
                except Exception:
                    # 续租失败时不假定仍有所有权；后续 guard 与最终提交都会再校验。
                    return

        thread = threading.Thread(target=pulse, daemon=True)
        thread.start()
        try:
            self._event(
                run_id, token, "stage.started", {"stage": "evidence", "label": "固定版本与证据"}
            )
            with Session(self.engine) as session:
                run = session.get(RunRecord, run_id)
                repo = session.get(RepositoryRecord, run.repo_id)
                resource = next(iter(run.input_version["resources"]), {})
                full_name = repo.full_name
                executor = run.configuration.get("executor")
                needs_capture = repo.data_source == "github" and resource.get("pending_evidence")
            if needs_capture:
                self._event(
                    run_id, token, "tool.started", {"tool": "capture_github", "read_only": True}
                )
                capture = capture_github(
                    full_name,
                    resource,
                    self.client_factory(self.settings),
                    lambda: self.guard(run_id, token),
                    include_context=executor == "agent",
                )
                with Session(self.engine) as session, session.begin():
                    run, _ = self._owned(session, run_id, token)
                    # 同仓库证据入库串行，防止并发任务争抢当前快照与相同制品唯一键。
                    session.execute(
                        select(func.pg_advisory_xact_lock(func.hashtextextended(run.repo_id, 42)))
                    )
                    self._owned(session, run_id, token)
                    bind_capture(session, run, capture, self.store)
                    append_run_event(
                        session,
                        run_id,
                        "tool.completed",
                        {
                            "tool": "capture_github",
                            "coverage_complete": capture.payload["coverage_complete"],
                            "warnings": capture.payload["warnings"],
                        },
                    )
            self._wait(run_id, token)
            self._event(
                run_id, token, "stage.completed", {"stage": "evidence", "label": "证据已固定"}
            )
            self._event(
                run_id, token, "tool.started", {"tool": "verify_artifacts", "read_only": True}
            )
            with Session(self.engine) as session:
                evidence = run_evidence(session, run_id)
                run = session.get(RunRecord, run_id)
                if not evidence and run.task_type != "knowledge_qa":
                    raise DomainError(409, "evidence_unavailable", "任务尚无可引用证据")
                log_count = 0
                for item in evidence:
                    self.guard(run_id, token)
                    artifact = session.get(ArtifactRecord, item.artifact_id)
                    self.store.read_text(artifact.storage_key, artifact.sha256)
                    log_count += item.source_type == "log"
                count = len(evidence)
                run = session.get(RunRecord, run_id)
                resource = next(iter(run.input_version["resources"]), {})
                missing_logs = run.task_type == "ci_debug" and log_count == 0
            self._event(
                run_id,
                token,
                "tool.completed",
                {"tool": "verify_artifacts", "evidence_count": count},
            )
            if executor == "agent":
                if missing_logs:
                    self._finish(
                        run_id,
                        token,
                        "needs_attention",
                        code="evidence_unavailable",
                        message="没有可读取的 job 日志，无法生成 CI 排障报告",
                    )
                else:
                    self._analyze(run_id, token)
                return
            self._event(
                run_id,
                token,
                "stage.started",
                {"stage": "simulation", "label": "验证后台执行通道（模拟）"},
            )
            self._wait(run_id, token)
            self._event(
                run_id, token, "stage.completed", {"stage": "simulation", "label": "模拟流程完成"}
            )
            result = {
                "kind": "simulation_summary",
                "label": "模拟执行完成，尚未调用模型",
                "evidence_count": count,
                "coverage_complete": resource.get("coverage_complete", True),
                "model_calls": 0,
                "analysis_report_available": False,
            }
            if missing_logs:
                self._finish(
                    run_id,
                    token,
                    "needs_attention",
                    result=result,
                    code="evidence_unavailable",
                    message="已保存 CI 元数据，但没有可读取的 job 日志；请检查权限或日志保留期限",
                )
            else:
                self._finish(run_id, token, "succeeded", result=result)
        except RunCancelled:
            self._finish(run_id, token, "cancelled")
        except RunTimedOut:
            self._finish(run_id, token, "failed", code="timeout", message="任务达到总时长限制")
        except LeaseLost:
            logger.info("Lease lost for run %s; no further writes", run_id)
        except DomainError as error:
            code = (
                error.code
                if error.code
                in {"input_changed", "artifact_missing", "timeout", "budget_exceeded", "tool_error"}
                or error.code.startswith("model_")
                else "evidence_unavailable"
            )
            self._finish(run_id, token, "failed", code=code, message=error.message)
        except Exception as error:
            logger.error("Run %s stopped: %s", run_id, type(error).__name__)
            self._finish(
                run_id,
                token,
                "failed",
                code="internal_error",
                message="执行失败，请检查 worker 日志",
            )
        finally:
            pulse_stop.set()
            thread.join(timeout=3)

    def run_once(self):
        claimed = self.claim()
        if claimed is None:
            return False
        try:
            self.execute(*claimed)
        except LeaseLost:
            pass
        return True

    def run_forever(self):
        while not self.stop.is_set():
            try:
                if not self.run_once():
                    self.stop.wait(self.settings.worker_poll_seconds)
            except Exception as error:
                logger.error("Worker loop: %s", type(error).__name__)
                self.stop.wait(self.settings.worker_poll_seconds)


def main():
    parser = argparse.ArgumentParser(description="DevFlow 持久化分析 worker")
    parser.add_argument("--once", action="store_true", help="至多领取一个任务后退出")
    parser.add_argument("--owner", help="可选进程标识，用于诊断租约持有者")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    engine = create_database_engine(settings)
    worker = Worker(engine, settings, owner=args.owner)
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: worker.stop.set())
    try:
        if args.once:
            worker.run_once()
        else:
            worker.run_forever()
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
