# 文件用途：确认慢连接和慢响应都受总时限约束，迟到响应不重复记账。
import io
import json
import threading
import time

import pytest
from budget_samples import StubLedger
from devflow.config import Settings
from devflow.model_gateway import DeepSeekModel, ModelError


@pytest.mark.parametrize("where", ["connect", "body"])
def test_total_deadline_stops_slow_transport_and_keeps_unknown_usage(where):
    release = threading.Event()
    done = threading.Event()
    raw = json.dumps(
        {
            "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        }
    ).encode()

    class Response(io.BytesIO):
        def read(self, *args):
            if where == "body":
                release.wait(timeout=4)
            return super().read(*args)

        def close(self):
            super().close()
            done.set()

    class Opener:
        calls = 0

        def open(self, *args, **kwargs):
            self.calls += 1
            if where == "connect":
                release.wait(timeout=4)
            return Response(raw)

    opener = Opener()
    ledger = StubLedger()
    model = DeepSeekModel(
        Settings(_env_file=None, model_provider="deepseek", deepseek_api_key="private-test"),
        opener=opener,
        ledger=ledger,
    )
    started = time.monotonic()
    try:
        with pytest.raises(ModelError) as exc:
            model.complete([], [], timeout=0.08)
        assert exc.value.code == "model_network_error"
        assert time.monotonic() - started < 1.5
        assert opener.calls == 1 and len(ledger.finished) == 1
        assert ledger.finished[0]["usage"] is None and ledger.finished[0]["sent"] is True
    finally:
        release.set()
    assert done.wait(timeout=2)
    assert len(ledger.finished) == 1  # 迟到的已知响应不能在后台改写结算或任务结果。
