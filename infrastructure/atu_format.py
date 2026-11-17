"""Formato de tramas ATU: columnas, tipos y fechas como texto.

Lo comparten el sink de la aplicación (TrackRecordWriter) y las herramientas
de tools/ que leen, convierten o unen esos archivos.
"""

from __future__ import annotations

import pandas as pd

ATU_COLUMNS = [
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

# Siempre numéricas. RUC, IMEI y documento van como texto para no perder
# ceros a la izquierda (NRO_DOC_CONDUCTOR = "06583153") ni pasar el IMEI a
# notación científica.
COORD_COLUMNS = ["LATITUD", "LONGITUD", "VELOCIDAD"]

# Numéricas al escribir un Excel consolidado (CODIGO_RUTA y SENTIDO incluidos).
EXCEL_NUMERIC_COLUMNS = ["CODIGO_RUTA", *COORD_COLUMNS, "SENTIDO"]

DATE_FMT = "%Y-%m-%d %H:%M:%S"
EXCEL_DATE_FMT = "YYYY-MM-DD HH:MM:SS"

# Separador de los CSV de tramas.
CSV_SEP = "|"


def missing_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in ATU_COLUMNS if c not in df.columns]


def normalize_dates_text(series: pd.Series) -> pd.Series:
    """
    Fechas a texto "YYYY-MM-DD HH:MM:SS". Lo que no se pueda interpretar
    queda como estaba, solo sin la "T" de ISO 8601.
    """

    parsed = pd.to_datetime(series, errors="coerce")
    out = parsed.dt.strftime(DATE_FMT)
    fallback = series.astype("string").str.replace("T", " ", regex=False)
    return out.fillna(fallback)
