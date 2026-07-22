from datetime import datetime

import pandas as pd

from services.trackpoints_processor import TrackPointsProcessor
from services.trackpoints_writer import TrackPointsWriter
from services.vehicle_mapper import VehicleMapper


class FixedRangeProcessor:
    """
    Procesa listados simples (RUC, CODIGO_RUTA, PLACA, IMEI) sin fechas propias,
    aplicando un mismo intervalo de fechas fijo a todos los vehículos.
    """

    COLUMN_ALIASES = {
        "RUC": "RUC_EMPRESA",
        "RUC_EMPRESA": "RUC_EMPRESA",
        "CODIGO_RUTA": "CODIGO_RUTA",
        "PLACA": "PLACA",
        "IMEI": "IMEI",
    }

    REQUIRED_COLUMNS = [
        "RUC_EMPRESA",
        "CODIGO_RUTA",
        "PLACA",
        "IMEI",
    ]

    def __init__(
        self,
        fmtrack_client,
    ):
        self.fmtrack_client = fmtrack_client

        self.vehicle_mapper = VehicleMapper(
            fmtrack_client
        )

        self.track_processor = TrackPointsProcessor(
            fmtrack_client,
            require_ignition_on=True,
        )

    def _parse_boundary(
        self,
        value: str,
        *,
        is_end: bool,
    ) -> datetime:

        value = value.strip()

        parsed = datetime.fromisoformat(value)

        if is_end and len(value) <= 10:

            parsed = parsed.replace(
                hour=23,
                minute=59,
                second=59,
            )

        return parsed

    def _load_listing(
        self,
        input_file: str,
    ) -> pd.DataFrame:

        sheets = pd.read_excel(
            input_file,
            sheet_name=None,
            dtype=str,
        )

        df = pd.concat(
            sheets.values(),
            ignore_index=True,
        )

        df.columns = (
            df.columns
            .str.strip()
            .str.upper()
        )

        df = df.rename(
            columns=self.COLUMN_ALIASES
        )

        missing = [
            column
            for column in self.REQUIRED_COLUMNS
            if column not in df.columns
        ]

        if missing:
            raise ValueError(
                f"Columnas faltantes en el listado: {missing}"
            )

        df = df[self.REQUIRED_COLUMNS].copy()

        for column in self.REQUIRED_COLUMNS:

            df[column] = (
                df[column]
                .astype(str)
                .str.strip()
            )

        return df

    def process(
        self,
        input_file: str,
        output_file: str,
        start_date: str,
        end_date: str,
    ) -> None:

        start = self._parse_boundary(
            start_date,
            is_end=False,
        )

        end = self._parse_boundary(
            end_date,
            is_end=True,
        )

        print(
            f"Intervalo fijo: {start} -> {end}"
        )

        print(
            f"Leyendo {input_file}"
        )

        df = self._load_listing(
            input_file
        )

        print(
            f"Vehículos en el listado: {len(df)}"
        )

        df = self.vehicle_mapper.enrich(
            df
        )

        df["START_DATETIME"] = start
        df["END_DATETIME"] = end

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
            f"Vehículos leídos       : {total}"
        )

        print(
            f"Vehículos procesados   : {processed}"
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
