# 文件用途：统一业务错误响应，并避免暴露敏感输入和数据库详情。
import uuid

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError


class DomainError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


def error_response(request: Request, status: int, code: str, message: str, **extra):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        {"detail": {"code": code, "message": message, "request_id": request_id, **extra}},
        status_code=status,
        headers={"X-Request-ID": request_id, "Cache-Control": "no-store"},
    )


async def domain_error_handler(request: Request, exc: DomainError):
    return error_response(request, exc.status, exc.code, exc.message)


async def http_error_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict):
        return error_response(
            request,
            exc.status_code,
            detail.get("code", "request_failed"),
            detail.get("message", "请求失败"),
        )
    return error_response(request, exc.status_code, "request_failed", str(detail))


async def validation_error_handler(request: Request, exc: RequestValidationError):
    # 仅返回位置、类型与说明；不回显原始输入或可能含敏感数据的上下文。
    issues = [
        {"location": list(issue["loc"]), "type": issue["type"], "message": issue["msg"]}
        for issue in exc.errors()
    ]
    return error_response(request, 422, "validation_error", "请求参数不合法", issues=issues)


async def database_error_handler(request: Request, exc: SQLAlchemyError):
    return error_response(
        request, 503, "database_unavailable", "数据库未就绪，请检查连接及迁移状态"
    )
