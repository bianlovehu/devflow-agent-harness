# 文件用途：模型适配器单元测试使用显式假账本，避免访问任何业务数据库。
from uuid import uuid4


class StubLedger:
    def __init__(self):
        self.reservations, self.dispatched, self.finished = [], [], []

    def reserve(self, **values):
        self.reservations.append(values)
        return {
            "request_id": str(uuid4()),
            "warning": False,
            "reserved_cny": "0.4",
            "pricing_version": "unit-test",
        }

    def dispatch(self, request_id):
        self.dispatched.append(request_id)

    def finish(self, request_id, usage=None, *, sent=True):
        self.finished.append({"request_id": request_id, "usage": usage, "sent": sent})
