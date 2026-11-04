# 文件用途：验证 GitHub 只读请求、输入范围、有限分页、错误分类及令牌隔离。
import io
import json
import time
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

import pytest
from devflow.config import Settings
from devflow.errors import DomainError
from devflow.github_client import MAX_RESPONSE_BYTES, GitHubClient, NoRedirect, parse_repository_url
from devflow.github_source import issue_references


class Response(io.BytesIO):
    def __init__(self, body, status=200, headers=None):
        super().__init__(body if isinstance(body, bytes) else json.dumps(body).encode())
        self.status = status
        self.headers = headers or {}


class Opener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def reset_rate_cooldowns():
    GitHubClient._cooldowns.clear()
    yield
    GitHubClient._cooldowns.clear()


def client(*responses):
    opener = Opener(*responses)
    sleeps = []
    clock = [time.monotonic()]

    def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay

    adapter = GitHubClient(
        Settings(_env_file=None, github_token="secret-test-token"),
        opener=opener,
        sleep=sleep,
        clock=lambda: clock[0],
    )
    return adapter, opener, sleeps


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/Owner/Project.git", "owner/project"),
        ("https://github.com/owner/project/", "owner/project"),
        ("owner/project", "owner/project"),
    ],
)
def test_repository_parser(url, expected):
    assert parse_repository_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",
        "https://example.com/a/b",
        "https://github.com.evil/a/b",
        "https://user:pass@github.com/a/b",
        "https://github.com/a/b?token=secret",
        "https://github.com/a/b#x",
        "https://github.com:444/a/b",
        "https://github.com:bad/a/b",
        "https://[broken",
        "https://github.com/a/../b",
        "a/..",
        "a/b/extra",
        "a/b%2fsecret",
        "a/b\\secret",
    ],
)
def test_invalid_repository_addresses_are_rejected(url):
    with pytest.raises(DomainError) as error:
        parse_repository_url(url)
    assert error.value.code == "github_invalid_repository"


def test_only_get_and_fixed_api_host_receive_token():
    adapter, opener, _ = client(Response({"id": 1}))
    assert adapter.get("/repos/owner/project") == {"id": 1}
    request, timeout = opener.requests[0]
    assert request.get_method() == "GET"
    assert request.host == "api.github.com"
    assert request.get_header("Authorization") == "Bearer secret-test-token"
    assert request.get_header("X-github-api-version") == "2026-03-10"
    assert timeout <= 30
    with pytest.raises(DomainError):
        adapter.get("https://evil.example/repos/owner/project")
    assert len(opener.requests) == 1


def test_pagination_stays_on_same_path_and_marks_partial_results():
    adapter, opener, _ = client(
        Response(
            [{"id": 1}, {"id": 2}], headers={"Link": '<https://evil.example/steal>; rel="next"'}
        ),
        Response([{"id": 3}, {"id": 4}]),
    )
    items, limited = adapter.paginate("/repos/owner/project/pulls", limit=3)
    assert [item["id"] for item in items] == [1, 2, 3]
    assert limited is True
    assert [
        parse_qs(urlsplit(request.full_url).query)["page"] for request, _ in opener.requests
    ] == [["1"], ["2"]]
    assert all(request.host == "api.github.com" for request, _ in opener.requests)


def test_empty_nonprogressing_pages_are_rejected():
    adapter, _, _ = client(
        Response([], headers={"Link": '<https://api.github.com/next>; rel="next"'})
    )
    with pytest.raises(DomainError) as error:
        adapter.paginate("/repos/owner/project/pulls")
    assert error.value.code == "github_invalid_response"


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "github_authentication_failed"),
        (403, "github_forbidden"),
        (404, "github_not_found"),
        (409, "github_repository_not_ready"),
        (410, "github_resource_gone"),
        (422, "github_invalid_request"),
    ],
)
def test_error_classification_does_not_echo_provider_secrets(status, code):
    adapter, opener, sleeps = client(Response({"message": "secret-test-token"}, status))
    with pytest.raises(DomainError) as error:
        adapter.get("/repos/owner/project")
    assert error.value.code == code
    assert "secret-test-token" not in error.value.message
    assert len(opener.requests) == 1 and sleeps == []


def test_long_rate_limits_are_returned_without_early_retry():
    adapter, opener, sleeps = client(Response({}, 429, {"Retry-After": "60"}))
    with pytest.raises(DomainError) as error:
        adapter.get("/repos/owner/project")
    assert error.value.status == 429 and error.value.retry_after == 60
    assert len(opener.requests) == 1 and sleeps == []


def test_primary_rate_limit_honors_reset_time():
    adapter, opener, sleeps = client(
        Response(
            {}, 403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(int(time.time()) + 30)}
        )
    )
    with pytest.raises(DomainError) as error:
        adapter.get("/repos/owner/project")
    assert error.value.code == "github_rate_limited" and error.value.retry_after >= 30
    assert len(opener.requests) == 1 and sleeps == []


