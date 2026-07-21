import pandas as pd

from services.trackpoints_processor import TrackPointsProcessor
from services.trackpoints_writer import TrackPointsWriter


class PipelineProcessor:

    def __init__(
        self,
        fmtrack_client,
    ):

        self.fmtrack_client = fmtrack_client

        self.track_processor = TrackPointsProcessor(
            fmtrack_client
        )

    def _load_objects(
        self,
    ) -> dict[str, dict]:

        print(
            "Obteniendo catálogo de vehículos..."
        )

        objects = self.fmtrack_client.get_objects()

        print(
            f"Vehículos encontrados: {len(objects)}"
        )

        return objects

    def _attach_object_ids(
        self,
        df: pd.DataFrame,
        objects: dict,
    ) -> pd.DataFrame:

        df = df.copy()

        df["OBJECT_ID"] = (
            df["PLACA"]
            .astype(str)
            .str.strip()
            .map(
                lambda plate:
                    objects.get(
                        plate,
                        {}
                    ).get("object_id")
            )
        )

        missing = (
            df["OBJECT_ID"]
            .isna()
            .sum()
        )

        print(
            f"Vehículos sin OBJECT_ID: {missing}"
        )

        return df

    def process(
        self,
        input_file: str,
        output_file: str,
    ) -> None:

        print(
            f"Leyendo {input_file}"
        )

        sheets = pd.read_excel(
            input_file,
            sheet_name=None,
            dtype=str,
        )

        df = pd.concat(
            sheets.values(),
            ignore_index=True,
        )

        print(len(df))

        print(df.groupby(df["FECHORA_INI_VIAJE"]).size())

        objects = self._load_objects()

        df = self._attach_object_ids(
            df,
            objects,
        )

        writer = TrackPointsWriter(
            output_file
        )

        writer.open()

        total = len(df)

        processed = 0

        errors = 0

        track_points = 0

        for index, row in df.iterrows():

            if pd.isna(
                row["OBJECT_ID"]
            ):

                errors += 1

                print(
                    f"[ERROR] {row['PLACA']} "
                    "sin OBJECT_ID."
                )

                continue

            result = (
                self.track_processor.process_row(
                    row
                )
            )

            if result["success"]:

                if result["points"]:

                    writer.append(
                        result["points"]
                    )

                    track_points += len(
                        result["points"]
                    )

                processed += 1

            else:

                errors += 1

                print(
                    f"[ERROR] "
                    f"{row['PLACA']} -> "
                    f"{result['error']}"
                )

            if (index + 1) % 100 == 0:

                print(
                    f"Procesados "
                    f"{index + 1}/{total}"
                )

        writer.close()

        print()

        print("=" * 40)
        print("RESUMEN")
        print("=" * 40)

        print(
            f"Tramos leídos          : {total}"
        )

        print(
            f"Tramos procesados      : {processed}"
        )

        print(
            f"Errores                : {errors}"
        )

        print(
            f"Track points generados : {track_points}"
        )

        print(
            f"Archivo generado       : {output_file}"
        )