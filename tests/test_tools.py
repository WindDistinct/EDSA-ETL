"""Herramientas offline de tools/ (sin red): formato ATU y cruce de despachos con tramas."""

from __future__ import annotations

import datetime as dt

import openpyxl
import pandas as pd

from infrastructure.atu_format import ATU_COLUMNS, missing_columns, normalize_dates_text
from infrastructure.track_record_writer import TrackRecordWriter
from tools.despachos_tramas import cruzar, load_despachos

MAX = pd.Timedelta(hours=6)
RECORTE = pd.Timedelta(hours=2)


# atu_format

def test_normalize_dates_text_quita_la_t_y_conserva_lo_que_no_entiende():

    serie = pd.Series(["2026-10-20T10:34:17", "2026-10-21T00:00:05", "sin fecha"])

    assert list(normalize_dates_text(serie)) == ["2026-10-20 10:34:17", "2026-10-21 00:00:05", "sin fecha"]


def test_missing_columns_y_writer_usan_el_mismo_esquema():

    assert missing_columns(pd.DataFrame(columns=ATU_COLUMNS)) == []
    assert missing_columns(pd.DataFrame(columns=["PLACA"]))[0] == "RUC_EMPRESA"
    assert TrackRecordWriter.BASE_HEADERS == ATU_COLUMNS


# despachos_tramas

def _despachos_excel(path, filas):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ID2", "FECHA", "RUC_EMPRESA", "PLACA", "IMEI", "CODIGO_RUTA", "SENTIDO", "HORA SENTIDO", "LLEG.",
               "NRO_DOC_CONDUCTOR"])
    for i, (placa, sentido, hora, lleg) in enumerate(filas, start=1):
        ws.append([i, dt.datetime(2026, 10, 20), "20606259540", placa, "", 1205, sentido, hora, lleg, 6583153])
    wb.save(path)
    return path


def test_load_despachos_corrige_omite_y_recorta(tmp_path):

    path = _despachos_excel(
        tmp_path / "despachos.xlsx",
        [
            ("A1I730", "IDA", "10:.34", "13:00"),     # 2: tipeo -> corregido
            ("A1I730", "VUELTA", "23:00", "01:00"),   # 3: cruza medianoche
            ("B1X797", "IDA", "05:00", "14:00"),      # 4: fin imposible -> recorte, limitado por la fila 5
            ("B1X797", "VUELTA", "06:30", "08:00"),   # 5
            ("B1X797", "IDA", "18:!5", "20:00"),      # 6: irrecuperable -> omitido
            ("B1X797", "CIRCULAR", "09:00", "10:00"), # 7: sentido inválido -> omitido
        ],
    )

    despachos, irregulares = load_despachos(path, MAX, RECORTE)

    por_fila = despachos.set_index("FILA_EXCEL")

    assert por_fila.loc[2, "INI"] == pd.Timestamp("2026-10-20 10:34")
    assert por_fila.loc[2, "SENTIDO"] == 0
    assert por_fila.loc[2, "NRO_DOC_CONDUCTOR"] == "06583153"
    assert por_fila.loc[3, "FIN"] == pd.Timestamp("2026-10-21 01:00")
    assert por_fila.loc[4, "FIN"] == pd.Timestamp("2026-10-20 06:29:59")  # no invade el despacho de las 06:30
    assert set(por_fila.index) == {2, 3, 4, 5}

    acciones = irregulares.groupby("FILA_EXCEL")["TIPO"].apply(set).to_dict()

    assert "HORA_CORREGIDA" in acciones[2]
    assert "CRUCE_MEDIANOCHE" in acciones[3]
    assert "FIN_IMPOSIBLE" in acciones[4]
    assert acciones[6] == {"FECHA_INCOMPLETA"}
    assert acciones[7] == {"SENTIDO_INVALIDO"}


def test_cruzar_asigna_tramas_por_placa_e_intervalo(tmp_path):

    path = _despachos_excel(tmp_path / "despachos.xlsx", [("A1I730", "IDA", "10:00", "11:00"), ("SINGPS", "IDA", "10:00", "11:00")])

    despachos, _ = load_despachos(path, MAX, RECORTE)

    tramas = pd.DataFrame(
        {
            "PLACA": ["A1I730"] * 3,
            "IMEI": ["863238075031916"] * 3,
            "FECHA_HORA_TRACK": pd.to_datetime(["2026-10-20 09:59:59", "2026-10-20 10:00:00", "2026-10-20 11:00:00"]),
            "LATITUD": [-12.0, -12.1, -12.2],
            "LONGITUD": [-77.0] * 3,
            "VELOCIDAD": [10] * 3,
        }
    )

    result, sin_tramas, puntos = cruzar(despachos, tramas)

    assert list(result.columns) == ATU_COLUMNS
    assert list(result["LATITUD"]) == [-12.1, -12.2]  # extremos incluidos, 09:59:59 fuera
    assert puntos == {2: 2, 3: 0}
    assert list(sin_tramas["MOTIVO"]) == ["placa sin tramas en el mes"]
