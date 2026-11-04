# 文件用途：显式下载、校验固定版本的本地 E5 模型，不消耗模型 API 额度。
import hashlib
import os
import urllib.request

from devflow.embeddings import MODEL_DIR, MODEL_FILES, MODEL_REPO, MODEL_REVISION, get_embedder


def main():
    for name, digest in MODEL_FILES.items():
        target = MODEL_DIR / name
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
            print(f"Verified {name}", flush=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".part")
        url = f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{name}"
        print(f"Downloading {name}", flush=True)
        try:
            with urllib.request.urlopen(url, timeout=60) as source, temporary.open("wb") as out:
                while data := source.read(1024 * 1024):
                    out.write(data)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != digest:
                raise RuntimeError(f"SHA256 mismatch: {name}")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    model = get_embedder()
    print(f"Ready: {model.key}; dimensions={len(model.encode(['就绪'], query=True)[0])}")


if __name__ == "__main__":
    main()
