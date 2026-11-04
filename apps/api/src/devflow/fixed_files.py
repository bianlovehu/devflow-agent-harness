# 文件用途：只读指定提交的普通文本 blob，校验路径、文件类型、大小和 Git 内容哈希。
import base64
import binascii
import hashlib
import re
from pathlib import PurePosixPath

from devflow.errors import DomainError
from devflow.github_client import GitHubClient, ref_path, repo_path

MAX_FILE_BYTES = 256 * 1024
SUFFIXES = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".md",
    ".mdx",
    ".txt",
    ".xml",
    ".properties",
    ".lock",
    ".env",
    ".example",
}


def safe_path(path: str) -> str:
    if (
        not path
        or len(path) > 480
        or path.startswith("/")
        or "\\" in path
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in path)
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        raise DomainError(422, "invalid_file_path", "文件路径不合法")
    return path


def supported(path: str) -> bool:
    safe_path(path)
    return PurePosixPath(path).suffix.lower() in SUFFIXES or PurePosixPath(path).name in {
        "Dockerfile",
        "Makefile",
        ".gitignore",
        ".gitattributes",
        ".editorconfig",
        ".env",
    }


class FixedFileReader:
    def __init__(self, client: GitHubClient, full_name: str):
        self.client = client
        self.root = repo_path(full_name)
        self.trees = {}
        self.blobs = {}

    def read(self, sha: str, path: str) -> bytes:
        safe_path(path)
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise DomainError(422, "invalid_commit", "读取文件必须指定完整提交 SHA")
        if not supported(path):
            raise DomainError(422, "unsupported_file", "文件类型不在首批文本支持范围内")
        tree = sha
        parts = path.split("/")
        # 按目录逐级读取非递归 tree，拒绝符号链接、子模块和截断目录。
        for index, name in enumerate(parts):
            if tree not in self.trees:
                self.trees[tree] = self.client.get(f"{self.root}/git/trees/{ref_path(tree)}")
            data = self.trees[tree]
            if data.get("truncated"):
                raise DomainError(409, "tree_incomplete", "GitHub 目录被截断，不能声称文件完整")
            entry = next((row for row in data.get("tree", []) if row.get("path") == name), None)
            if not entry:
                raise DomainError(404, "file_not_found", "指定提交中没有此文件")
            last = index == len(parts) - 1
            if not last:
                if entry.get("type") != "tree" or entry.get("mode") != "040000":
                    raise DomainError(422, "unsupported_file", "不跟随符号链接或子模块")
                tree = entry["sha"]
                continue
            if entry.get("mode") not in {"100644", "100755"} or entry.get("type") != "blob":
                raise DomainError(422, "unsupported_file", "只读取普通文件，不跟随符号链接或子模块")
            if not isinstance(entry.get("size"), int) or entry["size"] > MAX_FILE_BYTES:
                raise DomainError(413, "file_too_large", "文件超过 256 KiB 读取上限")
            blob_sha = entry["sha"]
            if blob_sha not in self.blobs:
                blob = self.client.get(f"{self.root}/git/blobs/{ref_path(blob_sha)}")
                try:
                    if blob.get("encoding") != "base64":
                        raise ValueError()
                    raw = base64.b64decode("".join(blob["content"].split()), validate=True)
                    raw.decode("utf-8-sig")
                except (KeyError, ValueError, UnicodeError, binascii.Error):
                    raise DomainError(
                        422, "unsupported_encoding", "只支持有效 UTF-8 文本"
                    ) from None
                if b"\x00" in raw:
                    raise DomainError(422, "binary_file", "不把二进制文件作为文本证据")
                digest = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
                if len(raw) > MAX_FILE_BYTES or len(raw) != entry["size"] or digest != blob_sha:
                    raise DomainError(
                        502, "blob_integrity_error", "Git blob 大小或内容哈希校验失败"
                    )
                self.blobs[blob_sha] = raw
            return self.blobs[blob_sha]
        raise AssertionError("unreachable")
