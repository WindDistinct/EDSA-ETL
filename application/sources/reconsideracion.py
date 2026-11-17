"""Fuente: Excel "Reconsideracion_Viajes_Rechazados" -> un viaje por fila.

Columnas: N°, RUC, Placa, Ruta, Sentido, H. Inicio, H. Fin (fechas
dd/mm/yyyy HH:MM:SS, hora de Lima). El N° es la ref del viaje y encabeza el
nombre de su CSV.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from domain.models import DateRange, Sentido, Trip, TripOutcome, TripStatus

FECHA_FMT = "%d/%m/%Y %H:%M:%S"
REQUIRED = {"Placa", "Sentido", "H. Inicio", "H. Fin"}


def _texto(value) -> str | None:
    text = "" if value is None else str(value).strip()
    return None if text in ("", "nan") else text


def leer_viajes(path: str | Path) -> list[Trip | TripOutcome]:
    """
    Cada fila -> Trip; las filas con fechas o sentido inválidos vuelven como
    TripOutcome FILA_INVALIDA.
    """

    df = pd.read_excel(path, dtype=str)
    # La primera columna es "N°" (el encabezado puede venir con encoding raro).
    df = df.rename(columns={df.columns[0]: "N"})

    faltan = REQUIRED - set(df.columns)
    if faltan:
        raise ValueError(f"Faltan columnas en el Excel de reconsideración: {sorted(faltan)}")

    items: list[Trip | TripOutcome] = []

    for row in df.to_dict("records"):
        ref = str(row["N"]).strip()
        placa = str(row["Placa"]).strip().upper()

        def invalida(detalle: str) -> TripOutcome:
            return TripOutcome(status=TripStatus.FILA_INVALIDA, ref=ref, placa=placa, detail=detalle)

        try:
            date_range = DateRange(
                start=datetime.strptime(str(row["H. Inicio"]).strip(), FECHA_FMT),
                end=datetime.strptime(str(row["H. Fin"]).strip(), FECHA_FMT),
            )
        except ValueError as ex:
            items.append(invalida(f"H. Inicio {row['H. Inicio']!r} / H. Fin {row['H. Fin']!r}: {ex}"))
            continue

        sentido = Sentido.try_parse(row["Sentido"])
        if sentido is None:
            items.append(invalida(f"Sentido {row['Sentido']!r}"))
            continue

        items.append(
            Trip(
                placa=placa,
                date_range=date_range,
                ruc_empresa=_texto(row.get("RUC")),
                codigo_ruta=_texto(row.get("Ruta")),
                sentido=sentido,
                ref=ref,
            )
        )

    return items
