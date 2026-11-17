from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pandas as pd

from application.run_trips import RunReport, report_path, run_trips
from domain.models import DateRange, Sentido, Trip, TripOutcome, TripStatus
from domain.rules import extract_driver_document, parse_boundary, parse_operational_datetime
from infrastructure.track_record_writer import TrackRecordWriter


def _parse_salida(despacho: dict) -> datetime | None:
    try:
        value = pd.to_datetime(f"{despacho.get('fecha')} {despacho.get('hora')}")
    except (ValueError, TypeError):
        return None
    return None if pd.isna(value) else value.to_pydatetime()


def _trip_from_despacho(despacho: dict, ref: str) -> Trip | TripOutcome:
    """
    Un despacho de LUCA -> Trip con el rango salida -> último punto (real o,
    si falta, calculado). Un despacho sin rango válido vuelve como
    TripOutcome FILA_INVALIDA para que quede en el reporte.
    """

    placa = (despacho.get("placa") or "").strip()

    salida = _parse_salida(despacho)

    fin = parse_operational_datetime(despacho.get("hora_real_ultimo_punto")) or parse_operational_datetime(
        despacho.get("hora_calculada_ultimo_punto")
    )

    if salida is None or fin is None:
        falta = "salida" if salida is None else "hora del último punto"
        return TripOutcome(status=TripStatus.FILA_INVALIDA, ref=ref, placa=placa, detail=f"Despacho sin {falta}")

    try:
        date_range = DateRange(start=salida, end=fin)
    except ValueError:
        return TripOutcome(
            status=TripStatus.FILA_INVALIDA, ref=ref, placa=placa, detail=f"Fin {fin} anterior a la salida {salida}"
        )

    sentido = Sentido.try_parse(despacho.get("sentido"))

    return Trip(
        placa=placa,
        date_range=date_range,
        ruc_empresa=despacho.get("ruc_empresa"),
        codigo_ruta=despacho.get("codigo_ruta"),
        sentido=sentido,
        nro_doc_conductor=extract_driver_document(despacho.get("conductor")),
        fechora_ini_viaje=salida,
        ref=ref,
    )


def _clip_to_window(trip: Trip, window: DateRange) -> Trip | None:
    """
    El viaje recortado a su intersección con la ventana, o None si no tiene
    track points posibles dentro de ella.
    """

    date_range = trip.date_range

    if date_range.start > window.end or date_range.end < window.start:
        return None

    clipped = DateRange(start=max(date_range.start, window.start), end=min(date_range.end, window.end))

    return replace(trip, date_range=clipped)


class DispatchJob:
    """
    Los despachos siempre se obtienen de LUCA_Backend (dispatch_client) y sus
    coordenadas GPS se resuelven con el proveedor elegido (track_client:
    FMTrackClient o LucaClient).
    """

    def __init__(self, dispatch_client, track_client, *, max_workers: int = 8):
        self._dispatch_client = dispatch_client
        self._track_client = track_client
        self._max_workers = max_workers

    def run(
        self,
        fecha_inicio: str,
        fecha_fin: str,
        output_file: str,
    ) -> RunReport:

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

        items: list[Trip | TripOutcome] = []

        for i, despacho in enumerate(despachos):

            item = _trip_from_despacho(despacho, ref=str(i + 1))

            if isinstance(item, Trip):
                item = _clip_to_window(item, window)

            if item is not None:
                items.append(item)

        with TrackRecordWriter(output_file, include_ignition_status=False) as sink:
            report = run_trips(items, self._track_client, sink, workers=self._max_workers)

        report.write_csv(report_path(output_file))

        return report
