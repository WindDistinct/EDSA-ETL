from datetime import datetime

import pandas as pd


class OperationalProcessor:

    def __init__(self):
        pass


    def _parse_datetime(
        self,
        value,
    ) -> datetime | None:
        """
        Convierte fechas provenientes del Excel operacional.
        """

        if pd.isna(value):
            return None

        value = str(value).strip()

        if not value:
            return None

        value = (
            value
            .replace(
                " GMT-0500 (hora estándar de Perú)",
                "",
            )
            .replace(
                " GMT-0500 (hora estándar del Perú)",
                "",
            )
        )

        try:
            return datetime.strptime(
                value,
                "%a %b %d %Y %H:%M:%S",
            )

        except ValueError:
            return None


    def _build_start_datetime(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Construye FECHORA_INI_VIAJE.
        """

        df["FECHORA_INI_VIAJE"] = pd.to_datetime(
            df["FECHA"].astype(str)
            + " "
            + df["HORA"].astype(str),
            errors="coerce",
        )

        return df


    def _prepare_operational_file(
        self,
        input_file: str,
    ) -> pd.DataFrame:
        """
        Une Ida y Vuelta y normaliza columnas.
        """

        sheets = pd.read_excel(
            input_file,
            sheet_name=[
                "Ida",
                "Vuelta",
            ],
        )

        ida = sheets["Ida"].copy()
        vuelta = sheets["Vuelta"].copy()


        ida["SENTIDO"] = 0
        vuelta["SENTIDO"] = 1


        df = pd.concat(
            [
                ida,
                vuelta,
            ],
            ignore_index=True,
        )


        df.columns = (
            df.columns
            .str.strip()
            .str.upper()
        )


        df["NRO_DOC_CONDUCTOR"] = (
            df["CONDUCTOR"]
            .apply(self._extract_driver_document)
        )


        df["PLACA"] = (
            df["PLACA"]
            .astype(str)
            .str.strip()
        )


        df = self._build_start_datetime(
            df
        )


        df["FECHA_HORA_FIN_TRAMO"] = (
            df["HORA_REAL_ULTIMO_PUNTO"]
            .apply(
                self._parse_datetime
            )
        )


        df["FECHA_HORA_FIN_TRAMO_CALCULADA"] = (
            df["HORA_CALCULADA_ULTIMO_PUNTO"]
            .apply(
                self._parse_datetime
            )
        )


        return df

    def _get_vehicle_metadata(
        self,
        clean_file: str,
    ) -> pd.DataFrame:
        """
        Obtiene la relación PLACA -> IMEI
        desde el documento limpio.
        """

        df = pd.read_excel(
            clean_file,
            dtype=str,
        )


        df.columns = (
            df.columns
            .str.strip()
            .str.upper()
        )


        vehicles = (
            df[
                [
                    "PLACA",
                    "IMEI",
                ]
            ]
            .drop_duplicates(
                subset=[
                    "PLACA"
                ]
            )
        )


        vehicles["PLACA"] = (
            vehicles["PLACA"]
            .astype(str)
            .str.strip()
        )


        return vehicles
    
    def _extract_driver_document(
        self,
        value,
    ) -> str:

        if pd.isna(value):
            return ""

        value = str(value)

        parts = value.split(",")

        if len(parts) < 2:
            return ""

        return parts[-1].strip()

    def process(
        self,
        operational_file: str,
        clean_file: str,
        output_file: str,
    ) -> None:

        operational_df = self._prepare_operational_file(
            operational_file
        )


        vehicle_df = self._get_vehicle_metadata(
            clean_file
        )


        df = operational_df.merge(
            vehicle_df,
            on="PLACA",
            how="left",
        )


        clean_df = pd.read_excel(
            clean_file,
            dtype=str,
        )

        clean_df.columns = (
            clean_df.columns
            .str.strip()
            .str.upper()
        )


        ruc = (
            clean_df["RUC_EMPRESA"]
            .iloc[0]
        )


        ruta = (
            clean_df["CODIGO_RUTA"]
            .iloc[0]
        )


        df["RUC_EMPRESA"] = ruc
        df["CODIGO_RUTA"] = ruta


        columns = [
            "RUC_EMPRESA",
            "PLACA",
            "IMEI",
            "CODIGO_RUTA",
            "FECHORA_INI_VIAJE",
            "FECHA_HORA_FIN_TRAMO",
            "FECHA_HORA_FIN_TRAMO_CALCULADA",
            "SENTIDO",
            "NRO_DOC_CONDUCTOR",
        ]

        missing_columns = [
            column
            for column in columns
            if column not in df.columns
        ]

        if missing_columns:
            raise ValueError(
                f"Columnas faltantes: {missing_columns}"
            )

        result = df[columns]


        result.to_excel(
            output_file,
            index=False,
        )


        print(
            f"Registros procesados: {len(result)}"
        )

        print(
            "Documento operacional generado correctamente."
        )