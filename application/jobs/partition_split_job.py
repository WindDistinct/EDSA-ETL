from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from domain.rules import assign_partition

logger = logging.getLogger(__name__)


class PartitionSplitJob:
    """
    Divide un documento de tramos grande en N particiones por rango de fecha,
    cada una con una hoja por día.
    """

    def __init__(self, partitions: int = 4):
        self.partitions = partitions

    def run(
        self,
        input_file: str,
        output_folder: str,
    ) -> None:

        df = pd.read_excel(
            input_file,
            dtype={
                "RUC_EMPRESA": str,
                "PLACA": str,
                "IMEI": str,
                "CODIGO_RUTA": str,
                "NRO_DOC_CONDUCTOR": str,
            },
        )

        df["FECHORA_INI_VIAJE"] = pd.to_datetime(
            df["FECHORA_INI_VIAJE"]
        )

        start = df["FECHORA_INI_VIAJE"].min()
        end = df["FECHORA_INI_VIAJE"].max()

        window = (end - start) / self.partitions

        limits = [
            start + window * i
            for i in range(1, self.partitions)
        ]

        df["PARTITION"] = df["FECHORA_INI_VIAJE"].apply(
            lambda dt: assign_partition(dt, limits)
        )

        output_path = Path(output_folder)

        output_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        for partition, data in df.groupby("PARTITION"):

            start_date = (
                data["FECHORA_INI_VIAJE"]
                .min()
                .strftime("%Y-%m-%d")
            )

            end_date = (
                data["FECHORA_INI_VIAJE"]
                .max()
                .strftime("%Y-%m-%d")
            )

            filename = (
                f"part_{partition:02}_"
                f"{start_date}_"
                f"{end_date}.xlsx"
            )

            file = output_path / filename

            with pd.ExcelWriter(
                file,
                engine="openpyxl",
            ) as writer:

                data = data.drop(columns=["PARTITION"])

                data["FECHA"] = (
                    data["FECHORA_INI_VIAJE"]
                    .dt.strftime("%Y-%m-%d")
                )

                for day, daily_data in data.groupby("FECHA"):

                    daily_data.drop(
                        columns=["FECHA"]
                    ).to_excel(
                        writer,
                        sheet_name=day,
                        index=False,
                    )

            logger.info(
                "Partición %02d: %d registros (%s -> %s)",
                partition,
                len(data),
                start_date,
                end_date,
            )
