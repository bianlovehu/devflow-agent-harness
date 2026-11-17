# 文件用途：验证固定代码采集、归档完整性和不执行仓库内容。
import io
import tarfile
from types import SimpleNamespace

import pytest
from devflow.code.capture import blob_hash, collect, exclusion, text_lines
from devflow.core.config import Settings
from devflow.core.errors import DomainError


@pytest.mark.parametrize(
    "raw,expected",
    [
        (b"a\r\nb\r\n", ["a", "b"]),
        (b"a\nb", ["a", "b"]),
        (b"a\rb", ["a", "b"]),
        (b"\xef\xbb\xbfa\n", ["a"]),
        (b"", [""]),
    ],
)
def test_original_line_mapping(raw, expected):
    assert text_lines(raw) == expected


@pytest.mark.parametrize(
    "path,mode,size,reason",
    [
        ("../bad.py", "100644", 1, "invalid_path"),
        ("file.py", "120000", 1, "symlink_or_submodule"),
        ("node_modules/a.js", "100644", 1, "excluded_directory"),
        (".env", "100644", 1, "sensitive_file"),
        ("token.pem", "100644", 1, "sensitive_file"),
        ("x.py", "100644", 262145, "file_too_large"),
        ("x.png", "100644", 5, "unsupported_type"),
        (".github/workflows/ci.yml", "100644", 5, None),
        (".env.example", "100644", 5, None),
        ("CON.java", "100644", 5, None),
    ],
)
def test_policy(path, mode, size, reason):
    assert exclusion(path, mode, size) == reason


class ArchiveClient:
    def __init__(
        self, files, *, corrupt=False, unsafe=False, truncated=False, archive_newline=None
    ):
        self.files, self.corrupt, self.unsafe, self.truncated = files, corrupt, unsafe, truncated
        self.archive_newline = archive_newline

    def get(self, path, params=None):
        if "/git/commits/" in path:
            return {"sha": "a" * 40, "tree": {"sha": "b" * 40}}
        return {
            "truncated": self.truncated,
            "tree": [
                {
                    "path": path,
                    "type": "blob",
                    "mode": "100644",
                    "size": len(raw),
                    "sha": blob_hash(raw),
                }
                for path, raw in self.files.items()
            ],
        }

    def code_archive(self, name, commit, guard):
        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode="w:gz") as tar:
            for path, raw in self.files.items():
                info = tarfile.TarInfo("root/" + ("../bad.py" if self.unsafe else path))
                data = b"x" * len(raw) if self.corrupt else raw
                if self.archive_newline is not None:
                    data = data.replace(b"\r\n", b"\n").replace(b"\n", self.archive_newline)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        out.seek(0)
        return out


def test_archive_hash_and_partial_policy():
    client = ArchiveClient({"a.py": b"hello\n", "b.py": b"hello\n", "image.png": b"img"})
    settings = Settings(_env_file=None, code_max_files=1)
    rows, contents, coverage = collect(
        SimpleNamespace(data_source="github", full_name="a/b"),
        "a" * 40,
        client,
        settings,
        lambda: None,
    )
    assert set(contents) == {"a.py"}
    assert rows[1]["skip_reason"] == "snapshot_budget"
    assert not coverage["eligible_complete"] and coverage["inventory_complete"]


@pytest.mark.parametrize(
    "changes,code",
    [({"corrupt": True}, "code_integrity_error"), ({"unsafe": True}, "code_archive_unsafe")],
)
def test_unsafe_or_corrupt_archive_fails(changes, code):
    with pytest.raises(DomainError) as error:
        collect(
            SimpleNamespace(data_source="github", full_name="a/b"),
            "a" * 40,
            ArchiveClient({"a.py": b"code"}, **changes),
            Settings(_env_file=None),
            lambda: None,
        )
    assert error.value.code == code


def test_binary_and_encoding_recorded_without_body():
    rows, contents, coverage = collect(
        SimpleNamespace(data_source="github", full_name="a/b"),
        "a" * 40,
        ArchiveClient({"a.py": b"x\0x", "b.py": b"\xff"}),
        Settings(_env_file=None),
        lambda: None,
    )
    assert not contents
    assert {row["skip_reason"] for row in rows} == {"binary_file", "unsupported_encoding"}
    assert coverage["inventory_complete"]


@pytest.mark.parametrize(
    "destination,success",
    [
        ("https://codeload.github.com/a/b/tar.gz/" + "a" * 40, True),
        ("https://evil.example/archive", False),
    ],
)
def test_archive_redirect_auth_boundary(destination, success):
    from urllib.error import HTTPError

    from devflow.repositories.github_client import GitHubClient

    calls = []

    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            if len(calls) == 1:
                raise HTTPError(request.full_url, 302, "redirect", {"Location": destination}, None)
            assert request.get_header("Authorization") is None
            return io.BytesIO(b"archive-bytes")

    client = GitHubClient(
        Settings(_env_file=None, github_token="test-private-token"), opener=Opener()
    )
    if success:
        with client.code_archive("a/b", "a" * 40) as archive:
            assert archive.read() == b"archive-bytes"
        assert calls[0].get_header("Authorization") == "Bearer test-private-token"
    else:
        with pytest.raises(DomainError) as error:
            client.code_archive("a/b", "a" * 40)
        assert error.value.code == "github_archive_redirect"
        assert len(calls) == 1


@pytest.mark.parametrize(
    "original,archive_newline",
    [(b"one\ntwo\n", b"\r\n"), (b"one\r\ntwo\r\n", b"\n"), (b"\n" * 262144, b"\r\n")],
    ids=["lf-to-crlf", "crlf-to-lf", "size-limit"],
)
def test_archive_line_endings_recovered_only_with_exact_git_hash(original, archive_newline):
    client = ArchiveClient({"README.md": original}, archive_newline=archive_newline)
    rows, contents, coverage = collect(
        SimpleNamespace(data_source="github", full_name="a/b"),
        "a" * 40,
        client,
        Settings(_env_file=None),
        lambda: None,
    )
    assert contents["README.md"] == original
    assert rows[0]["blob_sha"] == blob_hash(original)
    assert coverage["newline_restored_files"] == 1 and coverage["eligible_complete"]


def test_archive_mixed_line_endings_not_guessed():
    client = ArchiveClient({"README.md": b"one\r\ntwo\n"}, archive_newline=b"\r\n")
    with pytest.raises(DomainError) as error:
        collect(
            SimpleNamespace(data_source="github", full_name="a/b"),
            "a" * 40,
            client,
            Settings(_env_file=None),
            lambda: None,
        )
    assert error.value.code == "code_integrity_error" and "README.md" in error.value.message
