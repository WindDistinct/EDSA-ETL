from __future__ import annotations

from datetime import datetime

from domain.models import DateRange, Sentido, Trip
from infrastructure.trip_csv_writer import TripCsvWriter
from tests.conftest import point


def _trip(sentido=Sentido.VUELTA) -> Trip:
    return Trip(
        placa="A1I730",
        date_range=DateRange(start=datetime(2026, 10, 20, 10, 34), end=datetime(2026, 10, 20, 13, 0, 28)),
        sentido=sentido,
        ref="1",
    )


def test_writes_one_csv_named_after_first_point(tmp_path):

    sink = TripCsvWriter(tmp_path)

    # Desordenados a propósito: el nombre usa el primer punto en el tiempo.
    name = sink.write(
        _trip(),
        [point("2026-10-20T10:34:37", lat=-12.07566, speed=28), point("2026-10-20T10:34:17", lat=-12.0750933, speed=32)],
    )

    assert name == "1_A1I730_20261020_103417.csv"

    lines = (tmp_path / name).read_text(encoding="utf-8").splitlines()

    assert lines == [
        "latitud,longitud,timestamp,velocidad,sentido",
        "-12.0750933,-77.0,2026-10-20 10:34:17,32,V",
        "-12.07566,-77.0,2026-10-20 10:34:37,28,V",
    ]
    assert not list(tmp_path.glob("*.tmp"))


def test_existing_finds_previous_file_for_same_ref_and_plate(tmp_path):

    sink = TripCsvWriter(tmp_path)

    assert sink.existing(_trip()) is None

    (tmp_path / "1_A1I730_20261020_103417.csv").write_text("x")
    (tmp_path / "10_A1I730_20261020_103417.csv").write_text("x")

    assert sink.existing(_trip()) == "1_A1I730_20261020_103417.csv"
