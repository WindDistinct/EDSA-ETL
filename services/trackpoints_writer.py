from pathlib import Path

from openpyxl import Workbook
from openpyxl.workbook.workbook import Workbook as WorkbookType

class TrackPointsWriter:

    HEADERS = [
        "RUC_EMPRESA",
        "PLACA",
        "IMEI",
        "CODIGO_RUTA",
        "SENTIDO",
        "NRO_DOC_CONDUCTOR",
        "INICIO_TRAMO",
        "FIN_TRAMO",
        "FECHA_HORA_TRACK",
        "LATITUD",
        "LONGITUD",
        "VELOCIDAD",
    ]

    def __init__(self, output_file: str):

        self.output_file = Path(output_file)

        self.workbook: Workbook | None = None

        self.sheets: dict[str, any] = {}
        
    def open(self):

        if self.workbook is not None:
            return
            
        self.output_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.workbook = Workbook()

        default = self.workbook.active

        self.workbook.remove(default)

    def _get_sheet(
        self,
        day: str,
    ):

        if day in self.sheets:
            return self.sheets[day]

        ws = self.workbook.create_sheet(day)

        ws.append(self.HEADERS)

        self.sheets[day] = ws

        return ws
    
    def close(self):

        if self.workbook is None:
            return

        self.workbook.save(
            self.output_file
        )

        self.workbook.close()

        self.workbook = None
        
    def append(
        self,
        points: list[dict],
    ) -> None:

        for point in points:

            day = point["datetime"][:10]

            sheet = self._get_sheet(day)

            sheet.append(
                [
                    point["ruc_empresa"],
                    point["placa"],
                    point["imei"],
                    point["codigo_ruta"],
                    point["sentido"],
                    point["nro_doc_conductor"],
                    point["inicio_tramo"],
                    point["fin_tramo"],
                    point["datetime"],
                    point["latitude"],
                    point["longitude"],
                    point["speed"],
                ]
            )