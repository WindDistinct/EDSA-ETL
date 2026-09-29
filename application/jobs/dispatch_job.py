from __future__ import annotations

from datetime import timedelta

import pandas as pd

from application.track_pipeline import PipelineSummary, TrackPipeline
from domain.models import DateRange
from domain.rules import (
    extract_driver_document,
    parse_boundary,
    parse_operational_datetime,
    resolve_date_range,
)

SENTIDO_A_CODIGO = {
    "ida": 0,
    "vuelta": 1,
}

DISPATCH_OUTPUT_COLUMNS = [
    "RUC_EMPRESA",
    "PLACA",
    "IMEI",
    "CODIGO_RUTA",
    "FECHORA_INI_VIAJE",
    "FECHA_HORA_FIN_TRAMO",
    "FECHA_HORA_FIN_TRAMO_CALCULADA",
    "SENTIDO",
    "NRO_DOC_CONDUCTOR",
]


class DispatchJob:
    """
    Reemplaza operational/partition-split/pipeline para cualquier cliente: los
    despachos siempre se obtienen de LUCA_Backend (dispatch_client), y sus
    coordenadas GPS se resuelven con el proveedor de tracking elegido
    (track_client: FMTrackClient o LucaClient) mediante el mismo TrackPipeline
    de siempre.
    """

    def __init__(self, dispatch_client, track_client, *, max_workers: int = 8):
        self._dispatch_client = dispatch_client
        self._pipeline = TrackPipeline(
            track_client,
            require_ignition_on=False,
            include_ignition_status=False,
            max_workers=max_workers,
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

        return pd.DataFrame(filas, columns=DISPATCH_OUTPUT_COLUMNS, dtype=object)

    def run(
        self,
        fecha_inicio: str,
        fecha_fin: str,
        output_file: str,
    ) -> PipelineSummary:

        # El rango filtra la hora de los track points, no la de salida: cada
        # tramo se consulta solo en su intersección con [start, end]. LUCA
        # filtra despachos por día calendario, así que se pide también el día
        # anterior para no perder tramos que cruzan la medianoche hacia el rango.
        window = DateRange(
            start=parse_boundary(fecha_inicio, is_end=False),
            end=parse_boundary(fecha_fin, is_end=True),
        )

        despachos = self._dispatch_client.get_dispatch_records(
            (window.start.date() - timedelta(days=1)).isoformat(),
            window.end.date().isoformat(),
        )

        df = self._build_dataframe(despachos)

        df = df.loc[[_overlaps(row, window) for _, row in df.iterrows()]]

        return self._pipeline.run(
            df,
            output_file,
            date_range_fn=lambda row: _clip_to_window(resolve_date_range(row), window),
        )


def _clip_to_window(date_range: DateRange, window: DateRange) -> DateRange:
    return DateRange(
        start=max(date_range.start, window.start),
        end=min(date_range.end, window.end),
    )


def _overlaps(row: pd.Series, window: DateRange) -> bool:
    """
    True si el tramo tiene track points posibles dentro de la ventana. Los
    tramos sin rango válido se conservan para que el pipeline los reporte
    como error, igual que antes.
    """

    try:
        date_range = resolve_date_range(row)
    except ValueError:
        return True

    return date_range.start <= window.end and date_range.end >= window.start
