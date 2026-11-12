# 文件用途：仅用标准库显式准备构建权重；优先复用已校验本地文件，否则下载固定官方版本。
import argparse
import ast
import hashlib
import json
import os
import shutil
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def model_spec():
    tree = ast.parse((ROOT / "apps/api/src/devflow/embeddings.py").read_text(encoding="utf-8"))
    wanted = {"MODEL_REPO", "MODEL_REVISION", "MODEL_FILES"}
    return {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in wanted
    }


def prepare(destination):
    spec = model_spec()
    relative = Path("multilingual-e5-small") / spec["MODEL_REVISION"]
    manifest = {}
    for name, expected in spec["MODEL_FILES"].items():
        target = Path(destination) / relative / name
        cached = ROOT / "data/models" / relative / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == expected:
            manifest[name] = expected
            continue
        temporary = target.with_suffix(".part")
        try:
            if cached.is_file() and hashlib.sha256(cached.read_bytes()).hexdigest() == expected:
                shutil.copyfile(cached, temporary)
            else:
                url = f"https://huggingface.co/{spec['MODEL_REPO']}/resolve/{spec['MODEL_REVISION']}/{name}"
                with urlopen(url, timeout=60) as response, temporary.open("wb") as out:
                    shutil.copyfileobj(response, out)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != expected:
                raise RuntimeError(f"Model SHA256 mismatch: {name}")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        manifest[name] = expected
    (Path(destination) / "MODEL-MANIFEST.json").write_text(
        json.dumps(
            {
                "repository": spec["MODEL_REPO"],
                "revision": spec["MODEL_REVISION"],
                "files": manifest,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\r\n",
    )
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / ".cache/build-models"))
    args = parser.parse_args()
    print(json.dumps(prepare(args.output), indent=2))


if __name__ == "__main__":
    main()
