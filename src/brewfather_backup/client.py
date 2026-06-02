"""A thin Brewfather API v2 client built on ``httpx``.

Handles Basic auth, list pagination (``limit`` + ``start_after``), fetching full
records (``complete=true``), and transparent retries on ``429`` responses while
honoring the ``Retry-After`` header.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from types import TracebackType
from typing import Any, Self

import httpx

from .config import Settings

# Brewfather caps page size at 50 documents per request.
PAGE_SIZE = 50


class BrewfatherError(RuntimeError):
    """Raised when the Brewfather API returns an unexpected error response."""


class BrewfatherClient:
    """Client for the Brewfather API.

    Usable as a context manager so the underlying HTTP connection is closed::

        with BrewfatherClient(settings) as client:
            recipes = list(client.iter_full("/recipes"))
    """

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 5,
    ) -> None:
        self._sleep = sleep
        self._max_retries = max_retries
        self._client = client or httpx.Client(
            base_url=settings.base_url,
            auth=(settings.user_id, settings.api_key),
            timeout=settings.request_timeout,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _request(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        """GET ``path``, retrying on 429 and raising on other error statuses."""
        for attempt in range(self._max_retries + 1):
            response = self._client.get(path, params=params)
            if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                if attempt == self._max_retries:
                    raise BrewfatherError(
                        f"GET {path} still rate-limited after {self._max_retries} retries"
                    )
                self._sleep(_retry_after_seconds(response))
                continue
            if response.is_error:
                raise BrewfatherError(
                    f"GET {path} failed with {response.status_code}: {response.text}"
                )
            return response
        # Unreachable: the loop either returns or raises.
        raise BrewfatherError(f"GET {path} exhausted retries")

    def paginate(self, path: str, **params: Any) -> Iterator[dict[str, Any]]:
        """Yield list-summary documents across all pages of a collection."""
        start_after: str | None = None
        while True:
            page_params = {**params, "limit": PAGE_SIZE}
            if start_after is not None:
                page_params["start_after"] = start_after
            page: list[dict[str, Any]] = self._request(path, page_params).json()
            yield from page
            if len(page) < PAGE_SIZE:
                return
            start_after = page[-1]["_id"]

    def get(self, path: str, record_id: str) -> dict[str, Any]:
        """Fetch a single record with all fields (``complete=true``)."""
        result: dict[str, Any] = self._request(
            f"{path}/{record_id}", {"complete": "true"}
        ).json()
        return result

    def iter_full(self, path: str) -> Iterator[dict[str, Any]]:
        """Paginate a collection then yield each record in full detail."""
        for summary in list(self.paginate(path)):
            yield self.get(path, summary["_id"])


def _retry_after_seconds(response: httpx.Response, default: float = 1.0) -> float:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default
