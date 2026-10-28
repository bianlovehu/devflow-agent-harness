# 文件用途：提供任务列表、标题和标签处理的演示业务逻辑。
def list_tasks(tasks: list[dict], actor_id: str) -> list[dict]:
    """Only the owner can see a task."""
    # 按当前用户筛选输入任务，访问边界由这一层实现。
    return [task for task in tasks if task["owner_id"] == actor_id]


def task_title(task: dict) -> str:
    return " ".join(str(task["title"]).split())


def normalize_labels(payload: dict) -> list[str]:
    # 显式处理允许为空的标签，并拒绝其他不符合契约的类型。
    labels = payload.get("labels")
    if labels is None:
        return []
    if not isinstance(labels, list):
        raise ValueError("labels must be a list or null")
    return [str(label).strip().lower() for label in labels if str(label).strip()]
