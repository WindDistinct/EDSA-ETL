from datetime import datetime

from pathlib import Path

import pandas as pd
import time


class ExcelProcessor:

    def __init__(
        self,
        fmtrack_client,
        batch_size: int = 1000,
        batch_delay: int = 10,
    ):
        self.fmtrack_client = fmtrack_client
        self.batch_size = batch_size
        self.batch_delay = batch_delay

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

        return dt.isoformat(
            timespec="milliseconds"
        ) + "Z"

    def _process_row(
        self,
        row: pd.Series,
        objects: dict[str, dict],
    ) -> dict:
        
        self.failed_rows = []

        placa = row["PLACA"]

        vehicle = objects.get(placa)

        if not vehicle:
            return {}

        object_id = vehicle["object_id"]

        track_datetime = self._format_datetime(
            row["FECHA_HORA_TRACK"]
        )
        
        coordinate = self.fmtrack_client.get_closest_coordinate(
            object_id=object_id,
            target_datetime=track_datetime,
        )

        if not coordinate:
            print(
                f"Sin coordenadas: placa={placa}, fecha={track_datetime}"
            )
            
            self.failed_rows.append({
                "PLACA": placa,
                "FECHA_HORA_TRACK": row["FECHA_HORA_TRACK"],
            })

            return {}

        return {
            "LATITUD": coordinate["latitude"],
            "LONGITUD": coordinate["longitude"],
            "VELOCIDAD": coordinate["speed"],
        }

    def process(
        self,
        input_file: str,
        output_file: str,
    ) -> None:

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

        df["LATITUD"] = pd.to_numeric(
            df["LATITUD"],
            errors="coerce",
        )

        df["LONGITUD"] = pd.to_numeric(
            df["LONGITUD"],
            errors="coerce",
        )

        df["VELOCIDAD"] = pd.to_numeric(
            df["VELOCIDAD"],
            errors="coerce",
        )

        print(
            f"Registros encontrados: {len(df)}"
        )

        objects = self.fmtrack_client.get_objects()

        print(
            f"Vehículos FM Track encontrados: {len(objects)}"
        )

        df["OBJECT_ID"] = df["PLACA"].apply(
            lambda placa: objects.get(placa, {}).get("object_id")
        )

        not_found = df[
            df["OBJECT_ID"].isna()
        ]

        print(
            f"Placas no encontradas: {len(not_found)}"
        )

        total_rows = len(df)

        for start in range(
            0,
            total_rows,
            self.batch_size,
        ):

            end = min(
                start + self.batch_size,
                total_rows,
            )

            print(
                f"Procesando filas {start} - {end}"
            )

            batch = df.iloc[start:end]

            for index, row in batch.iterrows():

                try:

                    result = self._process_row(
                        row,
                        objects,
                    )

                    for column, value in result.items():
                        df.at[index, column] = value

                except Exception as ex:

                    print(
                        f"Error procesando fila {index}: {ex}"
                    )

                processed += 1

                if processed % 50 == 0:
                    print(
                        f"Procesadas {processed}/{total_rows}"
                    )

            if end < total_rows:

                print(
                    f"Esperando {self.batch_delay} segundos..."
                )

                time.sleep(
                    self.batch_delay
                )

        # Eliminamos columna auxiliar
        df.drop(
            columns=["OBJECT_ID"],
            inplace=True,
        )

        df.to_excel(
            output_file,
            index=False,
        )

        print(
            "Archivo generado correctamente."
        )