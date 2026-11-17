"""Casos de uso del CLI: cada uno es fuente -> run_trips(proveedor, sink) -> reporte.

Reciben los clientes ya construidos (main.py los arma y los cierra), así
que se pueden probar con dobles sin red.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from application.run_trips import RunReport, report_path, run_trips
from application.sources.despachos_luca import viajes_de_despachos
from application.sources.rango_fijo import viajes_de_listado, viajes_de_vehiculos
from application.sources.reconsideracion import leer_viajes
from domain.models import DateRange
from domain.ports import TrackProvider
from domain.rules import parse_boundary
from infrastructure.track_record_writer import TrackRecordWriter
from infrastructure.trip_csv_writer import TripCsvWriter


def _window(start: str, end: str) -> DateRange:
    return DateRange(start=parse_boundary(start, is_end=False), end=parse_boundary(end, is_end=True))


def despachos(
    dispatch_client,
    track_client: TrackProvider,
    *,
    start: str,
    end: str,
    output: str,
    workers: int = 8,
) -> RunReport:
    """
    Despachos de LUCA_Backend -> Excel ATU. La ventana [start, end] filtra la
    hora de los track points, no la de salida: cada tramo se consulta solo en
    su intersección con la ventana. LUCA filtra despachos por día calendario,
    así que se pide también el día anterior para no perder tramos que cruzan
    la medianoche hacia la ventana.
    """

    window = _window(start, end)

    registros = dispatch_client.get_dispatch_records(
        (window.start.date() - timedelta(days=1)).isoformat(),
        window.end.date().isoformat(),
    )

    items = viajes_de_despachos(registros, window)

    with TrackRecordWriter(output, include_ignition_status=False) as sink:
        report = run_trips(items, track_client, sink, workers=workers)

    report.write_csv(report_path(output))

    return report


def rango_fijo(
    track_client: TrackProvider,
    *,
    start: str,
    end: str,
    output: str,
    workers: int = 8,
    input_file: str | None = None,
    vehicle_source=None,
    codigo_ruta=None,
) -> RunReport:
    """
    Un mismo rango para todo un listado -> Excel ATU (con IGNITION_STATUS).
    El listado sale del Excel input_file o, sin él, del catálogo de
    vehicle_source (LUCA).
    """

    date_range = _window(start, end)

    if input_file:
        items = viajes_de_listado(input_file, date_range)
    elif vehicle_source is not None:
        items = viajes_de_vehiculos(vehicle_source.get_objects(), date_range, codigo_ruta)
    else:
        raise ValueError("rango_fijo necesita input_file o vehicle_source.")

    with TrackRecordWriter(output, include_ignition_status=True) as sink:
        report = run_trips(items, track_client, sink, workers=workers)

    report.write_csv(report_path(output))

    return report


def reconsideracion(
    track_client: TrackProvider,
    *,
    input_file: str,
    output_dir: str,
    workers: int = 8,
    limite: int | None = None,
) -> RunReport:
    """
    Excel de viajes rechazados -> un CSV por viaje en output_dir, más
    output_dir/_resumen.csv. Reanudable: los viajes con CSV previo se saltan.
    """

    items = leer_viajes(input_file)

    if limite:
        items = items[:limite]

    report = run_trips(items, track_client, TripCsvWriter(output_dir), workers=workers)

    report.write_csv(Path(output_dir) / "_resumen.csv")

    return report
