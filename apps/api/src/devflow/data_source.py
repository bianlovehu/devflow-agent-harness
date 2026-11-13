# 文件用途：定义仓库读取协议，并选择文件或数据库数据源。
from functools import lru_cache
from typing import Annotated, Protocol

from fastapi import Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from devflow.config import PROJECT_ROOT, Settings, get_settings
from devflow.contracts import (
    CIRunDetail,
    CIRunSummary,
    DataSource,
    DocumentDetail,
    DocumentSummary,
    FixtureDataset,
    PullRequestDetail,
    PullRequestSummary,
    Repository,
)
from devflow.database import get_session


class RepositoryDataSource(Protocol):
    """Future adapters implement these methods behind the same business API."""

    mode: DataSource

    def collection_metadata(self, repo_id: str, kind: str) -> dict: ...
    def list_repositories(self) -> list[Repository]: ...
    def get_repository(self, repo_id: str) -> Repository: ...
    def list_pull_requests(self, repo_id: str) -> list[PullRequestSummary]: ...
    def get_pull_request(self, repo_id: str, number: int) -> PullRequestDetail: ...
    def list_ci_runs(self, repo_id: str) -> list[CIRunSummary]: ...
    def get_ci_run(self, repo_id: str, run_id: int) -> CIRunDetail: ...
    def list_documents(self, repo_id: str) -> list[DocumentSummary]: ...
    def get_document(self, repo_id: str, document_id: str) -> DocumentDetail: ...


def not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "not_found", "message": "仓库或资源不存在"},
    )


def summary(model, target):
    return target.model_validate({name: getattr(model, name) for name in target.model_fields})


class FixtureDataSource:
    mode: DataSource = "fixture"

    def collection_metadata(self, repo_id: str, kind: str) -> dict:
        return {}

    def __init__(self, dataset: FixtureDataset):
        self.dataset = dataset

    def list_repositories(self) -> list[Repository]:
        return self.dataset.repositories

    def get_repository(self, repo_id: str) -> Repository:
        for repo in self.dataset.repositories:
            if repo.id == repo_id:
                return repo
        raise not_found()

    def list_pull_requests(self, repo_id: str) -> list[PullRequestSummary]:
        self.get_repository(repo_id)
        return [
            summary(pr, PullRequestSummary)
            for pr in self.dataset.pull_requests
            if pr.repo_id == repo_id
        ]

    def get_pull_request(self, repo_id: str, number: int) -> PullRequestDetail:
        self.get_repository(repo_id)
        for pr in self.dataset.pull_requests:
            if pr.repo_id == repo_id and pr.number == number:
                return pr
        raise not_found()

    def list_ci_runs(self, repo_id: str) -> list[CIRunSummary]:
        self.get_repository(repo_id)
        return [
            summary(run, CIRunSummary) for run in self.dataset.ci_runs if run.repo_id == repo_id
        ]

    def get_ci_run(self, repo_id: str, run_id: int) -> CIRunDetail:
        self.get_repository(repo_id)
        for run in self.dataset.ci_runs:
            if run.repo_id == repo_id and run.id == run_id:
                return run
        raise not_found()

    def list_documents(self, repo_id: str) -> list[DocumentSummary]:
        self.get_repository(repo_id)
        return [
            summary(doc, DocumentSummary)
            for doc in self.dataset.documents
            if doc.repo_id == repo_id
        ]

    def get_document(self, repo_id: str, document_id: str) -> DocumentDetail:
        self.get_repository(repo_id)
        for doc in self.dataset.documents:
            if doc.repo_id == repo_id and doc.id == document_id:
                return doc
        raise not_found()


@lru_cache
def fixture_source() -> FixtureDataSource:
    # 缓存校验后的文件样例，文件更新后需重启服务重新读取。
    dataset_path = PROJECT_ROOT / "fixtures" / "taskboard" / "dataset.json"
    return FixtureDataSource(FixtureDataset.model_validate_json(dataset_path.read_bytes()))


class CombinedRepositorySource:
    """本地单用户仓库目录；每个资源仍按登记来源和所属仓库读取。"""

    mode = "mixed"

    def __init__(self, session, settings):
        from devflow.github_source import GitHubRepositorySource
        from devflow.persistent_source import DatabaseRepositorySource

        self.session = session
        self.sources = {
            "fixture": DatabaseRepositorySource(session, "fixture"),
            "github": GitHubRepositorySource(session, settings),
        }

    def for_repository(self, repo_id):
        from devflow.models import RepositoryRecord

        record = self.session.get(RepositoryRecord, repo_id)
        if record is None or record.data_source not in self.sources:
            raise not_found()
        return self.sources[record.data_source]

    def list_repositories(self):
        return sorted(
            [repo for source in self.sources.values() for repo in source.list_repositories()],
            key=lambda repo: repo.full_name,
        )

    def get_repository(self, repo_id):
        return self.for_repository(repo_id).get_repository(repo_id)

    def collection_metadata(self, repo_id, kind):
        return self.for_repository(repo_id).collection_metadata(repo_id, kind)

    def list_pull_requests(self, repo_id):
        return self.for_repository(repo_id).list_pull_requests(repo_id)

    def get_pull_request(self, repo_id, number):
        return self.for_repository(repo_id).get_pull_request(repo_id, number)

    def list_ci_runs(self, repo_id):
        return self.for_repository(repo_id).list_ci_runs(repo_id)

    def get_ci_run(self, repo_id, run_id):
        return self.for_repository(repo_id).get_ci_run(repo_id, run_id)

    def list_documents(self, repo_id):
        return self.for_repository(repo_id).list_documents(repo_id)

    def get_document(self, repo_id, document_id):
        return self.for_repository(repo_id).get_document(repo_id, document_id)


def get_data_source(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
) -> RepositoryDataSource:
    # 文件样例模式维持只读；数据库目录同时包含样例和已登记的真实仓库。
    if settings.data_source == "github" or settings.fixture_storage == "database":
        return CombinedRepositorySource(session, settings)
    try:
        return fixture_source()
    except (OSError, ValidationError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "fixture_unavailable",
                "message": "样例数据未就绪，请运行 scripts/build_fixtures.py 并重启 API",
            },
        ) from exc
