from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from config import settings
from domain.models import DateRange, TrackPoint, Vehicle
from domain.rules import format_for_api, to_local_isoformat
from infrastructure.http_retry import RateGate, request_with_retry

logger = logging.getLogger(__name__)

# Máximo de puntos por página que acepta /objects/{id}/coordinates.
PAGE_SIZE = 1000


class FMTrackError(RuntimeError):
    """
    Error de FM Track sin la URL de la petición: la api_key viaja como query
    param, así que str() de un httpx.HTTPStatusError la expondría en logs
    y reportes.
    """

    def __init__(self, endpoint: str, status_code: int | None, detail: str = "") -> None:
        self.endpoint = endpoint
        self.status_code = status_code
        message = f"FM Track {endpoint} -> HTTP {status_code}" if status_code else f"FM Track {endpoint}"
        super().__init__(f"{message} {detail}".strip())


class FMTrackClient:
    def __init__(
        self,
        *,
        credentials: list[dict[str, str]] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = settings.fmtrack_base_url

        if credentials is None:
            credentials = [
                {"name": "default", "api_key": settings.fmtrack_api_key},
                {"name": "inter", "api_key": settings.fmtrack_api_key_inter},
            ]

        # Una key vacía en .env no se intenta.
        self._credentials = [c for c in credentials if c.get("api_key")]

        # object_id -> credencial con la que se listó; se llena en get_objects()
        # para no probar todas las keys en cada consulta de coordenadas.
        self._credential_by_object: dict[str, dict[str, str]] = {}

        # Pausa compartida por todos los workers ante un 429.
        self._gate = RateGate()

        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=30.0,
            transport=transport,
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

        try:
            response = request_with_retry(
                self._client,
                method,
                endpoint,
                params=query_params,
                gate=self._gate,
            )
        except httpx.TransportError as ex:
            raise FMTrackError(endpoint, None, type(ex).__name__) from None

        if response.is_error:
            raise FMTrackError(endpoint, response.status_code, response.reason_phrase)

        return response.json()

    def _credentials_for(self, object_id: str) -> list[dict[str, str]]:
        """
        La credencial con la que se catalogó el objeto si se conoce; si no,
        todas en orden.
        """

        known = self._credential_by_object.get(object_id)

        return [known] if known else self._credentials

    def get_objects(self) -> dict[str, Vehicle]:
        """
        Lista los objetos de todas las API Keys disponibles y los combina.
        Una key que falla se omite con un aviso; solo falla si fallan todas.
        Ante placas repetidas gana la primera key. Retorna un diccionario
        indexado por placa.
        """

        objects: dict[str, Vehicle] = {}

        last_exception: Exception | None = None

        any_ok = False

        for credential in self._credentials:
            try:
                data = self._request(
                    "GET",
                    "/objects",
                    version=1,
                    api_key=credential["api_key"],
                )
            except FMTrackError as ex:
                logger.warning("[OMITIDA] credencial %s -> %s", credential["name"], ex)
                last_exception = ex
                continue

            any_ok = True

            count = 0

            for obj in data:
                plate = obj.get("name")

                if not plate or plate in objects:
                    continue

                objects[plate] = Vehicle(
                    plate=plate,
                    object_id=obj["id"],
                    imei=str(obj.get("imei", "")),
                    credential=credential["name"],
                )

                self._credential_by_object[obj["id"]] = credential

                count += 1

            logger.info("[OK] %s -> %d vehículos encontrados.", credential["name"], count)

        if not any_ok:
            raise RuntimeError("No fue posible consultar FM Track.") from last_exception

        return objects

    def get_object(self, object_id: str) -> dict[str, Any]:
        """
        Obtiene un único objeto de FM Track por ID.
        """

        last_exception = None

        for credential in self._credentials_for(object_id):
            try:
                data = self._request(
                    "GET",
                    f"/objects/{object_id}",
                    version=1,
                    api_key=credential["api_key"],
                )

                return {
                    **data,
                    "credential": credential["name"],
                }

            except FMTrackError as ex:
                logger.debug("[ERROR] %s -> %s", credential["name"], ex)
                last_exception = ex

        raise RuntimeError(
            f"No fue posible consultar el objeto en FM Track: {last_exception}"
        ) from last_exception

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

        params: dict[str, Any] = {
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

        last_exception = None

        for credential in self._credentials_for(object_id):
            try:
                data = self._request(
                    "GET",
                    f"/objects/{object_id}/coordinates",
                    api_key=credential["api_key"],
                    version=2,
                    params=params,
                )

                return {
                    **data,
                    "credential": credential["name"],
                }

            except FMTrackError as ex:
                logger.debug("[ERROR] %s -> %s", credential["name"], ex)
                last_exception = ex

        raise RuntimeError(
            f"No fue posible consultar las coordenadas del objeto: {last_exception}"
        ) from last_exception

    def fetch_track(self, object_id: str, date_range: DateRange) -> list[TrackPoint]:
        """
        Todos los puntos del objeto en el rango, recorriendo la paginación
        (continuation_token), con datetime en hora local de Lima.
        """

        points: list[TrackPoint] = []

        continuation_token = None

        while True:

            page = self.get_object_coordinates(
                object_id=object_id,
                from_datetime=format_for_api(date_range.start),
                to_datetime=format_for_api(date_range.end),
                continuation_token=continuation_token,
                limit=PAGE_SIZE,
            )

            for item in page.get("items") or []:

                position = item.get("position", {})

                points.append(
                    TrackPoint(
                        datetime=to_local_isoformat(item["datetime"]),
                        latitude=position.get("latitude"),
                        longitude=position.get("longitude"),
                        speed=position.get("speed"),
                        ignition_status=item.get("ignition_status"),
                    )
                )

            continuation_token = page.get("continuation_token")

            if continuation_token is None:
                return points

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
