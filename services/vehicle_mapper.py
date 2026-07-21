import pandas as pd


class VehicleMapper:

    def __init__(
        self,
        fmtrack_client,
    ):
        self.fmtrack_client = fmtrack_client


    def build_mapping(self) -> dict[str, dict]:
        """
        Obtiene el catálogo de vehículos desde FM Track.

        Retorna:
        {
            "A0P736": {
                "object_id": "...",
                "imei": "...",
                "credential": "default"
            }
        }
        """

        return self.fmtrack_client.get_objects()


    def enrich(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Agrega OBJECT_ID basado en PLACA.
        """

        mapping = self.build_mapping()

        df = df.copy()

        df["OBJECT_ID"] = (
            df["PLACA"]
            .map(
                lambda placa:
                    mapping.get(
                        str(placa).strip(),
                        {}
                    )
                    .get("object_id")
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