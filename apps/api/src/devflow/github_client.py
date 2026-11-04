# 文件用途：封装 GitHub 只读 HTTP、有限分页、限流退避和无令牌日志下载。
import hashlib
import json
import math
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from threading import RLock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from devflow.config import Settings
from devflow.errors import DomainError

API_ROOT = "https://api.github.com"
API_VERSION = "2026-03-10"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


def parse_repository_url(value: str) -> str:
    value = value.strip()
    if "://" in value:
        try:
            url = urlsplit(value)
            valid = (
                url.scheme == "https" and url.hostname == "github.com" and url.port in (None, 443)
            )
        except ValueError:
            raise DomainError(422, "github_invalid_repository", "仓库地址格式不正确") from None
        if not valid or url.username or url.password or url.query or url.fragment:
            raise DomainError(
                422, "github_invalid_repository", "请使用 github.com 的 HTTPS 仓库地址"
            )
        value = url.path.removeprefix("/").removesuffix("/")
    value = value.removesuffix(".git")
    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}", value
    ) or value.split("/")[-1] in {".", ".."}:
        raise DomainError(
            422, "github_invalid_repository", "仓库地址格式应为 https://github.com/owner/repo"
        )
    return value.lower()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass
class Reply:
    status: int
    headers: dict[str, str]
    body: bytes


