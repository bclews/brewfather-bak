"""Application configuration loaded from the environment / a ``.env`` file."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Brewfather backup settings.

    Credentials are required; everything else has a sensible default. Values are
    read from environment variables prefixed with ``BREWFATHER_`` (and a local
    ``.env`` file if present).
    """

    model_config = SettingsConfigDict(
        env_prefix="BREWFATHER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    user_id: str = Field(..., description="Brewfather user id (Settings -> API).")
    api_key: str = Field(..., description="Brewfather API key (Settings -> API).")

    base_url: str = "https://api.brewfather.app/v2"
    output_dir: Path = Path("backups")
    request_timeout: float = 30.0
    concurrency: int = Field(default=8, ge=1, description="Max concurrent record fetches.")

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        """Reject obviously malformed URLs at load time rather than at request time.

        Kept as a plain ``str`` (not ``HttpUrl``) so the value passes through to
        ``httpx`` unchanged; we only check the scheme.
        """
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return value
