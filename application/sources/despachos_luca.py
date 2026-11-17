"""Fuente: despachos de LUCA_Backend (/reportes/generar_reporte_despachos) -> viajes.

Conoce el formato del payload de LUCA (fechas tipo "Mon Jul 06 2026 14:00:00
GMT-0500 (hora estándar de Perú)", conductor "Apellido, Nombre, DNI").
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pandas as pd

from domain.models import DateRange, Sentido, Trip, TripOutcome, TripStatus

_SUFIJOS_ZONA = (
    " GMT-0500 (hora estándar de Perú)",
    " GMT-0500 (hora estándar del Perú)",
)


def parse_operational_datetime(value: str | None) -> datetime | None:
    """
    Fecha de LUCA ("Mon Jul 06 2026 14:00:00 GMT-0500 (hora estándar de
    Perú)") -> datetime en hora de Lima, sin zona. None si no se entiende.
    """

    if value is None:
        return None

    value = str(value).strip()

    for sufijo in _SUFIJOS_ZONA:
        value = value.replace(sufijo, "")

    try:
        return datetime.strptime(value, "%a %b %d %Y %H:%M:%S")
    except ValueError:
        return None


def extract_driver_document(value: str | None) -> str:
    """
    Documento del conductor desde "Nombre Apellido, 12345678" (lo que va
    después de la última coma). "" si no hay coma.
    """

    if value is None:
        return ""

    parts = str(value).split(",")

    if len(parts) < 2:
        return ""

    return parts[-1].strip()


def _parse_salida(despacho: dict) -> datetime | None:
    try:
        value = pd.to_datetime(f"{despacho.get('fecha')} {despacho.get('hora')}")
    except (ValueError, TypeError):
        return None
    return None if pd.isna(value) else value.to_pydatetime()


def trip_from_despacho(despacho: dict, ref: str) -> Trip | TripOutcome:
    """
    Un despacho -> Trip con el rango salida -> último punto (real o, si falta,
    calculado). Sin rango válido vuelve como TripOutcome FILA_INVALIDA.
    """

    placa = (despacho.get("placa") or "").strip()

    salida = _parse_salida(despacho)

    fin = parse_operational_datetime(despacho.get("hora_real_ultimo_punto")) or parse_operational_datetime(
        despacho.get("hora_calculada_ultimo_punto")
    )

    if salida is None or fin is None:
        falta = "salida" if salida is None else "hora del último punto"
        return TripOutcome(status=TripStatus.FILA_INVALIDA, ref=ref, placa=placa, detail=f"Despacho sin {falta}")

    try:
        date_range = DateRange(start=salida, end=fin)
    except ValueError:
        return TripOutcome(
            status=TripStatus.FILA_INVALIDA, ref=ref, placa=placa, detail=f"Fin {fin} anterior a la salida {salida}"
        )

    return Trip(
        placa=placa,
        date_range=date_range,
        ruc_empresa=despacho.get("ruc_empresa"),
        codigo_ruta=despacho.get("codigo_ruta"),
        sentido=Sentido.try_parse(despacho.get("sentido")),
        nro_doc_conductor=extract_driver_document(despacho.get("conductor")),
        fechora_ini_viaje=salida,
        ref=ref,
    )


def clip_to_window(trip: Trip, window: DateRange) -> Trip | None:
    """
    El viaje recortado a su intersección con la ventana, o None si no tiene
    track points posibles dentro de ella. fechora_ini_viaje conserva la
    salida real.
    """

    date_range = trip.date_range

    if date_range.start > window.end or date_range.end < window.start:
        return None

    return replace(
        trip,
        date_range=DateRange(start=max(date_range.start, window.start), end=min(date_range.end, window.end)),
    )


def viajes_de_despachos(despachos: list[dict], window: DateRange) -> list[Trip | TripOutcome]:
    """
    Todos los despachos -> viajes recortados a la ventana. Los que no se
    cruzan con la ventana se descartan; los inválidos quedan para el reporte.
    """

    items: list[Trip | TripOutcome] = []

    for i, despacho in enumerate(despachos):

        item = trip_from_despacho(despacho, ref=str(i + 1))

        if isinstance(item, Trip):
            item = clip_to_window(item, window)

        if item is not None:
            items.append(item)

    return items
