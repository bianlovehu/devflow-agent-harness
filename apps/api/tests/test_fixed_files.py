# 文件用途：验证固定 SHA 的文件读取、截断 diff 判断和原始日志字节存储边界。
import base64
import hashlib

import pytest
from devflow.artifact_store import ArtifactStore
from devflow.errors import DomainError
from devflow.evidence_capture import capture_github, patch_complete
from devflow.fixed_files import FixedFileReader, safe_path
from github_samples import JOB, PR, RUN, FakeGitHub


class EvidenceGitHub(FakeGitHub):
    def __init__(self):
        super().__init__()
        self.head = "b" * 40
        self.move_after_files = False
        self.raw_log = b"2026-10-29T00:00:00Z first\nsecond\r\nlast\n"
        self.blob_data = b"print('fixed evidence')\n"
        self.blob_sha = hashlib.sha1(
            b"blob " + str(len(self.blob_data)).encode() + b"\0" + self.blob_data
        ).hexdigest()
        self.mode = "100644"
        self.truncated = False

    def get(self, path, params=None):
        if "/git/trees/" in path:
            self.calls.append(path)
            return {
                "truncated": self.truncated,
                "tree": [
                    {
                        "path": "first.py",
                        "mode": self.mode,
                        "type": "blob",
                        "sha": self.blob_sha,
                        "size": len(self.blob_data),
                    }
                ],
            }
        if "/git/blobs/" in path:
            self.calls.append(path)
            return {"encoding": "base64", "content": base64.b64encode(self.blob_data).decode()}
        if path.endswith("/attempts/2"):
            return {**RUN, "status": "completed", "conclusion": "failure"}
        data = super().get(path, params)
        if path.endswith("/pulls/7"):
            data["head"]["sha"] = self.head
        return data

    def paginate(self, path, **kwargs):
        if path.endswith("/attempts/2/jobs"):
            self.calls.append(path)
            return [{**JOB, "status": "completed", "conclusion": "failure"}], False
        items, limited = super().paginate(path, **kwargs)
        if path.endswith("/pulls"):
            for item in items:
                item["head"]["sha"] = self.head
        if path.endswith("/files"):
            items = items[:1]
            items[0].pop("patch", None)
            if self.move_after_files:
                self.head = "c" * 40
        return items, limited

    def raw_job_log(self, full_name, run_id, job_id):
        assert (full_name, run_id, job_id) == ("owner/project", 10, 20)
        return self.raw_log


@pytest.mark.parametrize(
    "path", ["../x.py", "/x.py", "a/./x.py", "a//x.py", "a\\x.py", "a\nx.py", ""]
)
def test_unsafe_paths(path):
    with pytest.raises(DomainError, match="文件路径"):
        safe_path(path)


def test_fixed_reader_verifies_blob_and_does_not_follow_links():
    client = EvidenceGitHub()
    reader = FixedFileReader(client, "owner/project")
    assert reader.read("b" * 40, "first.py") == client.blob_data
    assert all("/git/" in path for path in client.calls)
    client.mode = "120000"
    with pytest.raises(DomainError, match="普通文件"):
        FixedFileReader(client, "owner/project").read("b" * 40, "first.py")
    client.mode = "160000"
    with pytest.raises(DomainError):
        FixedFileReader(client, "owner/project").read("b" * 40, "first.py")
    client.mode = "100644"
    client.truncated = True
    with pytest.raises(DomainError, match="截断"):
        FixedFileReader(client, "owner/project").read("b" * 40, "first.py")


def test_fixed_reader_rejects_blob_hash_mismatch_and_branch_names():
    client = EvidenceGitHub()
    client.blob_sha = "c" * 40
    with pytest.raises(DomainError, match="哈希"):
        FixedFileReader(client, "owner/project").read("b" * 40, "first.py")
    with pytest.raises(DomainError, match="完整提交"):
        FixedFileReader(client, "owner/project").read("main", "first.py")


