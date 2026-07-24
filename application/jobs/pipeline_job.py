from __future__ import annotations

from application.track_pipeline import PipelineSummary, TrackPipeline
from domain.rules import resolve_date_range
from infrastructure.excel_io import read_all_sheets


class PipelineJob:
    """
    Procesa tramos con fechas propias por fila (FECHORA_INI_VIAJE / FECHA_HORA_FIN_TRAMO),
    normalmente generados por OperationalJob + PartitionSplitJob.
    """

    def __init__(self, fmtrack_client):
        self._pipeline = TrackPipeline(
            fmtrack_client,
            require_ignition_on=False,
            include_ignition_status=False,
        )

    def run(
        self,
        input_file: str,
        output_file: str,
    ) -> PipelineSummary:

        df = read_all_sheets(input_file, dtype=str)

        return self._pipeline.run(
            df,
            output_file,
            date_range_fn=resolve_date_range,
        )
