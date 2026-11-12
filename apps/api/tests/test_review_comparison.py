# 文件用途：验证前后对照来自同一初稿、旧输出复核不能复用，以及失败不能当作改进。
import importlib.util
from copy import deepcopy

import pytest
from devflow.config import PROJECT_ROOT, Settings
from devflow.eval_runner import execute_case
from devflow.evaluation import digest, load_dataset, write_json
from devflow.review_eval_cli import initial_execution


def test_initial_snapshot_preserves_original_usage_reads_and_tool_count():
    cases, _, _ = load_dataset("evals/devflow-v1")
    execution = execute_case(
        next(c for c in cases if c.case_id == "pr-owner-removed"),
        Settings(_env_file=None, model_provider="fake"),
    )
    record = execution["result"]["report_review"]
    original = initial_execution(execution, None)
    assert original["result"]["report"] == record["initial_report"]
    assert original["observed"] == record["initial_observed"]
    assert original["result"]["tool_calls"] == record["initial_tool_calls"]
    assert original["usage"] == record["initial_usage"]
    assert "report_review" not in original["result"]
    assert all(c["phase"] == "analysis" for c in original["trace"]["calls"])
    assert digest(execution["result"]["report"]) == record["output_report_sha256"]
    # 修改阶段即使发生内部失败，也不能把此前存在的初稿误记为不存在。
    failed = {
        **execution,
        "result": {},
        "error": {"code": "evaluation_internal_error"},
        "report_review_state": record,
    }
    recovered = initial_execution(failed, None)
    assert recovered["error"] is None and recovered["result"]["report"] == record["initial_report"]


def comparison(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "report_review_comparison", PROJECT_ROOT / "scripts/report_review_comparison.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases, _, _ = load_dataset("evals/devflow-v1")
    execution = execute_case(
        next(c for c in cases if c.case_id == "pr-owner-removed"),
        Settings(_env_file=None, model_provider="fake"),
    )
    row = {"before": initial_execution(execution, None), "after": execution, "billing": []}
    row.update(before_sha256=digest(row["before"]), after_sha256=digest(row["after"]))
    (tmp_path / "jobs").mkdir()
    write_json(tmp_path / "jobs/case.json", row)
    write_json(
        tmp_path / "state.json",
        {
            "cases": ["case"],
            "completed": ["case"],
            "fingerprint": "fixed",
            "comparison": "same initial",
        },
    )
    verdict = {
        "verdict": "pass",
        "target_errors": [],
        "abstained": False,
        "false_positive": False,
        "missed_issue": False,
        "notes": "测试用的结构复核记录。",
    }
    reviews = {
        "reviewer": "GPT",
        "fingerprint": "fixed",
        "cases": [
            {
                "case_id": "case",
                "before_sha256": row["before_sha256"],
                "after_sha256": row["after_sha256"],
                "before": deepcopy(verdict),
                "after": deepcopy(verdict),
            }
        ],
    }
    return module, reviews


def test_equal_results_do_not_count_as_target_error_reduction(tmp_path):
    module, reviews = comparison(tmp_path)
    result = module.summarize(tmp_path, reviews)
    assert result["acceptance"]["target_errors_reduced"] is False


def test_changed_output_cannot_inherit_old_gpt_review(tmp_path):
    module, reviews = comparison(tmp_path)
    reviews["cases"][0]["after_sha256"] = "other"
    with pytest.raises(ValueError, match="旧复核"):
        module.summarize(tmp_path, reviews)


def test_new_failure_requires_an_explanation(tmp_path):
    module, reviews = comparison(tmp_path)
    reviews["cases"][0]["after"]["verdict"] = "fail"
    with pytest.raises(ValueError, match="退步必须解释"):
        module.summarize(tmp_path, reviews)
