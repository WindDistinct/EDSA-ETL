"""Convierte uno o varios Excel (con varias hojas) a un unico CSV.

- Junta TODAS las hojas de cada archivo en un solo CSV.
- Separador de campos: "|"
- Fechas normalizadas a "YYYY-MM-DD HH:MM:SS" (se quita la "T").
- Todo se lee como texto para no perder ceros a la izquierda
  (p.ej. NRO_DOC_CONDUCTOR = "06583153") ni notacion cientifica en el IMEI.

Uso:
    python scripts/xlsx_to_csv.py input/archivo.xlsx -o output/salida.csv
    python scripts/xlsx_to_csv.py "input/*.xlsx" -o output/salida.csv
"""

from __future__ import annotations

import argparse
import glob
import sys

import pandas as pd

COLUMNS = [
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
DATE_COLUMNS = ["FECHORA_INI_VIAJE", "FECHA_HORA_TRACK"]


def normalize_dates(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    out = parsed.dt.strftime("%Y-%m-%d %H:%M:%S")
    # Si algo no se pudo parsear, al menos quitamos la "T" del texto original.
    fallback = series.astype("string").str.replace("T", " ", regex=False)
    return out.fillna(fallback)


def load_frames(patterns: list[str]) -> list[pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    files = []
    for pattern in patterns:
        matched = sorted(glob.glob(pattern))
        if not matched:
            print(f"AVISO: sin coincidencias para {pattern!r}", file=sys.stderr)
        files.extend(matched)

    if not files:
        sys.exit("ERROR: no se encontro ningun archivo de entrada.")

    for path in files:
        sheets = pd.read_excel(path, sheet_name=None, dtype=str)
        for name, df in sheets.items():
            if df.empty:
                continue
            df.columns = [str(c).strip() for c in df.columns]
            missing = [c for c in COLUMNS if c not in df.columns]
            if missing:
                sys.exit(f"ERROR: en {path} hoja {name!r} faltan columnas: {missing}")
            df = df[COLUMNS].copy()
            for col in DATE_COLUMNS:
                df[col] = normalize_dates(df[col])
            frames.append(df)
            print(f"  {path} :: hoja {name!r} -> {len(df)} filas")
    return frames


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("inputs", nargs="+", help="Archivos .xlsx o patrones glob")
    parser.add_argument("-o", "--output", required=True, help="Ruta del CSV de salida")
    parser.add_argument("--sep", default="|", help="Separador de campos (por defecto '|')")
    parser.add_argument(
        "--dedup",
        action="store_true",
        help="Elimina filas duplicadas exactas tras juntar todo",
    )
    args = parser.parse_args()

    frames = load_frames(args.inputs)
    result = pd.concat(frames, ignore_index=True)

    before = len(result)
    if args.dedup:
        result = result.drop_duplicates(ignore_index=True)

    result.to_csv(args.output, sep=args.sep, index=False, lineterminator="\n")

    print(f"\nOK: {len(result)} filas -> {args.output}")
    if args.dedup and before != len(result):
        print(f"     ({before - len(result)} duplicados eliminados)")


if __name__ == "__main__":
    main()
