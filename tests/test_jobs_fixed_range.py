from datetime import datetime

import pandas as pd
from openpyxl import load_workbook

from application.jobs.fixed_range_job import FixedRangeJob
from domain.models import DateRange
from tests.conftest import FakeTrackProvider, point, vehicle


def test_fixed_range_job_applies_same_range_to_every_row(tmp_path):

    provider = FakeTrackProvider(
        objects={"A0P736": vehicle("A0P736", "obj-1")},
        tracks={"obj-1": [point("2026-07-06T09:00:00")]},
    )

    listing = pd.DataFrame({"RUC": ["123"], "CODIGO_RUTA": ["R1"], "PLACA": ["A0P736"], "IMEI": ["863238075031916"]})

    input_file = tmp_path / "listing.xlsx"
    output_file = tmp_path / "out.xlsx"

    listing.to_excel(input_file, index=False)

    report = FixedRangeJob(provider).run(
        str(output_file),
        input_file=str(input_file),
        start_date="2026-07-06 00:00:00",
        end_date="2026-07-06 23:59:59",
    )

    assert (report.processed, report.track_points) == (1, 1)
    assert provider.ranges["obj-1"] == DateRange(datetime(2026, 7, 6), datetime(2026, 7, 6, 23, 59, 59))
    assert "2026-07-06" in load_workbook(output_file).sheetnames
    assert (tmp_path / "out_resumen.csv").exists()


class FakeVehicleSourceClient:
    """
    Doble de prueba de LucaClient para el rol de vehicle_source_client. No hace red.
    """

    def __init__(self, objects):
        self._objects = objects

    def get_objects(self):
        return dict(self._objects)


def test_fixed_range_job_builds_listing_from_luca_when_no_input_file(tmp_path):

    luca = FakeVehicleSourceClient({"A0P736": vehicle("A0P736", "A0P736", credential="luca")})

    provider = FakeTrackProvider(
        objects={"A0P736": vehicle("A0P736", "obj-1")},
        tracks={"obj-1": [point("2026-07-06T09:00:00")]},
    )

    output_file = tmp_path / "out.xlsx"

    report = FixedRangeJob(provider, vehicle_source_client=luca).run(
        str(output_file),
        start_date="2026-07-06 00:00:00",
        end_date="2026-07-06 23:59:59",
        codigo_ruta=6,
    )

    # El object_id sale del catálogo del proveedor GPS, no del de LUCA.
    assert list(provider.ranges) == ["obj-1"]
    assert (report.processed, report.track_points) == (1, 1)
    assert "2026-07-06" in load_workbook(output_file).sheetnames
