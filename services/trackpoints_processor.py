from datetime import datetime
from typing import Any

class TrackPointsProcessor:

    def __init__(
        self,
        fmtrack_client,
    ):
        self.fmtrack_client = fmtrack_client

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

        start = self._resolve_datetime(
            row["FECHA_HORA_TRACK"]
        )

        end = self._resolve_datetime(
            row["FECHA_HORA_FIN_TRAMO"]
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

        while True:

            response = self.fmtrack_client.get_object_coordinates(
                object_id=object_id,
                from_datetime=start.isoformat(),
                to_datetime=end.isoformat(),
                continuation_token=continuation_token,
                limit=1000,
            )

            items = response.get("items", [])

            for item in items:

                position = item.get("position", {})

                points.append(
                    {
                        "datetime": item["datetime"],
                        "latitude": position.get("latitude"),
                        "longitude": position.get("longitude"),
                        "speed": position.get("speed"),
                    }
                )
            
            continuation_token = response.get(
                "continuation_token"
            )

            if continuation_token is None:
                break

        return points
    
    def process_row(
    self,
    row,
) -> list[dict]:
        """
        Procesa un único tramo y devuelve todos los track points
        enriquecidos con la información del tramo.
        """

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
                    "placa": row.get("PLACA"),
                    "imei": row.get("IMEI"),
                    "codigo_ruta": row.get("CODIGO_RUTA"),
                    "object_id": object_id,
                    "inicio_tramo": start.isoformat(),
                    "fin_tramo": end.isoformat(),
                    **point,
                }
            )

        print(
            f"[TRACK] {row.get('PLACA')} -> "
            f"{len(enriched_points)} puntos "
            f"({start} -> {end})"
        )

        return enriched_points
    
    def _group_points_by_day(
        self,
        points: list[dict],
    ) -> dict[str, list[dict]]:

        grouped: dict[str, list[dict]] = {}

        for point in points:

            day = (
                datetime.fromisoformat(
                    point["datetime"].replace("Z", "+00:00")
                )
                .date()
                .isoformat()
            )

            grouped.setdefault(
                day,
                []
            ).append(point)

        return grouped
    
    