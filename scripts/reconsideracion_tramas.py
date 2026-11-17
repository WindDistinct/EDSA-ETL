"""Genera un CSV de trama GPS (FM Track) por cada viaje rechazado a reconsiderar.

Entrada:
- Excel "Reconsideracion_Viajes_Rechazados" (una hoja) con las columnas
  N°, Placa, Sentido, H. Inicio, H. Fin (fechas dd/mm/yyyy HH:MM:SS, hora Lima).

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
import csv
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd
from alive_progress import alive_bar

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from application.trip_resolver import TripResolver  # noqa: E402
from domain.models import DateRange, TrackResult, Trip  # noqa: E402
from domain.rules import LOCAL_TZ  # noqa: E402
from infrastructure.fmtrack_client import FMTrackClient  # noqa: E402
from logging_config import configure_logging  # noqa: E402

logger = logging.getLogger("reconsideracion_tramas")

HEADER = ["latitud", "longitud", "timestamp", "velocidad", "sentido"]
SENTIDOS = {"IDA": "I", "VUELTA": "V"}
FECHA_FMT = "%d/%m/%Y %H:%M:%S"


def _parse_fecha(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.strptime(str(value).strip(), FECHA_FMT)


def _leer_listado(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, dtype=str)
    # La primera columna es "N°" (el encabezado puede venir con encoding raro).
    df = df.rename(columns={df.columns[0]: "N"})
    faltan = {"Placa", "Sentido", "H. Inicio", "H. Fin"} - set(df.columns)
    if faltan:
        raise SystemExit(f"Faltan columnas en el Excel: {sorted(faltan)}")
    return df


def _ya_generado(out_dir: Path, n: str, placa: str) -> Path | None:
    return next(out_dir.glob(f"{n}_{placa}_*.csv"), None)


def _escribir(out_dir: Path, n: str, placa: str, sentido: str, result: TrackResult) -> Path:
    points = sorted(result.points, key=lambda p: p.datetime)
    primero = datetime.fromisoformat(points[0].datetime)
    path = out_dir / f"{n}_{placa}_{primero:%Y%m%d_%H%M%S}.csv"
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for p in points:
            w.writerow([
                p.latitude,
                p.longitude,
                p.datetime.replace("T", " "),
                p.speed,
                sentido,
            ])
    tmp.replace(path)
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("excel", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=Path("output/reconsideracion"))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limite", type=int, default=None, help="Procesar solo las primeras N filas (prueba).")
    args = ap.parse_args()

    # La barra de alive_progress usa caracteres que cp1252 (consola Windows) no soporta.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    configure_logging(logging.WARNING)

    df = _leer_listado(args.excel)
    if args.limite:
        df = df.head(args.limite)
    out_dir: Path = args.output
    out_dir.mkdir(parents=True, exist_ok=True)

    client = FMTrackClient()
    vehicles = client.get_objects()
    resolver = TripResolver(client, require_ignition_on=False)

    resumen: list[dict] = []
    pendientes: list[tuple[str, str, str, Trip, dict]] = []

    for _, row in df.iterrows():
        n = str(row["N"]).strip()
        placa = str(row["Placa"]).strip().upper()
        base = {"N": n, "PLACA": placa, "H_INICIO": row["H. Inicio"], "H_FIN": row["H. Fin"]}

        existente = _ya_generado(out_dir, n, placa)
        if existente:
            resumen.append({**base, "ESTADO": "existente", "ARCHIVO": existente.name})
            continue

        sentido = SENTIDOS.get(str(row["Sentido"]).strip().upper())
        try:
            inicio = _parse_fecha(row["H. Inicio"]).replace(tzinfo=LOCAL_TZ)
            fin = _parse_fecha(row["H. Fin"]).replace(tzinfo=LOCAL_TZ)
            rango = DateRange(start=inicio, end=fin)
        except Exception as ex:
            resumen.append({**base, "ESTADO": "fila_invalida", "DETALLE": str(ex)})
            continue
        if sentido is None:
            resumen.append({**base, "ESTADO": "fila_invalida", "DETALLE": f"Sentido '{row['Sentido']}'"})
            continue

        vehicle = vehicles.get(placa)
        if vehicle is None:
            resumen.append({**base, "ESTADO": "sin_object_id", "DETALLE": "Placa no encontrada en FM Track"})
            continue

        trip = Trip(
            ruc_empresa=row.get("RUC"),
            placa=placa,
            imei=vehicle.imei,
            codigo_ruta=row.get("Ruta"),
            sentido=sentido,
            nro_doc_conductor=None,
            object_id=vehicle.object_id,
            date_range=rango,
        )
        pendientes.append((n, placa, sentido, trip, base))

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool, alive_bar(len(pendientes)) as bar:
            futures = {pool.submit(resolver.resolve, p[3]): p for p in pendientes}
            for fut in as_completed(futures):
                n, placa, sentido, _, base = futures[fut]
                result = fut.result()
                if not result.success:
                    resumen.append({**base, "ESTADO": "error", "DETALLE": result.error})
                elif not result.points:
                    resumen.append({**base, "ESTADO": "sin_puntos"})
                else:
                    path = _escribir(out_dir, n, placa, sentido, result)
                    resumen.append({**base, "ESTADO": "ok", "PUNTOS": len(result.points), "ARCHIVO": path.name})
                bar()
    finally:
        client.close()

        res_df = pd.DataFrame(resumen, columns=["N", "PLACA", "H_INICIO", "H_FIN", "ESTADO", "PUNTOS", "ARCHIVO", "DETALLE"])
        res_df["PUNTOS"] = res_df["PUNTOS"].astype("Int64")
        res_df["_orden"] =pd.to_numeric(res_df["N"], errors="coerce")
        res_df = res_df.sort_values("_orden").drop(columns="_orden")
        res_df.to_csv(out_dir / "_resumen.csv", index=False, encoding="utf-8-sig")

        print()
        print(res_df["ESTADO"].value_counts().to_string())
        print(f"\nArchivos en: {out_dir.resolve()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
