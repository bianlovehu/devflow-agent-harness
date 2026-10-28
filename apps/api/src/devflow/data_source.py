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


def get_data_source(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
) -> RepositoryDataSource:
    # 按明确配置选择数据源，不在数据库故障时偷偷回退到文件样例。
    if settings.data_source == "github":
        raise HTTPException(
            status_code=503,
            detail={
                "code": "data_source_unavailable",
                "message": "GitHub 适配器将在第 5 步接入，请使用 DATA_SOURCE=fixture",
            },
        )
    if settings.fixture_storage == "database":
        from devflow.persistent_source import DatabaseRepositorySource

        return DatabaseRepositorySource(session, settings.data_source)
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
