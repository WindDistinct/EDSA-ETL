"""Genera un CSV de trama GPS (FM Track) por cada viaje rechazado a reconsiderar.

Entrada:
- Excel "Reconsideracion_Viajes_Rechazados" (una hoja) con las columnas
  N°, RUC, Placa, Ruta, Sentido, H. Inicio, H. Fin (fechas dd/mm/yyyy HH:MM:SS,
  hora Lima).

Salida (una carpeta):
- {N}_{PLACA}_{YYYYMMDD_HHMMSS}.csv por viaje, con el formato de
  Plantilla_Traza_Reconsideracion.csv:
      latitud,longitud,timestamp,velocidad,sentido
  El timestamp del nombre es el del primer punto GPS del viaje.
  sentido: IDA -> I, VUELTA -> V. Sin filtro de ignicion.
- _resumen.csv con el estado de cada fila (ok, existente, sin_puntos,
  sin_object_id, error, fila_invalida).

Los viajes sin puntos o con error NO generan archivo y quedan en el resumen.
Si se vuelve a correr, salta los N° que ya tienen archivo, asi solo reintenta
los que faltan.

Uso:
    python scripts/reconsideracion_tramas.py "input/Reconsideracion_Viajes_Rechazados_1794927644146 - 0.xlsx"
    python scripts/reconsideracion_tramas.py EXCEL -o output/reconsideracion --workers 8
    python scripts/reconsideracion_tramas.py EXCEL --limite 10
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from application.run_trips import run_trips  # noqa: E402
from domain.models import DateRange, Sentido, Trip, TripOutcome, TripStatus  # noqa: E402
from infrastructure.fmtrack_client import FMTrackClient  # noqa: E402
from infrastructure.trip_csv_writer import TripCsvWriter  # noqa: E402
from logging_config import configure_logging  # noqa: E402

FECHA_FMT = "%d/%m/%Y %H:%M:%S"
REQUIRED = {"Placa", "Sentido", "H. Inicio", "H. Fin"}


def _texto(value) -> str | None:
    text = "" if value is None else str(value).strip()
    return None if text in ("", "nan") else text


def leer_viajes(path: Path) -> list[Trip | TripOutcome]:
    """
    Cada fila del Excel -> Trip; las filas con fechas o sentido inválidos
    vuelven como TripOutcome FILA_INVALIDA.
    """

    df = pd.read_excel(path, dtype=str)
    # La primera columna es "N°" (el encabezado puede venir con encoding raro).
    df = df.rename(columns={df.columns[0]: "N"})

    faltan = REQUIRED - set(df.columns)
    if faltan:
        raise SystemExit(f"Faltan columnas en el Excel: {sorted(faltan)}")

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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("excel", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=Path("output/reconsideracion"))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limite", type=int, default=None, help="Procesar solo las primeras N filas (prueba).")
    args = ap.parse_args()

    configure_logging(logging.WARNING)

    items = leer_viajes(args.excel)
    if args.limite:
        items = items[: args.limite]

    sink = TripCsvWriter(args.output)
    client = FMTrackClient()

    try:
        report = run_trips(items, client, sink, workers=args.workers)
    finally:
        client.close()

    report.write_csv(args.output / "_resumen.csv")

    print()
    print(pd.Series(report.counts()).to_string())
    print(f"\nArchivos en: {args.output.resolve()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
