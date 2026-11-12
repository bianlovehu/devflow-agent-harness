# 文件用途：验证对照计划、未压缩对照和费用保护；测试仅用fake模型，不发真实请求。
from devflow.baseline_cli import plan_jobs
from devflow.config import Settings
from devflow.eval_runner import build_gateway, execute_case
from devflow.evaluation import load_dataset


def test_production_knowledge_trailing_newline_can_be_read_again(tmp_path):
    import json
    import os

    import pytest
    from devflow.config import get_settings
    from devflow.eval_retrieval import ProductionRetrieval

    if os.getenv("DEVFLOW_TEST_DATABASE") != "1":
        pytest.skip("isolated PostgreSQL required")
    cases, _, _ = load_dataset("evals/devflow-v1")
    case = next(c for c in cases if c.case_id == "qa-owner")
    with ProductionRetrieval(get_settings(), [case], tmp_path / "artifacts") as corpus:
        tools, _ = build_gateway(case)
        tools.knowledge_search = corpus.tool(case, "hybrid")
        found = tools.execute(
            "search_knowledge", json.dumps({"repo_id": "eval-repo", "query": case.question})
        )
        item = next(h for h in found["data"]["items"] if h["filename"] == "qa-owner-doc.md")
        assert tools.evidence[item["id"]]["end_line"] == 1
        reread = tools.execute(
            "read_evidence",
            json.dumps({"repo_id": "eval-repo", "evidence_id": item["id"], "limit": 20}),
        )
        assert reread["ok"] and reread["data"]["end_line"] == 1
        assert reread["data"]["lines"][0]["text"] == case.sources[0].content.rstrip("\n")


def test_fixed_plans_keep_all_development_cases_and_three_repetitions():
    cases, _, _ = load_dataset("evals/devflow-v1")
    dev = [c for c in cases if c.split == "dev"]
    analysis = plan_jobs(dev, "analysis")
    assert len(analysis) == 40
    assert {j["case_id"] for j in analysis} == {c.case_id for c in dev}
    stability = plan_jobs(dev, "stability")
    assert len(stability) == 9
    for case in {j["case_id"] for j in stability}:
        assert {j["repeat"] for j in stability if j["case_id"] == case} == {1, 2, 3}


def test_metadata_never_invents_ci_base_or_qa_resource():
    cases, _, _ = load_dataset("evals/devflow-v1")
    for case in cases:
        gateway, _ = build_gateway(case)
        assert gateway.metadata["data_source"] == "evaluation_fixture"
        resources = gateway.metadata["input_version"]["resources"]
        if case.task_type == "knowledge_qa":
            assert resources == []
        elif case.task_type == "ci_debug":
            assert "base_sha" not in resources[0]
        else:
            assert resources[0]["base_sha"] and resources[0]["head_sha"]


def test_uncompressed_and_budgeted_use_same_evidence_and_measurable_context_change():
    cases, _, _ = load_dataset("evals/devflow-v1")
    case = next(c for c in cases if c.case_id == "pr-owner-removed")
    history = [
        {"id": f"history-{i}", "role": "user", "content": f"历史记录{i}:" + "无关历史资料" * 100}
        for i in range(15)
    ]
    settings = Settings(_env_file=None, model_provider="fake")
    full = execute_case(
        case,
        settings,
        history=history,
        configuration_updates={"context_mode": "uncompressed", "context_input_tokens": 120000},
    )
    budgeted = execute_case(
        case,
        settings,
        history=history,
        configuration_updates={"context_mode": "budgeted", "context_input_tokens": 20000},
    )
    assert full["error"] is None and budgeted["error"] is None
    assert full["evidence"] == budgeted["evidence"]
    assert (
        full["result"]["context"][0]["estimated_input"]
        > budgeted["result"]["context"][0]["estimated_input"]
    )
    assert budgeted["result"]["context"][0]["saved_tokens"] > 0
