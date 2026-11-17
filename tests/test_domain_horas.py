from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest
from openpyxl.utils.datetime import from_excel, to_excel

from domain.horas import (
    combinar,
    cruzar_medianoche,
    excel_serial,
    normalizar_dni,
    parse_hora,
    recortar_fin,
)


# parse_hora: textos con errores de tipeo

@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("12:.04", time(12, 4)),
        ("22::21", time(22, 21)),
        ("19;45", time(19, 45)),
        ("22:_53", time(22, 53)),
        ("4:19am", time(4, 19)),
        ("4:19pm", time(16, 19)),
        ("12:30pm", time(12, 30)),
        ("09:11:00", time(9, 11)),
    ],
)
def test_parse_hora_corrige_textos(texto, esperado):

    hora, nota = parse_hora(texto)

    assert hora == esperado
    assert nota


@pytest.mark.parametrize("texto", ["18:!5", "", "-", "25:00", "abc"])
def test_parse_hora_rechaza_textos_irrecuperables(texto):

    assert parse_hora(texto) == (None, "")


def test_parse_hora_time_se_usa_tal_cual():

    assert parse_hora(time(8, 5)) == (time(8, 5), "")


def test_parse_hora_none():

    assert parse_hora(None) == (None, "")


# parse_hora: valores que Excel reinterpretó

def test_parse_hora_numero_decimal_guardado_como_fecha_1900():

    # "9.31" -> Excel lo guarda como el número 9.31 (una fecha de enero de 1900)
    hora, nota = parse_hora(from_excel(9.31))

    assert hora == time(9, 31)
    assert "9.31" in nota


def test_parse_hora_numero_entero_sin_separador():

    hora, _ = parse_hora(from_excel(836))

    assert hora == time(8, 36)


def test_parse_hora_fecha_dia_mes():

    # "16.04" -> Excel lo convirtió en la fecha 16/04
    hora, _ = parse_hora(datetime(2026, 4, 16))

    assert hora == time(16, 4)


def test_parse_hora_fecha_que_no_es_hora():

    assert parse_hora(datetime(2026, 4, 28)) == (None, "")


@pytest.mark.parametrize("serial", [1.5, 9.31, 59, 60, 61, 836, 2359, 46000.75])
def test_excel_serial_equivale_a_openpyxl(serial):

    value = from_excel(serial)

    assert excel_serial(value) == pytest.approx(to_excel(value))


# tramo

def test_combinar_descarta_la_hora_de_la_fecha():

    assert combinar(datetime(2026, 6, 3, 15, 0), time(8, 30)) == datetime(2026, 6, 3, 8, 30)
    assert combinar(date(2026, 6, 3), time(8, 30)) == datetime(2026, 6, 3, 8, 30)


def test_cruzar_medianoche_pasa_la_llegada_al_dia_siguiente():

    fin, cruzo = cruzar_medianoche(datetime(2026, 6, 3, 23, 0), datetime(2026, 6, 3, 1, 0))

    assert (fin, cruzo) == (datetime(2026, 6, 4, 1, 0), True)


def test_cruzar_medianoche_no_toca_un_tramo_normal():

    fin, cruzo = cruzar_medianoche(datetime(2026, 6, 3, 8, 0), datetime(2026, 6, 3, 10, 0))

    assert (fin, cruzo) == (datetime(2026, 6, 3, 10, 0), False)


def test_recortar_fin_imposible():

    ini = datetime(2026, 6, 3, 8, 0)

    fin, recortado = recortar_fin(ini, ini + timedelta(hours=9))

    assert (fin, recortado) == (ini + timedelta(hours=2), True)


def test_recortar_fin_respeta_duracion_creible():

    ini = datetime(2026, 6, 3, 8, 0)

    assert recortar_fin(ini, ini + timedelta(hours=6)) == (ini + timedelta(hours=6), False)


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("06583153", "06583153"), ("6583153", "06583153"), (6583153, "06583153"), ("#N/A", ""), ("NO DATA", ""), (None, "")],
)
def test_normalizar_dni(valor, esperado):

    assert normalizar_dni(valor) == esperado
