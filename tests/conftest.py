import pytest

from brewfather_backup.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        user_id="user123",
        api_key="secret456",
        base_url="https://api.brewfather.app/v2",
        _env_file=None,  # type: ignore[call-arg]
    )
