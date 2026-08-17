from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from config import settings
from domain.models import Vehicle
from infrastructure.http_retry import request_with_retry

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("America/Lima")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _ts_ms_to_iso_utc(ts_ms: int) -> str:
    return (
        datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _local_dates_between(start: datetime, end: datetime) -> list[str]:
    start_local = start.astimezone(LOCAL_TZ).date()
    end_local = end.astimezone(LOCAL_TZ).date()

    dates = []
    current = start_local

    while current <= end_local:
        dates.append(current.isoformat())
        current += timedelta(days=1)

    return dates


class LucaClient:
    def __init__(self, empresa: int, ruta: int) -> None:
        self._empresa = empresa
        self._ruta = ruta

        self._client = httpx.Client(
            base_url=settings.luca_base_url,
            headers={"x-api-key": settings.luca_api_key},
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def _post(self, endpoint: str, json: dict[str, Any]) -> httpx.Response:
        return request_with_retry(self._client, "POST", endpoint, json=json)

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

    def get_object_coordinates(
        self,
        object_id: str,
        from_datetime: str,
        to_datetime: str,
        *,
        continuation_token: str | None = None,
        limit: int | None = None,
        include_geozones: bool | None = None,
        include_tire_parameters: bool = False,
    ) -> dict[str, Any]:
        """
        Obtiene los puntos GPS continuos de una placa dentro de un rango de fechas,
        combinando la respuesta de uno o más días (LUCA reporta por día calendario).
        """

        start_dt = _parse_utc(from_datetime)
        end_dt = _parse_utc(to_datetime)

        items: list[dict[str, Any]] = []

        for fecha in _local_dates_between(start_dt, end_dt):

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

                punto_dt_obj = datetime.fromtimestamp(
                    punto["timestamp_ms"] / 1000, tz=timezone.utc
                )

                if not (start_dt <= punto_dt_obj <= end_dt):
                    continue

                punto_dt = _ts_ms_to_iso_utc(punto["timestamp_ms"])

                items.append(
                    {
                        "datetime": punto_dt,
                        "position": {
                            "latitude": punto.get("latitude"),
                            "longitude": punto.get("longitude"),
                            "speed": punto.get("speed"),
                        },
                    }
                )

        items.sort(key=lambda item: item["datetime"])

        logger.info("[OK] luca -> %d puntos GPS obtenidos para %s.", len(items), object_id)

        return {
            "items": items,
            "continuation_token": None,
            "credential": "luca",
        }

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