class GitHubClient:
    _cooldowns: dict[tuple[str, str], float] = {}
    _rate_lock = RLock()

    def __init__(self, settings: Settings, opener=None, sleep=time.sleep, clock=time.monotonic):
        self.token = settings.github_token.get_secret_value().strip()
        self.timeout = settings.github_timeout_seconds
        self.opener = opener or build_opener(NoRedirect())
        self.sleep = sleep
        self.clock = clock
        self.deadline = self.clock() + 60

    def _open(self, url: str, authenticated: bool) -> Reply:
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise DomainError(504, "github_timeout", "GitHub 读取达到总时长限制，请稍后重试")
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "DevFlow/0.1",
            "X-GitHub-Api-Version": API_VERSION,
        }
        # 令牌仅发给固定 API 主机；签名日志下载地址绝不携带 Authorization。
        if authenticated and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(url, headers=headers, method="GET")
        try:
            with self.opener.open(request, timeout=min(self.timeout, remaining)) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise DomainError(
                        502, "github_response_too_large", "GitHub 返回内容超过读取上限"
                    )
                return Reply(
                    response.status, {k.lower(): v for k, v in response.headers.items()}, body
                )
        except HTTPError as error:
            try:
                return Reply(
                    error.code, {k.lower(): v for k, v in error.headers.items()}, error.read(4096)
                )
            finally:
                error.close()

    def _rate_wait(self, reply: Reply) -> int:
        waits = []
        value = reply.headers.get("retry-after")
        if value:
            try:
                waits.append(int(value))
            except ValueError:
                try:
                    waits.append(int(parsedate_to_datetime(value).timestamp() - time.time()) + 1)
                except (ValueError, TypeError, OverflowError):
                    pass
        if reply.headers.get("x-ratelimit-remaining") == "0":
            try:
                waits.append(int(reply.headers["x-ratelimit-reset"]) - int(time.time()) + 1)
            except (KeyError, ValueError):
                pass
        return max(1, max(waits)) if waits else 60

    def _bucket(self, url: str, authenticated: bool) -> tuple[str, str]:
        # 只保留不可逆令牌摘要，不将令牌本身写入共享缓存。
        token = self.token if authenticated else ""
        return (urlsplit(url).hostname or "", hashlib.sha256(token.encode()).hexdigest())

    def _call(self, url: str, authenticated: bool = True, logs: bool = False) -> Reply:
        bucket = self._bucket(url, authenticated)
        for attempt in range(3):
            with self._rate_lock:
                remaining = self._cooldowns.get(bucket, 0) - self.clock()
                if remaining > 0:
                    delay = math.ceil(remaining)
                    raise DomainError(
                        429,
                        "github_rate_limited",
                        f"GitHub 请求处于冷却中，请等待 {delay} 秒",
                        delay,
                    )
                self._cooldowns.pop(bucket, None)
            try:
                reply = self._open(url, authenticated)
            except (URLError, TimeoutError, OSError):
                if attempt < 2:
                    self.sleep(0.5 * (2**attempt))
                    continue
                raise DomainError(
                    503, "github_network_error", "GitHub 网络连接失败，请稍后重试"
                ) from None
            if reply.status < 400 and reply.status != 202:
                return reply
            rate_limited = reply.status == 429 or (
                reply.status == 403
                and (
                    reply.headers.get("x-ratelimit-remaining") == "0"
                    or "retry-after" in reply.headers
                    or b"rate limit" in reply.body.lower()
                )
            )
            if rate_limited:
                delay = self._rate_wait(reply)
                with self._rate_lock:
                    self._cooldowns[bucket] = max(
                        self._cooldowns.get(bucket, 0), self.clock() + delay
                    )
                # 长等待交还给调用方；不在 HTTP 请求中阻塞几十分钟，也不提前重试。
                if attempt < 2 and delay <= 2:
                    self.sleep(delay)
                    continue
                raise DomainError(
                    429,
                    "github_rate_limited",
                    f"GitHub 请求已限流，请至少等待 {delay} 秒后重试",
                    delay,
                )
            if reply.status >= 500 and attempt < 2:
                self.sleep(0.5 * (2**attempt))
                continue
            if logs and reply.status in {404, 410}:
                raise DomainError(410, "github_logs_unavailable", "该 job 的日志已过期或不可用")
            if reply.status == 401 and not self.token:
                raise DomainError(
                    401,
                    "github_authentication_required",
                    "读取此资源需要配置具有相应只读权限的 GitHub Token",
                )
            errors = {
                202: (409, "github_logs_not_ready", "日志尚未准备完成，请稍后重试"),
                401: (401, "github_authentication_failed", "GitHub Token 无效或已过期"),
                403: (403, "github_forbidden", "GitHub 拒绝访问，请检查所选仓库和只读权限"),
                404: (404, "github_not_found", "GitHub 资源不存在或当前账号无权查看"),
                409: (409, "github_repository_not_ready", "仓库尚无可读取的提交或资源"),
                410: (410, "github_resource_gone", "GitHub 资源已不再可用"),
                422: (422, "github_invalid_request", "GitHub 不接受当前资源参数"),
            }
            status, code, message = errors.get(
                reply.status, (502, "github_upstream_error", "GitHub 暂时无法提供该资源")
            )
            raise DomainError(status, code, message)
        raise AssertionError("unreachable")

    def json_response(self, path: str, params: dict | None = None) -> tuple[Any, dict]:
        if not path.startswith("/repos/") or "?" in path or "#" in path:
            raise DomainError(422, "github_invalid_path", "GitHub 读取路径不被允许")
        url = API_ROOT + path + ("?" + urlencode(params) if params else "")
        reply = self._call(url)
        if reply.status in {301, 302, 307, 308}:
            location = reply.headers.get("location", "")
            parsed = urlsplit(location)
            if (
                parsed.scheme != "https"
                or parsed.netloc != "api.github.com"
                or not parsed.path.startswith(("/repos/", "/repositories/"))
            ):
                raise DomainError(502, "github_unsafe_redirect", "GitHub 返回了不允许的 API 重定向")
            reply = self._call(location)
        try:
            return json.loads(reply.body), reply.headers
        except (ValueError, UnicodeError):
            raise DomainError(
                502, "github_invalid_response", "GitHub 返回的数据格式不正确"
            ) from None

    def get(self, path: str, params: dict | None = None) -> Any:
        data = self.json_response(path, params)[0]
        if not isinstance(data, dict):
            raise DomainError(502, "github_invalid_response", "GitHub 资源数据格式不正确")
        return data

    def paginate(
        self, path: str, *, key: str | None = None, limit: int = 300, params: dict | None = None
    ) -> tuple[list[dict], bool]:
        items = []
        page = 1
        while True:
            data, headers = self.json_response(
                path, {**(params or {}), "per_page": min(100, limit), "page": page}
            )
            rows = data.get(key) if key and isinstance(data, dict) else data
            if not isinstance(rows, list) or any(not isinstance(item, dict) for item in rows):
                raise DomainError(502, "github_invalid_response", "GitHub 分页数据格式不正确")
            available = limit - len(items)
            items.extend(rows[:available])
            has_next = 'rel="next"' in headers.get("link", "")
            total = data.get("total_count") if isinstance(data, dict) else None
            more = (
                has_next or (isinstance(total, int) and total > len(items)) or len(rows) > available
            )
            if len(items) >= limit:
                return items, more
            if not has_next:
                return items, more
            if not rows:
                raise DomainError(502, "github_invalid_response", "GitHub 分页未取得进展")
            # 仅使用 next 的存在性；不跟随外部提供的链接或查询地址。
            page += 1

    def job_log(self, full_name: str, run_id: int, job_id: int) -> str:
        return self.raw_job_log(full_name, run_id, job_id).decode("utf-8", errors="replace")

    def raw_job_log(self, full_name: str, run_id: int, job_id: int) -> bytes:
        full_name = parse_repository_url(full_name)
        root = "/repos/" + full_name
        job = self.get(f"{root}/actions/jobs/{job_id}")
        if job.get("run_id") != run_id:
            raise DomainError(404, "github_job_not_found", "该 job 不属于所选 CI 运行")
        if job.get("status") != "completed":
            raise DomainError(409, "github_logs_not_ready", "job 尚未完成，请稍后读取日志")
        reply = self._call(API_ROOT + f"{root}/actions/jobs/{job_id}/logs", logs=True)
        for _ in range(2):
            if reply.status not in {301, 302, 303, 307, 308}:
                break
            location = reply.headers.get("location", "")
            parsed = urlsplit(location)
            host = parsed.hostname or ""
            trusted = host.endswith(
                (
                    ".actions.githubusercontent.com",
                    ".blob.core.windows.net",
                    ".githubusercontent.com",
                )
            )
            if parsed.scheme != "https" or parsed.netloc != host or not trusted:
                raise DomainError(
                    502, "github_unsafe_redirect", "日志下载地址不在允许的 GitHub 存储域名内"
                )
            reply = self._call(location, authenticated=False, logs=True)
        if reply.status != 200:
            raise DomainError(502, "github_invalid_response", "GitHub 未返回有效的日志内容")
        return reply.body


def repo_path(full_name: str) -> str:
    return "/repos/" + parse_repository_url(full_name)


def ref_path(value: str) -> str:
    return quote(value, safe="")


def utc_now() -> datetime:
    return datetime.now(UTC)
