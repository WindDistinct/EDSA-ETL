from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from config import settings
from domain.models import TrackPoint, Vehicle

logger = logging.getLogger(__name__)


class FMTrackClient:
    def __init__(self) -> None:
        self._base_url = settings.fmtrack_base_url

        self._credentials = [
            {
                "name": "default",
                "api_key": settings.fmtrack_api_key,
            },
            {
                "name": "inter",
                "api_key": settings.fmtrack_api_key_inter,
            },
        ]

        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        api_key: str,
        version: int,
        params: dict[str, Any] | None = None,
    ) -> Any:
        query_params = {
            "version": version,
            "api_key": api_key,
        }

        if params:
            query_params.update(params)

        response = self._client.request(
            method,
            endpoint,
            params=query_params,
        )

        response.raise_for_status()

        return response.json()

    def get_objects(self) -> dict[str, Vehicle]:
        """
        Intenta obtener los objetos utilizando las API Keys disponibles.
        Retorna un diccionario indexado por placa.
        """

        last_exception = None

        for credential in self._credentials:
            try:
                data = self._request(
                    "GET",
                    "/objects",
                    version=1,
                    api_key=credential["api_key"],
                )

                objects: dict[str, Vehicle] = {}

                for obj in data:
                    plate = obj.get("name")

                    if not plate:
                        continue

                    objects[plate] = Vehicle(
                        plate=plate,
                        object_id=obj["id"],
                        imei=str(obj.get("imei", "")),
                        credential=credential["name"],
                    )

                logger.info(
                    "[OK] %s -> %d vehículos encontrados.",
                    credential["name"],
                    len(objects),
                )

                return objects

            except Exception as ex:
                logger.error("[ERROR] %s -> %s", credential["name"], ex)
                last_exception = ex

        raise RuntimeError("No fue posible consultar FM Track.") from last_exception

    def get_object(self, object_id: str) -> dict[str, Any]:
        """
        Obtiene un único objeto de FM Track por ID.
        """

        last_exception = None

        for credential in self._credentials:
            try:
                data = self._request(
                    "GET",
                    f"/objects/{object_id}",
                    version=1,
                    api_key=credential["api_key"],
                )

                logger.info("[OK] %s -> objeto encontrado.", credential["name"])

                return {
                    **data,
                    "credential": credential["name"],
                }

            except Exception as ex:
                logger.error("[ERROR] %s -> %s", credential["name"], ex)
                last_exception = ex

        raise RuntimeError("No fue posible consultar el objeto en FM Track.") from last_exception

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
        Obtiene las coordenadas históricas de un objeto.
        """

        last_exception = None

        for credential in self._credentials:
            try:
                params = {
                    "from_datetime": from_datetime,
                    "to_datetime": to_datetime,
                    "include_tire_parameters": str(include_tire_parameters).lower(),
                }

                if continuation_token:
                    params["continuation_token"] = continuation_token

                if limit:
                    params["limit"] = limit

                if include_geozones is not None:
                    params["include_geozones"] = str(include_geozones).lower()

                data = self._request(
                    "GET",
                    f"/objects/{object_id}/coordinates",
                    api_key=credential["api_key"],
                    version=2,
                    params=params,
                )

                logger.info("[OK] %s -> coordenadas obtenidas.", credential["name"])

                return {
                    **data,
                    "credential": credential["name"],
                }

            except Exception as ex:
                logger.error("[ERROR] %s -> %s", credential["name"], ex)
                last_exception = ex

        raise RuntimeError(
            "No fue posible consultar las coordenadas del objeto."
        ) from last_exception

    def get_closest_coordinate(
        self,
        object_id: str,
        target_datetime: str,
        *,
        window_seconds: int = 30,
    ) -> TrackPoint | None:
        """
        Obtiene la coordenada más cercana a un instante determinado.

        Args:
            object_id: UUID del objeto en FM Track.
            target_datetime: Fecha objetivo en formato ISO 8601 UTC.
            window_seconds: Ventana de búsqueda alrededor del instante.

        Returns:
            Coordenada más cercana encontrada o None.
        """

        target = datetime.fromisoformat(
            target_datetime.replace("Z", "+00:00")
        )

        from_datetime = (
            target.timestamp() - window_seconds
        )

        to_datetime = (
            target.timestamp() + window_seconds
        )

        from_dt = datetime.fromtimestamp(
            from_datetime,
            tz=timezone.utc,
        ).isoformat(timespec="milliseconds").replace("+00:00", "Z")

        to_dt = datetime.fromtimestamp(
            to_datetime,
            tz=timezone.utc,
        ).isoformat(timespec="milliseconds").replace("+00:00", "Z")

        data = self.get_object_coordinates(
            object_id=object_id,
            from_datetime=from_dt,
            to_datetime=to_dt,
            limit=100,
        )

        items = data.get("items", [])

        if not items:
            return None

        closest = min(
            items,
            key=lambda item: abs(
                (
                    datetime.fromisoformat(
                        item["datetime"].replace("Z", "+00:00")
                    )
                    - target
                ).total_seconds()
            ),
        )

        position = closest.get("position", {})

        return TrackPoint(
            datetime=closest.get("datetime"),
            latitude=position.get("latitude"),
            longitude=position.get("longitude"),
            speed=position.get("speed"),
        )
