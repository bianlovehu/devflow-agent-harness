# 文件用途：验证评测数据隔离、真实 Agent 执行、失败定位、人工复核绑定和回归门禁。
import importlib.util
import json
from collections import Counter
from copy import deepcopy

import pytest
from devflow.config import PROJECT_ROOT, Settings
from devflow.eval_cli import main
from devflow.eval_runner import build_gateway, execute_case
from devflow.evaluation import (
    EVALUATOR_VERSION,
    aggregate,
    apply_reviews,
    compare_runs,
    digest,
    grade,
    load_dataset,
    quality_exit,
    read_json,
    review_template,
    write_json,
)
from devflow.model_gateway import ModelError, Usage

DATASET = PROJECT_ROOT / "evals/devflow-v1"


@pytest.fixture(scope="module")
def dataset():
    return load_dataset(DATASET)


@pytest.fixture(scope="module")
def evaluated(dataset):
    cases, labels, version = dataset
    selected = [
        c
        for c in cases
        if c.case_id in {"pr-owner-removed", "pr-owner-fixed", "pr-null-unchanged", "qa-missing"}
    ]
    rows = []
    for case in selected:
        execution = execute_case(case, Settings(_env_file=None, model_provider="fake"))
        rows.append(
            {
                "case_id": case.case_id,
                "case_sha256": digest(case.model_dump()),
                "execution": execution,
                "failures": grade(case, labels[case.case_id], execution),
                "review": {"verdict": "pending"},
            }
        )
    return {
        "schema_version": 1,
        "evaluator_version": EVALUATOR_VERSION,
        "run_id": "original",
        "dataset": version,
        "profile": {"model": "fake"},
        "cases": rows,
        "summary": aggregate(rows),
    }


