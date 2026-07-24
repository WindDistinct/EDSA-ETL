from datetime import datetime

import pytest

from domain.models import DateRange, TrackPoint, TrackResult, Trip


def test_date_range_rejects_end_before_start():

    with pytest.raises(ValueError):
        DateRange(
            start=datetime(2026, 1, 2),
            end=datetime(2026, 1, 1),
        )


def test_date_range_allows_equal_start_and_end():

    dt = datetime(2026, 1, 1, 12, 0, 0)

    date_range = DateRange(start=dt, end=dt)

    assert date_range.start == dt
    assert date_range.end == dt


def _make_trip(**overrides) -> Trip:

    defaults = dict(
        ruc_empresa="123",
        placa="A0P736",
        imei="863238075031916",
        codigo_ruta="R1",
        sentido="0",
        nro_doc_conductor="12345678",
        object_id="obj-1",
        date_range=DateRange(
            start=datetime(2026, 1, 1),
            end=datetime(2026, 1, 2),
        ),
    )

    defaults.update(overrides)

    return Trip(**defaults)


def test_track_result_success_when_no_error():

    result = TrackResult(
        trip=_make_trip(),
        points=[
            TrackPoint(
                datetime="2026-01-01T00:00:00.000",
                latitude=-12.0,
                longitude=-77.0,
                speed=10.0,
            )
        ],
    )

    assert result.success is True


def test_track_result_failure_when_error_set():

    result = TrackResult(
        trip=_make_trip(),
        points=[],
        error="La fecha inicial es obligatoria.",
    )

    assert result.success is False
