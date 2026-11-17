"""Recupera los despachos omitidos que se corrigieron a mano y los suma a las tramas.

Entradas:
- Excel de irregularidades corregido: se leen las filas que queden en la hoja
  "Omitidos" (las ocultas se ignoran) con las horas de las columnas
  "HORA SENTIDO (original)" y "LLEG. (original)".
- Excel de despachos: da RUC, ruta, sentido y conductor de cada FILA_EXCEL.
- Excel de tramas (usa la misma cache .pkl que despachos_tramas.py).
- CSV principal de tramas, generado con xlsx_to_csv.py.

Reglas:
- Llegada menor que la salida -> cruza medianoche (+1 dia).
- Hora invalida o salida igual a llegada -> no se recupera, queda en el reporte.
- Un punto GPS pertenece a un solo viaje: si ya esta en el documento principal, o
  lo comparten dos viajes encadenados (09:11 fin / 09:11 inicio), se conserva una vez.
- El documento principal NO se modifica: se escriben archivos nuevos con sufijo.

Uso:
    python scripts/recuperar_omitidos.py "input/1205_JUNIO_VARGASANT_tramas_irregularidades (2).xlsx"
    python scripts/recuperar_omitidos.py CORREGIDO --sin-xlsx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import openpyxl
import pandas as pd

from despachos_tramas import COLUMNS, DATE_FMT, clean_doc, cruzar, load_despachos, load_tramas, parse_hora, write_resultado

COL_HORA = "HORA SENTIDO (original)"
COL_LLEG = "LLEG. (original)"
MAX_DURACION = pd.Timedelta(hours=6)
RECORTE = pd.Timedelta(hours=2)


def load_correcciones(path: Path) -> list[dict]:
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Omitidos"]
    rows = ws.iter_rows(values_only=True)
    header = [str(c).strip() if c is not None else "" for c in next(rows)]
    registros = [
        dict(zip(header, r))
        for fila, r in enumerate(rows, start=2)
        if not ws.row_dimensions[fila].hidden and r[0] is not None
    ]
    wb.close()
    return registros


def load_filas_despacho(path: Path) -> dict[int, dict]:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    rows = wb.worksheets[0].iter_rows(values_only=True)
    header = [str(c).strip() if c is not None else "" for c in next(rows)]
    filas = {fila: dict(zip(header, r)) for fila, r in enumerate(rows, start=2)}
    wb.close()
    return filas


def armar_despachos(
    correcciones: list[dict], filas: dict[int, dict], validos: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (despachos recuperables, reporte de los que no se pueden recuperar)."""
    recuperados: list[dict] = []
    descartados: list[dict] = []

    for c in correcciones:
        fila = int(c["FILA_EXCEL"])
        base = {"FILA_EXCEL": fila, "ID2": c["ID2"], "PLACA": c["PLACA"], "HORA": c[COL_HORA], "LLEG": c[COL_LLEG]}
        d = filas.get(fila)
        if d is None or d["ID2"] != c["ID2"] or str(d["PLACA"]).strip().upper() != str(c["PLACA"]).strip().upper():
            descartados.append({**base, "MOTIVO": "FILA_EXCEL no coincide con el Excel de despachos"})
            continue

        hora_ini, _ = parse_hora(c[COL_HORA])
        hora_fin, _ = parse_hora(c[COL_LLEG])
        if hora_ini is None or hora_fin is None:
            descartados.append({**base, "MOTIVO": "hora invalida"})
            continue

        fecha = pd.Timestamp(d["FECHA"]).normalize()
        ini = fecha + pd.Timedelta(hours=hora_ini.hour, minutes=hora_ini.minute, seconds=hora_ini.second)
        fin = fecha + pd.Timedelta(hours=hora_fin.hour, minutes=hora_fin.minute, seconds=hora_fin.second)
        if fin == ini:
            descartados.append({**base, "MOTIVO": "sigue con salida igual a llegada"})
            continue
        if fin < ini:
            fin += pd.Timedelta(days=1)

        placa = base["PLACA"]
        otros = validos[(validos["PLACA"] == placa) & (validos["INI"] < fin) & (validos["FIN"] > ini)]
        avisos = [f"fila {f} ({i:%H:%M}-{t:%H:%M})" for f, i, t in zip(otros["FILA_EXCEL"], otros["INI"], otros["FIN"])]
        recuperados.append(
            {
                "FILA_EXCEL": fila,
                "ID2": c["ID2"],
                "RUC_EMPRESA": str(d["RUC_EMPRESA"]).strip(),
                "PLACA": placa,
                "CODIGO_RUTA": d["CODIGO_RUTA"],
                "INI": ini,
                "FIN": fin,
                "SENTIDO": 0 if str(d["SENTIDO"]).strip().upper() == "IDA" else 1,
                "NRO_DOC_CONDUCTOR": clean_doc(d["NRO_DOC_CONDUCTOR"]),
                "DURACION": str(fin - ini).replace("0 days ", ""),
                "AVISO": ("duracion mayor a 6h; " if fin - ini > MAX_DURACION else "")
                + (f"se solapa con {', '.join(avisos)}" if avisos else ""),
            }
        )

    return pd.DataFrame(recuperados), pd.DataFrame(descartados)


