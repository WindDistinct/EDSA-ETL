from __future__ import annotations

import logging
from datetime import datetime

import httpx
import pytest

from domain.models import DateRange
from infrastructure.fmtrack_client import FMTrackClient
from logging_config import RedactSecretsFilter

CREDENTIALS = [
    {"name": "default", "api_key": "KEY-A"},
    {"name": "inter", "api_key": "KEY-B"},
]


def _client(handler, credentials=CREDENTIALS) -> FMTrackClient:
    return FMTrackClient(credentials=credentials, transport=httpx.MockTransport(handler))


def test_get_objects_merges_credentials_and_skips_failing_one():

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["api_key"] == "KEY-A":
            return httpx.Response(200, json=[{"id": "o1", "name": "AAA111", "imei": 1}])
        return httpx.Response(403)

    objects = _client(handler).get_objects()

    assert list(objects) == ["AAA111"]
    assert objects["AAA111"].credential == "default"


def test_get_objects_combines_vehicles_from_both_keys():

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["api_key"] == "KEY-A":
            return httpx.Response(200, json=[{"id": "o1", "name": "AAA111"}])
        return httpx.Response(200, json=[{"id": "o2", "name": "BBB222"}, {"id": "o3", "name": "AAA111"}])

    objects = _client(handler).get_objects()

    assert objects["AAA111"].object_id == "o1"
    assert objects["BBB222"].credential == "inter"


def test_coordinates_use_only_the_vehicle_credential():

    used_keys: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/objects":
            if request.url.params["api_key"] == "KEY-A":
                return httpx.Response(200, json=[])
            return httpx.Response(200, json=[{"id": "o2", "name": "BBB222"}])
        used_keys.append(request.url.params["api_key"])
        return httpx.Response(200, json={"items": [], "continuation_token": None})

    client = _client(handler)
    client.get_objects()
    client.get_object_coordinates("o2", "2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z")

    assert used_keys == ["KEY-B"]


def test_empty_api_keys_are_ignored():

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params["api_key"])
        return httpx.Response(200, json=[])

    _client(handler, [{"name": "default", "api_key": "KEY-A"}, {"name": "inter", "api_key": ""}]).get_objects()

    assert seen == ["KEY-A"]


def test_errors_do_not_expose_api_key():

    client = _client(lambda request: httpx.Response(404))

    with pytest.raises(RuntimeError) as info:
        client.get_object_coordinates("o9", "2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z")

    assert "KEY-" not in str(info.value)
    assert "KEY-" not in str(info.value.__cause__)


def test_redact_filter_masks_api_key():

    record = logging.LogRecord("x", logging.ERROR, __file__, 1, "GET %s", ("https://h/objects?version=2&api_key=SECRET&x=1",), None)

    RedactSecretsFilter().filter(record)

    assert record.getMessage() == "GET https://h/objects?version=2&api_key=***&x=1"


def test_fetch_track_follows_pagination_and_converts_to_lima_time():

    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append(params)
        item = lambda dt, lat: {"datetime": dt, "position": {"latitude": lat, "longitude": -77.0, "speed": 10}, "ignition_status": "ON"}  # noqa: E731
        if "continuation_token" not in params:
            return httpx.Response(200, json={"items": [item("2026-07-06T14:00:00.000Z", -12.0)], "continuation_token": "next"})
        return httpx.Response(200, json={"items": [item("2026-07-07T03:30:00.000Z", -12.1)], "continuation_token": None})

    points = _client(handler).fetch_track(
        "o1", DateRange(start=datetime(2026, 7, 6, 0, 0), end=datetime(2026, 7, 6, 23, 59, 59))
    )

    # 14:00Z -> 09:00 Lima; 03:30Z del 07 -> 22:30 Lima del 06
    assert [p.datetime for p in points] == ["2026-07-06T09:00:00", "2026-07-06T22:30:00"]
    assert [p.latitude for p in points] == [-12.0, -12.1]
    assert points[0].ignition_status == "ON"

    assert calls[0]["from_datetime"] == "2026-07-06T00:00:00.000-05:00"
    assert calls[0]["to_datetime"] == "2026-07-06T23:59:59.000-05:00"
    assert calls[0]["limit"] == "1000"
    assert calls[1]["continuation_token"] == "next"
