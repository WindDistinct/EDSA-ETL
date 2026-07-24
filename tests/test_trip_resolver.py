from datetime import datetime

from application.trip_resolver import TripResolver
from domain.models import DateRange, Trip
from tests.conftest import FakeFMTrackClient


def _make_trip(object_id: str = "obj-1") -> Trip:

    return Trip(
        ruc_empresa="123",
        placa="A0P736",
        imei="863238075031916",
        codigo_ruta="R1",
        sentido="0",
        nro_doc_conductor="12345678",
        object_id=object_id,
        date_range=DateRange(
            start=datetime(2026, 7, 6, 0, 0, 0),
            end=datetime(2026, 7, 6, 23, 59, 59),
        ),
    )


def _item(dt: str, lat: float, lon: float, speed: float, ignition: str) -> dict:

    return {
        "datetime": dt,
        "position": {
            "latitude": lat,
            "longitude": lon,
            "speed": speed,
        },
        "ignition_status": ignition,
    }


def test_resolve_merges_paginated_pages():

    pages = {
        "obj-1": [
            {
                "items": [_item("2026-07-06T14:00:00.000Z", -12.0, -77.0, 10.0, "ON")],
                "continuation_token": "next",
            },
            {
                "items": [_item("2026-07-06T15:00:00.000Z", -12.1, -77.1, 20.0, "ON")],
                "continuation_token": None,
            },
        ]
    }

    client = FakeFMTrackClient(coordinate_pages=pages)

    resolver = TripResolver(client)

    result = resolver.resolve(_make_trip())

    assert result.success
    assert len(result.points) == 2
    assert result.points[0].latitude == -12.0
    assert result.points[1].latitude == -12.1


def test_resolve_filters_ignition_off_when_required():

    pages = {
        "obj-1": [
            {
                "items": [
                    _item("2026-07-06T14:00:00.000Z", -12.0, -77.0, 10.0, "OFF"),
                    _item("2026-07-06T15:00:00.000Z", -12.1, -77.1, 20.0, "ON"),
                ],
                "continuation_token": None,
            },
        ]
    }

    client = FakeFMTrackClient(coordinate_pages=pages)

    resolver = TripResolver(client, require_ignition_on=True)

    result = resolver.resolve(_make_trip())

    assert len(result.points) == 1
    assert result.points[0].ignition_status == "ON"


def test_resolve_returns_error_result_on_client_exception():

    class BoomClient:
        def get_object_coordinates(self, **kwargs):
            raise RuntimeError("boom")

    resolver = TripResolver(BoomClient())

    result = resolver.resolve(_make_trip())

    assert not result.success
    assert "boom" in result.error
    assert result.points == []
