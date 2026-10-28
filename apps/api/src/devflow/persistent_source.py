# 文件用途：通过数据库读取仓库与当前有效的资源快照。
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from devflow.contracts import (
    CIRunDetail,
    CIRunSummary,
    DataSource,
    DocumentDetail,
    DocumentSummary,
    PullRequestDetail,
    PullRequestSummary,
    Repository,
)
from devflow.data_source import not_found, summary
from devflow.models import RepositoryRecord, ResourceSnapshot


class DatabaseRepositorySource:
    def __init__(self, session: Session, mode: DataSource):
        self.session = session
        self.mode = mode

    def _record(self, repo_id: str) -> RepositoryRecord:
        record = self.session.get(RepositoryRecord, repo_id)
        if record is None or record.data_source != self.mode:
            raise not_found()
        return record

    def _contract(self, record: RepositoryRecord) -> Repository:
        counts = dict(
            self.session.execute(
                select(ResourceSnapshot.kind, func.count())
                .where(ResourceSnapshot.repo_id == record.id, ResourceSnapshot.is_current.is_(True))
                .group_by(ResourceSnapshot.kind)
            ).all()
        )
        return Repository(
            id=record.id,
            data_source=record.data_source,
            full_name=record.full_name,
            description=record.description,
            language=record.language,
            default_branch=record.default_branch,
            default_commit=record.default_commit,
            updated_at=record.source_updated_at,
            pull_request_count=counts.get("pull_request", 0),
            ci_run_count=counts.get("ci_run", 0),
            document_count=counts.get("document", 0),
        )

    def list_repositories(self) -> list[Repository]:
        records = self.session.scalars(
            select(RepositoryRecord)
            .where(RepositoryRecord.data_source == self.mode)
            .order_by(RepositoryRecord.full_name)
        ).all()
        return [self._contract(record) for record in records]

    def get_repository(self, repo_id: str) -> Repository:
        return self._contract(self._record(repo_id))

    def _list(self, repo_id: str, kind: str):
        self._record(repo_id)
        return self.session.scalars(
            select(ResourceSnapshot)
            .where(
                ResourceSnapshot.repo_id == repo_id,
                ResourceSnapshot.kind == kind,
                ResourceSnapshot.is_current.is_(True),
            )
            .order_by(ResourceSnapshot.external_id)
        ).all()

    def _get(self, repo_id: str, kind: str, external_id: str):
        self._record(repo_id)
        record = self.session.scalar(
            select(ResourceSnapshot).where(
                ResourceSnapshot.repo_id == repo_id,
                ResourceSnapshot.kind == kind,
                ResourceSnapshot.external_id == external_id,
                ResourceSnapshot.is_current.is_(True),
            )
        )
        if record is None:
            raise not_found()
        return record

    def list_pull_requests(self, repo_id: str) -> list[PullRequestSummary]:
        return [
            summary(PullRequestDetail.model_validate(item.payload), PullRequestSummary)
            for item in self._list(repo_id, "pull_request")
        ]

    def get_pull_request(self, repo_id: str, number: int) -> PullRequestDetail:
        return PullRequestDetail.model_validate(
            self._get(repo_id, "pull_request", str(number)).payload
        )

    def list_ci_runs(self, repo_id: str) -> list[CIRunSummary]:
        return [
            summary(CIRunDetail.model_validate(item.payload), CIRunSummary)
            for item in self._list(repo_id, "ci_run")
        ]

    def get_ci_run(self, repo_id: str, run_id: int) -> CIRunDetail:
        return CIRunDetail.model_validate(self._get(repo_id, "ci_run", str(run_id)).payload)

    def list_documents(self, repo_id: str) -> list[DocumentSummary]:
        return [
            summary(DocumentDetail.model_validate(item.payload), DocumentSummary)
            for item in self._list(repo_id, "document")
        ]

    def get_document(self, repo_id: str, document_id: str) -> DocumentDetail:
        return DocumentDetail.model_validate(self._get(repo_id, "document", document_id).payload)
