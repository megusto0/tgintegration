from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import BaseSettings, Field, validator


class Settings(BaseSettings):
    ns_url: str = Field(..., env="NS_URL")
    ns_token: Optional[str] = Field(default=None, env="NS_TOKEN")
    ns_api_secret: Optional[str] = Field(default=None, env="NS_API_SECRET")
    tg_token: str = Field(..., env="TG_TOKEN")
    allowed_user_ids: List[int] = Field(default_factory=list, env="ALLOWED_USER_IDS")
    media_root: Path = Field(..., env="MEDIA_ROOT")
    media_base_url: str = Field(..., env="MEDIA_BASE_URL")
    app_base_url: str = Field(..., env="APP_BASE_URL")
    tg_chat_id: Optional[int] = Field(default=None, env="TG_CHAT_ID")
    host: str = Field("0.0.0.0", env="HOST")
    port: int = Field(8000, env="PORT")

    class Config:
        env_file = ".env"
        case_sensitive = False

    @validator("allowed_user_ids", pre=True)
    def _split_allowed_ids(cls, value: Optional[str]) -> List[int]:
        if not value:
            return []
        result: List[int] = []
        for chunk in str(value).split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                result.append(int(chunk))
            except ValueError as exc:  # noqa: B902
                raise ValueError(f"Invalid user id: {chunk}") from exc
        return result

    @validator("ns_url", "media_base_url", "app_base_url")
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def has_token(self) -> bool:
        return bool(self.ns_token)

    @property
    def has_api_secret(self) -> bool:
        return bool(self.ns_api_secret)


@lru_cache()
def get_settings() -> Settings:
    return Settings()
