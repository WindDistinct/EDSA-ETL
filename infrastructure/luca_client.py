from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from config import settings
from domain.models import DateRange, TrackPoint, Vehicle
from domain.tiempo import LOCAL_TZ, to_local
from infrastructure.http_retry import RateGate, request_with_retry

logger = logging.getLogger(__name__)


def _local_dates_between(start: datetime, end: datetime) -> list[str]:
    start_local = to_local(start).date()
    end_local = to_local(end).date()

    dates = []
    current = start_local

    while current <= end_local:
        dates.append(current.isoformat())
        current += timedelta(days=1)

    return dates


class LucaClient:
    def __init__(
        self,
        empresa: int,
        ruta: int,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._empresa = empresa
        self._ruta = ruta

        self._client = httpx.Client(
            base_url=settings.luca_base_url,
            headers={"x-api-key": settings.luca_api_key},
            timeout=30.0,
            transport=transport,
        )

        self._gate = RateGate()

    def close(self) -> None:
        self._client.close()

    def _post(self, endpoint: str, json: dict[str, Any]) -> httpx.Response:
        return request_with_retry(self._client, "POST", endpoint, json=json, gate=self._gate)

    def get_objects(self) -> dict[str, Vehicle]:
        """
        Obtiene los IMEI de todos los vehículos de la empresa configurada.
        Retorna un diccionario indexado por placa.
        """

        response = self._post(
            "/reportes/obtener_imeis_vehiculos",
            json={"empresa": self._empresa},
        )

        response.raise_for_status()

        imeis = response.json().get("imeis", {})

        objects = {
            plate: Vehicle(
                plate=plate,
                object_id=plate,
                imei=str(imei or ""),
                credential="luca",
            )
            for plate, imei in imeis.items()
        }

        logger.info("[OK] luca -> %d vehículos encontrados.", len(objects))

        return objects

    def fetch_track(self, object_id: str, date_range: DateRange) -> list[TrackPoint]:
        """
        Puntos GPS de una placa (object_id = placa en LUCA) dentro del rango,
        combinando uno o más días (LUCA reporta por día calendario), con
        datetime en hora local de Lima.
        """

        start = to_local(date_range.start)
        end = to_local(date_range.end)

        points: list[tuple[int, TrackPoint]] = []

        for fecha in _local_dates_between(start, end):

            response = self._post(
                "/reportes/generar_reporte_puntos_gps",
                json={
                    "empresa": self._empresa,
                    "ruta": self._ruta,
                    "placa": object_id,
                    "fecha": fecha,
                },
            )

            response.raise_for_status()

            for punto in response.json().get("puntos", []):

                ts_ms = punto["timestamp_ms"]
                instante = datetime.fromtimestamp(ts_ms / 1000, tz=LOCAL_TZ)

                if not (start <= instante <= end):
                    continue

                points.append(
                    (
                        ts_ms,
                        TrackPoint(
                            datetime=instante.replace(tzinfo=None).isoformat(timespec="seconds"),
                            latitude=punto.get("latitude"),
                            longitude=punto.get("longitude"),
                            speed=punto.get("speed"),
                        ),
                    )
                )

        points.sort(key=lambda pair: pair[0])

        logger.info("[OK] luca -> %d puntos GPS obtenidos para %s.", len(points), object_id)

        return [point for _, point in points]

    def get_dispatch_records(self, fecha_inicio: str, fecha_fin: str) -> list[dict[str, Any]]:
        """
        Obtiene el listado de despachos (placa, hora, conductor, sentido, hora
        real/calculada de fin) de la empresa/ruta configurada entre dos fechas.
        """

        response = self._post(
            "/reportes/generar_reporte_despachos",
            json={
                "empresa": self._empresa,
                "ruta": self._ruta,
                "fecha_inicio": fecha_inicio,
                "fecha_fin": fecha_fin,
            },
        )

        response.raise_for_status()

        despachos = response.json().get("despachos", [])

        logger.info("[OK] luca -> %d despachos obtenidos.", len(despachos))

        return despachos
