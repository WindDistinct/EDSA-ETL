from datetime import datetime, timezone

from domain.rules import (
    extract_driver_document,
    format_for_api,
    parse_boundary,
    parse_operational_datetime,
    to_local_isoformat,
)


# format_for_api

def test_format_for_api_preserves_wall_clock_and_adds_milliseconds():

    value = datetime(2026, 7, 6, 14, 0, 0, 123000)

    result = format_for_api(value)

    assert result.startswith("2026-07-06T14:00:00.123")


# to_local_isoformat

def test_to_local_isoformat_same_day():

    result = to_local_isoformat("2026-07-06T20:00:00.000Z")

    assert result == "2026-07-06T15:00:00"


def test_to_local_isoformat_crosses_day_boundary():

    result = to_local_isoformat("2026-07-06T03:00:00.000Z")

    assert result == "2026-07-05T22:00:00"


# parse_boundary

def test_parse_boundary_date_only_end_extends_to_end_of_day():

    result = parse_boundary("2026-07-06", is_end=True)

    assert result == datetime(2026, 7, 6, 23, 59, 59)


def test_parse_boundary_full_datetime_end_untouched():

    result = parse_boundary("2026-07-06 14:00:00", is_end=True)

    assert result == datetime(2026, 7, 6, 14, 0, 0)


def test_parse_boundary_start_date_only_stays_midnight():

    result = parse_boundary("2026-07-06", is_end=False)

    assert result == datetime(2026, 7, 6, 0, 0, 0)


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


def test_format_for_api_naive_se_interpreta_como_lima():

    assert format_for_api(datetime(2026, 7, 6, 14, 0)) == "2026-07-06T14:00:00.000-05:00"


def test_format_for_api_convierte_utc_a_lima():

    value = datetime(2026, 7, 6, 19, 0, tzinfo=timezone.utc)

    assert format_for_api(value) == "2026-07-06T14:00:00.000-05:00"
