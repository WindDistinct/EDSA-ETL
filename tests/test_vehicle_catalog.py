import pandas as pd

from application.vehicle_catalog import VehicleCatalog
from domain.models import Vehicle
from tests.conftest import FakeFMTrackClient


def test_attach_object_ids_maps_known_plate_and_leaves_unknown_as_nan():

    vehicles = {
        "A0P736": Vehicle(
            plate="A0P736",
            object_id="obj-1",
            imei="863238075031916",
            credential="default",
        )
    }

    client = FakeFMTrackClient(objects=vehicles)

    catalog = VehicleCatalog(client)

    df = pd.DataFrame({"PLACA": ["A0P736", "ZZZ999"]})

    result = catalog.attach_object_ids(df)

    assert result.loc[0, "OBJECT_ID"] == "obj-1"
    assert pd.isna(result.loc[1, "OBJECT_ID"])


def test_build_caches_client_call():

    client = FakeFMTrackClient(objects={})

    calls = {"n": 0}

    original_get_objects = client.get_objects

    def counting_get_objects():
        calls["n"] += 1
        return original_get_objects()

    client.get_objects = counting_get_objects

    catalog = VehicleCatalog(client)

    catalog.build()
    catalog.build()

    assert calls["n"] == 1
