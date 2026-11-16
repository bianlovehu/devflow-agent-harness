# 文件用途：验证功能分组后的根目录定位、递归源码指纹和评测源码快照。
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from devflow.analysis import agent
from devflow.core.config import PROJECT_ROOT, Settings
from devflow.evaluation import eval_cli, review_eval_cli


def write_source(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\r\n")


@pytest.mark.parametrize("override", [False, True])
def test_project_root_and_env_file_are_independent_of_working_directory(tmp_path, override):
    environment = os.environ.copy()
    environment.pop("DEVFLOW_PROJECT_ROOT", None)
    expected = PROJECT_ROOT
    if override:
        expected = tmp_path / "deployment"
        environment["DEVFLOW_PROJECT_ROOT"] = str(expected)
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json; from devflow.core.config import PROJECT_ROOT, Settings; "
            "print(json.dumps([str(PROJECT_ROOT), str(Settings.model_config['env_file'])]))",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == [str(expected), str(expected / ".env")]


def test_agent_fingerprint_tracks_other_groups_and_relative_paths(tmp_path, monkeypatch):
    package = tmp_path / "devflow"
    entry = package / "analysis/agent.py"
    source = package / "storage/models.py"
    write_source(entry, "# analysis entry\n")
    write_source(source, "VALUE = 1\n")
    monkeypatch.setattr(agent, "__file__", str(entry))
    settings = Settings(_env_file=None, model_provider="fake")
    original = agent.model_configuration(settings)["code_sha256"]
    write_source(source, "VALUE = 2\n")
    edited = agent.model_configuration(settings)["code_sha256"]
    assert edited != original
    relocated = package / "knowledge/models.py"
    relocated.parent.mkdir()
    source.rename(relocated)
    assert agent.model_configuration(settings)["code_sha256"] != edited


def test_evaluation_provenance_tracks_nested_source_changes(tmp_path, monkeypatch):
    source = tmp_path / "apps/api/src/devflow/storage/models.py"
    write_source(source, "VALUE = 1\n")
    write_source(tmp_path / "pyproject.toml", "# project\n")
    write_source(tmp_path / "uv.lock", "# lock\n")
    monkeypatch.setattr(eval_cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        eval_cli.subprocess,
        "check_output",
        lambda args, **kwargs: "fixed-commit\n" if args[1] == "rev-parse" else "",
    )
    original = eval_cli.provenance()["working_code_sha256"]
    write_source(source, "VALUE = 2\n")
    assert eval_cli.provenance()["working_code_sha256"] != original


def test_review_snapshot_preserves_nested_files_with_same_name(tmp_path, monkeypatch):
    package = tmp_path / "apps/api/src/devflow"
    write_source(package / "knowledge/api.py", "# knowledge routes\n")
    write_source(package / "memory/api.py", "# memory routes\n")
    monkeypatch.setattr(review_eval_cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        review_eval_cli, "get_settings", lambda: SimpleNamespace(model_provider="stub")
    )
    monkeypatch.setattr(review_eval_cli, "model_configuration", lambda settings: {})
    monkeypatch.setattr(
        review_eval_cli, "provenance", lambda: {"working_code_sha256": "snapshot-test"}
    )
    monkeypatch.setattr(review_eval_cli, "load_dataset", lambda dataset: ([], {}, {}))
    monkeypatch.setattr(
        review_eval_cli,
        "get_budget_ledger",
        lambda: SimpleNamespace(summary=lambda: {"status": "ok"}),
    )
    monkeypatch.setattr(
        review_eval_cli,
        "execute_case",
        lambda *args, **kwargs: pytest.fail("unexpected model call"),
    )
    directory = tmp_path / "comparison"
    args = SimpleNamespace(dataset="unused", directory=directory, case=None, limit=0)
    assert review_eval_cli.run_batch(args) == 0
    snapshot = json.loads((directory / "source-snapshot.json").read_text(encoding="utf-8"))
    files = {Path(name).as_posix(): content for name, content in snapshot["files"].items()}
    assert files == {
        "apps/api/src/devflow/knowledge/api.py": "# knowledge routes\n",
        "apps/api/src/devflow/memory/api.py": "# memory routes\n",
    }
