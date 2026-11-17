"""Reglas para armar el tramo (salida -> llegada) de un despacho cargado a mano.

Los Excel operacionales traen la hora escrita por personas: con errores de
tipeo, o reinterpretada por Excel como número o fecha. Estas reglas recuperan
la hora cuando no hay ambigüedad y fijan los criterios de cruce de medianoche
y de duración imposible. No dependen de pandas ni de openpyxl.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

# Duración por encima de la cual el fin del viaje no es creíble.
MAX_DURACION_VIAJE = timedelta(hours=6)
# Duración que se toma cuando el fin no es creíble (salida + recorte).
RECORTE_VIAJE = timedelta(hours=2)
# Viajes más cortos que esto se incluyen, pero se marcan para revisar.
DURACION_CORTA = timedelta(minutes=15)

# "12:.04", "22::21", "19;45", "22:_53", "4:19am", "09:11:00"
_TIME_TEXT_RE = re.compile(
    r"^\s*(\d{1,2})\s*[:;.,_]+\s*(\d{2})(?::\d{2})?\s*(am|pm)?\s*$",
    re.IGNORECASE,
)

_EXCEL_EPOCH = datetime(1899, 12, 30)
_EXCEL_LEAP_BUG = datetime(1900, 3, 1)


def excel_serial(value: datetime) -> float:
    """
    Número de serie de Excel de un datetime (días desde 1899-12-30, con el
    falso 29/02/1900 de Excel). Equivale a openpyxl.utils.datetime.to_excel.
    """

    serial = (value.replace(tzinfo=None) - _EXCEL_EPOCH).total_seconds() / 86400

    if value.replace(tzinfo=None) < _EXCEL_LEAP_BUG:
        serial -= 1

    return serial


def parse_hora(value: object) -> tuple[time | None, str]:
    """
    Devuelve (hora, nota). hora=None si no se puede usar; nota != "" si se
    corrigió un error de tipeo:

        "12:.04", "22::21", "19;45", "4:19am"         -> 12:04, 22:21, 19:45, 04:19
        9.31 (Excel lo guardó como número/fecha 1900) -> 09:31
        836 (número entero)                           -> 08:36
        16/04/2026 (Excel lo leyó como día/mes)       -> 16:04
    """

    if value is None:
        return None, ""

    if isinstance(value, datetime):
        serial = excel_serial(value)

        if serial < 24:
            # Se escribió "9.31" en vez de "9:31" y Excel lo guardó como número.
            hh = int(serial)
            mm = round((serial - hh) * 100)
            if mm < 60:
                return time(hh, mm), f"numero {serial:.2f} leido como {hh:02d}:{mm:02d}"

        elif serial == int(serial) and 100 <= serial <= 2359 and serial % 100 < 60:
            # Se escribió "836" sin separador.
            hh, mm = divmod(int(serial), 100)
            return time(hh, mm), f"numero {int(serial)} leido como {hh:02d}:{mm:02d}"

        elif value.year >= 2000 and value.time() == time(0) and value.day <= 23 and value.month < 60:
            # Se escribió "16.04" y Excel lo convirtió en la fecha 16/04.
            hh, mm = value.day, value.month
            return time(hh, mm), f"fecha {value:%d/%m/%Y} leida como {hh:02d}:{mm:02d}"

        return None, ""

    if isinstance(value, time):
        return value, ""

    if isinstance(value, str):
        m = _TIME_TEXT_RE.match(value)
        if m:
            hh, mm = int(m.group(1)), int(m.group(2))
            if m.group(3) and m.group(3).lower() == "pm" and hh < 12:
                hh += 12
            if hh < 24 and mm < 60:
                return time(hh, mm), f"texto {value!r} leido como {hh:02d}:{mm:02d}"

    return None, ""


def combinar(fecha: date | datetime, hora: time) -> datetime:
    """
    Fecha del despacho + hora del Excel. Si fecha es un datetime (o
    pd.Timestamp) se descarta su hora.
    """

    if isinstance(fecha, datetime):
        fecha = fecha.date()

    return datetime.combine(fecha, hora)


def cruzar_medianoche(ini: datetime, fin: datetime) -> tuple[datetime, bool]:
    """
    Llegada anterior a la salida -> la llegada es del día siguiente.
    Devuelve (fin, se_ajustó).
    """

    if fin < ini:
        return fin + timedelta(days=1), True

    return fin, False


def recortar_fin(
    ini: datetime,
    fin: datetime,
    *,
    max_duracion: timedelta = MAX_DURACION_VIAJE,
    recorte: timedelta = RECORTE_VIAJE,
) -> tuple[datetime, bool]:
    """
    Si la duración supera max_duracion el fin no es creíble y se reemplaza
    por ini + recorte. Devuelve (fin, se_recortó).
    """

    if fin - ini > max_duracion:
        return ini + recorte, True

    return fin, False


def normalizar_dni(value: object) -> str:
    """
    DNI del conductor como texto de 8 dígitos (Excel pierde los ceros a la
    izquierda). Valores no numéricos ("#N/A", "NO DATA") -> "".
    """

    text = "" if value is None else str(value).strip()

    if text.isdigit():
        return text.zfill(8)

    return ""
