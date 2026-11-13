# 文件用途：验证三组记忆对照的独立标注、答案评分与真实调用开关。

import pytest
from devflow.config import PROJECT_ROOT, Settings
from devflow.eval_memory import grade_answer
from devflow.evaluation import read_json


def test_memory_corpus_contains_thirty_same_repository_experiences_and_separate_labels():
    directory = PROJECT_ROOT / "evals/memory-v1"
    inputs = read_json(directory / "inputs.json")
    labels = read_json(directory / "expectations.json")
    keys = {m["key"] for m in inputs["memories"]}
    assert len(keys) >= 30 and len(keys) == len(inputs["memories"])
    assert {c["case_id"] for c in inputs["cases"]} == {c["case_id"] for c in labels["cases"]}
    assert all(c["repo_id"] == "repo-taskboard" for c in inputs["cases"])
    assert set(labels["negative_memory_keys"]) <= keys
    assert not any("verdicts" in c or "relevant" in c for c in inputs["cases"])
    assert Settings(_env_file=None).memory_recall_strategy == "recent"


@pytest.mark.parametrize(
    "reply,quality",
    [
        ('{"verdicts":{"A":"supported"},"evidence":{"A":["F1"]},"answer":"理由"}', 1),
        ('{"verdicts":{"A":"supported"},"evidence":{"A":["memory-1"]},"answer":"理由"}', 0),
        ('{"verdicts":{"A":"supported"},"evidence":{"A":[]},"answer":"理由"}', 0),
        ('{"verdicts":{"A":"contradicted"},"evidence":{"A":["F1"]},"answer":"理由"}', 0),
        ("[]", 0),
        ("bad json", 0),
    ],
)
def test_answer_quality_requires_current_fact_citations(reply, quality):
    case = {"claims": {"A": "输出为5"}, "facts": {"F1": "2+3=5"}}
    label = {"verdicts": {"A": "supported"}}
    assert grade_answer(reply, case, label)["quality"] == quality
