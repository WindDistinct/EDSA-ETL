"""Da formato a los campos de uno o varios Excel, SIN juntar hojas.

Cada archivo se reescribe manteniendo sus hojas tal cual (una por dia).
Lo unico que cambia es el formato de los campos:

- Fechas normalizadas a "YYYY-MM-DD HH:MM:SS" (se quita la "T").
- Columnas reordenadas al formato objetivo.
- IDs como texto para no perder ceros a la izquierda
  (NRO_DOC_CONDUCTOR = "06583153") ni pasar el IMEI a notacion cientifica.
- LATITUD / LONGITUD / VELOCIDAD quedan como numero.

Uso:
    python scripts/xlsx_formatear.py input/archivo.xlsx
    python scripts/xlsx_formatear.py input/archivo.xlsx -o output/archivo_fmt.xlsx
    python scripts/xlsx_formatear.py "input/*.xlsx" --suffix _fmt
    python scripts/xlsx_formatear.py input/archivo.xlsx --in-place
    python scripts/xlsx_formatear.py input/archivo.xlsx --dates datetime
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

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
NUMERIC_COLUMNS = ["LATITUD", "LONGITUD", "VELOCIDAD"]
DATE_FMT = "%Y-%m-%d %H:%M:%S"
EXCEL_DATE_FMT = "YYYY-MM-DD HH:MM:SS"


def normalize_dates_text(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    out = parsed.dt.strftime(DATE_FMT)
    fallback = series.astype("string").str.replace("T", " ", regex=False)
    return out.fillna(fallback)


def format_sheet(df: pd.DataFrame, dates_mode: str) -> pd.DataFrame:
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise KeyError(f"faltan columnas: {missing}")
    df = df[COLUMNS].copy()

    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if dates_mode == "datetime":
        for col in DATE_COLUMNS:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    else:
        for col in DATE_COLUMNS:
            df[col] = normalize_dates_text(df[col])
    return df


def resolve_output(src: Path, args: argparse.Namespace) -> Path:
    if args.in_place:
        return src
    if args.output:
        return Path(args.output)
    return src.with_name(f"{src.stem}{args.suffix}{src.suffix}")


def process_file(path: Path, args: argparse.Namespace) -> None:
    sheets = pd.read_excel(path, sheet_name=None, dtype=str)
    out_path = resolve_output(path, args)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            if df.empty:
                df.to_excel(writer, sheet_name=name[:31], index=False)
                print(f"  {path.name} :: hoja {name!r} -> vacia (copiada)")
                continue
            try:
                formatted = format_sheet(df, args.dates)
            except KeyError as exc:
                sys.exit(f"ERROR: en {path} hoja {name!r} {exc}")
            formatted.to_excel(writer, sheet_name=name[:31], index=False)
            ws = writer.sheets[name[:31]]
            ws.freeze_panes = "A2"
            if args.dates == "datetime":
                for col in DATE_COLUMNS:
                    idx = COLUMNS.index(col) + 1
                    for (cell,) in ws.iter_rows(
                        min_col=idx, max_col=idx, min_row=2, max_row=ws.max_row
                    ):
                        cell.number_format = EXCEL_DATE_FMT
            print(f"  {path.name} :: hoja {name!r} -> {len(formatted)} filas")

    print(f"OK: {path.name} -> {out_path}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("inputs", nargs="+", help="Archivos .xlsx o patrones glob")
    parser.add_argument(
        "-o",
        "--output",
        help="Ruta de salida (solo valido con UN archivo de entrada)",
    )
    parser.add_argument(
        "--suffix",
        default="_fmt",
        help="Sufijo para el archivo de salida cuando no se usa -o ni --in-place (por defecto '_fmt')",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Sobrescribe el archivo original",
    )
    parser.add_argument(
        "--dates",
        choices=["text", "datetime"],
        default="text",
        help="text: cadena exacta 'YYYY-MM-DD HH:MM:SS' (por defecto). "
        "datetime: celdas de fecha reales con ese formato de presentacion.",
    )
    args = parser.parse_args()

    files: list[str] = []
    for pattern in args.inputs:
        matched = sorted(glob.glob(pattern))
        if not matched:
            print(f"AVISO: sin coincidencias para {pattern!r}", file=sys.stderr)
        files.extend(matched)
    if not files:
        sys.exit("ERROR: no se encontro ningun archivo de entrada.")
    if args.output and len(files) > 1:
        sys.exit("ERROR: -o solo se puede usar con un unico archivo de entrada.")

    for f in files:
        process_file(Path(f), args)


if __name__ == "__main__":
    main()
