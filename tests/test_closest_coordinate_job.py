import pandas as pd

from application.jobs.closest_coordinate_job import ClosestCoordinateJob
from domain.models import TrackPoint, Vehicle
from tests.conftest import FakeFMTrackClient


def test_closest_coordinate_job_writes_matched_coordinates(tmp_path):

    vehicles = {
        "A0P736": Vehicle(
            plate="A0P736",
            object_id="obj-1",
            imei="863238075031916",
            credential="default",
        )
    }

    closest = {
        "obj-1": TrackPoint(
            datetime="2026-06-03T10:12:00.000Z",
            latitude=-12.0,
            longitude=-77.0,
            speed=10.0,
        )
    }

    client = FakeFMTrackClient(objects=vehicles, closest=closest)

    df = pd.DataFrame(
        {
            "RUC_EMPRESA": ["123"],
            "PLACA": ["A0P736"],
            "IMEI": ["863238075031916"],
            "CODIGO_RUTA": ["R1"],
            "FECHORA_INI_VIAJE": ["2026-06-03 10:00:00"],
            "FECHA_HORA_TRACK": ["2026-06-03 10:12:00"],
            "NRO_DOC_CONDUCTOR": ["12345678"],
            "LATITUD": [None],
            "LONGITUD": [None],
            "VELOCIDAD": [None],
        }
    )

    input_file = tmp_path / "input.xlsx"
    output_file = tmp_path / "output.xlsx"

    df.to_excel(input_file, index=False)

    job = ClosestCoordinateJob(client)

    job.run(str(input_file), str(output_file))

    result = pd.read_excel(output_file)

    assert result.loc[0, "LATITUD"] == -12.0
    assert result.loc[0, "LONGITUD"] == -77.0
    assert job.stats.success == 1
    assert job.stats.not_found == 0


def test_closest_coordinate_job_counts_not_found_plate(tmp_path):

    client = FakeFMTrackClient(objects={})

    df = pd.DataFrame(
        {
            "RUC_EMPRESA": ["123"],
            "PLACA": ["ZZZ999"],
            "IMEI": ["000"],
            "CODIGO_RUTA": ["R1"],
            "FECHORA_INI_VIAJE": ["2026-06-03 10:00:00"],
            "FECHA_HORA_TRACK": ["2026-06-03 10:12:00"],
            "NRO_DOC_CONDUCTOR": ["12345678"],
            "LATITUD": [None],
            "LONGITUD": [None],
            "VELOCIDAD": [None],
        }
    )

    input_file = tmp_path / "input.xlsx"
    output_file = tmp_path / "output.xlsx"

    df.to_excel(input_file, index=False)

    job = ClosestCoordinateJob(client)

    job.run(str(input_file), str(output_file))

    assert job.stats.not_found == 1
    assert job.stats.success == 0
