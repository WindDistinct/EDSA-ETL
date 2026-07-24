from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from domain.models import DateRange, Trip

LOCAL_TZ = ZoneInfo("America/Lima")


def _resolve_datetime(value: Any) -> datetime | None:

    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, str):

        value = value.strip()

        if not value:
            return None

        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

    return None


def resolve_date_range(row: Mapping[str, Any]) -> DateRange:
    """
    Resuelve el rango de fechas de un tramo a partir de una fila de datos.
    """

    start = _resolve_datetime(
        row.get("START_DATETIME")
        or row.get("FECHORA_INI_VIAJE")
    )

    end = _resolve_datetime(
        row.get("END_DATETIME")
        or row.get("FECHA_HORA_FIN_TRAMO")
    )

    if end is None:

        end = _resolve_datetime(
            row.get("FECHA_HORA_FIN_TRAMO_CALCULADA")
        )

    if start is None:
        raise ValueError(
            "La fecha inicial es obligatoria."
        )

    if end is None:
        raise ValueError(
            "No existe fecha final."
        )

    return DateRange(start=start, end=end)


def build_trip_from_row(
    row: Mapping[str, Any],
    *,
    object_id: str,
    date_range: DateRange,
) -> Trip:
    """
    Construye un Trip a partir de una fila de datos ya enriquecida con OBJECT_ID.
    """

    return Trip(
        ruc_empresa=row.get("RUC_EMPRESA"),
        placa=row.get("PLACA"),
        imei=row.get("IMEI"),
        codigo_ruta=row.get("CODIGO_RUTA"),
        sentido=row.get("SENTIDO"),
        nro_doc_conductor=row.get("NRO_DOC_CONDUCTOR"),
        object_id=object_id,
        date_range=date_range,
    )


def format_for_api(value: datetime) -> str:
    """
    Convierte un datetime al formato ISO 8601 esperado por FM Track.
    """

    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()

    return (
        value.astimezone()
        .isoformat(
            timespec="milliseconds"
        )
        .replace(
            "+00:00",
            "Z",
        )
    )


def to_local_isoformat(value: str) -> str:
    """
    Convierte un datetime ISO 8601 (UTC) a hora local (America/Lima), naive.
    """

    parsed = datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )

    return (
        parsed.astimezone(LOCAL_TZ)
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )


def filter_ignition_on(
    items: Iterable[dict],
    require_on: bool,
) -> list[dict]:
    """
    Filtra items dejando solo los que tienen ignition_status == "ON".
    """

    if not require_on:
        return list(items)

    return [
        item
        for item in items
        if item.get("ignition_status") == "ON"
    ]


def parse_boundary(value: str, *, is_end: bool) -> datetime:
    """
    Parsea un límite de fecha (inicio o fin) de un rango fijo.
    Si es fin de rango y solo se especificó la fecha (sin hora),
    se extiende hasta el final del día.
    """

    value = value.strip()

    parsed = datetime.fromisoformat(value)

    if is_end and len(value) <= 10:

        parsed = parsed.replace(
            hour=23,
            minute=59,
            second=59,
        )

    return parsed


def assign_partition(dt: datetime, limits: list[datetime]) -> int:
    """
    Determina a qué partición pertenece una fecha, dado una lista de límites.
    """

    for index, limit in enumerate(limits):

        if dt < limit:
            return index + 1

    return len(limits) + 1


def parse_operational_datetime(value: str | None) -> datetime | None:
    """
    Convierte fechas provenientes del Excel operacional.
    El llamador debe convertir valores NaN/NaT a None antes de invocar esta función.
    """

    if value is None:
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


def extract_driver_document(value: str | None) -> str:
    """
    Extrae el número de documento del conductor de un campo de texto libre
    con formato "Nombre Apellido, 12345678".
    """

    if value is None:
        return ""

    value = str(value)

    parts = value.split(",")

    if len(parts) < 2:
        return ""

    return parts[-1].strip()
