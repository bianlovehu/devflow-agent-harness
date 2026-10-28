# 文件用途：使用真实 PostgreSQL 验证数据库就绪与向量运算。
import os

import pytest
from devflow.config import get_settings
from devflow.database import create_database_engine
from devflow.health import inspect_health
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.getenv("DEVFLOW_TEST_DATABASE") != "1",
    reason="Use scripts/check.ps1 -Integration with the local PostgreSQL container running",
)


def test_real_postgres_readiness_and_vector_distance() -> None:
    engine = create_database_engine(get_settings())
    try:
        result = inspect_health(engine)
        assert result.status == "ok", result.model_dump()
        with engine.connect() as connection:
            distance = connection.execute(
                text("SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector")
            ).scalar_one()
        assert distance == pytest.approx(1.0)
    finally:
        engine.dispose()
