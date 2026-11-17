"""Zona horaria del negocio.

Toda hora operacional (despachos, Excel, rangos del CLI) es hora de Lima. Una
fecha sin zona horaria se interpreta siempre como Lima, nunca como la zona del
equipo donde corre el proceso: así el resultado no cambia si se ejecuta en un
servidor configurado en UTC.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/Lima")


def to_local(value: datetime) -> datetime:
    """
    Devuelve el datetime con zona horaria de Lima. Si no trae zona se asume
    Lima; si la trae, se convierte.
    """

    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()

    if value.tzinfo is None:
        return value.replace(tzinfo=LOCAL_TZ)

    return value.astimezone(LOCAL_TZ)
