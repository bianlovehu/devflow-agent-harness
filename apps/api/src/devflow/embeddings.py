# 文件用途：校验固定 E5 权重，使用 CPU ONNX 推理与相同 tokenizer，不在请求时联网下载。
import hashlib
import os
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np
from tokenizers import Tokenizer

from devflow.config import PROJECT_ROOT
from devflow.errors import DomainError

MODEL_REPO = "Xenova/multilingual-e5-small"
MODEL_REVISION = "761b726dd34fb83930e26aab4e9ac3899aa1fa78"
MODEL_KEY = f"{MODEL_REPO}@{MODEL_REVISION}:int8:mean:l2:v1"
MODEL_FILES = {
    "onnx/model_quantized.onnx": "f80102d3f2a1229f387d3c81909990d8945513e347b0eab049f7de3c6f98c193",
    "tokenizer.json": "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39",
}
MODEL_DIR = (
    Path(os.environ.get("DEVFLOW_MODEL_ROOT", PROJECT_ROOT / "data/models"))
    / ("multilingual-e5-small")
    / MODEL_REVISION
)
_lock = threading.Lock()


class LocalEmbedder:
    key = MODEL_KEY

    def __init__(self):
        import onnxruntime as ort

        for name, digest in MODEL_FILES.items():
            path = MODEL_DIR / name
            if not path.is_file():
                raise DomainError(
                    503, "embedding_not_ready", "请先运行 scripts/prepare_rag.py 下载本地向量模型"
                )
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise DomainError(
                    503, "embedding_corrupt", "本地向量模型校验失败，请重新运行 prepare_rag.py"
                )
        self.tokenizer = Tokenizer.from_file(str(MODEL_DIR / "tokenizer.json"))
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        self.inference_tokenizer = Tokenizer.from_file(str(MODEL_DIR / "tokenizer.json"))
        self.inference_tokenizer.enable_padding(pad_id=1, pad_token="<pad>")
        self.inference_tokenizer.enable_truncation(max_length=512)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self.session = ort.InferenceSession(
            str(MODEL_DIR / "onnx/model_quantized.onnx"),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )

    def encode(self, texts, *, query=False):
        prefix = "query: " if query else "passage: "
        vectors = []
        for offset in range(0, len(texts), 8):
            encoded = self.inference_tokenizer.encode_batch(
                [prefix + t for t in texts[offset : offset + 8]]
            )
            inputs = {
                "input_ids": np.asarray([t.ids for t in encoded], dtype=np.int64),
                "attention_mask": np.asarray([t.attention_mask for t in encoded], dtype=np.int64),
                "token_type_ids": np.asarray([t.type_ids for t in encoded], dtype=np.int64),
            }
            inputs = {item.name: inputs[item.name] for item in self.session.get_inputs()}
            hidden = self.session.run(None, inputs)[0]
            mask = inputs["attention_mask"][..., None]
            pooled = (hidden * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1)
            pooled /= np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-12)
            vectors.extend(pooled.astype(np.float32).tolist())
        return vectors


@lru_cache(maxsize=1)
def _embedder():
    return LocalEmbedder()


def get_embedder():
    with _lock:
        return _embedder()