@pytest.mark.parametrize(
    ("patch", "add", "delete", "complete"),
    [
        (None, 1, 1, False),
        ("@@ -1 +1 @@\n-old\n+new", 1, 1, True),
        ("@@ -1,3 +1,3 @@\n same\n-old\n+new", 1, 1, False),
        ("@@ -1 +1 @@\n-old", 1, 1, False),
        ("", 1, 0, False),
        ("@@ -0,0 +1 @@\n+new", 1, 0, True),
    ],
)
def test_diff_completeness(patch, add, delete, complete):
    assert patch_complete(patch, add, delete) is complete


def test_capture_supplements_missing_patch_and_detects_moving_pr():
    resource = {
        "kind": "pull_request",
        "external_id": "7",
        "base_sha": PR["base"]["sha"],
        "head_sha": PR["head"]["sha"],
    }
    client = EvidenceGitHub()
    captured = capture_github("owner/project", resource, client)
    assert captured.payload["coverage"][0]["patch_complete"] is False
    assert captured.payload["coverage"][0]["supplemented"] is True
    assert {row[2] for row in captured.sources if row[0] == "file"} == {"a" * 40, "b" * 40}
    client.move_after_files = True
    with pytest.raises(DomainError, match="版本已变化"):
        capture_github("owner/project", resource, client)


def test_ci_capture_uses_fixed_attempt_and_original_log_bytes(tmp_path):
    client = EvidenceGitHub()
    captured = capture_github(
        "owner/project",
        {"kind": "ci_run", "external_id": "10", "head_sha": "b" * 40, "run_attempt": 2},
        client,
    )
    source = next(row for row in captured.sources if row[0] == "log")
    assert source[1] == "actions/10/attempt-2/job-20.log"
    assert source[3] == client.raw_log
    store = ArtifactStore(tmp_path)
    key, digest, size = store.put_bytes(source[3])
    assert (tmp_path / key).read_bytes() == client.raw_log
    assert digest == hashlib.sha256(client.raw_log).hexdigest()
    assert size == len(client.raw_log)
    assert "/repos/owner/project/actions/runs/10/attempts/2/jobs" in client.calls


@pytest.mark.parametrize("status", ["added", "removed", "renamed"])
def test_capture_add_remove_and_rename_use_correct_sides(status):
    client = EvidenceGitHub()
    original_paginate = client.paginate
    original_get = client.get

    def paginate(path, **kwargs):
        if path.endswith("/files"):
            return [
                {
                    "filename": "first.py",
                    "previous_filename": "before.py",
                    "status": status,
                    "additions": 1,
                    "deletions": 0,
                }
            ], False
        return original_paginate(path, **kwargs)

    def get(path, params=None):
        result = original_get(path, params)
        if "/git/trees/" in path:
            result["tree"].append({**result["tree"][0], "path": "before.py"})
        return result

    client.paginate, client.get = paginate, get
    captured = capture_github(
        "owner/project",
        {"kind": "pull_request", "external_id": "7", "base_sha": "a" * 40, "head_sha": "b" * 40},
        client,
    )
    files = [(row[1], row[2]) for row in captured.sources if row[0] == "file"]
    if status == "added":
        assert files == [("first.py", "b" * 40)]
        assert captured.payload["coverage"][0]["base_absent"] is True
    elif status == "removed":
        assert files == [("before.py", "a" * 40)]
        assert captured.payload["coverage"][0]["head_absent"] is True
    else:
        assert files == [("before.py", "a" * 40), ("first.py", "b" * 40)]


def test_metadata_is_included_in_total_evidence_budget(monkeypatch):
    monkeypatch.setattr("devflow.evidence_capture.MAX_CAPTURE_BYTES", 1)
    with pytest.raises(DomainError) as error:
        capture_github(
            "owner/project",
            {"kind": "ci_run", "external_id": "10", "head_sha": "b" * 40, "run_attempt": 2},
            EvidenceGitHub(),
        )
    assert error.value.code == "evidence_budget_exceeded"
