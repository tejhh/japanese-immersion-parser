"""Application settings loaded from environment variables (prefix ``JIP_``)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JIP_", env_file=".env", extra="ignore")

    app_name: str = "Japanese Immersion Parser API"
    environment: Literal["development", "test", "production"] = "development"

    database_url: str = "postgresql://jip:jip@localhost:5432/jip"
    db_pool_min_size: int = Field(default=1, ge=1)
    db_pool_max_size: int = Field(default=10, ge=1)

    sudachi_dict: Literal["small", "core", "full"] = "core"
    sudachi_split_mode: Literal["A", "B", "C"] = "C"

    max_text_chars: int = Field(default=100_000, ge=1)
    store_tokens: bool = True

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
