# 文件用途：验证演示服务的访问边界、标签契约和标题格式。
from taskboard.service import list_tasks, normalize_labels, task_title


def test_task_is_visible_only_to_owner():
    tasks = [
        {"id": 1, "owner_id": "alice", "title": "first"},
        {"id": 2, "owner_id": "bob", "title": "second"},
    ]
    assert [task["id"] for task in list_tasks(tasks, "alice")] == [1]


def test_null_labels_are_empty():
    assert normalize_labels({"labels": None}) == []


def test_missing_labels_are_empty():
    assert normalize_labels({}) == []


def test_labels_are_normalized():
    assert normalize_labels({"labels": [" BUG ", "", "Help"]}) == ["bug", "help"]


def test_title_is_trimmed():
    assert task_title({"title": "  hello world  "}) == "hello world"
