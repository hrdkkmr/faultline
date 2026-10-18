"""Application configuration, loaded from environment variables (and `.env` at the repo root)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    falkordb_host: str = Field(default="localhost", min_length=1)
    falkordb_port: int = Field(default=6379, ge=1, le=65535)
    falkordb_user: str = Field(default="falkordb", min_length=1)
    falkordb_password: str | None = Field(default=None, repr=False)
    graph_name: str = Field(default="faultline", alias="FAULTLINE_GRAPH", pattern=r"^[A-Za-z0-9_\-]+$")

    max_depth: int = Field(default=6, alias="FAULTLINE_MAX_DEPTH", ge=1, le=10)
    query_timeout_ms: int = Field(default=5000, alias="FAULTLINE_QUERY_TIMEOUT_MS", ge=100, le=60000)

    data_dir: Path = Field(default=Path("data"), alias="FAULTLINE_DATA_DIR")
    log_level: str = Field(default="INFO", alias="FAULTLINE_LOG_LEVEL")

    llm_provider: str = Field(default="", alias="FAULTLINE_LLM_PROVIDER")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY", repr=False)
    llm_model: str = Field(default="claude-opus-5-5", alias="FAULTLINE_LLM_MODEL")
    llm_timeout_s: float = Field(default=20.0, alias="FAULTLINE_LLM_TIMEOUT_S", gt=0, le=120)

    @field_validator("falkordb_password", "anthropic_api_key", mode="before")
    @classmethod
    def _empty_to_none(cls, v: object) -> object:
        return None if v == "" else v

    @field_validator("log_level")
    @classmethod
    def _valid_level(cls, v: str) -> str:
        v = v.upper()
        if v not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ValueError(f"invalid FAULTLINE_LOG_LEVEL: {v}")
        return v

    @field_validator("llm_provider")
    @classmethod
    def _valid_provider(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in {"", "none", "anthropic"}:
            raise ValueError(f"unsupported FAULTLINE_LLM_PROVIDER: {v!r} (expected '' or 'anthropic')")
        return "" if v == "none" else v

    @property
    def data_path(self) -> Path:
        return self.data_dir if self.data_dir.is_absolute() else REPO_ROOT / self.data_dir


@lru_cache
def get_settings() -> Settings:
    return Settings()
