from __future__ import annotations

import logging

import pandas as pd

from domain.models import Vehicle

logger = logging.getLogger(__name__)


class VehicleCatalog:
    """
    Cataloga los vehículos de FM Track (PLACA -> Vehicle) y los asocia
    a un listado de filas por PLACA.
    """

    def __init__(self, fmtrack_client):
        self.fmtrack_client = fmtrack_client
        self._cache: dict[str, Vehicle] | None = None

    def build(self) -> dict[str, Vehicle]:

        if self._cache is None:
            self._cache = self.fmtrack_client.get_objects()

        return self._cache

    def attach_object_ids(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Agrega la columna OBJECT_ID a partir de PLACA.
        """

        vehicles = self.build()

        df = df.copy()

        df["OBJECT_ID"] = (
            df["PLACA"]
            .astype(str)
            .str.strip()
            .map(
                lambda plate:
                    getattr(
                        vehicles.get(plate),
                        "object_id",
                        None,
                    )
            )
        )

        missing = (
            df["OBJECT_ID"]
            .isna()
            .sum()
        )

        logger.warning("Vehículos sin OBJECT_ID: %d", missing)

        return df
