from __future__ import annotations

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
    Procesa listados simples (RUC, CODIGO_RUTA, PLACA, IMEI) sin fechas propias,
    aplicando un mismo intervalo de fechas fijo a todos los vehículos.
    """

    def __init__(self, fmtrack_client, *, max_workers: int = 8):
        self._pipeline = TrackPipeline(
            fmtrack_client,
            require_ignition_on=False,
            include_ignition_status=True,
            max_workers=max_workers,
        )

    def run(
        self,
        input_file: str,
        output_file: str,
        start_date: str,
        end_date: str,
    ) -> PipelineSummary:

        fixed_range = DateRange(
            start=parse_boundary(start_date, is_end=False),
            end=parse_boundary(end_date, is_end=True),
        )

        df = read_listing_excel(
            input_file,
            column_aliases=COLUMN_ALIASES,
            required_columns=REQUIRED_COLUMNS,
        )

        return self._pipeline.run(
            df,
            output_file,
            date_range_fn=lambda row: fixed_range,
        )
