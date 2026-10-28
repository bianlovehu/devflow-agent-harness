# 文件用途：验证无密钥样例浏览、资源隔离及案例证据一致性。
import hashlib
import json
from unittest.mock import patch

import pytest
from devflow.config import PROJECT_ROOT, Settings, get_settings
from devflow.data_source import fixture_source
from devflow.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    settings = Settings(
        _env_file=None, data_source="fixture", fixture_storage="files", deepseek_api_key=""
    )
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_fixture_browsing_needs_no_credentials_and_never_calls_model(client):
    with patch("devflow.model_probe.urlopen") as request:
        repositories = client.get("/api/v1/repositories")
        assert repositories.status_code == 200
        assert repositories.json()["data_source"] == "fixture"
        repo = repositories.json()["items"][0]
        assert repo["pull_request_count"] == 3
        assert repo["ci_run_count"] == 3
        assert repo["document_count"] == 4
        for resource, expected in [("pull-requests", 3), ("ci-runs", 3), ("documents", 4)]:
            response = client.get(f"/api/v1/repositories/{repo['id']}/{resource}")
            assert response.status_code == 200
            assert len(response.json()["items"]) == expected
            assert response.json()["data_source"] == "fixture"
        request.assert_not_called()


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/repositories/unknown",
        "/api/v1/repositories/unknown/pull-requests",
        "/api/v1/repositories/unknown/ci-runs/201",
        "/api/v1/repositories/repo-taskboard/pull-requests/999",
        "/api/v1/repositories/repo-taskboard/ci-runs/999",
        "/api/v1/repositories/repo-taskboard/documents/unknown",
    ],
)
def test_resources_are_scoped_to_known_repository(client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "not_found"


def test_summary_endpoints_exclude_large_content_and_evaluation_answers(client):
    for resource in ("pull-requests", "ci-runs", "documents"):
        response = client.get(f"/api/v1/repositories/repo-taskboard/{resource}")
        data = response.json()
        assert "expected_findings" not in response.text
        assert "must_not_conclude" not in response.text
        for item in data["items"]:
            assert not {"files", "log", "content"} & item.keys()


def test_details_expose_fixed_versions_and_content(client):
    pr = client.get("/api/v1/repositories/repo-taskboard/pull-requests/102").json()
    assert len(pr["head_sha"]) == 40
    assert "+    return list(tasks)" in pr["files"][0]["patch"]
    ci = client.get("/api/v1/repositories/repo-taskboard/ci-runs/201").json()
    assert "test_null_labels_are_empty" in ci["log"]
    assert ci["head_sha"] != pr["head_sha"]
    doc = client.get("/api/v1/repositories/repo-taskboard/documents/access-policy").json()
    assert "AUTH-01" in doc["content"]
    assert len(doc["version"]) == 64


def test_runtime_configuration_does_not_expose_secret(client):
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, deepseek_api_key="private-test-value"
    )
    response = client.get("/api/v1/runtime")
    assert response.status_code == 200
    assert response.json()["model"]["configured"] is True
    assert "private-test-value" not in response.text
    assert "api_key" not in response.text


def test_unimplemented_github_mode_never_silently_returns_fixture(client):
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, data_source="github")
    response = client.get("/api/v1/repositories")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "data_source_unavailable"


def test_fixture_snapshot_hashes_and_case_evidence_are_consistent():
    dataset = fixture_source().dataset
    repository_ids = {repo.id for repo in dataset.repositories}
    root = PROJECT_ROOT / "fixtures" / "taskboard"
    for pr in dataset.pull_requests:
        assert pr.repo_id in repository_ids
        for changed in pr.files:
            source = root / "snapshots" / pr.head_sha / changed.path
            assert source.read_text(encoding="utf-8") == changed.head_content
            assert (
                hashlib.sha256(changed.head_content.encode()).hexdigest() == changed.content_sha256
            )
    for run in dataset.ci_runs:
        pr = next(pr for pr in dataset.pull_requests if pr.number == run.pull_request_number)
        assert run.head_sha == pr.head_sha
        assert (root / "ci-logs" / f"{run.id}.txt").read_text(encoding="utf-8") == run.log
        assert hashlib.sha256(run.log.encode()).hexdigest() == run.log_sha256
    for doc in dataset.documents:
        assert hashlib.sha256(doc.content.encode()).hexdigest() == doc.version
        assert len(doc.content.splitlines()) == doc.line_count

    cases = json.loads(
        (PROJECT_ROOT / "evals" / "fixtures" / "expectations.json").read_text(encoding="utf-8")
    )["cases"]
    assert len(cases) == 6
    for case in cases:
        assert case["must_not_conclude"]
        for ref in case["evidence"]:
            if ref["type"] == "file":
                content = (root / "snapshots" / ref["version"] / ref["resource_id"]).read_text(
                    encoding="utf-8"
                )
            else:
                run = next(run for run in dataset.ci_runs if str(run.id) == ref["resource_id"])
                assert run.head_sha == ref["version"]
                assert run.log_sha256 == ref["content_sha256"]
                content = run.log
            excerpt = "\n".join(content.splitlines()[ref["start_line"] - 1 : ref["end_line"]])
            assert excerpt == ref["quote"]


def test_synthetic_pr_behaviors_match_the_annotations():
    # Execute only the tiny service module authored in fixtures in this project.
    # The application itself never executes repository code.
    source = fixture_source()
    base_sha = source.dataset.repositories[0].default_commit

    def load_service(commit):
        path = (
            PROJECT_ROOT / "fixtures" / "taskboard" / "snapshots" / commit / "taskboard/service.py"
        )
        namespace = {}
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)
        return namespace

    base = load_service(base_sha)
    tasks = [{"id": 1, "owner_id": "alice"}, {"id": 2, "owner_id": "bob"}]
    assert base["list_tasks"](tasks, "alice") == [tasks[0]]
    assert base["normalize_labels"]({"labels": None}) == []
    clean = load_service(source.get_pull_request("repo-taskboard", 101).head_sha)
    assert clean["task_title"]({"title": "  hello   world "}) == "hello world"
    assert clean["list_tasks"](tasks, "alice") == [tasks[0]]
    unsafe = load_service(source.get_pull_request("repo-taskboard", 102).head_sha)
    assert unsafe["list_tasks"](tasks, "alice") == tasks
    regression = load_service(source.get_pull_request("repo-taskboard", 103).head_sha)
    assert regression["normalize_labels"]({}) == []
    with pytest.raises(ValueError, match="labels must be a list or null"):
        regression["normalize_labels"]({"labels": None})
