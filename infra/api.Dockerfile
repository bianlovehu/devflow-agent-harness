# 文件用途：构建锁定Python依赖与离线E5权重的API/worker共用镜像。
FROM mirror.gcr.io/library/python:3.11.17-slim-bookworm@sha256:f06d01d4ba3f8ad5af45a3ec87df19c1d317d8e8961edc0fabda61811af6f7cf AS app
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 \
    DEVFLOW_PROJECT_ROOT=/app DEVFLOW_MODEL_ROOT=/opt/devflow-models \
    PATH=/app/.venv/bin:$PATH UV_LINK_MODE=copy
WORKDIR /app
RUN pip install --no-cache-dir uv==0.11.3
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
# 依赖下载与代码变更分层，源码变更无需重复下载锁定依赖。
COPY apps/api ./apps/api
RUN uv sync --frozen --no-dev --no-editable
COPY alembic.ini ./
COPY fixtures ./fixtures
COPY scripts/prepare_rag.py ./scripts/prepare_rag.py
# 来自显式prepare_model_assets.py步骤；构建与普通请求均不隐式下载权重。
COPY --from=model_weights / /opt/devflow-models/
RUN python -c "from devflow.embeddings import get_embedder; get_embedder()"
RUN groupadd --gid 10001 devflow && useradd --uid 10001 --gid 10001 --no-create-home devflow \
    && mkdir -p /app/data && chown -R devflow:devflow /app/data
USER devflow
CMD ["python", "-m", "uvicorn", "devflow.main:app", "--host", "0.0.0.0", "--port", "8000"]
