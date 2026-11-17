from __future__ import annotations

from datetime import datetime

import pandas as pd

from application.sources.despachos_luca import (
    clip_to_window,
    extract_driver_document,
    parse_operational_datetime,
    trip_from_despacho,
    viajes_de_despachos,
)
from application.sources.reconsideracion import leer_viajes
from domain.models import DateRange, Sentido, Trip, TripOutcome, TripStatus

DESPACHO = {
    "ruc_empresa": "20123456789",
    "placa": " A0P736 ",
    "codigo_ruta": "R1",
    "fecha": "2026-07-06",
    "hora": "08:00:00",
    "hora_real_ultimo_punto": "Mon Jul 06 2026 14:00:00 GMT-0500 (hora estándar de Perú)",
    "hora_calculada_ultimo_punto": "Mon Jul 06 2026 15:00:00 GMT-0500 (hora estándar de Perú)",
    "sentido": "vuelta",
    "conductor": "PEREZ, JUAN, 12345678",
}


# despachos_luca

def test_trip_from_despacho_maps_luca_fields():

    trip = trip_from_despacho(DESPACHO, ref="3")

    assert trip == Trip(
        placa="A0P736",
        date_range=DateRange(datetime(2026, 7, 6, 8, 0), datetime(2026, 7, 6, 14, 0)),
        ruc_empresa="20123456789",
        codigo_ruta="R1",
        sentido=Sentido.VUELTA,
        nro_doc_conductor="12345678",
        fechora_ini_viaje=datetime(2026, 7, 6, 8, 0),
        ref="3",
    )


def test_trip_from_despacho_uses_calculated_end_when_real_is_missing():

    trip = trip_from_despacho({**DESPACHO, "hora_real_ultimo_punto": None}, ref="1")

    assert trip.date_range.end == datetime(2026, 7, 6, 15, 0)


def test_trip_from_despacho_without_range_is_invalid_row():

    sin_fin = trip_from_despacho({**DESPACHO, "hora_real_ultimo_punto": None, "hora_calculada_ultimo_punto": None}, "1")
    sin_salida = trip_from_despacho({**DESPACHO, "fecha": None, "hora": None}, "2")
    al_reves = trip_from_despacho({**DESPACHO, "hora": "16:00:00"}, "3")

    for outcome in (sin_fin, sin_salida, al_reves):
        assert isinstance(outcome, TripOutcome)
        assert outcome.status is TripStatus.FILA_INVALIDA
        assert outcome.placa == "A0P736"


def test_clip_to_window_keeps_real_departure():

    trip = trip_from_despacho(DESPACHO, ref="1")
    window = DateRange(datetime(2026, 7, 6, 10, 0), datetime(2026, 7, 6, 12, 0))

    clipped = clip_to_window(trip, window)

    assert clipped.date_range == window
    assert clipped.fechora_ini_viaje == datetime(2026, 7, 6, 8, 0)


def test_viajes_de_despachos_drops_trips_outside_window_and_keeps_invalid():

    fuera = {**DESPACHO, "placa": "FUERA", "hora": "15:30:00",
             "hora_real_ultimo_punto": "Mon Jul 06 2026 18:00:00 GMT-0500 (hora estándar de Perú)"}
    invalido = {**DESPACHO, "placa": "MAL", "fecha": None}

    items = viajes_de_despachos([DESPACHO, fuera, invalido], DateRange(datetime(2026, 7, 6, 10), datetime(2026, 7, 6, 12)))

    assert [(type(i).__name__, i.placa) for i in items] == [("Trip", "A0P736"), ("TripOutcome", "MAL")]


# reconsideracion

def test_leer_viajes_de_reconsideracion(tmp_path):

    path = tmp_path / "reconsideracion.xlsx"

    pd.DataFrame(
        {
            "N°": [1, 2, 3],
            "RUC": ["20606259540"] * 3,
            "Placa": ["a1i730", "A6D799", "B1X797"],
            "Ruta": ["1205"] * 3,
            "Sentido": ["VUELTA", "IDA", "CIRCULAR"],
            "H. Inicio": ["20/10/2026 10:34:00", "20/10/2026 13:00", "20/10/2026 15:00:00"],
            "H. Fin": ["20/10/2026 13:00:28", "20/10/2026 15:25:44", "20/10/2026 17:00:00"],
        }
    ).to_excel(path, index=False)

    viaje, mala_fecha, mal_sentido = leer_viajes(path)

    assert viaje == Trip(
        placa="A1I730",
        date_range=DateRange(datetime(2026, 10, 20, 10, 34), datetime(2026, 10, 20, 13, 0, 28)),
        ruc_empresa="20606259540",
        codigo_ruta="1205",
        sentido=Sentido.VUELTA,
        ref="1",
    )
    assert (mala_fecha.status, mala_fecha.ref) == (TripStatus.FILA_INVALIDA, "2")
    assert (mal_sentido.status, mal_sentido.ref) == (TripStatus.FILA_INVALIDA, "3")
    assert "CIRCULAR" in mal_sentido.detail


# extract_driver_document

def test_extract_driver_document_no_comma():

    assert extract_driver_document("Juan Perez") == ""


def test_extract_driver_document_one_comma():

    assert extract_driver_document("Juan Perez, 12345678") == "12345678"


def test_extract_driver_document_multiple_commas():

    assert extract_driver_document("Perez, Juan, 12345678") == "12345678"


def test_extract_driver_document_none_returns_empty():

    assert extract_driver_document(None) == ""


# parse_operational_datetime

def test_parse_operational_datetime_variant_de():

    result = parse_operational_datetime(
        "Mon Jul 06 2026 14:00:00 GMT-0500 (hora estándar de Perú)"
    )

    assert result == datetime(2026, 7, 6, 14, 0, 0)


def test_parse_operational_datetime_variant_del():

    result = parse_operational_datetime(
        "Mon Jul 06 2026 14:00:00 GMT-0500 (hora estándar del Perú)"
    )

    assert result == datetime(2026, 7, 6, 14, 0, 0)


def test_parse_operational_datetime_unparsable_returns_none():

    assert parse_operational_datetime("no es una fecha") is None


def test_parse_operational_datetime_none_returns_none():

    assert parse_operational_datetime(None) is None
