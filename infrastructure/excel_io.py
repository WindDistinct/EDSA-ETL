from __future__ import annotations

import pandas as pd


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza los nombres de columnas: sin espacios, en mayúsculas.
    """

    df = df.copy()

    df.columns = (
        df.columns
        .str.strip()
        .str.upper()
    )

    return df


def read_all_sheets(path: str, *, dtype=str) -> pd.DataFrame:
    """
    Lee todas las hojas de un Excel y las concatena en un único DataFrame.
    """

    sheets = pd.read_excel(
        path,
        sheet_name=None,
        dtype=dtype,
    )

    return pd.concat(
        sheets.values(),
        ignore_index=True,
    )


def read_listing_excel(
    path: str,
    *,
    column_aliases: dict[str, str],
    required_columns: list[str],
) -> pd.DataFrame:
    """
    Lee un listado simple (todas las hojas), normaliza columnas,
    aplica alias y valida que estén presentes las columnas requeridas.
    """

    df = read_all_sheets(path, dtype=str)

    df = normalize_columns(df)

    df = df.rename(columns=column_aliases)

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Columnas faltantes en el listado: {missing}"
        )

    df = df[required_columns].copy()

    for column in required_columns:

        df[column] = (
            df[column]
            .astype(str)
            .str.strip()
        )

    return df
