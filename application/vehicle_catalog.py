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
        Agrega la columna OBJECT_ID a partir de PLACA y completa IMEI
        con el catálogo cuando la fila no trae uno propio.
        """

        vehicles = self.build()

        df = df.copy()

        placas = df["PLACA"].astype(str).str.strip()

        df["OBJECT_ID"] = placas.map(
            lambda plate:
                getattr(
                    vehicles.get(plate),
                    "object_id",
                    None,
                )
        )

        missing = (
            df["OBJECT_ID"]
            .isna()
            .sum()
        )

        logger.warning("Vehículos sin OBJECT_ID: %d", missing)

        catalog_imei = placas.map(
            lambda plate: getattr(vehicles.get(plate), "imei", None) or None
        )

        if "IMEI" in df.columns:
            row_imei = (
                df["IMEI"]
                .astype(str)
                .str.strip()
                .replace({"": None, "nan": None, "None": None})
            )
            df["IMEI"] = row_imei.fillna(catalog_imei)
        else:
            df["IMEI"] = catalog_imei

        return df
