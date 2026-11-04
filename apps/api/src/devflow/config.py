# 文件用途：读取服务端环境配置，并隐藏密钥等敏感字段。
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

PROJECT_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_source: Literal["fixture", "github"] = "fixture"
    fixture_storage: Literal["database", "files"] = "database"
    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_model: str = "deepseek-flash"
    model_provider: Literal["fake", "deepseek", "aliyun"] = "fake"
    analysis_executor: Literal["simulation", "agent"] = "agent"
    model_timeout_seconds: int = Field(default=90, ge=5, le=180)
    model_max_output_tokens: int = Field(default=2000, ge=256, le=8000)
    context_input_tokens: int = Field(default=12000, ge=2000, le=64000)
    dashscope_api_key: SecretStr = SecretStr("")
    dashscope_base_url: str = ""
    dashscope_model: str = "deepseek-v4.1-flash"
    github_token: SecretStr = SecretStr("")
    github_timeout_seconds: int = Field(default=30, ge=1, le=60)

    worker_lease_seconds: int = Field(default=30, ge=10, le=300)
    worker_poll_seconds: float = Field(default=1, ge=0.1, le=30)
    simulation_step_seconds: float = Field(default=3, ge=0, le=30)

    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "devflow"
    postgres_user: str = "devflow"
    postgres_password: SecretStr = SecretStr("devflow-local")

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
