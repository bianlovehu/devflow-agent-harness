# 文件用途：持久化 GitHub 仓库摘要，并按登记范围读取 PR、Issue、CI 与 job 日志。
import hashlib
import re
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from devflow.config import Settings
from devflow.contracts import (
    ChangedFile,
    CIJob,
    CIRunDetail,
    CIRunSummary,
    CIStep,
    JobLog,
    LinkedIssue,
    PullRequestDetail,
    PullRequestSummary,
    Repository,
    SourceNotice,
)
from devflow.errors import DomainError
from devflow.github_client import GitHubClient, parse_repository_url, ref_path, repo_path, utc_now
from devflow.models import RepositoryRecord


def malformed():
    return DomainError(502, "github_invalid_response", "GitHub 资源字段不完整，请稍后重试")


def pull_summary(data: dict, repo_id: str, fetched_at: datetime) -> PullRequestSummary:
    return PullRequestSummary(
        repo_id=repo_id,
        data_source="github",
        number=data["number"],
        title=data["title"],
        body=data.get("body") or "",
        author=(data.get("user") or {}).get("login") or "unknown",
        state="merged" if data.get("merged_at") or data.get("merged") else data["state"],
        base_sha=data["base"]["sha"],
        head_sha=data["head"]["sha"],
        updated_at=data["updated_at"],
        html_url=f"https://github.com/{parse_repository_url(data['base']['repo']['full_name'])}/pull/{data['number']}",
        fetched_at=fetched_at,
    )


def ci_summary(data: dict, repo_id: str, full_name: str, fetched_at: datetime) -> CIRunSummary:
    parents = data.get("pull_requests") or []
    return CIRunSummary(
        id=data["id"],
        repo_id=repo_id,
        data_source="github",
        pull_request_number=parents[0]["number"] if parents else None,
        name=data.get("name") or data.get("display_title") or "GitHub Actions",
        conclusion=data.get("conclusion"),
        stage=None,
        head_sha=data["head_sha"],
        started_at=data.get("run_started_at") or data["created_at"],
        duration_seconds=None,
        status=data["status"],
        run_attempt=data.get("run_attempt", 1),
        html_url=f"https://github.com/{full_name}/actions/runs/{data['id']}",
        fetched_at=fetched_at,
    )


def issue_references(body: str, full_name: str) -> list[int]:
    # 只识别正文中同仓库的引用；不把正文当作工具指令，也不声称这些引用会自动关闭 Issue。
    pattern = r"https://github\.com/([A-Za-z0-9-]+/[A-Za-z0-9_.-]+)/issues/(\d+)|(?<![\w/.-])(?:([A-Za-z0-9-]+/[A-Za-z0-9_.-]+))?#(\d+)"
    found = []
    for match in re.finditer(pattern, body):
        owner_repo = match.group(1) or match.group(3)
        number = int(match.group(2) or match.group(4))
        if (
            number > 0
            and (owner_repo is None or owner_repo.lower() == full_name.lower())
            and number not in found
        ):
            found.append(number)
    return found


