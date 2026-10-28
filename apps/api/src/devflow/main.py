# 文件用途：组装 FastAPI 服务、业务路由及统一请求处理。
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from devflow import __version__
from devflow.config import get_settings
from devflow.database import create_database_engine
from devflow.errors import (
    DomainError,
    database_error_handler,
    domain_error_handler,
    error_response,
    http_error_handler,
    validation_error_handler,
)
from devflow.health import HealthResponse, inspect_health
from devflow.repositories import router as repositories_router
from devflow.workflow_api import router as workflows_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # 启动时创建连接池，服务退出时释放连接资源。
    app.state.engine = create_database_engine(get_settings())
    yield
    app.state.engine.dispose()


app = FastAPI(
    title="DevFlow API",
    description="PR 风险审查与 CI 排障；已提供工程骨架和人工构造的仓库样例。",
    version=__version__,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Idempotency-Key"],
)


@app.get("/api/v1/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    return {"status": "ok", "service": "devflow-api", "version": __version__}


@app.get(
    "/api/v1/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "Dependencies are not ready"}},
    tags=["health"],
)
def health(request: Request, response: Response) -> HealthResponse:
    result = inspect_health(request.app.state.engine)
    response.headers["Cache-Control"] = "no-store"
    if result.status != "ok":
        response.status_code = 503
    return result


app.include_router(repositories_router)

app.include_router(workflows_router)
app.add_exception_handler(DomainError, domain_error_handler)
app.add_exception_handler(StarletteHTTPException, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(SQLAlchemyError, database_error_handler)


@app.exception_handler(Exception)
async def internal_error_handler(request: Request, exc: Exception):
    return error_response(request, 500, "internal_error", "服务器处理失败，请使用 request_id 排查")


@app.middleware("http")
async def request_context(request: Request, call_next):
    # 统一分配请求 ID，并在写操作进入业务层之前检查浏览器来源。
    request.state.request_id = str(uuid.uuid4())
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        allowed = {
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            "http://127.0.0.1:8000",
            "http://localhost:8000",
        }
        if origin is not None and origin not in allowed:
            return error_response(request, 403, "origin_denied", "请求来源不被允许")
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    if request.url.path.startswith("/api/v1/"):
        response.headers["Cache-Control"] = "no-store"
    return response
