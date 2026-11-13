# 文件用途：读取服务端环境配置，并隐藏密钥等敏感字段。
import os
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

PROJECT_ROOT = Path(os.environ.get("DEVFLOW_PROJECT_ROOT", Path(__file__).resolve().parents[4]))


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
    memory_recall_strategy: Literal["none", "recent", "semantic"] = "recent"
    analysis_executor: Literal["simulation", "agent"] = "agent"
    model_timeout_seconds: int = Field(default=90, ge=5, le=180)
    model_max_output_tokens: int = Field(default=20000, ge=256, le=20000)
    context_input_tokens: int = Field(default=120000, ge=2000, le=120000)
    budget_total_cny: Decimal = Field(default=Decimal("200"), gt=0)
    budget_warning_cny: Decimal = Field(default=Decimal("140"), ge=0)
    budget_stop_cny: Decimal = Field(default=Decimal("180"), gt=0)
    dashscope_api_key: SecretStr = SecretStr("")
    dashscope_base_url: str = ""
    dashscope_model: str = "deepseek-v4.1-flash"
    github_token: SecretStr = SecretStr("")
    github_timeout_seconds: int = Field(default=30, ge=1, le=60)

    worker_lease_seconds: int = Field(default=30, ge=10, le=300)
    worker_poll_seconds: float = Field(default=1, ge=0.1, le=30)
    simulation_step_seconds: float = Field(default=3, ge=0, le=30)
    web_origin: str = "http://127.0.0.1:3000"

    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "devflow"
    postgres_user: str = "devflow"
    postgres_password: SecretStr = SecretStr("devflow-local")

    @model_validator(mode="after")
    def ordered_budget(self):
        if not self.budget_warning_cny < self.budget_stop_cny <= self.budget_total_cny:
            raise ValueError("预算必须满足提醒阈值 < 停止阈值 <= 总预算")
        return self

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


def validate_service_configuration(settings):
    """启动前只做本地配置校验，不请求供应商或修改账本。"""
    origin = urlsplit(settings.web_origin)
    if (
        origin.scheme not in {"http", "https"}
        or not origin.hostname
        or origin.username
        or origin.password
        or origin.query
        or origin.fragment
        or origin.path not in {"", "/"}
    ):
        raise ValueError("WEB_ORIGIN必须是合法的HTTP/HTTPS来源")
    if settings.model_provider == "fake":
        return
    aliyun = settings.model_provider == "aliyun"
    key = settings.dashscope_api_key if aliyun else settings.deepseek_api_key
    if not key.get_secret_value().strip():
        raise ValueError("真实模型模式需要在服务端配置API Key")
    endpoint = settings.dashscope_base_url if aliyun else "https://api.deepseek.com"
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.port
    ):
        raise ValueError("真实模型端点必须是无鉴权信息的官方HTTPS Base URL")
    from devflow.errors import DomainError
    from devflow.runtime_policy import pricing

    try:
        pricing(
            settings.model_provider,
            settings.dashscope_model if aliyun else settings.deepseek_model,
            endpoint,
        )
    except DomainError as error:
        raise ValueError(error.message) from None
