from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import pandas as pd
from alive_progress import alive_bar

from application.trip_resolver import TripResolver
from application.vehicle_catalog import VehicleCatalog
from domain.models import DateRange, Trip
from domain.rules import build_trip_from_row
from infrastructure.track_record_writer import TrackRecordWriter

logger = logging.getLogger(__name__)


@dataclass
class PipelineSummary:
    total: int
    processed: int
    errors: int
    track_points: int
    output_file: str


class TrackPipeline:
    """
    Orquestador único para 'mapear vehículos -> resolver tramo -> escribir -> resumen'.
    La única diferencia entre los distintos jobs de tracking es cómo se
    obtiene el DateRange de cada fila, parametrizado vía date_range_fn.
    """

    def __init__(
        self,
        fmtrack_client,
        *,
        require_ignition_on: bool = False,
        include_ignition_status: bool = True,
        max_workers: int = 8,
    ):
        self._vehicle_catalog = VehicleCatalog(fmtrack_client)
        self._resolver = TripResolver(
            fmtrack_client,
            require_ignition_on=require_ignition_on,
        )
        self._include_ignition_status = include_ignition_status
        self._max_workers = max_workers

    def _build_trips(
        self,
        df: pd.DataFrame,
        date_range_fn: Callable[[pd.Series], DateRange],
    ) -> tuple[list[Trip], int]:

        trips: list[Trip] = []

        errors = 0

        for _, row in df.iterrows():

            if pd.isna(row["OBJECT_ID"]):

                errors += 1

                logger.error("[ERROR] %s sin OBJECT_ID.", row.get("PLACA"))

                continue

            try:

                date_range = date_range_fn(row)

                trip = build_trip_from_row(
                    row,
                    object_id=row["OBJECT_ID"],
                    date_range=date_range,
                )

            except Exception as ex:

                errors += 1

                logger.error("[ERROR] %s -> %s", row.get("PLACA"), ex)

                continue

            trips.append(trip)

        return trips, errors

    def run(
        self,
        df: pd.DataFrame,
        output_file: str,
        *,
        date_range_fn: Callable[[pd.Series], DateRange],
    ) -> PipelineSummary:

        df = self._vehicle_catalog.attach_object_ids(df)

        writer = TrackRecordWriter(
            output_file,
            include_ignition_status=self._include_ignition_status,
        )

        writer.open()

        total = len(df)

        trips, errors = self._build_trips(df, date_range_fn)

        processed = 0

        track_points = 0

        with alive_bar(total, title="Procesando tramos") as bar:

            for _ in range(errors):
                bar()

            with ThreadPoolExecutor(max_workers=self._max_workers) as executor:

                futures = {
                    executor.submit(self._resolver.resolve, trip): trip
                    for trip in trips
                }

                for future in as_completed(futures):

                    trip = futures[future]

                    bar.text(f"-> {trip.placa}")

                    result = future.result()

                    if result.success:

                        if result.points:

                            writer.append(trip, result.points)

                            track_points += len(result.points)

                        processed += 1

                    else:

                        errors += 1

                        logger.error("[ERROR] %s -> %s", trip.placa, result.error)

                    bar()

        writer.close()

        logger.info(
            "RESUMEN | leidos=%d procesados=%d errores=%d track_points=%d archivo=%s",
            total,
            processed,
            errors,
            track_points,
            output_file,
        )

        return PipelineSummary(
            total=total,
            processed=processed,
            errors=errors,
            track_points=track_points,
            output_file=output_file,
        )
