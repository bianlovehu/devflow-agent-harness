# 文件用途：提供运行配置和仓库资源的只读 HTTP 接口。
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from devflow.config import Settings, get_settings
from devflow.contracts import (
    CIRunDetail,
    CIRunSummary,
    Collection,
    DocumentDetail,
    DocumentSummary,
    JobLog,
    PullRequestDetail,
    PullRequestSummary,
    Repository,
    RepositoryCreate,
    RuntimeInfo,
)
from devflow.data_source import CombinedRepositorySource, RepositoryDataSource, get_data_source
from devflow.database import get_session
from devflow.errors import DomainError
from devflow.github_source import GitHubRepositorySource

router = APIRouter(prefix="/api/v1", tags=["repositories"])
Source = Annotated[RepositoryDataSource, Depends(get_data_source)]


@router.get("/runtime", response_model=RuntimeInfo)
def runtime(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, object]:
    # Reading configuration never contacts the model or exposes the key.
    return {
        "data_source": settings.data_source,
        "fixture_storage": settings.fixture_storage,
        "task_execution_available": settings.data_source == "github"
        or settings.fixture_storage == "database",
        "repository_adapter_available": True,
        "github_configured": bool(settings.github_token.get_secret_value().strip()),
        "model": {
            "provider": settings.model_provider,
            "name": settings.dashscope_model
            if settings.model_provider == "aliyun"
            else "fixture-demo-v1"
            if settings.model_provider == "fake"
            else settings.deepseek_model,
            "configured": settings.model_provider == "fake"
            or bool(
                (
                    settings.dashscope_api_key
                    if settings.model_provider == "aliyun"
                    else settings.deepseek_api_key
                )
                .get_secret_value()
                .strip()
            ),
        },
    }


@router.get("/repositories", response_model=Collection[Repository])
def repositories(source: Source, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return Collection[Repository](data_source=source.mode, items=source.list_repositories())


@router.get("/repositories/{repo_id}", response_model=Repository)
def repository(repo_id: str, source: Source):
    return source.get_repository(repo_id)


@router.get("/repositories/{repo_id}/pull-requests", response_model=Collection[PullRequestSummary])
def pull_requests(repo_id: str, source: Source):
    return Collection[PullRequestSummary](
        data_source=source.get_repository(repo_id).data_source,
        items=source.list_pull_requests(repo_id),
        **source.collection_metadata(repo_id, "pull_request"),
    )


@router.get("/repositories/{repo_id}/pull-requests/{number}", response_model=PullRequestDetail)
def pull_request(repo_id: str, number: int, source: Source):
    return source.get_pull_request(repo_id, number)


@router.get("/repositories/{repo_id}/ci-runs", response_model=Collection[CIRunSummary])
def ci_runs(repo_id: str, source: Source):
    return Collection[CIRunSummary](
        data_source=source.get_repository(repo_id).data_source,
        items=source.list_ci_runs(repo_id),
        **source.collection_metadata(repo_id, "ci_run"),
    )


@router.get("/repositories/{repo_id}/ci-runs/{run_id}", response_model=CIRunDetail)
def ci_run(repo_id: str, run_id: int, source: Source):
    return source.get_ci_run(repo_id, run_id)


@router.get("/repositories/{repo_id}/documents", response_model=Collection[DocumentSummary])
def documents(repo_id: str, source: Source):
    return Collection[DocumentSummary](
        data_source=source.get_repository(repo_id).data_source, items=source.list_documents(repo_id)
    )


@router.get("/repositories/{repo_id}/documents/{document_id}", response_model=DocumentDetail)
def document(repo_id: str, document_id: str, source: Source):
    return source.get_document(repo_id, document_id)


@router.post("/repositories", response_model=Repository, status_code=201)
def add_repository(
    data: RepositoryCreate,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    if settings.data_source != "github" and settings.fixture_storage != "database":
        raise DomainError(409, "github_mode_required", "添加真实仓库需要 GitHub 数据模式")
    # 此 POST 仅登记本地仓库；适配器对 GitHub 的所有请求仍为 GET。
    return GitHubRepositorySource(session, settings).add_repository(data.url)


@router.post("/repositories/{repo_id}/refresh", response_model=Repository)
def refresh_repository(repo_id: str, source: Source):
    if isinstance(source, CombinedRepositorySource):
        source = source.for_repository(repo_id)
    if not isinstance(source, GitHubRepositorySource):
        raise DomainError(409, "github_mode_required", "样例数据不需要从 GitHub 刷新")
    return source.refresh(repo_id)


@router.get("/repositories/{repo_id}/ci-runs/{run_id}/jobs/{job_id}/logs", response_model=JobLog)
def job_logs(repo_id: str, run_id: int, job_id: int, source: Source):
    if isinstance(source, CombinedRepositorySource):
        source = source.for_repository(repo_id)
    if not isinstance(source, GitHubRepositorySource):
        raise DomainError(404, "not_found", "样例 CI 的日志在运行详情中读取")
    return source.get_job_log(repo_id, run_id, job_id)
