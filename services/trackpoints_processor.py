from datetime import datetime
from typing import Any
from client.fmtrack_client import FMTrackClient

class TrackPointsProcessor:

    def __init__(
        self,
        fmtrack_client,
    ):
        self.fmtrack_client = fmtrack_client
        
    def _format_datetime(
        self,
        value: datetime,
    ) -> str:

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

        start = self._resolve_datetime(
            row["FECHORA_INI_VIAJE"]
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
                from_datetime=self._format_datetime(start),
                to_datetime=self._format_datetime(end),
                continuation_token=continuation_token,
                limit=1000,
            )

            items = response.get(
                "items"
            ) or []
            
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
                        "ruc_empresa": row.get("RUC_EMPRESA"),
                        "placa": row.get("PLACA"),
                        "imei": row.get("IMEI"),
                        "codigo_ruta": row.get("CODIGO_RUTA"),
                        "sentido": row.get("SENTIDO"),
                        "nro_doc_conductor": row.get(
                            "NRO_DOC_CONDUCTOR"
                        ),
                        "object_id": object_id,
                        "inicio_tramo": self._format_datetime(start),
                        "fin_tramo": self._format_datetime(end),
                        **point,
                    }
                )

            if not points:
                print(
                    f"[WARN] {row.get('PLACA')} -> "
                    "sin puntos encontrados"
                )

                return []

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
    
    def process_dataframe(
        self,
        df,
    ) -> list[dict]:

        all_points = []

        total = len(df)

        print(
            f"Iniciando procesamiento de {total} tramos..."
        )

        for index, row in df.iterrows():

            try:

                points = self.process_row(
                    row
                )

                all_points.extend(
                    points
                )


            except Exception as ex:

                print(
                    f"[ERROR] fila {index} "
                    f"{row.get('PLACA')} -> {ex}"
                )


            if (index + 1) % 100 == 0:

                print(
                    f"Procesadas {index + 1}/{total}"
                )


        print(
            f"Total track points generados: {len(all_points)}"
        )

        return all_points