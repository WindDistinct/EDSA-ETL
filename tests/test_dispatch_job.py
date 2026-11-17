from __future__ import annotations

from datetime import datetime

from openpyxl import load_workbook

from application.jobs.dispatch_job import DispatchJob
from domain.models import DateRange, TripStatus
from tests.conftest import FakeTrackProvider, point, vehicle


class FakeDispatchClient:
    """
    Doble de prueba de LucaClient para el rol de dispatch_client. No hace red.
    """

    def __init__(self, despachos: list[dict]):
        self._despachos = despachos
        self.calls: list[tuple[str, str]] = []

    def get_dispatch_records(self, fecha_inicio: str, fecha_fin: str) -> list[dict]:
        self.calls.append((fecha_inicio, fecha_fin))
        return list(self._despachos)


DESPACHO = {
    "ruc_empresa": "20123456789",
    "placa": "A0P736",
    "codigo_ruta": "R1",
    "fecha": "2026-07-06",
    "hora": "08:00:00",
    "hora_real_ultimo_punto": "Mon Jul 06 2026 14:00:00 GMT-0500 (hora estándar de Perú)",
    "hora_calculada_ultimo_punto": None,
    "sentido": "ida",
    "conductor": "PEREZ, JUAN, 12345678",
}


def test_dispatch_job_uses_dispatch_client_for_despachos_and_track_client_for_gps(tmp_path):

    dispatch_client = FakeDispatchClient([DESPACHO])
    track_client = FakeTrackProvider(
        objects={"A0P736": vehicle("A0P736", "obj-1")},
        tracks={"obj-1": [point("2026-07-06T09:00:00")]},
    )

    output_file = tmp_path / "out.xlsx"

    report = DispatchJob(dispatch_client, track_client).run(
        fecha_inicio="2026-07-01",
        fecha_fin="2026-07-10",
        output_file=str(output_file),
    )

    assert dispatch_client.calls == [("2026-06-30", "2026-07-10")]
    assert (report.processed, report.track_points) == (1, 1)
    assert track_client.ranges["obj-1"] == DateRange(datetime(2026, 7, 6, 8, 0), datetime(2026, 7, 6, 14, 0))

    row = [c.value for c in load_workbook(output_file)["2026-07-06"][2]]

    assert row[9] == "0"  # sentido "ida" -> 0
    assert row[10] == "12345678"  # documento del conductor


def test_dispatch_job_works_when_dispatch_and_track_client_are_the_same_object(tmp_path):

    class FakeLucaLikeClient(FakeDispatchClient, FakeTrackProvider):
        def __init__(self, despachos, objects, tracks):
            FakeDispatchClient.__init__(self, despachos)
            FakeTrackProvider.__init__(self, objects=objects, tracks=tracks)

    client = FakeLucaLikeClient(
        [DESPACHO],
        {"A0P736": vehicle("A0P736", "A0P736", credential="luca")},
        {"A0P736": [point("2026-07-06T09:00:00")]},
    )

    report = DispatchJob(client, client).run(
        fecha_inicio="2026-07-01",
        fecha_fin="2026-07-10",
        output_file=str(tmp_path / "out.xlsx"),
    )

    assert (report.processed, report.track_points) == (1, 1)


def test_dispatch_job_clips_track_range_to_window_and_skips_trips_outside(tmp_path):

    # 08:00 -> 14:00: se cruza con la ventana 10:00 -> 12:00
    dentro = {**DESPACHO, "placa": "DENTRO"}

    # 15:30 -> 18:00: no tiene track points dentro de la ventana
    fuera = {
        **DESPACHO,
        "placa": "FUERA",
        "hora": "15:30:00",
        "hora_real_ultimo_punto": "Mon Jul 06 2026 18:00:00 GMT-0500 (hora estándar de Perú)",
    }

    dispatch_client = FakeDispatchClient([dentro, fuera])
    track_client = FakeTrackProvider(
        objects={p: vehicle(p, p) for p in ("DENTRO", "FUERA")},
        tracks={"DENTRO": [point("2026-07-06T10:00:00")]},
    )

    output_file = tmp_path / "out.xlsx"

    report = DispatchJob(dispatch_client, track_client).run(
        fecha_inicio="2026-07-06 10:00",
        fecha_fin="2026-07-06 12:00",
        output_file=str(output_file),
    )

    assert dispatch_client.calls == [("2026-07-05", "2026-07-06")]
    assert (report.total, report.processed) == (1, 1)
    assert track_client.ranges == {"DENTRO": DateRange(datetime(2026, 7, 6, 10, 0), datetime(2026, 7, 6, 12, 0))}

    sheet = load_workbook(output_file)["2026-07-06"]

    # FECHORA_INI_VIAJE sigue siendo la salida real, no el inicio de la ventana
    assert "08:00" in str(sheet.cell(row=2, column=5).value)


def test_dispatch_job_reports_despachos_without_valid_range(tmp_path):

    sin_fin = {**DESPACHO, "placa": "SINFIN", "hora_real_ultimo_punto": None}
    sin_salida = {**DESPACHO, "placa": "SINSALIDA", "hora": None, "fecha": None}

    dispatch_client = FakeDispatchClient([sin_fin, sin_salida, DESPACHO])
    track_client = FakeTrackProvider(
        objects={"A0P736": vehicle("A0P736", "obj-1")},
        tracks={"obj-1": [point("2026-07-06T09:00:00")]},
    )

    report = DispatchJob(dispatch_client, track_client).run(
        fecha_inicio="2026-07-01",
        fecha_fin="2026-07-10",
        output_file=str(tmp_path / "out.xlsx"),
    )

    status = {o.placa: o.status for o in report.outcomes}

    assert status == {
        "SINFIN": TripStatus.FILA_INVALIDA,
        "SINSALIDA": TripStatus.FILA_INVALIDA,
        "A0P736": TripStatus.OK,
    }
    assert report.errors == 2
