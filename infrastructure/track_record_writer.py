from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from domain.models import TrackPoint, Trip


class TrackRecordWriter:

    BASE_HEADERS = [
        "RUC_EMPRESA",
        "PLACA",
        "IMEI",
        "CODIGO_RUTA",
        "FECHORA_INI_VIAJE",
        "FECHA_HORA_TRACK",
        "LATITUD",
        "LONGITUD",
        "VELOCIDAD",
        "SENTIDO",
        "NRO_DOC_CONDUCTOR",
    ]

    def __init__(
        self,
        output_file: str,
        include_ignition_status: bool = False,
    ):

        self.output_file = Path(output_file)

        self.workbook: Workbook | None = None

        self.sheets: dict[str, any] = {}

        self.include_ignition_status = include_ignition_status

        self.headers = self.BASE_HEADERS + (
            ["IGNITION_STATUS"]
            if include_ignition_status
            else []
        )

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

        ws.append(self.headers)

        self.sheets[day] = ws

        return ws

    def close(self):

        if self.workbook is None:
            return

        if not self.sheets:
            self.workbook.create_sheet("SIN_DATOS")

        self.workbook.save(
            self.output_file
        )

        self.workbook.close()

        self.workbook = None

    def append(
        self,
        trip: Trip,
        points: list[TrackPoint],
    ) -> None:

        for point in points:

            day = point.datetime[:10]

            sheet = self._get_sheet(day)

            row = [
                trip.ruc_empresa,
                trip.placa,
                trip.imei,
                trip.codigo_ruta,
                trip.date_range.start.isoformat(),
                point.datetime,
                point.latitude,
                point.longitude,
                point.speed,
                trip.sentido,
                trip.nro_doc_conductor,
            ]

            if self.include_ignition_status:
                row.append(
                    point.ignition_status
                )

            sheet.append(row)
