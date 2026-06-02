from pathlib import Path

import pytest

from brewfather_backup.config import Settings


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BREWFATHER_USER_ID", "user123")
    monkeypatch.setenv("BREWFATHER_API_KEY", "secret456")

    settings = Settings()

    assert settings.user_id == "user123"
    assert settings.api_key == "secret456"
    # Defaults
    assert settings.base_url == "https://api.brewfather.app/v2"
    assert settings.output_dir == Path("backups")
    assert settings.request_timeout == 30.0


def test_missing_credentials_raise_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BREWFATHER_USER_ID", raising=False)
    monkeypatch.delenv("BREWFATHER_API_KEY", raising=False)

    with pytest.raises(ValueError) as exc_info:
        Settings(_env_file=None)  # type: ignore[call-arg]

    message = str(exc_info.value)
    assert "user_id" in message
    assert "api_key" in message


def test_overrides_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BREWFATHER_USER_ID", "u")
    monkeypatch.setenv("BREWFATHER_API_KEY", "k")
    monkeypatch.setenv("BREWFATHER_BASE_URL", "https://example.test/v2")
    monkeypatch.setenv("BREWFATHER_OUTPUT_DIR", "/tmp/bf")
    monkeypatch.setenv("BREWFATHER_REQUEST_TIMEOUT", "10")

    settings = Settings()

    assert settings.base_url == "https://example.test/v2"
    assert settings.output_dir == Path("/tmp/bf")
    assert settings.request_timeout == 10.0
