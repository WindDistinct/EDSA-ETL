"""Resuelve un lote de viajes contra un proveedor GPS y los escribe en un sink.

Es el único bucle de la aplicación: todas las fuentes (despachos de LUCA,
listado con rango fijo, reconsideración, ...) entregan viajes y todas las
salidas (Excel ATU, un CSV por viaje, ...) los reciben por aquí.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from pathlib import Path

import pandas as pd
from alive_progress import alive_bar

from domain.models import Trip, TripOutcome, TripStatus
from domain.ports import TrackProvider, TripSink

logger = logging.getLogger(__name__)

DATE_FMT = "%Y-%m-%d %H:%M:%S"

REPORT_COLUMNS = ["REF", "PLACA", "INICIO", "FIN", "ESTADO", "PUNTOS", "ARCHIVO", "DETALLE"]

_FAILED = {TripStatus.ERROR, TripStatus.SIN_OBJECT_ID, TripStatus.FILA_INVALIDA}


@dataclass
class RunReport:
    outcomes: list[TripOutcome] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def processed(self) -> int:
        """Viajes consultados sin error (con o sin puntos)."""
        return sum(o.status in (TripStatus.OK, TripStatus.SIN_PUNTOS) for o in self.outcomes)

    @property
    def errors(self) -> int:
        return sum(o.status in _FAILED for o in self.outcomes)

    @property
    def track_points(self) -> int:
        return sum(o.points for o in self.outcomes)

    def counts(self) -> dict[str, int]:
        return dict(Counter(str(o.status) for o in self.outcomes))

    def to_dataframe(self) -> pd.DataFrame:

        rows = []

        for o in self.outcomes:
            date_range = o.trip.date_range if o.trip else None
            rows.append(
                {
                    "REF": o.ref,
                    "PLACA": o.placa,
                    "INICIO": date_range.start.strftime(DATE_FMT) if date_range else "",
                    "FIN": date_range.end.strftime(DATE_FMT) if date_range else "",
                    "ESTADO": str(o.status),
                    "PUNTOS": o.points,
                    "ARCHIVO": o.output,
                    "DETALLE": o.detail,
                }
            )

        df = pd.DataFrame(rows, columns=REPORT_COLUMNS)

        # Orden de la fuente: por REF numérico cuando lo es (N° 1, 2, ..., 10).
        orden = pd.to_numeric(df["REF"], errors="coerce")

        return df.assign(_o=orden).sort_values(["_o", "REF"], kind="stable").drop(columns="_o")

    def write_csv(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.to_dataframe().to_csv(path, index=False, encoding="utf-8-sig")
        return path

    def log_summary(self) -> None:
        logger.info(
            "RESUMEN | total=%d procesados=%d errores=%d track_points=%d estados=%s",
            self.total, self.processed, self.errors, self.track_points, self.counts(),
        )


def report_path(output_file: str | Path) -> Path:
    """<salida>_resumen.csv al lado del archivo de salida."""
    output_file = Path(output_file)
    return output_file.with_name(f"{output_file.stem}_resumen.csv")


def _attach_vehicle(trip: Trip, vehicles: dict) -> Trip | None:
    """
    Completa object_id (y el IMEI si la fila no trae uno) desde el catálogo
    del proveedor. None si la placa no está.
    """

    if trip.object_id:
        return trip

    vehicle = vehicles.get(str(trip.placa).strip())

    if vehicle is None:
        return None

    return replace(trip, object_id=vehicle.object_id, imei=trip.imei or vehicle.imei or None)


def run_trips(
    items: Iterable[Trip | TripOutcome],
    provider: TrackProvider,
    sink: TripSink,
    *,
    workers: int = 8,
    title: str = "Procesando viajes",
) -> RunReport:
    """
    items: viajes a resolver; un TripOutcome en la lista (p. ej. una fila
    inválida de la fuente) pasa directo al reporte.

    Las consultas al proveedor corren en paralelo; la escritura en el sink
    se hace siempre desde este hilo, en el orden en que terminan.
    """

    items = list(items)

    report = RunReport()

    vehicles = provider.get_objects()

    pending: list[Trip] = []

    for item in items:

        if isinstance(item, TripOutcome):
            report.outcomes.append(item)
            continue

        previous = sink.existing(item)

        if previous:
            report.outcomes.append(TripOutcome.of(item, TripStatus.EXISTENTE, output=previous))
            continue

        trip = _attach_vehicle(item, vehicles)

        if trip is None:
            logger.warning("[SIN_OBJECT_ID] %s no está en el catálogo del proveedor.", item.placa)
            report.outcomes.append(
                TripOutcome.of(item, TripStatus.SIN_OBJECT_ID, detail="Placa no encontrada en el proveedor GPS")
            )
            continue

        pending.append(trip)

    with alive_bar(len(items), title=title) as bar:

        for _ in range(len(items) - len(pending)):
            bar()

        with ThreadPoolExecutor(max_workers=workers) as pool:

            futures = {
                pool.submit(provider.fetch_track, trip.object_id, trip.date_range): trip
                for trip in pending
            }

            for future in as_completed(futures):

                trip = futures[future]

                bar.text(f"-> {trip.placa}")

                try:
                    points = future.result()

                    if not points:
                        outcome = TripOutcome.of(trip, TripStatus.SIN_PUNTOS)
                    else:
                        output = sink.write(trip, points)
                        outcome = TripOutcome.of(trip, TripStatus.OK, points=len(points), output=output)

                except Exception as ex:
                    logger.error("[ERROR] %s (%s) -> %s", trip.placa, trip.ref, ex)
                    outcome = TripOutcome.of(trip, TripStatus.ERROR, detail=str(ex))

                report.outcomes.append(outcome)

                bar()

    report.log_summary()

    return report
