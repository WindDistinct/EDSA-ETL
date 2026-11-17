from __future__ import annotations

from application.run_trips import RunReport, report_path, run_trips
from domain.models import DateRange, Trip
from domain.rules import parse_boundary
from infrastructure.excel_io import read_listing_excel
from infrastructure.track_record_writer import TrackRecordWriter

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


def _clean(value) -> str | None:
    text = "" if value is None else str(value).strip()
    return None if text in ("", "nan", "None") else text


class FixedRangeJob:
    """
    Aplica un mismo intervalo de fechas a un listado de vehículos. El listado
    viene de un Excel simple (RUC, CODIGO_RUTA, PLACA, IMEI) o, sin Excel,
    de los vehículos de la empresa en LUCA (vehicle_source_client). Los
    puntos se resuelven con el proveedor elegido (track_client).
    """

    def __init__(self, track_client, *, vehicle_source_client=None, max_workers: int = 8):
        self._track_client = track_client
        self._vehicle_source_client = vehicle_source_client
        self._max_workers = max_workers

    def _trips_from_excel(self, input_file: str, date_range: DateRange) -> list[Trip]:

        df = read_listing_excel(
            input_file,
            column_aliases=COLUMN_ALIASES,
            required_columns=REQUIRED_COLUMNS,
        )

        return [
            Trip(
                placa=row["PLACA"],
                date_range=date_range,
                ruc_empresa=_clean(row["RUC_EMPRESA"]),
                imei=_clean(row["IMEI"]),
                codigo_ruta=_clean(row["CODIGO_RUTA"]),
                ref=str(i + 1),
            )
            for i, row in enumerate(df.to_dict("records"))
        ]

    def _trips_from_luca(self, date_range: DateRange, codigo_ruta) -> list[Trip]:

        if self._vehicle_source_client is None:
            raise ValueError("Se requiere vehicle_source_client cuando no se especifica input_file.")

        vehicles = self._vehicle_source_client.get_objects()

        return [
            Trip(
                placa=placa,
                date_range=date_range,
                imei=vehicle.imei or None,
                codigo_ruta=codigo_ruta,
                ref=str(i + 1),
            )
            for i, (placa, vehicle) in enumerate(vehicles.items())
        ]

    def run(
        self,
        output_file: str,
        *,
        start_date: str,
        end_date: str,
        input_file: str | None = None,
        codigo_ruta: str | int | None = None,
    ) -> RunReport:

        date_range = DateRange(
            start=parse_boundary(start_date, is_end=False),
            end=parse_boundary(end_date, is_end=True),
        )

        if input_file:
            trips = self._trips_from_excel(input_file, date_range)
        else:
            trips = self._trips_from_luca(date_range, codigo_ruta)

        with TrackRecordWriter(output_file, include_ignition_status=True) as sink:
            report = run_trips(trips, self._track_client, sink, workers=self._max_workers)

        report.write_csv(report_path(output_file))

        return report