class GitHubRepositorySource:
    mode = "github"

    def __init__(self, session: Session, settings: Settings, client: GitHubClient | None = None):
        self.session = session
        self.client = client or GitHubClient(settings)

    def _record(self, repo_id: str) -> RepositoryRecord:
        record = self.session.get(RepositoryRecord, repo_id)
        if record is None or record.data_source != "github":
            raise DomainError(404, "not_found", "GitHub 仓库未登记")
        return record

    def _contract(self, record: RepositoryRecord) -> Repository:
        state = record.sync_state or {}
        return Repository(
            id=record.id,
            data_source="github",
            full_name=record.full_name,
            description=record.description,
            language=record.language,
            default_branch=record.default_branch,
            default_commit=record.default_commit,
            updated_at=record.source_updated_at,
            pull_request_count=len(state.get("pull_request", {}).get("items", [])),
            ci_run_count=len(state.get("ci_run", {}).get("items", [])),
            document_count=0,
            fetched_at=state.get("fetched_at"),
            sync_warnings=[
                notice
                for kind in ("pull_request", "ci_run")
                for notice in state.get(kind, {}).get("warnings", [])
            ],
        )

    def list_repositories(self) -> list[Repository]:
        records = self.session.scalars(
            select(RepositoryRecord)
            .where(RepositoryRecord.data_source == "github")
            .order_by(RepositoryRecord.full_name)
        ).all()
        return [self._contract(record) for record in records]

    def get_repository(self, repo_id: str) -> Repository:
        return self._contract(self._record(repo_id))

    def collection_metadata(self, repo_id: str, kind: str) -> dict:
        group = (self._record(repo_id).sync_state or {}).get(kind, {})
        return {key: group[key] for key in ("fetched_at", "limited", "warnings") if key in group}

    def add_repository(self, url: str) -> Repository:
        return self._sync(parse_repository_url(url))

    def refresh(self, repo_id: str) -> Repository:
        return self._sync(self._record(repo_id).full_name)

    def _sync(self, full_name: str) -> Repository:
        fetched_at = utc_now()
        root = repo_path(full_name)
        metadata = self.client.get(root)
        try:
            canonical = parse_repository_url(metadata["full_name"])
            github_id = int(metadata["id"])
            if github_id <= 0:
                raise ValueError("invalid id")
            branch = metadata["default_branch"]
            if not branch:
                raise DomainError(
                    409, "github_repository_not_ready", "仓库尚无默认分支，请先创建首个提交"
                )
            commit = self.client.get(repo_path(canonical) + "/commits/" + ref_path(branch))["sha"]
            repo_id = f"github-{github_id}"
            old = self.session.get(RepositoryRecord, repo_id)
            old_state = old.sync_state if old and old.sync_state else {}
            state = {"fetched_at": fetched_at.isoformat(), "github_id": github_id}
            blocked = None
            for kind, suffix, key, params in [
                (
                    "pull_request",
                    "/pulls",
                    None,
                    {"state": "all", "sort": "updated", "direction": "desc"},
                ),
                ("ci_run", "/actions/runs", "workflow_runs", {}),
            ]:
                try:
                    if blocked is not None:
                        raise blocked
                    rows, limited = self.client.paginate(
                        repo_path(canonical) + suffix, key=key, limit=20, params=params
                    )
                    items = [
                        (
                            pull_summary(row, repo_id, fetched_at)
                            if kind == "pull_request"
                            else ci_summary(row, repo_id, canonical, fetched_at)
                        ).model_dump(mode="json")
                        for row in rows
                    ]
                    state[kind] = {
                        "items": items,
                        "fetched_at": fetched_at.isoformat(),
                        "limited": limited,
                        "warnings": [],
                    }
                except DomainError as error:
                    if error.status in {401, 429, 503, 504}:
                        blocked = error
                    # 独立权限失败保留之前的成功摘要和它的抓取时间，不伪装成空数据。
                    group = dict(
                        old_state.get(kind, {"items": [], "fetched_at": None, "limited": False})
                    )
                    group["warnings"] = [
                        SourceNotice(
                            code=error.code,
                            message=("PR列表：" if kind == "pull_request" else "CI列表：")
                            + error.message,
                            retry_after=error.retry_after,
                        ).model_dump()
                    ]
                    state[kind] = group
            values = Repository(
                id=repo_id,
                data_source="github",
                full_name=canonical,
                description=metadata.get("description") or "",
                language=metadata.get("language") or "未标注",
                default_branch=branch,
                default_commit=commit,
                updated_at=metadata["updated_at"],
                pull_request_count=0,
                ci_run_count=0,
                document_count=0,
            )
        except (KeyError, TypeError, ValueError, ValidationError):
            raise malformed() from None
        # 网络完成后再串行化写入；较早开始的并发同步不得覆盖较新的已完成结果。
        lock = int.from_bytes(hashlib.sha256(repo_id.encode()).digest()[:8], signed=True)
        self.session.execute(select(func.pg_advisory_xact_lock(lock)))
        record = self.session.scalar(
            select(RepositoryRecord)
            .where(RepositoryRecord.id == repo_id)
            .execution_options(populate_existing=True)
        )
        if (
            record
            and record.sync_state
            and record.sync_state.get("fetched_at", "") > state["fetched_at"]
        ):
            self.session.commit()
            return self._contract(record)
        if record is None:
            record = RepositoryRecord(id=repo_id)
            self.session.add(record)
        elif record.data_source != "github":
            raise DomainError(409, "repository_conflict", "仓库标识已被其他来源使用")
        for field in (
            "data_source",
            "full_name",
            "description",
            "language",
            "default_branch",
            "default_commit",
        ):
            setattr(record, field, getattr(values, field))
        record.source_updated_at = values.updated_at
        record.updated_at = utc_now()
        record.sync_state = state
        self.session.commit()
        return self._contract(record)

    def list_pull_requests(self, repo_id: str) -> list[PullRequestSummary]:
        group = (self._record(repo_id).sync_state or {}).get("pull_request", {})
        return [PullRequestSummary.model_validate(item) for item in group.get("items", [])]

    def get_pull_request(self, repo_id: str, number: int) -> PullRequestDetail:
        record = self._record(repo_id)
        root = repo_path(record.full_name)
        fetched_at = utc_now()
        data = self.client.get(f"{root}/pulls/{number}")
        rows, limited = self.client.paginate(f"{root}/pulls/{number}/files", limit=300)
        notices = []
        issues = []
        try:
            references = [
                item
                for item in issue_references(data.get("body") or "", record.full_name)
                if item != number
            ]
            for reference in references[:5]:
                try:
                    issue = self.client.get(f"{root}/issues/{reference}")
                    if "pull_request" not in issue:
                        issues.append(
                            LinkedIssue(
                                number=issue["number"],
                                title=issue["title"],
                                body=issue.get("body") or "",
                                state=issue["state"],
                                html_url=f"https://github.com/{record.full_name}/issues/{reference}",
                            )
                        )
                except DomainError as error:
                    notices.append(
                        SourceNotice(
                            code=error.code,
                            message=f"Issue #{reference}：" + error.message,
                            retry_after=error.retry_after,
                        )
                    )
                    if error.status in {401, 429, 503, 504}:
                        break
            if len(references) > 5:
                notices.append(
                    SourceNotice(
                        code="issue_reference_limit", message="仅读取正文中前5个同仓库 Issue 引用"
                    )
                )
            files = [
                ChangedFile(
                    path=row["filename"],
                    additions=row["additions"],
                    deletions=row["deletions"],
                    patch=row.get("patch") or "",
                    status=row.get("status", "modified"),
                    previous_path=row.get("previous_filename"),
                    patch_available=isinstance(row.get("patch"), str),
                )
                for row in rows
            ]
            limited = limited or int(data.get("changed_files", len(files))) > len(files)
            return PullRequestDetail(
                **pull_summary(data, repo_id, fetched_at).model_dump(),
                files=files,
                files_limited=limited,
                linked_issues=issues,
                warnings=notices,
            )
        except (KeyError, TypeError, ValueError, ValidationError):
            raise malformed() from None

    def list_ci_runs(self, repo_id: str) -> list[CIRunSummary]:
        group = (self._record(repo_id).sync_state or {}).get("ci_run", {})
        return [CIRunSummary.model_validate(item) for item in group.get("items", [])]

    def get_ci_run(self, repo_id: str, run_id: int) -> CIRunDetail:
        record = self._record(repo_id)
        root = repo_path(record.full_name)
        fetched_at = utc_now()
        data = self.client.get(f"{root}/actions/runs/{run_id}")
        rows, limited = self.client.paginate(
            f"{root}/actions/runs/{run_id}/jobs", key="jobs", limit=200, params={"filter": "latest"}
        )
        try:
            jobs = [
                CIJob(
                    id=row["id"],
                    run_id=row["run_id"],
                    name=row["name"],
                    status=row["status"],
                    conclusion=row.get("conclusion"),
                    started_at=row.get("started_at"),
                    completed_at=row.get("completed_at"),
                    steps=[
                        CIStep.model_validate(
                            {
                                key: step.get(key)
                                for key in ("number", "name", "status", "conclusion")
                            }
                        )
                        for step in row.get("steps", [])
                    ],
                )
                for row in rows
            ]
            if any(job.run_id != run_id for job in jobs):
                raise ValueError("job scope mismatch")
            return CIRunDetail(
                **ci_summary(data, repo_id, record.full_name, fetched_at).model_dump(),
                jobs=jobs,
                jobs_limited=limited,
            )
        except (KeyError, TypeError, ValueError, ValidationError):
            raise malformed() from None

    def get_job_log(self, repo_id: str, run_id: int, job_id: int) -> JobLog:
        record = self._record(repo_id)
        content = self.client.job_log(record.full_name, run_id, job_id)
        return JobLog(
            repo_id=repo_id,
            run_id=run_id,
            job_id=job_id,
            fetched_at=utc_now(),
            content=content,
            content_sha256=hashlib.sha256(content.encode()).hexdigest(),
        )

    def list_documents(self, repo_id: str):
        self._record(repo_id)
        return []

    def get_document(self, repo_id: str, document_id: str):
        self._record(repo_id)
        raise DomainError(404, "not_found", "该 GitHub 仓库尚未导入项目资料")
