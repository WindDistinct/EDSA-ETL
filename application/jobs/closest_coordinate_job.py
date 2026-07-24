from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter

import pandas as pd

from application.vehicle_catalog import VehicleCatalog

logger = logging.getLogger(__name__)


@dataclass
class ClosestCoordinateStats:
    processed: int = 0
    success: int = 0
    errors: int = 0
    not_found: int = 0


class ClosestCoordinateJob:
    """
    Modo legacy: busca la coordenada más cercana a UN timestamp por fila
    (no un rango), y escribe el resultado sobre el mismo listado de entrada.

    No está conectado al CLI principal por defecto; se conserva para
    búsquedas puntuales. Candidato a eliminar si deja de usarse.

    Nota: _format_datetime aquí trata el timestamp local del Excel como si
    ya fuera UTC (le agrega "Z" sin conversión de zona horaria). Esto es
    intencionalmente distinto de domain.rules.format_for_api (usado por el
    flujo de rangos), que sí ajusta por la zona horaria del sistema. No
    unificar ambas funciones sin antes verificar contra qué zona horaria
    fue registrada FECHA_HORA_TRACK en el origen de datos.
    """

    def __init__(
        self,
        fmtrack_client,
        batch_size: int = 1000,
        batch_delay: int = 10,
    ):
        self.fmtrack_client = fmtrack_client
        self.vehicle_catalog = VehicleCatalog(fmtrack_client)
        self.batch_size = batch_size
        self.batch_delay = batch_delay
        self.stats = ClosestCoordinateStats()

    def _format_datetime(self, value: str) -> str:
        """
        Convierte fecha Excel a formato FM Track.
        Ejemplo:
        2026-06-03 10:12:00
        ->
        2026-06-03T10:12:00.000Z
        """

        dt = datetime.strptime(
            value,
            "%Y-%m-%d %H:%M:%S",
        )

        return dt.isoformat(timespec="milliseconds") + "Z"

    def _process_row(
        self,
        row: pd.Series,
        vehicles: dict,
    ) -> dict:

        placa = row["PLACA"]

        vehicle = vehicles.get(placa)

        if not vehicle:
            self.stats.not_found += 1
            return {}

        track_datetime = self._format_datetime(
            row["FECHA_HORA_TRACK"]
        )

        coordinate = self.fmtrack_client.get_closest_coordinate(
            object_id=vehicle.object_id,
            target_datetime=track_datetime,
        )

        if not coordinate:
            return {}

        self.stats.success += 1

        return {
            "LATITUD": coordinate.latitude,
            "LONGITUD": coordinate.longitude,
            "VELOCIDAD": coordinate.speed,
        }

    def run(
        self,
        input_file: str,
        output_file: str,
    ) -> None:

        start_time = perf_counter()

        processed = 0

        df = pd.read_excel(
            input_file,
            dtype={
                "RUC_EMPRESA": str,
                "PLACA": str,
                "IMEI": str,
                "CODIGO_RUTA": str,
                "FECHORA_INI_VIAJE": str,
                "FECHA_HORA_TRACK": str,
                "NRO_DOC_CONDUCTOR": str,
            },
        )

        df["LATITUD"] = pd.to_numeric(df["LATITUD"], errors="coerce")
        df["LONGITUD"] = pd.to_numeric(df["LONGITUD"], errors="coerce")
        df["VELOCIDAD"] = pd.to_numeric(df["VELOCIDAD"], errors="coerce")

        logger.info("Registros encontrados: %d", len(df))

        vehicles = self.vehicle_catalog.build()

        logger.info("Vehículos FM Track encontrados: %d", len(vehicles))

        df["OBJECT_ID"] = df["PLACA"].apply(
            lambda placa: getattr(vehicles.get(placa), "object_id", None)
        )

        not_found = df[df["OBJECT_ID"].isna()]

        logger.info("Placas no encontradas: %d", len(not_found))

        total_rows = len(df)

        for start in range(0, total_rows, self.batch_size):

            end = min(start + self.batch_size, total_rows)

            logger.info("Procesando filas %d - %d", start, end)

            batch = df.iloc[start:end]

            for index, row in batch.iterrows():

                try:

                    result = self._process_row(row, vehicles)

                    for column, value in result.items():
                        df.at[index, column] = value

                except Exception as ex:

                    self.stats.errors += 1

                    logger.error("Error procesando fila %d: %s", index, ex)

                processed += 1

                if processed % 50 == 0:
                    logger.info("Procesadas %d/%d", processed, total_rows)

            if end < total_rows:

                logger.info("Esperando %d segundos...", self.batch_delay)

                time.sleep(self.batch_delay)

        df.drop(columns=["OBJECT_ID"], inplace=True)

        df.to_excel(output_file, index=False)

        elapsed = perf_counter() - start_time

        logger.info(
            "PROCESAMIENTO FINALIZADO | "
            "procesados=%d exitosas=%d no_encontradas=%d errores=%d tiempo=%.2fs",
            total_rows,
            self.stats.success,
            self.stats.not_found,
            self.stats.errors,
            elapsed,
        )

        logger.info("Archivo generado correctamente.")
