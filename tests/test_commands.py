from __future__ import annotations

from datetime import datetime

import pandas as pd
from openpyxl import load_workbook

from application import commands
from domain.models import DateRange
from tests.conftest import FakeTrackProvider, point, vehicle

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


class FakeDispatchClient:
    """Doble de LucaClient en el rol de origen de despachos. No hace red."""

    def __init__(self, despachos: list[dict]):
        self._despachos = despachos
        self.calls: list[tuple[str, str]] = []

    def get_dispatch_records(self, fecha_inicio: str, fecha_fin: str) -> list[dict]:
        self.calls.append((fecha_inicio, fecha_fin))
        return list(self._despachos)


# despachos

def test_despachos_writes_atu_excel_and_report(tmp_path):

    dispatch = FakeDispatchClient([DESPACHO])
    provider = FakeTrackProvider(
        objects={"A0P736": vehicle("A0P736", "obj-1")},
        tracks={"obj-1": [point("2026-07-06T09:00:00")]},
    )

    output = tmp_path / "out.xlsx"

    report = commands.despachos(dispatch, provider, start="2026-07-01", end="2026-07-10", output=str(output))

    assert dispatch.calls == [("2026-06-30", "2026-07-10")]
    assert (report.processed, report.track_points) == (1, 1)
    assert provider.ranges["obj-1"] == DateRange(datetime(2026, 7, 6, 8, 0), datetime(2026, 7, 6, 14, 0))

    row = [c.value for c in load_workbook(output)["2026-07-06"][2]]

    assert row[9] == "0"  # sentido "ida" -> 0
    assert row[10] == "12345678"  # documento del conductor
    assert (tmp_path / "out_resumen.csv").exists()


def test_despachos_clips_range_to_window(tmp_path):

    fuera = {
        **DESPACHO,
        "placa": "FUERA",
        "hora": "15:30:00",
        "hora_real_ultimo_punto": "Mon Jul 06 2026 18:00:00 GMT-0500 (hora estándar de Perú)",
    }

    dispatch = FakeDispatchClient([{**DESPACHO, "placa": "DENTRO"}, fuera])
    provider = FakeTrackProvider(
        objects={p: vehicle(p, p) for p in ("DENTRO", "FUERA")},
        tracks={"DENTRO": [point("2026-07-06T10:00:00")]},
    )

    output = tmp_path / "out.xlsx"

    report = commands.despachos(
        dispatch, provider, start="2026-07-06 10:00", end="2026-07-06 12:00", output=str(output)
    )

    assert dispatch.calls == [("2026-07-05", "2026-07-06")]
    assert report.total == 1
    assert provider.ranges == {"DENTRO": DateRange(datetime(2026, 7, 6, 10, 0), datetime(2026, 7, 6, 12, 0))}

    # FECHORA_INI_VIAJE sigue siendo la salida real, no el inicio de la ventana
    assert "08:00" in str(load_workbook(output)["2026-07-06"].cell(row=2, column=5).value)


def test_despachos_same_client_for_dispatch_and_gps(tmp_path):

    class FakeLuca(FakeDispatchClient, FakeTrackProvider):
        def __init__(self):
            FakeDispatchClient.__init__(self, [DESPACHO])
            FakeTrackProvider.__init__(
                self,
                objects={"A0P736": vehicle("A0P736", "A0P736", credential="luca")},
                tracks={"A0P736": [point("2026-07-06T09:00:00")]},
            )

    luca = FakeLuca()

    report = commands.despachos(luca, luca, start="2026-07-01", end="2026-07-10", output=str(tmp_path / "out.xlsx"))

    assert (report.processed, report.track_points) == (1, 1)


# rango_fijo

def test_rango_fijo_from_excel_listing(tmp_path):

    provider = FakeTrackProvider(
        objects={"A0P736": vehicle("A0P736", "obj-1")},
        tracks={"obj-1": [point("2026-07-06T09:00:00")]},
    )

    listing = tmp_path / "listing.xlsx"
    pd.DataFrame({"RUC": ["123"], "CODIGO_RUTA": ["R1"], "PLACA": ["A0P736"], "IMEI": ["863238075031916"]}).to_excel(
        listing, index=False
    )

    output = tmp_path / "out.xlsx"

    report = commands.rango_fijo(
        provider, start="2026-07-06", end="2026-07-06", output=str(output), input_file=str(listing)
    )

    assert (report.processed, report.track_points) == (1, 1)
    assert provider.ranges["obj-1"] == DateRange(datetime(2026, 7, 6), datetime(2026, 7, 6, 23, 59, 59))

    header = [c.value for c in load_workbook(output)["2026-07-06"][1]]
    assert header[-1] == "IGNITION_STATUS"


def test_rango_fijo_from_luca_vehicles(tmp_path):

    luca = FakeTrackProvider(objects={"A0P736": vehicle("A0P736", "A0P736", credential="luca")})
    provider = FakeTrackProvider(
        objects={"A0P736": vehicle("A0P736", "obj-1")},
        tracks={"obj-1": [point("2026-07-06T09:00:00")]},
    )

    output = tmp_path / "out.xlsx"

    report = commands.rango_fijo(
        provider, start="2026-07-06", end="2026-07-06", output=str(output), vehicle_source=luca, codigo_ruta=6
    )

    # El object_id sale del catálogo del proveedor GPS, no del de LUCA.
    assert list(provider.ranges) == ["obj-1"]
    assert (report.processed, report.track_points) == (1, 1)

    row = [c.value for c in load_workbook(output)["2026-07-06"][2]]
    assert row[3] == "6"  # CODIGO_RUTA desde --luca-ruta


# reconsideracion

def test_reconsideracion_writes_one_csv_per_trip_and_resumes(tmp_path):

    excel = tmp_path / "rechazados.xlsx"

    pd.DataFrame(
        {
            "N°": [1, 2, 3],
            "Placa": ["A1I730", "SINGPS", "VACIO"],
            "Sentido": ["VUELTA", "IDA", "IDA"],
            "H. Inicio": ["20/10/2026 10:34:00"] * 3,
            "H. Fin": ["20/10/2026 13:00:28"] * 3,
        }
    ).to_excel(excel, index=False)

    provider = FakeTrackProvider(
        objects={p: vehicle(p) for p in ("A1I730", "VACIO")},
        tracks={"obj-A1I730": [point("2026-10-20T10:34:17", speed=32)]},
    )

    out_dir = tmp_path / "salida"

    report = commands.reconsideracion(provider, input_file=str(excel), output_dir=str(out_dir))

    assert report.counts() == {"ok": 1, "sin_object_id": 1, "sin_puntos": 1}
    assert (out_dir / "1_A1I730_20261020_103417.csv").read_text(encoding="utf-8").splitlines()[1] == (
        "-12.0,-77.0,2026-10-20 10:34:17,32,V"
    )

    resumen = pd.read_csv(out_dir / "_resumen.csv", dtype=str)
    assert list(resumen["ESTADO"]) == ["ok", "sin_object_id", "sin_puntos"]

    # Segunda corrida: el viaje con CSV no se vuelve a consultar.
    provider.ranges.clear()

    report = commands.reconsideracion(provider, input_file=str(excel), output_dir=str(out_dir))

    assert report.counts()["existente"] == 1
    assert "obj-A1I730" not in provider.ranges
