# 文件用途：按内容哈希保存及校验不可变的本地文本制品。
import hashlib
import os
import re
import tempfile
from pathlib import Path

from devflow.config import PROJECT_ROOT
from devflow.errors import DomainError


class ArtifactStore:
    """Immutable local text artifacts. Hashes cover the actual CRLF UTF-8 bytes."""

    def __init__(self, root: Path | None = None):
        self.root = (root or PROJECT_ROOT / "data" / "artifacts").resolve()

    def put_text(self, content: str) -> tuple[str, str, int]:
        # 按实际写入的 CRLF 字节计算哈希，再通过临时文件原子替换目标。
        data = content.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n").encode()
        digest = hashlib.sha256(data).hexdigest()
        key = f"{digest[:2]}/{digest}.txt"
        destination = self._resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != data:
                raise DomainError(409, "artifact_corrupt", "制品内容与哈希不一致")
            return key, digest, len(data)
        descriptor, temporary = tempfile.mkstemp(prefix=".artifact-", dir=destination.parent)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            # 文件完整写入并刷新后，再一次性替换目标，避免读到半份内容。
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return key, digest, len(data)

    def read_text(self, key: str, digest: str) -> str:
        # 读取前同时校验路径和内容哈希，拒绝缺失或被修改的制品。
        path = self._resolve(key)
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise DomainError(409, "artifact_missing", "引用的制品文件缺失") from exc
        if hashlib.sha256(data).hexdigest() != digest:
            raise DomainError(409, "artifact_corrupt", "引用的制品校验失败")
        return data.decode("utf-8")

    def _resolve(self, key: str) -> Path:
        # 只接受内容哈希路径，解析后再次确认文件仍位于制品目录内。
        if not re.fullmatch(r"[0-9a-f]{2}/[0-9a-f]{64}\.txt", key):
            raise DomainError(409, "artifact_invalid", "制品路径不合法")
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise DomainError(409, "artifact_invalid", "制品路径超出存储范围")
        return path


def get_artifact_store() -> ArtifactStore:
    return ArtifactStore()