def test_short_rate_limit_waits_then_retries():
    adapter, _, sleeps = client(Response({}, 429, {"Retry-After": "1"}), Response({"id": 1}))
    assert adapter.get("/repos/owner/project") == {"id": 1}
    assert sleeps == [1]


def test_network_retries_are_bounded():
    adapter, opener, sleeps = client(URLError("failed"), URLError("failed"), URLError("failed"))
    with pytest.raises(DomainError) as error:
        adapter.get("/repos/owner/project")
    assert error.value.code == "github_network_error"
    assert len(opener.requests) == 3 and sleeps == [0.5, 1.0]


def test_total_read_budget_stops_before_network():
    adapter, opener, _ = client()
    adapter.deadline = time.monotonic() - 1
    with pytest.raises(DomainError) as error:
        adapter.get("/repos/owner/project")
    assert error.value.code == "github_timeout"
    assert opener.requests == []


def test_oversized_or_wrong_shape_responses_are_explicit():
    adapter, _, _ = client(Response(b"x" * (MAX_RESPONSE_BYTES + 1)))
    with pytest.raises(DomainError) as error:
        adapter.get("/repos/owner/project")
    assert error.value.code == "github_response_too_large"
    adapter, _, _ = client(Response([]))
    with pytest.raises(DomainError) as error:
        adapter.get("/repos/owner/project")
    assert error.value.code == "github_invalid_response"


def test_log_redirects_never_forward_token():
    adapter, opener, _ = client(
        Response({"run_id": 10, "status": "completed"}),
        Response(
            b"",
            302,
            {"Location": "https://productionresultssa0.blob.core.windows.net/log?sig=private"},
        ),
        Response(b"line 1\nline 2"),
    )
    assert adapter.job_log("owner/project", 10, 20) == "line 1\nline 2"
    assert [request.get_method() for request, _ in opener.requests] == ["GET"] * 3
    assert opener.requests[1][0].get_header("Authorization")
    assert opener.requests[2][0].get_header("Authorization") is None


def test_log_job_scope_is_verified_before_downloading():
    adapter, opener, _ = client(Response({"run_id": 999, "status": "completed"}))
    with pytest.raises(DomainError) as error:
        adapter.job_log("owner/project", 10, 20)
    assert error.value.code == "github_job_not_found" and len(opener.requests) == 1


@pytest.mark.parametrize(
    "status,code",
    [
        (404, "github_logs_unavailable"),
        (410, "github_logs_unavailable"),
        (202, "github_logs_not_ready"),
    ],
)
def test_missing_or_pending_logs_are_not_reported_as_empty(status, code):
    adapter, _, _ = client(Response({"run_id": 10, "status": "completed"}), Response({}, status))
    with pytest.raises(DomainError) as error:
        adapter.job_log("owner/project", 10, 20)
    assert error.value.code == code


def test_untrusted_log_host_and_api_redirect_are_rejected():
    adapter, opener, _ = client(
        Response({"run_id": 10, "status": "completed"}),
        Response(b"", 302, {"Location": "http://127.0.0.1/private"}),
    )
    with pytest.raises(DomainError) as error:
        adapter.job_log("owner/project", 10, 20)
    assert error.value.code == "github_unsafe_redirect" and len(opener.requests) == 2
    adapter, _, _ = client(Response(b"", 301, {"Location": "https://evil.example/steal"}))
    with pytest.raises(DomainError) as error:
        adapter.get("/repos/owner/project")
    assert error.value.code == "github_unsafe_redirect"
    assert NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example") is None


def test_issue_references_are_local_and_deduplicated():
    assert issue_references(
        "Fix #12, owner/project#12, other/project#99, "
        "https://github.com/owner/project/issues/13 and #0",
        "owner/project",
    ) == [12, 13]


def test_anonymous_401_requests_token_instead_of_claiming_token_is_invalid():
    adapter, _, _ = client(Response({}, 401))
    adapter.token = ""
    with pytest.raises(DomainError) as error:
        adapter.get("/repos/owner/project")
    assert error.value.code == "github_authentication_required"


def test_rate_cooldown_applies_to_new_clients_without_another_network_request():
    first, opener, _ = client(Response({}, 429, {"Retry-After": "60"}))
    with pytest.raises(DomainError):
        first.get("/repos/owner/project")
    second, next_opener, _ = client()
    with pytest.raises(DomainError) as error:
        second.get("/repos/another/repo")
    assert error.value.code == "github_rate_limited" and error.value.retry_after >= 59
    assert len(opener.requests) == 1 and next_opener.requests == []
