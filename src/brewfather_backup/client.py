"""A thin Brewfather API v2 client built on ``httpx``.

Handles Basic auth, list pagination (``limit`` + ``start_after``), fetching full
records (``complete=true``), and transparent retries on transient failures —
``429``/``5xx`` responses and connection-level errors — using ``Retry-After``
when present and exponential backoff with jitter otherwise.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Any, Self

import httpx

from .config import Settings

# Brewfather caps page size at 50 documents per request.
PAGE_SIZE = 50

# Status codes worth retrying: rate limiting plus transient server errors.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

# Cap how much of an error body we echo into exception messages.
_MAX_ERROR_BODY = 500


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
        backoff_factor: float = 0.5,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._sleep = sleep
        self._max_retries = max_retries
        self._backoff_factor = backoff_factor
        self._jitter = jitter
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

    def _backoff(self, attempt: int) -> float:
        """Exponential backoff (in seconds) with additive jitter for ``attempt``."""
        return self._backoff_factor * (2.0**attempt) + self._jitter()

    def _request(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        """GET ``path``, retrying transient failures and raising on others.

        Retries cover connection-level errors and :data:`RETRYABLE_STATUS`
        responses, honoring ``Retry-After`` when present. Non-retryable error
        statuses raise immediately; exhausted retries raise :class:`BrewfatherError`.
        """
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.get(path, params=params)
            except httpx.TransportError as exc:
                if attempt == self._max_retries:
                    raise BrewfatherError(
                        f"GET {path} failed after {self._max_retries} retries: {exc}"
                    ) from exc
                self._sleep(self._backoff(attempt))
                continue
            if response.status_code in RETRYABLE_STATUS:
                if attempt == self._max_retries:
                    raise BrewfatherError(
                        f"GET {path} still failing with {response.status_code} "
                        f"after {self._max_retries} retries"
                    )
                self._sleep(_retry_after_seconds(response, default=self._backoff(attempt)))
                continue
            if response.is_error:
                raise BrewfatherError(
                    f"GET {path} failed with {response.status_code}: {_truncate(response.text)}"
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
        for summary in self.paginate(path):
            yield self.get(path, summary["_id"])


def _retry_after_seconds(
    response: httpx.Response, default: float = 1.0, *, now: datetime | None = None
) -> float:
    """Seconds to wait per ``Retry-After``; supports delta-seconds and HTTP-date."""
    raw = response.headers.get("Retry-After")
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return default
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    now = now or datetime.now(UTC)
    return max(0.0, (retry_at - now).total_seconds())


def _truncate(text: str, limit: int = _MAX_ERROR_BODY) -> str:
    """Trim ``text`` to ``limit`` characters, marking elision with an ellipsis."""
    if len(text) <= limit:
        return text
    return text[:limit] + "…"
