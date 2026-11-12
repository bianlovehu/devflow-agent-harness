# 文件用途：对应用持久化目录打包与安全解包；恢复只允许空目标，不执行归档内代码。
import argparse
import sys
import tarfile
from pathlib import Path


def unpack(stream, destination):
    destination = Path(destination).resolve()
    if any(destination.iterdir()):
        raise ValueError("恢复要求应用数据卷为空")
    with tarfile.open(fileobj=stream, mode="r|gz") as archive:
        for member in archive:
            target = (destination / member.name).resolve()
            if (
                not target.is_relative_to(destination)
                or member.issym()
                or member.islnk()
                or not (member.isfile() or member.isdir())
            ):
                raise ValueError("归档包含非法路径或特殊文件")
            archive.extract(member, destination, filter="data")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["pack", "unpack", "empty"])
    args = parser.parse_args()
    root = Path("/app/data")
    if args.action == "empty":
        raise SystemExit(1 if any(root.iterdir()) else 0)
    if args.action == "unpack":
        unpack(sys.stdin.buffer, root)
    else:
        with tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz") as archive:
            for path in sorted(root.rglob("*")):
                if path.is_symlink():
                    raise ValueError("应用数据不允许符号链接")
                if path.is_file():
                    archive.add(path, arcname=str(path.relative_to(root)), recursive=False)


if __name__ == "__main__":
    main()