def test_fixed_dataset_counts_source_split_and_reproducible_generation(dataset, tmp_path):
    cases, labels, _ = dataset
    assert Counter(c.task_type for c in cases) == {
        "pr_review": 10,
        "ci_debug": 10,
        "knowledge_qa": 10,
    }
    assert Counter(c.split for c in cases) == {"dev": 20, "holdout": 10}
    assert {c.source_group for c in cases if c.split == "dev"}.isdisjoint(
        c.source_group for c in cases if c.split == "holdout"
    )
    assert len(labels) == 30
    spec = importlib.util.spec_from_file_location(
        "eval_builder", PROJECT_ROOT / "scripts/build_eval_dataset.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = tmp_path
    module.main()
    for filename in ["inputs.json", "expectations.json"]:
        assert (tmp_path / filename).read_bytes() == (DATASET / filename).read_bytes()


@pytest.mark.parametrize("mutation", ["duplicate", "cross_split", "anchor", "missing_label"])
def test_dataset_rejects_leakage_duplicates_and_invalid_references(tmp_path, mutation):
    inputs = read_json(DATASET / "inputs.json")
    labels = read_json(DATASET / "expectations.json")
    if mutation == "duplicate":
        inputs["cases"].append(inputs["cases"][0])
    elif mutation == "cross_split":
        inputs["cases"][-1]["source_group"] = inputs["cases"][0]["source_group"]
    elif mutation == "anchor":
        labels["cases"][1]["required_evidence"][0]["end_line"] = 999
    else:
        labels["cases"].pop()
    write_json(tmp_path / "inputs.json", inputs)
    write_json(tmp_path / "expectations.json", labels)
    with pytest.raises(ValueError):
        load_dataset(tmp_path)


def test_agent_uses_input_only_and_old_code_does_not_become_new_risk(evaluated):
    for row in evaluated["cases"]:
        assert not row["failures"]
        assert row["execution"]["result"]["provider"] == "fake"
        serialized = json.dumps(row["execution"]["trace"], ensure_ascii=False)
        assert "expected_findings" not in serialized and "must_not_conclude" not in serialized
    assert evaluated["cases"][0]["execution"]["result"]["report"]["findings"]
    for row in evaluated["cases"][1:3]:
        assert not row["execution"]["result"]["report"]["findings"]
    assert quality_exit(evaluated) == 3  # 自动通过仍需人工语义复核。


@pytest.mark.parametrize("bad", ["unknown", "unread", "wrong_revision"])
def test_grader_independently_checks_citations_and_version(dataset, evaluated, bad):
    cases, labels, _ = dataset
    case = next(c for c in cases if c.case_id == "pr-owner-removed")
    execution = deepcopy(evaluated["cases"][0]["execution"])
    cite = execution["result"]["report"]["findings"][0]["evidence"][0]
    if bad == "unknown":
        cite["evidence_id"] = "00000000-0000-0000-0000-000000000000"
    elif bad == "unread":
        execution["observed"] = {}
    else:
        cite["evidence_id"] = next(
            e["id"] for e in execution["evidence"] if e["source_key"] == "base"
        )
    failures = grade(case, labels[case.case_id], execution)
    assert "evidence_miss" in {f["tag"] for f in failures}
    if bad != "wrong_revision":
        assert "citation" in {f["tag"] for f in failures}


def test_missing_root_cause_has_actionable_failure_not_false_success(dataset):
    cases, labels, _ = dataset
    case = next(c for c in cases if c.case_id == "ci-lint")
    execution = execute_case(case, Settings(_env_file=None, model_provider="fake"))
    failures = grade(case, labels[case.case_id], execution)
    assert {f["tag"] for f in failures} == {"evidence_miss", "missed_issue", "wrong_stage"}
    assert next(f for f in failures if f["tag"] == "evidence_miss")["detail"]["read_by_tool"]
    assert all(f["next_step"] for f in failures)


def test_failed_call_preserves_known_usage_and_unknown_is_explicit(dataset, monkeypatch):
    from devflow import eval_runner

    class ErrorModel:
        provider, name = "fake", "error-test"
        usage = Usage(prompt_tokens=8, completion_tokens=3, total_tokens=11)

        def complete(self, *args, **kwargs):
            raise ModelError("model_rate_limited", "rate limited", usage=self.usage)

    monkeypatch.setattr(eval_runner, "FixtureModel", ErrorModel)
    settings = Settings(_env_file=None, model_provider="fake")
    execution = execute_case(dataset[0][0], settings)
    assert execution["error"]["code"] == "model_rate_limited"
    assert execution["usage"]["total_tokens"] == 11
    assert not execution["usage_unknown"]
    ErrorModel.usage = None
    assert execute_case(dataset[0][0], settings)["usage_unknown"]


def test_reviews_require_identity_notes_and_bind_exact_execution(evaluated):
    run = deepcopy(evaluated)
    template = review_template(run)
    review = template["reviews"][0]
    review.update(verdict="pass")
    with pytest.raises(ValueError, match="reviewer"):
        apply_reviews(run, template)
    review.update(reviewer="test-reviewer", notes="Test-only human review fixture.")
    apply_reviews(run, template)
    assert run["summary"]["human_passed"] == 1
    run["cases"][0]["execution"]["result"]["report"]["summary"] = "changed"
    with pytest.raises(ValueError, match="报告已变化"):
        apply_reviews(run, template)
    template["run_id"] = "another-run"
    with pytest.raises(ValueError, match="不属于"):
        apply_reviews(evaluated, template)


def test_compare_detects_regression_even_when_another_case_improves(evaluated):
    old, new = deepcopy(evaluated), deepcopy(evaluated)
    old["cases"][1]["failures"] = [{"tag": "false_positive", "check_id": "false_positive"}]
    new["cases"][0]["failures"] = [{"tag": "missed_issue", "check_id": "missed_issue"}]
    comparison = compare_runs(old, new)
    assert [r["case_id"] for r in comparison["improvements"]] == ["pr-owner-fixed"]
    assert [r["case_id"] for r in comparison["regressions"]] == ["pr-owner-removed"]
    assert comparison["unresolved"] == ["pr-owner-removed"]


@pytest.mark.parametrize("change", ["scope", "dataset", "model", "case", "evaluator"])
def test_compare_refuses_incompatible_baselines(evaluated, change):
    new = deepcopy(evaluated)
    if change == "scope":
        new["cases"].pop()
    elif change == "dataset":
        new["dataset"]["sha256"] = "changed"
    elif change == "model":
        new["profile"]["model"] = "another-model"
    elif change == "evaluator":
        new["evaluator_version"] = "another-grader"
    else:
        new["cases"][0]["case_sha256"] = "changed"
    with pytest.raises(ValueError):
        compare_runs(evaluated, new)


def test_new_output_cannot_inherit_old_semantic_pass(evaluated):
    old, new = deepcopy(evaluated), deepcopy(evaluated)
    old["cases"][0]["review"]["verdict"] = "pass"
    comparison = compare_runs(old, new)
    assert comparison["regressions"][0]["added"] == ["semantic_review_lost"]


def test_cli_defaults_fake_never_loads_real_settings_and_preserves_outputs(tmp_path, monkeypatch):
    def forbidden():
        raise AssertionError("default eval must not load configured credentials")

    monkeypatch.setattr("devflow.eval_cli.get_settings", forbidden)
    output = tmp_path / "run"
    assert main(["run", "--case", "pr-owner-fixed", "--output", str(output)]) == 3
    result = read_json(output / "results.json")
    assert result["profile"]["provider"] == "fake"
    assert result["configuration"]["model"] == "fixture-demo-v1"
    assert not read_json(output / "failures.json")["case_ids"]
    original = (output / "results.json").read_bytes()
    assert b"\r\n" in original and b"\n" not in original.replace(b"\r\n", b"")
    with pytest.raises(SystemExit) as error:
        main(["run", "--case", "pr-owner-fixed", "--output", str(output)])
    assert error.value.code == 2
    assert (output / "results.json").read_bytes() == original
    assert main(["compare", "--baseline", str(output), "--current", str(output)]) == 0


def test_fake_refuses_to_compare_incomplete_file_fragments(dataset):
    from devflow.fake_model import FixtureModel

    case = next(c for c in dataset[0] if c.case_id == "pr-owner-removed")
    gateway, _ = build_gateway(case)
    fragments = []
    for item in gateway.catalog():
        value = gateway.execute(
            "read_evidence",
            json.dumps(
                {
                    "repo_id": gateway.repo_id,
                    "evidence_id": item["id"],
                    "limit": 1,
                }
            ),
        )
        fragments.append(value["data"])
    _, changed = FixtureModel.changed_lines(
        {"metadata": gateway.metadata, "catalog": gateway.catalog()}, fragments
    )
    assert not changed


def test_cli_failure_review_rerun_and_regression_gate(tmp_path):
    baseline, reviewed, rerun = (tmp_path / name for name in ["baseline", "reviewed", "rerun"])
    assert main(["run", "--case", "ci-lint", "--output", str(baseline)]) == 1
    template = read_json(baseline / "reviews.json")
    template["reviews"][0].update(
        verdict="fail",
        reviewer="test-reviewer",
        notes="Test fixture: lint diagnosis was missed.",
        failure_tags=["wrong_root_cause"],
    )
    write_json(baseline / "reviews.json", template)
    assert (
        main(
            [
                "review",
                "--run",
                str(baseline),
                "--reviews",
                str(baseline / "reviews.json"),
                "--output",
                str(reviewed),
            ]
        )
        == 1
    )
    assert read_json(reviewed / "results.json")["summary"]["human_failed"] == 1
    assert main(["compare", "--baseline", str(baseline), "--current", str(reviewed)]) == 1
    assert (
        main(["run", "--cases-from", str(reviewed / "failures.json"), "--output", str(rerun)]) == 1
    )
    assert [r["case_id"] for r in read_json(rerun / "results.json")["cases"]] == ["ci-lint"]


def test_compare_tracks_each_reference_instead_of_hiding_new_miss_under_same_tag(evaluated):
    old, new = deepcopy(evaluated), deepcopy(evaluated)
    old["cases"][0]["failures"] = [{"tag": "evidence_miss", "check_id": "evidence_miss:head:2:2"}]
    new["cases"][0]["failures"] = [{"tag": "evidence_miss", "check_id": "evidence_miss:head:3:3"}]
    comparison = compare_runs(old, new)
    assert comparison["regressions"][0]["added"] == ["evidence_miss:head:3:3"]