def as_texto(result: pd.DataFrame) -> pd.DataFrame:
    """Mismo formato de texto que el CSV principal."""
    out = result[COLUMNS].copy()
    for col in ("FECHORA_INI_VIAJE", "FECHA_HORA_TRACK"):
        out[col] = pd.to_datetime(out[col]).dt.strftime(DATE_FMT)
    return out.astype(str)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("corregido", help="Excel de irregularidades con la hoja Omitidos corregida")
    parser.add_argument("--despachos", default="input/1205_JUNIO_VARGASANT.xlsx", help="Excel de despachos")
    parser.add_argument("--tramas", default="input/vargasant_1205_2026_06_01_06_30.xlsx", help="Excel de tramas")
    parser.add_argument("--principal", default="output/1205_JUNIO_VARGASANT_tramas.csv", help="CSV principal de tramas")
    parser.add_argument("-o", "--output-dir", help="Carpeta de salida (por defecto la del CSV principal)")
    parser.add_argument("--sep", default="|", help="Separador del CSV (por defecto '|')")
    parser.add_argument("--sin-xlsx", action="store_true", help="No escribir el Excel completo (es lo mas lento)")
    args = parser.parse_args()

    corregido, despachos_path = Path(args.corregido), Path(args.despachos)
    tramas_path, principal = Path(args.tramas), Path(args.principal)
    for p in (corregido, despachos_path, tramas_path, principal):
        if not p.exists():
            sys.exit(f"ERROR: no existe {p}")

    out_dir = Path(args.output_dir) if args.output_dir else principal.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = principal.stem
    csv_path = out_dir / f"{stem}_completo.csv"
    xlsx_path = out_dir / f"{stem}_completo.xlsx"
    reporte_path = out_dir / f"{stem}_recuperados.xlsx"

    print("Correcciones:")
    correcciones = load_correcciones(corregido)
    validos, _ = load_despachos(despachos_path, MAX_DURACION, RECORTE)
    despachos, descartados = armar_despachos(correcciones, load_filas_despacho(despachos_path), validos)
    print(f"  {len(correcciones)} filas leidas: {len(despachos)} recuperables, {len(descartados)} descartadas")
    if despachos.empty:
        sys.exit("ERROR: no hay despachos que recuperar.")

    print("\nTramas:")
    tramas = load_tramas(tramas_path, use_cache=True)
    nuevos, sin_tramas, puntos = cruzar(despachos, tramas)
    nuevos = as_texto(nuevos)
    print(f"  {len(nuevos)} puntos encontrados; {len(sin_tramas)} viajes sin tramas")

    print(f"\nDocumento principal: {principal}")
    base = pd.read_csv(principal, sep=args.sep, dtype=str, keep_default_na=False)
    if list(base.columns) != COLUMNS:
        sys.exit(f"ERROR: columnas inesperadas en {principal}: {list(base.columns)}")
    print(f"  {len(base)} filas")

    inicios = base[["PLACA", "FECHORA_INI_VIAJE"]].drop_duplicates()
    repetidos = nuevos.merge(inicios, on=["PLACA", "FECHORA_INI_VIAJE"])
    if not repetidos.empty:
        sys.exit("ERROR: ya hay viajes recuperados en el documento principal; revisa si ya se agregaron.")

    # Un punto GPS va una sola vez; gana el documento principal y luego el viaje anterior.
    total = len(nuevos)
    nuevos = nuevos.sort_values(["PLACA", "FECHA_HORA_TRACK", "FECHORA_INI_VIAJE"], ignore_index=True)
    nuevos = nuevos.drop_duplicates(["PLACA", "FECHA_HORA_TRACK"], keep="first")
    clave = base[["PLACA", "FECHA_HORA_TRACK"]].drop_duplicates()
    marcado = nuevos.merge(clave, on=["PLACA", "FECHA_HORA_TRACK"], how="left", indicator=True)
    nuevos = marcado.loc[marcado["_merge"] == "left_only", COLUMNS]
    ya_en_principal = int((marcado["_merge"] == "both").sum())
    print(f"  {total - len(marcado)} puntos repetidos entre viajes, {ya_en_principal} ya estaban en el principal")
    print(f"  {len(nuevos)} puntos nuevos")

    despachos["PUNTOS_ENCONTRADOS"] = despachos["FILA_EXCEL"].map(puntos)
    agregados = nuevos.groupby(["PLACA", "FECHORA_INI_VIAJE"]).size().rename("PUNTOS_AGREGADOS").reset_index()
    reporte = despachos.assign(FECHORA_INI_VIAJE=despachos["INI"].dt.strftime(DATE_FMT))
    reporte = reporte.merge(agregados, on=["PLACA", "FECHORA_INI_VIAJE"], how="left")
    reporte["PUNTOS_AGREGADOS"] = reporte["PUNTOS_AGREGADOS"].fillna(0).astype(int)
    reporte["FIN"] = reporte["FIN"].dt.strftime(DATE_FMT)
    columnas = ["FILA_EXCEL", "ID2", "PLACA", "SENTIDO", "FECHORA_INI_VIAJE", "FIN", "DURACION"]
    columnas += ["PUNTOS_ENCONTRADOS", "PUNTOS_AGREGADOS", "AVISO"]
    with pd.ExcelWriter(reporte_path, engine="openpyxl") as writer:
        reporte.sort_values("FILA_EXCEL")[columnas].to_excel(writer, sheet_name="Recuperados", index=False)
        descartados.to_excel(writer, sheet_name="No recuperados", index=False)
        sin_tramas.to_excel(writer, sheet_name="Sin tramas", index=False)

    completo = pd.concat([base, nuevos], ignore_index=True)
    completo = completo.sort_values(["FECHORA_INI_VIAJE", "PLACA", "FECHA_HORA_TRACK"], ignore_index=True)
    print(f"\nEscribiendo {csv_path}...")
    completo.to_csv(csv_path, sep=args.sep, index=False, lineterminator="\n")

    if not args.sin_xlsx:
        print(f"Escribiendo {xlsx_path} (tarda varios minutos)...")
        for col in ("FECHORA_INI_VIAJE", "FECHA_HORA_TRACK"):
            completo[col] = pd.to_datetime(completo[col])
        for col in ("CODIGO_RUTA", "LATITUD", "LONGITUD", "VELOCIDAD", "SENTIDO"):
            completo[col] = pd.to_numeric(completo[col], errors="coerce")
        write_resultado(completo, xlsx_path)

    print(f"\nOK: {len(base)} + {len(nuevos)} = {len(base) + len(nuevos)} filas")
    print(f"    {csv_path}\n    {reporte_path}")


if __name__ == "__main__":
    main()
