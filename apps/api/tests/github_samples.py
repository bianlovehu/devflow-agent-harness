# 文件用途：提供可控的 GitHub API 响应，供只读适配器和数据库集成测试使用。
from copy import deepcopy

from devflow.errors import DomainError

STAMP = "2026-10-28T08:00:00Z"
PR = {
    "number": 7,
    "title": "Read-only example",
    "body": "Fix #9; other/repo#99",
    "user": {"login": "developer"},
    "state": "open",
    "base": {"sha": "a" * 40, "repo": {"full_name": "owner/project"}},
    "head": {"sha": "b" * 40},
    "updated_at": STAMP,
    "changed_files": 2,
}
RUN = {
    "id": 10,
    "name": "Checks",
    "status": "in_progress",
    "conclusion": None,
    "head_sha": "b" * 40,
    "created_at": STAMP,
    "pull_requests": [],
    "run_attempt": 2,
}
JOB = {
    "id": 20,
    "run_id": 10,
    "name": "Tests",
    "status": "in_progress",
    "conclusion": None,
    "steps": [{"number": 1, "name": "Install", "status": "completed", "conclusion": "success"}],
}


class FakeGitHub:
    def __init__(self):
        self.calls = []
        self.pr_error = None
        self.malformed = False

    def get(self, path, params=None):
        self.calls.append(path)
        root = "/repos/owner/project"
        values = {
            root: {
                "id": 123,
                "full_name": "owner/project",
                "description": None,
                "language": "Python",
                "default_branch": "main",
                "updated_at": STAMP,
            },
            root + "/commits/main": {"sha": "a" * 40},
            root + "/pulls/7": PR,
            root + "/issues/9": {
                "number": 9,
                "title": "Issue",
                "body": "A constraint",
                "state": "open",
            },
            root + "/actions/runs/10": RUN,
        }
        if path not in values:
            raise AssertionError("Unexpected or out-of-scope path: " + path)
        return deepcopy(values[path])

    def paginate(self, path, *, key=None, limit=300, params=None):
        self.calls.append(path)
        root = "/repos/owner/project"
        if path == root + "/pulls":
            assert limit == 20 and params["state"] == "all"
            if self.pr_error:
                raise self.pr_error
            return [deepcopy(PR)], True
        if path == root + "/actions/runs":
            assert limit == 20 and key == "workflow_runs"
            return [deepcopy(RUN)], True
        if path == root + "/pulls/7/files":
            return [
                {
                    "filename": "first.py",
                    "status": "modified",
                    "additions": 1,
                    "deletions": 1,
                    "patch": "@@ -1 +1 @@\n-old\n+new",
                },
                {"filename": "binary.png", "status": "added", "additions": 0, "deletions": 0},
            ], False
        if path == root + "/actions/runs/10/jobs":
            assert key == "jobs" and params["filter"] == "latest"
            return [deepcopy(JOB)], False
        raise AssertionError("Unexpected or out-of-scope path: " + path)

    def job_log(self, full_name, run_id, job_id):
        assert (full_name, run_id, job_id) == ("owner/project", 10, 20)
        raise DomainError(410, "github_logs_unavailable", "日志已过期或不可用")
