from __future__ import annotations

import pandas as pd

from application.track_pipeline import PipelineSummary, TrackPipeline
from domain.models import DateRange
from domain.rules import parse_boundary
from infrastructure.excel_io import read_listing_excel

COLUMN_ALIASES = {
    "RUC": "RUC_EMPRESA",
    "RUC_EMPRESA": "RUC_EMPRESA",
    "CODIGO_RUTA": "CODIGO_RUTA",
    "PLACA": "PLACA",
    "IMEI": "IMEI",
}

REQUIRED_COLUMNS = [
    "RUC_EMPRESA",
    "CODIGO_RUTA",
    "PLACA",
    "IMEI",
]


class FixedRangeJob:
    """
    Aplica un mismo intervalo de fechas fijo a un listado de vehículos, sin
    fechas propias por fila. El listado puede venir de un Excel simple (RUC,
    CODIGO_RUTA, PLACA, IMEI) o, tal como en DispatchJob, directamente de LUCA
    (vehicle_source_client: siempre LucaClient, obtiene los vehículos de la
    empresa vía /reportes/obtener_imeis_vehiculos). Los track points siempre
    se resuelven con el proveedor de tracking elegido (track_client:
    FMTrackClient o LucaClient) mediante el mismo TrackPipeline de siempre.
    """

    def __init__(self, track_client, *, vehicle_source_client=None, max_workers: int = 8):
        self._vehicle_source_client = vehicle_source_client
        self._pipeline = TrackPipeline(
            track_client,
            require_ignition_on=False,
            include_ignition_status=True,
            max_workers=max_workers,
        )

    def _build_dataframe_from_luca(self, codigo_ruta) -> pd.DataFrame:

        vehicles = self._vehicle_source_client.get_objects()

        filas = [
            {
                "RUC_EMPRESA": None,
                "CODIGO_RUTA": codigo_ruta,
                "PLACA": placa,
                "IMEI": vehicle.imei,
            }
            for placa, vehicle in vehicles.items()
        ]

        return pd.DataFrame(filas, columns=REQUIRED_COLUMNS, dtype=object)

    def run(
        self,
        output_file: str,
        *,
        start_date: str,
        end_date: str,
        input_file: str | None = None,
        codigo_ruta: str | int | None = None,
    ) -> PipelineSummary:

        fixed_range = DateRange(
            start=parse_boundary(start_date, is_end=False),
            end=parse_boundary(end_date, is_end=True),
        )

        if input_file:

            df = read_listing_excel(
                input_file,
                column_aliases=COLUMN_ALIASES,
                required_columns=REQUIRED_COLUMNS,
            )

        else:

            if self._vehicle_source_client is None:
                raise ValueError(
                    "Se requiere vehicle_source_client cuando no se especifica input_file."
                )

            df = self._build_dataframe_from_luca(codigo_ruta)

        return self._pipeline.run(
            df,
            output_file,
            date_range_fn=lambda row: fixed_range,
        )
