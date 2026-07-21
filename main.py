from client.fmtrack_client import FMTrackClient
from services.excel_processor import ExcelProcessor


client = FMTrackClient()

try:

    processor = ExcelProcessor(client)

    processor.process(
        "input/reporte.xlsx",
        "output/reporte_test.xlsx",
    )

finally:
    client.close()