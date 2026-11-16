# 文件用途：安全采集固定提交的普通文本，保留排除项和字节完整性。
import gzip
import hashlib
import re
import tarfile
from pathlib import PurePosixPath

from devflow.core.config import PROJECT_ROOT
from devflow.core.errors import DomainError
from devflow.repositories.fixed_files import MAX_FILE_BYTES, safe_path, supported
from devflow.repositories.github_client import repo_path


class ScanReader:
    """在 tar 解析前限制实际解压字节，包括 PAX/长路径头和被跳过内容。"""

    def __init__(self, source, guard):
        self.source, self.guard, self.scanned = source, guard, 0

    def read(self, size=-1):
        self.guard()
        maximum = 250 * 1024 * 1024
        raw = self.source.read(min(size if size >= 0 else maximum + 1, maximum - self.scanned + 1))
        self.scanned += len(raw)
        if self.scanned > maximum:
            raise DomainError(413, "code_archive_too_large", "归档解压字节超过 250 MiB")
        return raw


EXTRA_SUFFIXES = {
    ".go",
    ".java",
    ".kt",
    ".kts",
    ".rs",
    ".rb",
    ".php",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cs",
    ".sql",
    ".sh",
    ".ps1",
    ".vue",
    ".svelte",
    ".css",
    ".scss",
    ".html",
    ".gradle",
    ".swift",
    ".proto",
}
EXCLUDED = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "vendor",
    "dist",
    "build",
    ".next",
    "__pycache__",
    ".cache",
    ".tools",
}


