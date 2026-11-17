from __future__ import annotations

from datetime import datetime

from domain.tiempo import LOCAL_TZ, to_local


def format_for_api(value: datetime) -> str:
    """
    Convierte un datetime al formato ISO 8601 que esperan las APIs, con el
    offset de Lima. Un datetime sin zona horaria se interpreta como hora de
    Lima (no como la zona del equipo).
    """

    return to_local(value).isoformat(timespec="milliseconds")


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
