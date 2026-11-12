# 文件用途：停止Compose写入者后备份数据库与应用制品，并只向空白新项目恢复。
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["backup", "restore"])
    parser.add_argument("--project", required=True)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--compose", default="compose.yaml")
    args = parser.parse_args()
    compose = ["docker", "compose", "-f", args.compose, "-p", args.project]
    directory = Path(args.directory).resolve()

    def run(*command, **kwargs):
        return subprocess.run([*compose, *command], check=True, **kwargs)

    if args.action == "backup":
        directory.mkdir(parents=True, exist_ok=False)
        # 阻止报告、知识版本、记忆和制品在两个备份之间发生不一致。
        run("stop", "api", "worker")
        try:
            with (directory / "database.dump").open("xb") as output:
                run(
                    "exec",
                    "-T",
                    "db",
                    "sh",
                    "-c",
                    'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc',
                    stdout=output,
                )
            with (directory / "artifacts.tar.gz").open("xb") as output:
                run(
                    "run",
                    "--rm",
                    "--no-deps",
                    "api",
                    "python",
                    "-m",
                    "devflow.data_archive",
                    "pack",
                    stdout=output,
                )
            files = {
                name: fingerprint(directory / name)
                for name in ["database.dump", "artifacts.tar.gz"]
            }
            images = json.loads(
                subprocess.check_output([*compose, "images", "--format", "json"], text=True)
            )
            (directory / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "source_project": args.project,
                        "files": files,
                        "images": images,
                        "compose_sha256": fingerprint(args.compose),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
                newline="\r\n",
            )
        finally:
            run("start", "api", "worker")
    else:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if manifest["source_project"] == args.project:
            raise ValueError("恢复必须指定不同的新项目，不能覆盖源项目")
        expected_names = {"database.dump", "artifacts.tar.gz"}
        if set(manifest["files"]) != expected_names:
            raise ValueError("备份清单不完整")
        for name, expected in manifest["files"].items():
            if fingerprint(directory / name) != expected:
                raise ValueError("备份校验失败")
        run("up", "-d", "--wait", "db")
        result = run(
            "exec",
            "-T",
            "db",
            "sh",
            "-c",
            'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc '
            '"SELECT count(*) FROM pg_tables WHERE schemaname NOT IN '
            "('pg_catalog','information_schema')\"",
            capture_output=True,
            text=True,
        )
        if result.stdout.strip() != "0":
            raise ValueError("恢复数据库不是空白，操作已拒绝")
        run("run", "--rm", "--no-deps", "api", "python", "-m", "devflow.data_archive", "empty")
        with (directory / "database.dump").open("rb") as source:
            run(
                "exec",
                "-T",
                "db",
                "sh",
                "-c",
                'exec pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" '
                "--no-owner --exit-on-error --single-transaction",
                stdin=source,
            )
        with (directory / "artifacts.tar.gz").open("rb") as source:
            run(
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "api",
                "python",
                "-m",
                "devflow.data_archive",
                "unpack",
                stdin=source,
            )
        run("up", "-d", "--wait", "--wait-timeout", "240")
    print(f"{args.action} complete: {directory}")


if __name__ == "__main__":
    main()
