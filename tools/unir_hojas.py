"""Une las tramas por dia en la menor cantidad de hojas posible.

Una hoja de Excel admite 1,048,576 filas. Si el total entra, queda una sola hoja
"Tramas"; si no, se reparte en "Tramas_1", "Tramas_2", ... cortando entre dias
(por FECHORA_INI_VIAJE) para que ningun viaje quede partido en dos hojas.

La entrada puede ser el CSV con separador "|" (mucho mas rapido de leer) o el
Excel con una hoja por dia. Los IDs se mantienen como texto y las fechas con el
formato "YYYY-MM-DD HH:MM:SS".

Uso:
    python tools/unir_hojas.py output/1205_JUNIO_VARGASANT_tramas_completo.csv
    python tools/unir_hojas.py output/archivo.xlsx -o output/archivo_unido.xlsx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from infrastructure.atu_format import ATU_COLUMNS as COLUMNS  # noqa: E402
from infrastructure.atu_format import CSV_SEP, missing_columns  # noqa: E402
from infrastructure.atu_format import EXCEL_NUMERIC_COLUMNS as NUMERIC_COLUMNS  # noqa: E402
MAX_FILAS_HOJA = 1_048_575  # 1,048,576 menos el encabezado


def load_tramas(path: Path, sep: str) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, sep=sep, dtype=str, keep_default_na=False)
    sheets = pd.read_excel(path, sheet_name=None, dtype=str, keep_default_na=False)
    return pd.concat(sheets.values(), ignore_index=True)


def repartir(df: pd.DataFrame, max_filas: int) -> list[pd.DataFrame]:
    """Agrupa dias consecutivos en bloques que entren en una hoja."""
    bloques: list[list[pd.DataFrame]] = [[]]
    filas = 0
    for dia, grupo in df.groupby(df["FECHORA_INI_VIAJE"].str[:10], sort=True):
        if len(grupo) > max_filas:
            sys.exit(f"ERROR: el dia {dia} tiene {len(grupo)} filas, no entra en una hoja.")
        if filas + len(grupo) > max_filas:
            bloques.append([])
            filas = 0
        bloques[-1].append(grupo)
        filas += len(grupo)
    return [pd.concat(b, ignore_index=True) for b in bloques]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", help="CSV o Excel de tramas")
    parser.add_argument("-o", "--output", help="Excel de salida (por defecto <entrada>_unido.xlsx)")
    parser.add_argument("--sep", default=CSV_SEP, help=f"Separador del CSV (por defecto '{CSV_SEP}')")
    parser.add_argument("--max-filas", type=int, default=MAX_FILAS_HOJA, help="Filas maximas por hoja")
    args = parser.parse_args()

    src = Path(args.input)
    if not src.exists():
        sys.exit(f"ERROR: no existe {src}")
    output = Path(args.output) if args.output else src.with_name(f"{src.stem}_unido.xlsx")
    if output.resolve() == src.resolve():
        sys.exit("ERROR: la salida no puede ser el mismo archivo de entrada.")
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Leyendo {src}...")
    df = load_tramas(src, args.sep)
    missing = missing_columns(df)
    if missing:
        sys.exit(f"ERROR: en {src} faltan columnas: {missing}")
    df = df[COLUMNS].sort_values(["FECHORA_INI_VIAJE", "PLACA", "FECHA_HORA_TRACK"], ignore_index=True)
    print(f"  {len(df)} filas")

    bloques = repartir(df, args.max_filas)
    print(f"Escribiendo {output} ({len(bloques)} hoja(s), tarda varios minutos)...")
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for i, bloque in enumerate(bloques, start=1):
            nombre = "Tramas" if len(bloques) == 1 else f"Tramas_{i}"
            for col in NUMERIC_COLUMNS:
                bloque[col] = pd.to_numeric(bloque[col], errors="coerce")
            bloque.to_excel(writer, sheet_name=nombre, index=False)
            writer.sheets[nombre].freeze_panes = "A2"
            desde, hasta = bloque["FECHORA_INI_VIAJE"].iloc[[0, -1]].str[:10]
            print(f"  hoja {nombre!r} -> {len(bloque)} filas ({desde} a {hasta})")

    print(f"\nOK: {len(df)} filas -> {output}")


if __name__ == "__main__":
    main()
