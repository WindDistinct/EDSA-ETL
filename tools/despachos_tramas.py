"""Cruza los despachos de un mes con las tramas GPS y genera un Excel por viaje.

Entradas:
- Excel de despachos (una hoja): FECHA, PLACA, SENTIDO, HORA SENTIDO, LLEG., ...
  Las columnas FECHORA_INI_VIAJE / FECHORA_FIN_VIAJE son formulas (=FECHA+HORA),
  asi que se recalculan aqui desde FECHA + HORA SENTIDO / LLEG.
  Con --usar-fechora se toman de esas columnas (ya corregidas a mano como valores);
  si la fecha cae fuera del dia del despacho (error de tipeo sumado a FECHA, p. ej.
  "16.41" -> 19/06 09:50) esa fila vuelve a HORA SENTIDO / LLEG.
- Excel de tramas (una hoja por dia) con el formato objetivo.

Reglas de limpieza de cada despacho:
- Hora escrita con error de tipeo y recuperable sin ambiguedad -> se CORRIGE:
    "12:.04", "22::21", "19;45", "4:19am"      -> 12:04, 22:21, 19:45, 04:19
    9.31 (Excel lo guardo como numero/fecha 1900) -> 09:31
    836 (numero entero)                          -> 08:36
    16/04/2026 (Excel lo leyo como dia/mes)      -> 16:04
- Hora vacia, "-", 00:00 en la salida o irrecuperable ("18:!5") -> INCOMPLETO, se omite.
- Llegada menor que la salida -> se asume que cruza medianoche (+1 dia).
- Duracion mayor a --max-horas (fin imposible) -> se RECORTA a salida + --horas-recorte.
Todo lo anterior queda anotado en el Excel de irregularidades.

El cruce con las tramas se hace por PLACA (el IMEI del despacho viene de un
BUSCARV y no siempre coincide con el GPS real); el IMEI de salida es el de la trama.

La primera lectura del Excel de tramas es lenta (~5M filas); se guarda una cache
.pkl al lado del archivo y las siguientes corridas la reutilizan.

Uso:
    python tools/despachos_tramas.py input/1205_JUNIO_VARGASANT.xlsx input/vargasant_1205_2026_06_01_06_30.xlsx
    python tools/despachos_tramas.py DESPACHOS TRAMAS -o output/vargasant/1205_junio.xlsx
    python tools/despachos_tramas.py DESPACHOS TRAMAS --solo-validar
    python tools/despachos_tramas.py DESPACHOS TRAMAS --max-horas 5 --horas-recorte 2
    python tools/despachos_tramas.py DESPACHOS TRAMAS --usar-fechora
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from domain.horas import DURACION_CORTA, combinar, cruzar_medianoche, normalizar_dni, parse_hora, recortar_fin  # noqa: E402
from domain.models import Sentido  # noqa: E402
from infrastructure.atu_format import ATU_COLUMNS as COLUMNS  # noqa: E402
from infrastructure.atu_format import DATE_FMT  # noqa: E402

def fechora_del_dia(value, fecha: pd.Timestamp, dias_extra: int) -> pd.Timestamp | None:
    """Devuelve la fecha-hora corregida a mano, o None si no cae en el dia del despacho."""
    if not isinstance(value, dt.datetime):
        return None
    ts = pd.Timestamp(value).round("s")
    return ts if 0 <= (ts.normalize() - fecha).days <= dias_extra else None


def fmt_original(value) -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.strftime(DATE_FMT)
    return str(value)


def load_despachos(
    path: Path, max_dur: pd.Timedelta, recorte: pd.Timedelta, usar_fechora: bool = False
) -> tuple[pd.DataFrame, pd.DataFrame]:
    # data_only=True: valores calculados de las formulas (IMEI viene de un BUSCARV).
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = [str(c).strip() if c is not None else "" for c in next(rows)]
    # FILA_EXCEL: numero de fila en la hoja, para ubicar el despacho (ID2 no es correlativo).
    registros = [
        {**dict(zip(header, r)), "FILA_EXCEL": fila}
        for fila, r in enumerate(rows, start=2)
        if any(v is not None for v in r)
    ]
    wb.close()

    validos: list[dict] = []
    irregulares: list[dict] = []

    for row in registros:
        base = {
            "FILA_EXCEL": row["FILA_EXCEL"],
            "ID2": row.get("ID2"),
            "FECHA": row["FECHA"].date() if isinstance(row["FECHA"], dt.datetime) else row["FECHA"],
            "PLACA": str(row["PLACA"]).strip().upper(),
            "SENTIDO": row["SENTIDO"],
            "HORA SENTIDO (original)": fmt_original(row["HORA SENTIDO"]),
            "LLEG. (original)": fmt_original(row["LLEG."]),
            "FECHORA_INI_VIAJE (original)": fmt_original(row.get("FECHORA_INI_VIAJE")),
            "FECHORA_FIN_VIAJE (original)": fmt_original(row.get("FECHORA_FIN_VIAJE")),
        }

        def irregular(tipo: str, accion: str, detalle: str, ini=None, fin=None) -> dict:
            irregulares.append(
                {
                    **base,
                    "TIPO": tipo,
                    "ACCION": accion,
                    "DETALLE": detalle,
                    "INI_USADO": ini.strftime(DATE_FMT) if ini is not None else "",
                    "FIN_USADO": fin.strftime(DATE_FMT) if fin is not None else "",
                }
            )
            return irregulares[-1]

        if not isinstance(row["FECHA"], dt.datetime):
            irregular("FECHA_INCOMPLETA", "OMITIDO", "FECHA vacia o invalida")
            continue

        sentido = Sentido.try_parse(row["SENTIDO"])
        if sentido is None:
            irregular("SENTIDO_INVALIDO", "OMITIDO", f"SENTIDO {row['SENTIDO']!r} no es IDA/VUELTA")
            continue

        fecha = pd.Timestamp(row["FECHA"]).normalize()
        ini = fechora_del_dia(row.get("FECHORA_INI_VIAJE"), fecha, 0) if usar_fechora else None
        fin = fechora_del_dia(row.get("FECHORA_FIN_VIAJE"), fecha, 1) if usar_fechora else None
        nota_ini = nota_fin = ""
        if ini is None:
            hora_ini, nota_ini = parse_hora(row["HORA SENTIDO"])
            if hora_ini is not None:
                ini = pd.Timestamp(combinar(fecha, hora_ini))
        if fin is None:
            hora_fin, nota_fin = parse_hora(row["LLEG."])
            if hora_fin is not None:
                fin = pd.Timestamp(combinar(fecha, hora_fin))
        if ini == fecha:
            ini = None  # 00:00 se usa como relleno de filas sin programar

        faltan = [n for n, h in (("HORA SENTIDO", ini), ("LLEG.", fin)) if h is None]
        if faltan:
            irregular("FECHA_INCOMPLETA", "OMITIDO", f"sin hora valida en: {', '.join(faltan)}")
            continue

        notas = []
        if nota_ini:
            notas.append(f"HORA SENTIDO: {nota_ini}")
        if nota_fin:
            notas.append(f"LLEG.: {nota_fin}")

        fin, cruzo = cruzar_medianoche(ini, fin)
        if cruzo:
            irregular("CRUCE_MEDIANOCHE", "AJUSTADO", "llegada despues de medianoche (+1 dia a la llegada)", ini, fin)

        if notas:
            irregular("HORA_CORREGIDA", "CORREGIDO", "; ".join(notas), ini, fin)

        dur = fin - ini
        registro_recorte = None
        if dur == pd.Timedelta(0):
            irregular("FECHA_INCOMPLETA", "OMITIDO", "salida igual a llegada (sin intervalo)", ini, fin)
            continue
        if dur > max_dur:
            fin_original = fin
            fin, _ = recortar_fin(ini, fin, max_duracion=max_dur, recorte=recorte)
            registro_recorte = irregular(
                "FIN_IMPOSIBLE",
                "RECORTADO",
                f"duracion {dur} > {max_dur}; fin {fin_original:%Y-%m-%d %H:%M} -> ini + {recorte}",
                ini,
                fin,
            )
        elif dur < DURACION_CORTA:
            irregular("DURACION_CORTA", "INCLUIDO", f"duracion {dur} (revisar)", ini, fin)

        validos.append(
            {
                "FILA_EXCEL": base["FILA_EXCEL"],
                "ID2": base["ID2"],
                "RUC_EMPRESA": str(row["RUC_EMPRESA"]).strip(),
                "PLACA": base["PLACA"],
                "IMEI_DESPACHO": str(row.get("IMEI") or "").strip(),
                "CODIGO_RUTA": row["CODIGO_RUTA"],
                "INI": ini,
                "FIN": fin,
                "SENTIDO": sentido.codigo,
                "NRO_DOC_CONDUCTOR": normalizar_dni(row["NRO_DOC_CONDUCTOR"]),
                "_recorte": registro_recorte,
            }
        )

    despachos = pd.DataFrame(validos).sort_values(["PLACA", "INI"], ignore_index=True)

    # El recorte no debe invadir el siguiente despacho de la misma placa.
    siguiente = despachos.groupby("PLACA")["INI"].shift(-1)
    for i in despachos.index[despachos["_recorte"].notna()]:
        nxt = siguiente[i]
        if pd.notna(nxt) and despachos.at[i, "INI"] < nxt < despachos.at[i, "FIN"]:
            despachos.at[i, "FIN"] = nxt - pd.Timedelta(seconds=1)
            reg = despachos.at[i, "_recorte"]
            reg["FIN_USADO"] = despachos.at[i, "FIN"].strftime(DATE_FMT)
            reg["DETALLE"] += " (limitado por el siguiente despacho)"

    return despachos.drop(columns="_recorte"), pd.DataFrame(irregulares)


def load_tramas(path: Path, use_cache: bool) -> pd.DataFrame:
    cache = path.with_suffix(".pkl")
    if use_cache and cache.exists() and cache.stat().st_mtime >= path.stat().st_mtime:
        print(f"  usando cache {cache}")
        return pd.read_pickle(cache)

    print(f"  leyendo {path} (tarda varios minutos)...")
    wb = openpyxl.load_workbook(path, read_only=True)
    frames = []
    for ws in wb.worksheets:
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None)
        if header is None:
            continue
        df = pd.DataFrame(rows, columns=[str(c).strip() for c in header])
        if df.empty:
            continue
        df = df[["PLACA", "IMEI", "FECHA_HORA_TRACK", "LATITUD", "LONGITUD", "VELOCIDAD"]]
        frames.append(df)
        print(f"    hoja {ws.title!r} -> {len(df)} filas")
    wb.close()

    tramas = pd.concat(frames, ignore_index=True)
    tramas["PLACA"] = tramas["PLACA"].astype(str).str.strip().str.upper()
    tramas["IMEI"] = tramas["IMEI"].astype(str).str.strip()
    tramas["FECHA_HORA_TRACK"] = pd.to_datetime(tramas["FECHA_HORA_TRACK"], errors="coerce")
    tramas = tramas.dropna(subset=["FECHA_HORA_TRACK"])
    tramas = tramas.drop_duplicates(subset=["PLACA", "FECHA_HORA_TRACK"])
    tramas = tramas.sort_values(["PLACA", "FECHA_HORA_TRACK"], ignore_index=True)

    if use_cache:
        tramas.to_pickle(cache)
        print(f"  cache guardada en {cache}")
    return tramas


def cruzar(despachos: pd.DataFrame, tramas: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[int, int]]:
    """Asigna a cada despacho las tramas de su placa con INI <= track <= FIN."""
    partes: list[pd.DataFrame] = []
    sin_tramas: list[dict] = []
    puntos: dict[int, int] = {}

    for placa, grupo in despachos.groupby("PLACA", sort=False):
        t = tramas[tramas["PLACA"] == placa]
        tiempos = t["FECHA_HORA_TRACK"].to_numpy()
        lo = np.searchsorted(tiempos, grupo["INI"].to_numpy(), side="left")
        hi = np.searchsorted(tiempos, grupo["FIN"].to_numpy(), side="right")

        for (_, d), a, b in zip(grupo.iterrows(), lo, hi):
            puntos[d["FILA_EXCEL"]] = int(b - a)
            if a == b:
                sin_tramas.append(
                    {
                        "FILA_EXCEL": d["FILA_EXCEL"],
                        "ID2": d["ID2"],
                        "PLACA": placa,
                        "INI": d["INI"].strftime(DATE_FMT),
                        "FIN": d["FIN"].strftime(DATE_FMT),
                        "MOTIVO": "placa sin tramas en el mes" if t.empty else "sin tramas en el intervalo",
                    }
                )
                continue
            seg = t.iloc[a:b]
            partes.append(
                pd.DataFrame(
                    {
                        "RUC_EMPRESA": d["RUC_EMPRESA"],
                        "PLACA": placa,
                        "IMEI": seg["IMEI"].to_numpy(),
                        "CODIGO_RUTA": d["CODIGO_RUTA"],
                        "FECHORA_INI_VIAJE": d["INI"],
                        "FECHA_HORA_TRACK": seg["FECHA_HORA_TRACK"].to_numpy(),
                        "LATITUD": seg["LATITUD"].to_numpy(),
                        "LONGITUD": seg["LONGITUD"].to_numpy(),
                        "VELOCIDAD": seg["VELOCIDAD"].to_numpy(),
                        "SENTIDO": d["SENTIDO"],
                        "NRO_DOC_CONDUCTOR": d["NRO_DOC_CONDUCTOR"],
                    }
                )
            )

    result = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=COLUMNS)
    result = result.sort_values(["FECHORA_INI_VIAJE", "PLACA", "FECHA_HORA_TRACK"], ignore_index=True)
    return result, pd.DataFrame(sin_tramas), puntos


def write_resultado(result: pd.DataFrame, path: Path) -> None:
    """Una hoja por dia (fecha de inicio del viaje), fechas como texto, igual que la entrada."""
    dia = result["FECHORA_INI_VIAJE"].dt.strftime("%Y-%m-%d")
    out = result.copy()
    for col in ("FECHORA_INI_VIAJE", "FECHA_HORA_TRACK"):
        out[col] = out[col].dt.strftime(DATE_FMT)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for nombre, hoja in out.groupby(dia, sort=True):
            hoja[COLUMNS].to_excel(writer, sheet_name=nombre, index=False)
            print(f"    hoja {nombre!r} -> {len(hoja)} filas")


def tabla_despachos(despachos: pd.DataFrame, irregulares: pd.DataFrame, puntos: dict[int, int] | None) -> pd.DataFrame:
    """Todos los despachos del Excel original (uno por fila) con su estado final."""
    validos = despachos[["FILA_EXCEL", "ID2", "PLACA", "INI", "FIN"]].rename(columns={"INI": "INI_USADO", "FIN": "FIN_USADO"})
    for col in ("INI_USADO", "FIN_USADO"):
        validos[col] = validos[col].dt.strftime(DATE_FMT)
    omitidos = irregulares.loc[irregulares["ACCION"] == "OMITIDO", ["FILA_EXCEL", "ID2", "PLACA"]] if not irregulares.empty else None
    tabla = pd.concat([validos, omitidos], ignore_index=True)

    acciones = (
        irregulares.groupby("FILA_EXCEL")["ACCION"].agg(", ".join) if not irregulares.empty else pd.Series(dtype=str)
    )
    tabla["ESTADO"] = tabla["FILA_EXCEL"].map(acciones).fillna("OK")
    if puntos is not None:
        tabla["PUNTOS_TRAMA"] = tabla["FILA_EXCEL"].map(puntos)
    return tabla.sort_values("FILA_EXCEL", ignore_index=True)


def write_irregularidades(
    irregulares: pd.DataFrame, sin_tramas: pd.DataFrame, todos: pd.DataFrame, path: Path
) -> None:
    if not irregulares.empty:
        irregulares = irregulares.sort_values("FILA_EXCEL", kind="stable", ignore_index=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        resumen = (
            irregulares.groupby(["TIPO", "ACCION"]).size().rename("CANTIDAD").reset_index()
            if not irregulares.empty
            else pd.DataFrame(columns=["TIPO", "ACCION", "CANTIDAD"])
        )
        if not sin_tramas.empty:
            extra = sin_tramas.groupby("MOTIVO").size().rename("CANTIDAD").reset_index()
            extra = extra.rename(columns={"MOTIVO": "TIPO"}).assign(ACCION="SIN_TRAMAS")
            resumen = pd.concat([resumen, extra], ignore_index=True)
        resumen.to_excel(writer, sheet_name="Resumen", index=False)

        hojas = {
            "Omitidos": irregulares[irregulares["ACCION"] == "OMITIDO"] if not irregulares.empty else irregulares,
            "Fin recortado": irregulares[irregulares["ACCION"] == "RECORTADO"] if not irregulares.empty else irregulares,
            "Horas corregidas": irregulares[irregulares["ACCION"] == "CORREGIDO"] if not irregulares.empty else irregulares,
            "Duracion corta": irregulares[irregulares["ACCION"] == "INCLUIDO"] if not irregulares.empty else irregulares,
            "Cruce medianoche": irregulares[irregulares["ACCION"] == "AJUSTADO"] if not irregulares.empty else irregulares,
        }
        for nombre, df in hojas.items():
            df.to_excel(writer, sheet_name=nombre, index=False)
        if not sin_tramas.empty:
            sin_tramas.sort_values("FILA_EXCEL").to_excel(writer, sheet_name="Sin tramas", index=False)
        todos.to_excel(writer, sheet_name="Despachos", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("despachos", help="Excel de despachos")
    parser.add_argument("tramas", help="Excel de tramas (una hoja por dia)")
    parser.add_argument("-o", "--output", help="Excel de salida (por defecto output/<despachos>_tramas.xlsx)")
    parser.add_argument("--max-horas", type=float, default=6, help="Duracion maxima creible de un viaje (def. 6)")
    parser.add_argument("--horas-recorte", type=float, default=2, help="Horas a tomar si el fin es imposible (def. 2)")
    parser.add_argument("--solo-validar", action="store_true", help="Solo genera el Excel de irregularidades")
    parser.add_argument(
        "--usar-fechora",
        action="store_true",
        help="Tomar inicio y fin de FECHORA_INI_VIAJE / FECHORA_FIN_VIAJE en vez de HORA SENTIDO / LLEG.",
    )
    parser.add_argument("--sin-cache", action="store_true", help="No leer ni guardar la cache .pkl de tramas")
    args = parser.parse_args()

    despachos_path = Path(args.despachos)
    tramas_path = Path(args.tramas)
    for p in (despachos_path, tramas_path):
        if not p.exists():
            sys.exit(f"ERROR: no existe {p}")

    output = Path(args.output) if args.output else Path("output") / f"{despachos_path.stem}_tramas.xlsx"
    output.parent.mkdir(parents=True, exist_ok=True)
    irregular_path = output.with_name(f"{output.stem}_irregularidades.xlsx")

    print("Despachos:")
    despachos, irregulares = load_despachos(
        despachos_path, pd.Timedelta(hours=args.max_horas), pd.Timedelta(hours=args.horas_recorte), args.usar_fechora
    )
    omitidos = int((irregulares["ACCION"] == "OMITIDO").sum()) if not irregulares.empty else 0
    print(f"  {len(despachos)} validos, {omitidos} omitidos")
    if not irregulares.empty:
        for (tipo, accion), n in irregulares.groupby(["TIPO", "ACCION"]).size().items():
            print(f"    {tipo:<18} {accion:<10} {n}")

    if args.solo_validar:
        write_irregularidades(irregulares, pd.DataFrame(), tabla_despachos(despachos, irregulares, None), irregular_path)
        print(f"\nOK: irregularidades -> {irregular_path}")
        return

    print("\nTramas:")
    tramas = load_tramas(tramas_path, use_cache=not args.sin_cache)
    print(f"  {len(tramas)} puntos, {tramas['PLACA'].nunique()} placas")

    print("\nCruce:")
    result, sin_tramas, puntos = cruzar(despachos, tramas)
    print(f"  {len(result)} puntos en {len(despachos) - len(sin_tramas)} viajes; {len(sin_tramas)} viajes sin tramas")

    print(f"\nEscribiendo {output}...")
    write_resultado(result, output)
    write_irregularidades(irregulares, sin_tramas, tabla_despachos(despachos, irregulares, puntos), irregular_path)
    print(f"\nOK: {output}\n    {irregular_path}")


if __name__ == "__main__":
    main()
