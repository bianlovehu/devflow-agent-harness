# 文件用途：提供运行配置和仓库资源的只读 HTTP 接口。
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from devflow.config import Settings, get_settings
from devflow.contracts import (
    CIRunDetail,
    CIRunSummary,
    Collection,
    DocumentDetail,
    DocumentSummary,
    PullRequestDetail,
    PullRequestSummary,
    Repository,
)
from devflow.data_source import RepositoryDataSource, get_data_source

router = APIRouter(prefix="/api/v1", tags=["repositories"])
Source = Annotated[RepositoryDataSource, Depends(get_data_source)]


@router.get("/runtime")
def runtime(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, object]:
    # Reading configuration never contacts the model or exposes the key.
    return {
        "data_source": settings.data_source,
        "fixture_storage": settings.fixture_storage,
        "task_execution_available": False,
        "repository_adapter_available": settings.data_source == "fixture",
        "model": {
            "provider": "deepseek",
            "name": settings.deepseek_model,
            "configured": bool(settings.deepseek_api_key.get_secret_value().strip()),
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
        data_source=source.mode, items=source.list_pull_requests(repo_id)
    )


@router.get("/repositories/{repo_id}/pull-requests/{number}", response_model=PullRequestDetail)
def pull_request(repo_id: str, number: int, source: Source):
    return source.get_pull_request(repo_id, number)


@router.get("/repositories/{repo_id}/ci-runs", response_model=Collection[CIRunSummary])
def ci_runs(repo_id: str, source: Source):
    return Collection[CIRunSummary](data_source=source.mode, items=source.list_ci_runs(repo_id))


@router.get("/repositories/{repo_id}/ci-runs/{run_id}", response_model=CIRunDetail)
def ci_run(repo_id: str, run_id: int, source: Source):
    return source.get_ci_run(repo_id, run_id)


@router.get("/repositories/{repo_id}/documents", response_model=Collection[DocumentSummary])
def documents(repo_id: str, source: Source):
    return Collection[DocumentSummary](
        data_source=source.mode, items=source.list_documents(repo_id)
    )


@router.get("/repositories/{repo_id}/documents/{document_id}", response_model=DocumentDetail)
def document(repo_id: str, document_id: str, source: Source):
    return source.get_document(repo_id, document_id)
