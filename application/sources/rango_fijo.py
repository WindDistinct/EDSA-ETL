"""Fuente: un mismo rango de fechas para todo un listado de vehículos."""

from __future__ import annotations

from domain.models import DateRange, Trip, Vehicle
from infrastructure.excel_io import read_listing_excel

COLUMN_ALIASES = {
    "RUC": "RUC_EMPRESA",
    "RUC_EMPRESA": "RUC_EMPRESA",
    "CODIGO_RUTA": "CODIGO_RUTA",
    "PLACA": "PLACA",
    "IMEI": "IMEI",
}

REQUIRED_COLUMNS = ["RUC_EMPRESA", "CODIGO_RUTA", "PLACA", "IMEI"]


def _clean(value) -> str | None:
    text = "" if value is None else str(value).strip()
    return None if text in ("", "nan", "None") else text


def viajes_de_listado(input_file: str, date_range: DateRange) -> list[Trip]:
    """
    Excel simple (RUC, CODIGO_RUTA, PLACA, IMEI; todas las hojas) -> un
    viaje por fila con el mismo rango.
    """

    df = read_listing_excel(input_file, column_aliases=COLUMN_ALIASES, required_columns=REQUIRED_COLUMNS)

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


def viajes_de_vehiculos(vehicles: dict[str, Vehicle], date_range: DateRange, codigo_ruta=None) -> list[Trip]:
    """
    Catálogo de vehículos (p. ej. LUCA /reportes/obtener_imeis_vehiculos) ->
    un viaje por placa. Ese catálogo no trae ruta ni RUC: la ruta se completa
    con codigo_ruta y el RUC queda vacío.
    """

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
