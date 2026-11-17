from __future__ import annotations

from datetime import datetime

import pandas as pd
from openpyxl import load_workbook

from application.run_trips import run_trips
from domain.models import DateRange, Sentido, TrackPoint, Trip, TripOutcome, TripStatus
from infrastructure.track_record_writer import TrackRecordWriter
from tests.conftest import FakeTrackProvider, point, vehicle

RANGE = DateRange(start=datetime(2026, 7, 6, 0, 0), end=datetime(2026, 7, 7, 23, 59, 59))


def trip(placa: str = "A0P736", ref: str = "1", **kwargs) -> Trip:
    return Trip(placa=placa, date_range=RANGE, ref=ref, **kwargs)


class MemorySink:
    """Sink en memoria; existing devuelve lo que se le indique por ref."""

    def __init__(self, previous: dict[str, str] | None = None):
        self.previous = previous or {}
        self.written: dict[str, tuple[Trip, list[TrackPoint]]] = {}

    def existing(self, trip: Trip) -> str | None:
        return self.previous.get(trip.ref)

    def write(self, trip: Trip, points: list[TrackPoint]) -> str:
        self.written[trip.ref] = (trip, points)
        return f"{trip.ref}.csv"


def test_run_trips_writes_atu_day_sheets(tmp_path):

    provider = FakeTrackProvider(
        objects={"A0P736": vehicle("A0P736", "obj-1")},
        tracks={"obj-1": [point("2026-07-06T09:00:00"), point("2026-07-07T01:00:00", lat=-12.1)]},
    )

    output_file = tmp_path / "out.xlsx"

    with TrackRecordWriter(str(output_file), include_ignition_status=True) as sink:
        report = run_trips(
            [trip(ruc_empresa="123", codigo_ruta="R1", sentido=Sentido.IDA, nro_doc_conductor="12345678")],
            provider,
            sink,
        )

    assert (report.total, report.processed, report.errors, report.track_points) == (1, 1, 0, 2)

    workbook = load_workbook(output_file)

    assert workbook.sheetnames == ["2026-07-06", "2026-07-07"]

    header = [c.value for c in workbook["2026-07-06"][1]]
    row = [c.value for c in workbook["2026-07-06"][2]]

    assert header[1] == "PLACA" and header[-1] == "IGNITION_STATUS"
    assert row[1] == "A0P736"
    assert row[2] == "863238075031916"  # IMEI completado desde el catálogo
    assert row[6] == -12.0
    assert row[9] == "0"  # Sentido.IDA -> código ATU
    assert row[-1] == "ON"


def test_run_trips_reports_each_status():

    provider = FakeTrackProvider(
        objects={p: vehicle(p) for p in ("OK1", "VACIO", "FALLA")},
        tracks={"obj-OK1": [point("2026-07-06T09:00:00")]},
        errors={"obj-FALLA": RuntimeError("FM Track /objects/x/coordinates -> HTTP 503")},
    )

    invalida = TripOutcome(status=TripStatus.FILA_INVALIDA, ref="5", placa="MAL", detail="sin fecha")

    sink = MemorySink()

    report = run_trips(
        [trip("OK1", "1"), trip("VACIO", "2"), trip("FALLA", "3"), trip("NOESTA", "4"), invalida],
        provider,
        sink,
    )

    status = {o.ref: o.status for o in report.outcomes}

    assert status == {
        "1": TripStatus.OK,
        "2": TripStatus.SIN_PUNTOS,
        "3": TripStatus.ERROR,
        "4": TripStatus.SIN_OBJECT_ID,
        "5": TripStatus.FILA_INVALIDA,
    }
    assert list(sink.written) == ["1"]
    assert (report.processed, report.errors, report.track_points) == (2, 3, 1)

    error = next(o for o in report.outcomes if o.ref == "3")
    assert "HTTP 503" in error.detail


def test_run_trips_skips_trips_already_in_sink():

    provider = FakeTrackProvider(objects={"A0P736": vehicle("A0P736")})

    sink = MemorySink(previous={"1": "1_A0P736_20260706_090000.csv"})

    report = run_trips([trip()], provider, sink)

    assert report.outcomes[0].status is TripStatus.EXISTENTE
    assert report.outcomes[0].output == "1_A0P736_20260706_090000.csv"
    assert provider.ranges == {}  # no se consultó al proveedor


def test_run_trips_keeps_imei_from_source_over_catalog():

    provider = FakeTrackProvider(
        objects={"A0P736": vehicle("A0P736", imei="CATALOGO")},
        tracks={"obj-A0P736": [point("2026-07-06T09:00:00")]},
    )

    sink = MemorySink()

    run_trips([trip(imei="FILA")], provider, sink)

    assert sink.written["1"][0].imei == "FILA"


def test_run_trips_resolves_trips_concurrently():

    plates = [f"P{i:03d}" for i in range(20)]

    provider = FakeTrackProvider(
        objects={p: vehicle(p) for p in plates},
        tracks={f"obj-{p}": [point("2026-07-06T09:00:00")] for p in plates},
    )

    report = run_trips([trip(p, str(i)) for i, p in enumerate(plates)], provider, MemorySink(), workers=8)

    assert (report.total, report.processed, report.track_points) == (20, 20, 20)


def test_report_csv_is_ordered_by_numeric_ref(tmp_path):

    provider = FakeTrackProvider(objects={p: vehicle(p) for p in ("A", "B", "C")})

    report = run_trips([trip("C", "10"), trip("A", "2"), trip("B", "1")], provider, MemorySink())

    path = report.write_csv(tmp_path / "_resumen.csv")

    df = pd.read_csv(path, dtype=str)

    assert list(df["REF"]) == ["1", "2", "10"]
    assert list(df.columns) == ["REF", "PLACA", "INICIO", "FIN", "ESTADO", "PUNTOS", "ARCHIVO", "DETALLE"]
    assert df.loc[0, "INICIO"] == "2026-07-06 00:00:00"
