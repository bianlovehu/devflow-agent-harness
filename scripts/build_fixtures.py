# 文件用途：用固定 Git 身份和时间生成可复现的演示案例。
"""Rebuild synthetic fixtures with real, deterministic local Git commit IDs."""

import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "taskboard"
STAMP = "2026-10-26T08:00:00Z"
REPO_ID = "repo-taskboard"
SEED_FILES = (
    ".gitattributes",
    "README.md",
    "pyproject.toml",
    "taskboard/__init__.py",
    "taskboard/service.py",
    "taskboard/settings.py",
    "taskboard/config_check.py",
    "tests/test_service.py",
)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))


def write_json(path: Path, value: object) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def git(workspace: Path, *args: str) -> str:
    # 只在传入的自建临时仓库运行 Git，并固定提交身份和时间。
    env = dict(os.environ)
    env.update(
        GIT_AUTHOR_NAME="DevFlow Demo",
        GIT_AUTHOR_EMAIL="demo@example.invalid",
        GIT_COMMITTER_NAME="DevFlow Demo",
        GIT_COMMITTER_EMAIL="demo@example.invalid",
        GIT_AUTHOR_DATE="2026-10-25T08:00:00+00:00",
        GIT_COMMITTER_DATE="2026-10-25T08:00:00+00:00",
    )
    return subprocess.run(
        ["git", "-C", str(workspace), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    ).stdout.strip()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def file_evidence(content: str, marker: str, commit: str) -> dict:
    number = next(i for i, line in enumerate(content.splitlines(), 1) if marker in line)
    return {
        "type": "file",
        "resource_id": "taskboard/service.py",
        "version": commit,
        "start_line": number,
        "end_line": number,
        "quote": content.splitlines()[number - 1],
    }


def build(workspace: Path) -> None:
    # 从演示源码生成提交、快照、diff、日志及独立参考标注。
    for name in SEED_FILES:
        write_text(workspace / name, read_text(FIXTURE / "seed" / name))
    git(workspace, "init", "-b", "main")
    git(workspace, "config", "core.autocrlf", "true")
    git(workspace, "config", "commit.gpgsign", "false")
    git(workspace, "config", "core.hooksPath", str(workspace / ".git" / "disabled-hooks"))
    git(workspace, "add", ".")
    git(workspace, "commit", "-m", "Synthetic Taskboard base")
    base_sha = git(workspace, "rev-parse", "HEAD")
    base_content = read_text(workspace / "taskboard/service.py")

    def snapshot(commit: str) -> None:
        for name in SEED_FILES:
            write_text(FIXTURE / "snapshots" / commit / name, read_text(workspace / name))

    snapshot(base_sha)
    changes = [
        (
            101,
            "规范化任务标题中的连续空格",
            "仅调整标题展示，合并连续空格并保留现有任务访问边界。",
            'return str(task["title"]).strip()',
            'return " ".join(str(task["title"]).split())',
        ),
        (
            102,
            "简化任务列表返回逻辑",
            "调整任务列表的集合处理方式，请核查行为是否保持一致。",
            'return [task for task in tasks if task["owner_id"] == actor_id]',
            "return list(tasks)",
        ),
        (
            103,
            "使用默认值简化可选标签处理",
            "减少可选标签分支，请核查缺省值、null 和非法输入的行为。",
            'labels = payload.get("labels")\n    if labels is None:\n        return []',
            'labels = payload.get("labels", [])',
        ),
    ]
    prs = []
    for number, title, body, old, new in changes:
        git(workspace, "checkout", "--detach", base_sha)
        head_content = base_content.replace(old, new)
        if head_content == base_content:
            raise RuntimeError(f"Missing mutation marker for PR {number}")
        write_text(workspace / "taskboard/service.py", head_content)
        git(workspace, "add", ".")
        git(workspace, "commit", "-m", f"Demo PR {number}: {title}")
        head_sha = git(workspace, "rev-parse", "HEAD")
        snapshot(head_sha)
        patch = (
            git(
                workspace, "diff", "--no-ext-diff", base_sha, head_sha, "--", "taskboard/service.py"
            )
            + "\n"
        )
        patch_path = FIXTURE / "pull-requests" / f"{number}.diff"
        write_text(patch_path, patch)
        additions = sum(
            line.startswith("+") and not line.startswith("+++") for line in patch.splitlines()
        )
        deletions = sum(
            line.startswith("-") and not line.startswith("---") for line in patch.splitlines()
        )
        prs.append(
            {
                "repo_id": REPO_ID,
                "data_source": "fixture",
                "number": number,
                "title": title,
                "body": body,
                "author": "demo-maintainer",
                "state": "open",
                "base_sha": base_sha,
                "head_sha": head_sha,
                "updated_at": STAMP,
                "files": [
                    {
                        "path": "taskboard/service.py",
                        "additions": additions,
                        "deletions": deletions,
                        "patch": patch,
                        "base_content": base_content,
                        "head_content": head_content,
                        "content_sha256": sha256(head_content),
                    }
                ],
            }
        )

    # In this demonstration the null regression is rejected by the explicit
    # type guard before iteration, so the log records that exact failure.
    # 从当前源码计算堆栈行号，新增注释后日志仍能准确引用对应代码。
    null_source = next(pr["files"][0]["head_content"] for pr in prs if pr["number"] == 103)
    null_error_line = next(
        i for i, line in enumerate(null_source.splitlines(), 1) if "raise ValueError" in line
    )
    config_source = read_text(FIXTURE / "seed" / "taskboard/settings.py")
    config_error_line = next(
        i for i, line in enumerate(config_source.splitlines(), 1) if "raise RuntimeError" in line
    )
    logs = {
        201: (
            "unit-tests",
            103,
            "test",
            "\n".join(
                [
                    "2026-10-26T08:00:00Z ##[group]Run python -m pytest",
                    "$ python -m pytest -q",
                    "tests/test_service.py .F...",
                    "__________________ test_null_labels_are_empty __________________",
                    '    assert normalize_labels({"labels": None}) == []',
                    f"taskboard/service.py:{null_error_line}: ValueError",
                    '    raise ValueError("labels must be a list or null")',
                    "E   ValueError: labels must be a list or null",
                    "FAILED tests/test_service.py::test_null_labels_are_empty",
                    "1 failed, 4 passed",
                    "##[error]Process completed with exit code 1.",
                    "",
                ]
            ),
        ),
        202: (
            "install-dependencies",
            101,
            "install",
            "\n".join(
                [
                    "2026-10-26T08:05:00Z ##[group]Install dependencies",
                    "$ python -m pip install taskboard-driver==99.0.0",
                    "Looking in indexes: https://pypi.org/simple",
                    "ERROR: Could not find a version that satisfies the requirement "
                    "taskboard-driver==99.0.0 (from versions: none)",
                    "ERROR: No matching distribution found for taskboard-driver==99.0.0",
                    "##[error]Process completed with exit code 1.",
                    "Test step skipped because dependency installation failed.",
                    "",
                ]
            ),
        ),
        203: (
            "validate-configuration",
            101,
            "configure",
            "\n".join(
                [
                    "2026-10-26T08:10:00Z ##[group]Validate configuration",
                    "$ python -m taskboard.config_check",
                    "Traceback (most recent call last):",
                    f'  File "taskboard/settings.py", line {config_error_line},'
                    " in load_database_url",
                    '    raise RuntimeError("DATABASE_URL is required")',
                    "RuntimeError: DATABASE_URL is required",
                    "##[error]Process completed with exit code 1.",
                    "Integration tests were not started.",
                    "",
                ]
            ),
        ),
    }
    runs = []
    for run_id, (name, pr_number, stage, log) in logs.items():
        commit = next(pr["head_sha"] for pr in prs if pr["number"] == pr_number)
        write_text(FIXTURE / "ci-logs" / f"{run_id}.txt", log)
        runs.append(
            {
                "id": run_id,
                "repo_id": REPO_ID,
                "data_source": "fixture",
                "pull_request_number": pr_number,
                "name": name,
                "conclusion": "failure",
                "stage": stage,
                "head_sha": commit,
                "started_at": STAMP,
                "duration_seconds": {201: 12, 202: 7, 203: 3}[run_id],
                "log": log,
                "log_sha256": sha256(log),
            }
        )

    doc_info = [
        ("architecture", "Taskboard 架构说明", "architecture", "architecture.md"),
        ("access-policy", "任务访问策略", "policy", "access-policy.md"),
        ("ci-runbook", "CI 故障排查手册", "runbook", "ci-runbook.md"),
        (
            "null-labels-postmortem",
            "可选标签处理回归复盘",
            "postmortem",
            "null-labels-postmortem.md",
        ),
    ]
    documents = []
    for doc_id, title, kind, name in doc_info:
        text = read_text(FIXTURE / "documents" / name)
        documents.append(
            {
                "id": doc_id,
                "repo_id": REPO_ID,
                "data_source": "fixture",
                "title": title,
                "kind": kind,
                "version": sha256(text),
                "updated_at": STAMP,
                "line_count": len(text.splitlines()),
                "content": text,
            }
        )
    repository = {
        "id": REPO_ID,
        "data_source": "fixture",
        "full_name": "devflow-demo/taskboard",
        "description": "人工构造的 Python 任务管理服务，用于 PR 审查、CI 排障和知识检索演示。",
        "language": "Python",
        "default_branch": "main",
        "default_commit": base_sha,
        "updated_at": STAMP,
        "pull_request_count": len(prs),
        "ci_run_count": len(runs),
        "document_count": len(documents),
    }
    write_json(
        FIXTURE / "dataset.json",
        {
            "schema_version": 1,
            "generated_at": STAMP,
            "repositories": [repository],
            "pull_requests": prs,
            "ci_runs": runs,
            "documents": documents,
        },
    )

    cases = [
        {
            "case_id": "pr-101-clean",
            "kind": "pr_review",
            "repo_id": REPO_ID,
            "target_id": 101,
            "expected_findings": [],
            "evidence": [
                file_evidence(
                    prs[0]["files"][0]["head_content"], 'return " ".join', prs[0]["head_sha"]
                )
            ],
            "must_not_conclude": ["凭标题空格变更推断权限漏洞", "把安装或配置失败归因于此行代码"],
        },
        {
            "case_id": "pr-102-missing-owner-filter",
            "kind": "pr_review",
            "repo_id": REPO_ID,
            "target_id": 102,
            "expected_findings": ["所有者过滤被移除，可向当前用户返回其他用户的任务。"],
            "evidence": [
                file_evidence(
                    prs[1]["files"][0]["head_content"], "return list(tasks)", prs[1]["head_sha"]
                )
            ],
            "must_not_conclude": ["已发生真实数据泄露", "未经检查的写入与删除接口也存在漏洞"],
        },
        {
            "case_id": "pr-103-null-labels",
            "kind": "pr_review",
            "repo_id": REPO_ID,
            "target_id": 103,
            "expected_findings": [
                "显式 null 不会使用 dict.get 的默认值，导致允许的 null 输入被类型检查拒绝。"
            ],
            "evidence": [
                file_evidence(
                    prs[2]["files"][0]["head_content"],
                    'labels = payload.get("labels", [])',
                    prs[2]["head_sha"],
                )
            ],
            "must_not_conclude": [
                "缺省字段也一定失败",
                "断言此版本抛出 NoneType 不可迭代错误；此版本先抛出 ValueError",
            ],
        },
    ]
    ci_expectations = {
        201: (
            "空值标签被类型检查拒绝，测试契约回归。",
            "E   ValueError: labels must be a list or null",
            ["误报为依赖安装问题", "断言此版本抛出 TypeError"],
        ),
        202: (
            "指定依赖版本无法从当前索引解析。",
            "ERROR: No matching distribution",
            ["断言应用单元测试失败", "仅凭样例日志断言外部软件源永久不可用"],
        ),
        203: (
            "启动检查缺少 DATABASE_URL 配置。",
            "RuntimeError: DATABASE_URL is required",
            ["要求用户公开数据库密码", "断言数据库已启动且服务端认证失败"],
        ),
    }
    for run in runs:
        finding, marker, exclusions = ci_expectations[run["id"]]
        line_number = next(i for i, line in enumerate(run["log"].splitlines(), 1) if marker in line)
        cases.append(
            {
                "case_id": f"ci-{run['id']}",
                "kind": "ci_debug",
                "repo_id": REPO_ID,
                "target_id": run["id"],
                "expected_findings": [finding],
                "evidence": [
                    {
                        "type": "log",
                        "resource_id": str(run["id"]),
                        "version": run["head_sha"],
                        "content_sha256": run["log_sha256"],
                        "start_line": line_number,
                        "end_line": line_number,
                        "quote": run["log"].splitlines()[line_number - 1],
                    }
                ],
                "must_not_conclude": exclusions,
            }
        )
    write_json(
        ROOT / "evals" / "fixtures" / "expectations.json", {"schema_version": 1, "cases": cases}
    )


def main() -> None:
    # 清理临时仓库前核对绝对路径，防止误删工作区外的目录。
    build_root = (ROOT / ".cache" / "fixture-build").resolve()
    build_root.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="taskboard-", dir=build_root)).resolve()
    try:
        build(workspace)
    finally:
        # This is a scratch directory created by this invocation. Verify its
        # absolute parent before recursive cleanup on Windows.
        if workspace.parent != build_root or not workspace.is_relative_to(ROOT.resolve()):
            raise RuntimeError("Refusing cleanup outside the project fixture-build directory")

        def remove_readonly(function, path, _error):
            os.chmod(path, stat.S_IWRITE)
            function(path)

        shutil.rmtree(workspace, onerror=remove_readonly)
    print("Generated 1 repository, 3 PRs, 3 CI runs, 4 documents and 6 annotated cases.")


if __name__ == "__main__":
    main()
