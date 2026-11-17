from __future__ import annotations

import json
from datetime import datetime

import httpx

from domain.models import DateRange
from infrastructure.luca_client import LucaClient


def _ms(iso_utc: str) -> int:
    return int(datetime.fromisoformat(iso_utc).timestamp() * 1000)


def test_fetch_track_queries_each_local_day_filters_and_sorts():

    fechas: list[str] = []

    puntos = {
        # 2026-07-06 Lima: 04:00 (fuera, antes del rango), 23:00 y 23:30
        "2026-07-06": [
            {"timestamp_ms": _ms("2026-07-07T04:30:00+00:00"), "latitude": -12.3, "longitude": -77.0, "speed": 5},
            {"timestamp_ms": _ms("2026-07-07T04:00:00+00:00"), "latitude": -12.2, "longitude": -77.0, "speed": 5},
            {"timestamp_ms": _ms("2026-07-06T09:00:00+00:00"), "latitude": -12.0, "longitude": -77.0, "speed": 5},
        ],
        # 2026-07-07 Lima: 00:30 (dentro) y 02:00 (fuera, después del rango)
        "2026-07-07": [
            {"timestamp_ms": _ms("2026-07-07T05:30:00.250+00:00"), "latitude": -12.4, "longitude": -77.0, "speed": 5},
            {"timestamp_ms": _ms("2026-07-07T07:00:00+00:00"), "latitude": -12.5, "longitude": -77.0, "speed": 5},
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        fechas.append(body["fecha"])
        return httpx.Response(200, json={"puntos": puntos[body["fecha"]]})

    client = LucaClient(empresa=1, ruta=2, transport=httpx.MockTransport(handler))

    points = client.fetch_track(
        "A0P736", DateRange(start=datetime(2026, 7, 6, 22, 0), end=datetime(2026, 7, 7, 1, 0))
    )

    assert fechas == ["2026-07-06", "2026-07-07"]
    assert [p.datetime for p in points] == ["2026-07-06T23:00:00", "2026-07-06T23:30:00", "2026-07-07T00:30:00"]
    assert [p.latitude for p in points] == [-12.2, -12.3, -12.4]
