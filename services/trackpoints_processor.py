from datetime import datetime
from typing import Any

class TrackPointsProcessor:

    def __init__(
        self,
        fmtrack_client,
        require_ignition_on: bool = False,
    ):
        self.fmtrack_client = fmtrack_client
        self.require_ignition_on = require_ignition_on

    def _format_datetime(
        self,
        value: datetime,
    ) -> str:

        if hasattr(value, "to_pydatetime"):
            value = value.to_pydatetime()

        return (
            value.astimezone()
            .isoformat(
                timespec="milliseconds"
            )
            .replace(
                "+00:00",
                "Z"
            )
        )

    def _resolve_datetime(
        self,
        value: Any,
    ) -> datetime | None:

        if value is None:
            return None

        if isinstance(value, datetime):
            return value

        if isinstance(value, str):

            value = value.strip()

            if not value:
                return None

            return datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )

        return None

    def _get_track_range(
        self,
        row,
    ) -> tuple[datetime, datetime]:

        start = (
            row.get("START_DATETIME")
            or row.get("FECHORA_INI_VIAJE")
        )

        end = (
            row.get("END_DATETIME")
            or row.get("FECHA_HORA_FIN_TRAMO")
        )

        if end is None:

            end = self._resolve_datetime(
                row["FECHA_HORA_FIN_TRAMO_CALCULADA"]
            )

        if start is None:
            raise ValueError(
                "La fecha inicial es obligatoria."
            )

        if end is None:
            raise ValueError(
                "No existe fecha final."
            )

        return start, end

    def _get_track_points(
        self,
        object_id: str,
        start: datetime,
        end: datetime,
    ) -> list[dict]:

        points: list[dict] = []

        continuation_token = None

        page = 1

        total_items = 0

        while True:

            response = self.fmtrack_client.get_object_coordinates(
                object_id=object_id,
                from_datetime=self._format_datetime(start),
                to_datetime=self._format_datetime(end),
                continuation_token=continuation_token,
                limit=1000,
            )

            items = response.get("items") or []

            total_items += len(items)

            for item in items:

                ignition_status = item.get("ignition_status")

                if (
                    self.require_ignition_on
                    and ignition_status != "ON"
                ):
                    continue

                position = item.get("position", {})

                points.append(
                    {
                        "datetime": item["datetime"],
                        "latitude": position.get("latitude"),
                        "longitude": position.get("longitude"),
                        "speed": position.get("speed"),
                        "ignition_status": ignition_status,
                    }
                )

            continuation_token = response.get(
                "continuation_token"
            )

            if continuation_token is None:
                break

            page += 1

        return points
    
    def process_row(
        self,
        row,
    ) -> dict:

        try:

            object_id = row.get("OBJECT_ID")

            if not object_id:
                raise ValueError(
                    "La fila no contiene OBJECT_ID."
                )

            start, end = self._get_track_range(
                row
            )

            points = self._get_track_points(
                object_id=object_id,
                start=start,
                end=end,
            )

            enriched_points = []

            for point in points:

                enriched_points.append(
                    {
                        "ruc_empresa": row.get("RUC_EMPRESA"),
                        "placa": row.get("PLACA"),
                        "imei": row.get("IMEI"),
                        "codigo_ruta": row.get("CODIGO_RUTA"),
                        "sentido": row.get("SENTIDO"),
                        "nro_doc_conductor": row.get("NRO_DOC_CONDUCTOR"),
                        "object_id": object_id,
                        "fechora_ini_viaje": start.isoformat(),
                        "fin_tramo": end.isoformat(),
                        **point,
                    }
                )

            return {
                "success": True,
                "points": enriched_points,
                "error": None,
            }

        except Exception as ex:

            return {
                "success": False,
                "points": [],
                "error": str(ex),
            }