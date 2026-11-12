# 文件用途：封装当前真实工作树为不可覆盖的候选源码包，保留暂存/未提交内容和逐文件哈希。
import argparse
import gzip
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def package(destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError(destination)
    names = sorted(
        set(
            git("ls-files", "--cached", "--others", "--exclude-standard", "-z").decode().split("\0")
        )
        - {""}
    )
    files = {}
    for name in names:
        path = ROOT / name
        if not path.is_file():
            continue
        if path.is_symlink() or name.startswith(("data/", ".cache/", ".tools/", ".venv/")):
            raise ValueError(f"候选源码不允许运行数据/符号链接: {name}")
        if path.name.startswith(".env") and path.name != ".env.example":
            raise ValueError(f"候选源码不允许凭据文件: {name}")
        files[name] = path.read_bytes()
    manifest = {
        "schema_version": 1,
        "git_commit": git("rev-parse", "HEAD").decode().strip(),
        "git_status": git("status", "--porcelain").decode(),
        "files": {n: hashlib.sha256(v).hexdigest() for n, v in files.items()},
    }
    manifest_raw = (
        json.dumps(manifest, ensure_ascii=False, indent=2).replace("\n", "\r\n") + "\r\n"
    ).encode()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as out, gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w") as archive:
            for name, raw in {**files, "RELEASE-MANIFEST.json": manifest_raw}.items():
                item = tarfile.TarInfo(name)
                item.size, item.mtime, item.mode = len(raw), 0, 0o644
                archive.addfile(item, io.BytesIO(raw))
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(destination.suffix + ".sha256").write_text(
        digest + "  " + destination.name + "\r\n", encoding="utf-8", newline=""
    )
    return {"archive": str(destination), "sha256": digest, "files": len(files)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
