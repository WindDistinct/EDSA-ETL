from pathlib import Path

import pandas as pd


class PartitionSplitter:

    def __init__(
        self,
        partitions: int = 4,
    ):
        self.partitions = partitions

    def split(
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
        
        def get_partition(
            date,
            limits,
        ):

            for index, limit in enumerate(limits):

                if date < limit:
                    return index + 1

            return len(limits) + 1
        
        df["PARTITION"] = (
            df["FECHORA_INI_VIAJE"]
            .apply(
                lambda x: get_partition(
                    x,
                    limits,
                )
            )
        )
        
        output_folder = Path(output_folder)

        output_folder.mkdir(
            parents=True,
            exist_ok=True,
        )

        generated = []

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

            file = output_folder / filename

            data.drop(
                columns=["PARTITION"]
            ).to_excel(
                file,
                index=False,
            )

            generated.append(file)
            
            print("\nArchivos generados:")
            
            print(
                f"Partición {partition:02}: "
                f"{len(data)} registros "
                f"({start_date} -> {end_date})"
            )