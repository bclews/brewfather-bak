import base64

import httpx
import pytest
import respx

from brewfather_backup.client import BrewfatherClient, BrewfatherError
from brewfather_backup.config import Settings

BASE = "https://api.brewfather.app/v2"


def _page(n: int, *, start: int) -> list[dict]:
    return [{"_id": f"id{i}", "name": f"item{i}"} for i in range(start, start + n)]


@respx.mock
def test_request_sends_basic_auth(settings: Settings) -> None:
    route = respx.get(f"{BASE}/recipes").mock(return_value=httpx.Response(200, json=[]))

    with BrewfatherClient(settings) as client:
        list(client.paginate("/recipes"))

    expected = base64.b64encode(b"user123:secret456").decode()
    assert route.calls.last.request.headers["Authorization"] == f"Basic {expected}"


@respx.mock
def test_paginate_walks_all_pages(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        start_after = request.url.params.get("start_after")
        assert request.url.params.get("limit") == "50"
        if start_after is None:
            return httpx.Response(200, json=_page(50, start=0))
        if start_after == "id49":
            return httpx.Response(200, json=_page(10, start=50))
        return httpx.Response(200, json=[])

    respx.get(f"{BASE}/recipes").mock(side_effect=handler)

    with BrewfatherClient(settings) as client:
        items = list(client.paginate("/recipes"))

    assert len(items) == 60
    assert items[0]["_id"] == "id0"
    assert items[-1]["_id"] == "id59"


@respx.mock
def test_paginate_stops_on_short_first_page(settings: Settings) -> None:
    route = respx.get(f"{BASE}/recipes").mock(
        return_value=httpx.Response(200, json=_page(3, start=0))
    )

    with BrewfatherClient(settings) as client:
        items = list(client.paginate("/recipes"))

    assert len(items) == 3
    assert route.call_count == 1


@respx.mock
def test_get_requests_complete_record(settings: Settings) -> None:
    route = respx.get(f"{BASE}/recipes/id42").mock(
        return_value=httpx.Response(200, json={"_id": "id42", "name": "Full", "fermentables": []})
    )

    with BrewfatherClient(settings) as client:
        record = client.get("/recipes", "id42")

    assert record["_id"] == "id42"
    assert route.calls.last.request.url.params.get("complete") == "true"


@respx.mock
def test_iter_full_paginates_then_fetches_each(settings: Settings) -> None:
    respx.get(f"{BASE}/recipes").mock(return_value=httpx.Response(200, json=_page(2, start=0)))
    respx.get(f"{BASE}/recipes/id0").mock(
        return_value=httpx.Response(200, json={"_id": "id0", "complete": True})
    )
    respx.get(f"{BASE}/recipes/id1").mock(
        return_value=httpx.Response(200, json={"_id": "id1", "complete": True})
    )

    with BrewfatherClient(settings) as client:
        records = list(client.iter_full("/recipes"))

    assert [r["_id"] for r in records] == ["id0", "id1"]
    assert all(r["complete"] for r in records)


@respx.mock
def test_retries_on_429_honoring_retry_after(settings: Settings) -> None:
    responses = [
        httpx.Response(429, headers={"Retry-After": "2"}),
        httpx.Response(200, json=[]),
    ]
    route = respx.get(f"{BASE}/recipes").mock(side_effect=responses)

    slept: list[float] = []
    with BrewfatherClient(settings, sleep=slept.append) as client:
        list(client.paginate("/recipes"))

    assert route.call_count == 2
    assert slept == [2.0]


@respx.mock
def test_raises_on_other_http_errors(settings: Settings) -> None:
    respx.get(f"{BASE}/recipes").mock(return_value=httpx.Response(401, text="nope"))

    with BrewfatherClient(settings) as client, pytest.raises(BrewfatherError) as exc_info:
        list(client.paginate("/recipes"))

    assert "401" in str(exc_info.value)
