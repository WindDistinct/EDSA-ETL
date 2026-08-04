from __future__ import annotations

import pandas as pd

from application.jobs.operational_job import OperationalJob
from application.track_pipeline import PipelineSummary, TrackPipeline
from domain.rules import extract_driver_document, parse_operational_datetime, resolve_date_range

SENTIDO_A_CODIGO = {
    "ida": 0,
    "vuelta": 1,
}


class LucaDispatchJob:
    """
    Reemplaza OperationalJob + PartitionSplitJob + PipelineJob para un cliente
    LUCA: obtiene el listado de despachos directo de LUCA_Backend (ya no hace
    falta el documento operacional ni el documento limpio) y resuelve sus
    coordenadas GPS con el mismo TrackPipeline de siempre.
    """

    def __init__(self, luca_client):
        self._client = luca_client
        self._pipeline = TrackPipeline(
            luca_client,
            require_ignition_on=False,
            include_ignition_status=False,
        )

    def _build_dataframe(self, despachos: list[dict]) -> pd.DataFrame:

        filas = []

        for despacho in despachos:

            filas.append(
                {
                    "RUC_EMPRESA": despacho.get("ruc_empresa"),
                    "PLACA": (despacho.get("placa") or "").strip(),
                    "IMEI": "",
                    "CODIGO_RUTA": despacho.get("codigo_ruta"),
                    "FECHORA_INI_VIAJE": pd.to_datetime(
                        f"{despacho.get('fecha')} {despacho.get('hora')}"
                    ),
                    "FECHA_HORA_FIN_TRAMO": parse_operational_datetime(
                        despacho.get("hora_real_ultimo_punto")
                    ),
                    "FECHA_HORA_FIN_TRAMO_CALCULADA": parse_operational_datetime(
                        despacho.get("hora_calculada_ultimo_punto")
                    ),
                    "SENTIDO": SENTIDO_A_CODIGO.get(despacho.get("sentido")),
                    "NRO_DOC_CONDUCTOR": extract_driver_document(
                        despacho.get("conductor")
                    ),
                }
            )

        return pd.DataFrame(filas, columns=OperationalJob.OUTPUT_COLUMNS, dtype=object)

    def run(
        self,
        fecha_inicio: str,
        fecha_fin: str,
        output_file: str,
    ) -> PipelineSummary:

        despachos = self._client.get_dispatch_records(fecha_inicio, fecha_fin)

        df = self._build_dataframe(despachos)

        return self._pipeline.run(
            df,
            output_file,
            date_range_fn=resolve_date_range,
        )
