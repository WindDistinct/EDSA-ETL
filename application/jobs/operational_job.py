from __future__ import annotations

import logging

import pandas as pd

from domain.rules import extract_driver_document, parse_operational_datetime
from infrastructure.excel_io import normalize_columns

logger = logging.getLogger(__name__)


class OperationalJob:
    """
    Une un documento operacional (hojas Ida/Vuelta) con un documento limpio
    (RUC/ruta/PLACA->IMEI) para generar el documento estándar de tramos
    consumido luego por PartitionSplitJob y PipelineJob.
    """

    OUTPUT_COLUMNS = [
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

    def _prepare_operational_file(
        self,
        operational_file: str,
    ) -> pd.DataFrame:

        sheets = pd.read_excel(
            operational_file,
            sheet_name=["Ida", "Vuelta"],
        )

        ida = sheets["Ida"].copy()
        vuelta = sheets["Vuelta"].copy()

        ida["SENTIDO"] = 0
        vuelta["SENTIDO"] = 1

        df = pd.concat(
            [ida, vuelta],
            ignore_index=True,
        )

        df = normalize_columns(df)

        df["NRO_DOC_CONDUCTOR"] = df["CONDUCTOR"].apply(
            lambda value: extract_driver_document(
                None if pd.isna(value) else value
            )
        )

        df["PLACA"] = (
            df["PLACA"]
            .astype(str)
            .str.strip()
        )

        df["FECHORA_INI_VIAJE"] = pd.to_datetime(
            df["FECHA"].astype(str) + " " + df["HORA"].astype(str),
            errors="coerce",
        )

        df["FECHA_HORA_FIN_TRAMO"] = df["HORA_REAL_ULTIMO_PUNTO"].apply(
            lambda value: parse_operational_datetime(
                None if pd.isna(value) else value
            )
        )

        df["FECHA_HORA_FIN_TRAMO_CALCULADA"] = df["HORA_CALCULADA_ULTIMO_PUNTO"].apply(
            lambda value: parse_operational_datetime(
                None if pd.isna(value) else value
            )
        )

        return df

    def _get_vehicle_metadata(
        self,
        clean_file: str,
    ) -> pd.DataFrame:

        df = pd.read_excel(clean_file, dtype=str)

        df = normalize_columns(df)

        vehicles = df[["PLACA", "IMEI"]].drop_duplicates(subset=["PLACA"])

        vehicles["PLACA"] = (
            vehicles["PLACA"]
            .astype(str)
            .str.strip()
        )

        return vehicles

    def run(
        self,
        operational_file: str,
        clean_file: str,
        output_file: str,
    ) -> None:

        operational_df = self._prepare_operational_file(operational_file)

        vehicle_df = self._get_vehicle_metadata(clean_file)

        df = operational_df.merge(
            vehicle_df,
            on="PLACA",
            how="left",
        )

        clean_df = pd.read_excel(clean_file, dtype=str)
        clean_df = normalize_columns(clean_df)

        df["RUC_EMPRESA"] = clean_df["RUC_EMPRESA"].iloc[0]
        df["CODIGO_RUTA"] = clean_df["CODIGO_RUTA"].iloc[0]

        missing_columns = [
            column
            for column in self.OUTPUT_COLUMNS
            if column not in df.columns
        ]

        if missing_columns:
            raise ValueError(f"Columnas faltantes: {missing_columns}")

        result = df[self.OUTPUT_COLUMNS]

        result.to_excel(output_file, index=False)

        logger.info("Registros procesados: %d", len(result))
        logger.info("Documento operacional generado correctamente.")