def blob_hash(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def text_lines(raw):
    return (
        raw.decode("utf-8-sig")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .removesuffix("\n")
        .split("\n")
    )


def exclusion(path, mode, size):
    try:
        safe_path(path)
    except DomainError:
        return "invalid_path"
    if mode not in {"100644", "100755"}:
        return "symlink_or_submodule"
    parts = PurePosixPath(path).parts
    name = parts[-1].lower()
    if any(part in EXCLUDED for part in parts[:-1]):
        return "excluded_directory"
    if (
        name.endswith((".pem", ".key", ".p12", ".pfx"))
        or (name == ".env" or name.startswith(".env."))
        and not name.endswith((".example", ".sample", ".template"))
    ):
        return "sensitive_file"
    if size > MAX_FILE_BYTES:
        return "file_too_large"
    if not supported(path) and PurePosixPath(path).suffix.lower() not in EXTRA_SUFFIXES:
        return "unsupported_type"
    return None


def collect(repo, commit, client, settings, guard):
    """返回清单及内存中有界文本；发布事务之外不写业务行。"""
    if repo.data_source == "fixture":
        root = PROJECT_ROOT / "fixtures/taskboard/snapshots" / commit
        if repo.id != "repo-taskboard" or not root.is_dir():
            raise DomainError(404, "fixture_code_missing", "该样例提交没有本地代码快照")
        inventory = []
        raws = {}
        for path in sorted(root.rglob("*")):
            guard()
            if path.is_dir() and not path.is_symlink():
                continue
            relative = path.relative_to(root).as_posix()
            mode = "120000" if path.is_symlink() else "100644"
            size = path.lstat().st_size
            row = {"path": relative, "mode": mode, "size": size, "sha": None, "type": "blob"}
            inventory.append(row)
            if not exclusion(relative, mode, size):
                raw = path.read_bytes()
                row["sha"] = blob_hash(raw)
                raws[relative] = raw
        complete = True
    else:
        root = repo_path(repo.full_name)
        metadata = client.get(root + "/git/commits/" + commit)
        if metadata.get("sha") != commit:
            raise DomainError(409, "code_commit_mismatch", "GitHub 返回了不同提交")
        data = client.get(root + "/git/trees/" + metadata["tree"]["sha"], {"recursive": "1"})
        inventory = [row for row in data["tree"] if row.get("type") != "tree"]
        complete = not data.get("truncated", False)
        raws = None
    inventory.sort(key=lambda row: row["path"])
    complete = complete and len(inventory) <= settings.code_max_entries
    rows, wanted, budget, count = [], {}, 0, 0
    for item in inventory[: settings.code_max_entries]:
        guard()
        path, mode, size = item["path"], item.get("mode", ""), item.get("size", 0)
        if (
            repo.data_source == "github"
            and mode in {"100644", "100755"}
            and (
                not isinstance(size, int)
                or size < 0
                or not re.fullmatch(r"[0-9a-f]{40}", item.get("sha") or "")
            )
        ):
            raise DomainError(502, "code_tree_invalid", "Git tree 缺少有效文件大小或 blob SHA")
        reason = exclusion(path, mode, size)
        if not reason and (
            count >= settings.code_max_files or budget + size > settings.code_max_bytes
        ):
            reason = "snapshot_budget"
        row = {
            "path": path,
            "kind": "file" if mode in {"100644", "100755"} else "special",
            "blob_sha": item.get("sha"),
            "size_bytes": size,
            "skip_reason": reason,
        }
        rows.append(row)
        if not reason:
            count += 1
            budget += size
            wanted[path] = row
    contents = {}

    def accept(path, raw):
        guard()
        row = wanted[path]
        if len(raw) != row["size_bytes"] or row["blob_sha"] and blob_hash(raw) != row["blob_sha"]:
            raise DomainError(502, "code_integrity_error", "代码大小或 Git blob 哈希校验失败")
        try:
            text_lines(raw)
        except UnicodeError:
            row["skip_reason"] = "unsupported_encoding"
            return
        if b"\0" in raw:
            row["skip_reason"] = "binary_file"
            return
        contents[path] = raw

    if raws is not None:
        for path in wanted:
            accept(path, raws[path])
    else:
        try:
            with client.code_archive(repo.full_name, commit, guard) as archive:
                with (
                    gzip.GzipFile(fileobj=archive) as decoded,
                    tarfile.open(fileobj=ScanReader(decoded, guard), mode="r|") as tar,
                ):
                    expanded, members, seen = 0, 0, set()
                    prefix = None
                    for entry in tar:
                        guard()
                        expanded += entry.size
                        members += 1
                        if expanded > 250 * 1024 * 1024 or members > 100000:
                            raise DomainError(413, "code_archive_too_large", "归档扫描超过安全上限")
                        parts = entry.name.rstrip("/").split("/")
                        if (
                            not parts
                            or any(part in {"", ".", ".."} for part in parts)
                            or entry.name.startswith("/")
                            or "\\" in entry.name
                        ):
                            raise DomainError(422, "code_archive_unsafe", "归档包含不安全路径")
                        prefix = prefix or parts[0]
                        if parts[0] != prefix:
                            raise DomainError(422, "code_archive_unsafe", "归档根目录不一致")
                        if entry.isdir():
                            continue
                        path = "/".join(parts[1:])
                        if path not in wanted:
                            continue
                        if path in seen or not entry.isfile() or entry.size > MAX_FILE_BYTES:
                            raise DomainError(
                                422, "code_archive_unsafe", "归档文件类型或重复路径不合法"
                            )
                        seen.add(path)
                        source = tar.extractfile(entry)
                        if source is None:
                            raise DomainError(502, "code_archive_invalid", "无法读取归档成员")
                        accept(path, source.read(MAX_FILE_BYTES + 1))
        except (tarfile.TarError, EOFError, OSError) as error:
            raise DomainError(502, "code_archive_invalid", "归档损坏或下载失败") from error
    for path, row in wanted.items():
        if path not in contents and not row["skip_reason"]:
            row["skip_reason"] = "archive_omitted"
    reasons = {}
    for row in rows:
        if reason := row["skip_reason"]:
            reasons[reason] = reasons.get(reason, 0) + 1
    coverage = {
        "inventory_complete": complete,
        "eligible_complete": complete
        and not any(key in reasons for key in {"snapshot_budget", "archive_omitted"}),
        "entries": len(rows),
        "saved_files": len(contents),
        "saved_bytes": sum(map(len, contents.values())),
        "excluded": reasons,
        "omitted_count": 0 if complete else None,
        "source": repo.data_source,
    }
    return rows, contents, coverage
