from datetime import datetime

import pytest

from domain.rules import (
    assign_partition,
    extract_driver_document,
    format_for_api,
    parse_boundary,
    parse_operational_datetime,
    resolve_date_range,
    to_local_isoformat,
)


# resolve_date_range

def test_resolve_date_range_uses_explicit_start_end():

    row = {
        "START_DATETIME": datetime(2026, 1, 1, 8, 0, 0),
        "END_DATETIME": datetime(2026, 1, 1, 18, 0, 0),
    }

    date_range = resolve_date_range(row)

    assert date_range.start == datetime(2026, 1, 1, 8, 0, 0)
    assert date_range.end == datetime(2026, 1, 1, 18, 0, 0)


def test_resolve_date_range_falls_back_to_operational_fields():

    row = {
        "FECHORA_INI_VIAJE": "2026-01-01T08:00:00",
        "FECHA_HORA_FIN_TRAMO": "2026-01-01T18:00:00",
    }

    date_range = resolve_date_range(row)

    assert date_range.start == datetime(2026, 1, 1, 8, 0, 0)
    assert date_range.end == datetime(2026, 1, 1, 18, 0, 0)


def test_resolve_date_range_falls_back_to_calculated_end_when_real_end_missing():

    row = {
        "FECHORA_INI_VIAJE": "2026-01-01T08:00:00",
        "FECHA_HORA_FIN_TRAMO_CALCULADA": "2026-01-01T19:00:00",
    }

    date_range = resolve_date_range(row)

    assert date_range.end == datetime(2026, 1, 1, 19, 0, 0)


def test_resolve_date_range_raises_when_start_missing():

    with pytest.raises(ValueError):
        resolve_date_range({"FECHA_HORA_FIN_TRAMO": "2026-01-01T18:00:00"})


def test_resolve_date_range_raises_when_end_missing():

    with pytest.raises(ValueError):
        resolve_date_range({"FECHORA_INI_VIAJE": "2026-01-01T08:00:00"})


# format_for_api

def test_format_for_api_preserves_wall_clock_and_adds_milliseconds():

    value = datetime(2026, 7, 6, 14, 0, 0, 123000)

    result = format_for_api(value)

    assert result.startswith("2026-07-06T14:00:00.123")


# to_local_isoformat

def test_to_local_isoformat_same_day():

    result = to_local_isoformat("2026-07-06T20:00:00.000Z")

    assert result == "2026-07-06T15:00:00.000"


def test_to_local_isoformat_crosses_day_boundary():

    result = to_local_isoformat("2026-07-06T03:00:00.000Z")

    assert result == "2026-07-05T22:00:00.000"


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


# assign_partition

def test_assign_partition_before_first_limit():

    limits = [datetime(2026, 1, 10), datetime(2026, 1, 20)]

    assert assign_partition(datetime(2026, 1, 5), limits) == 1


def test_assign_partition_after_last_limit():

    limits = [datetime(2026, 1, 10), datetime(2026, 1, 20)]

    assert assign_partition(datetime(2026, 1, 25), limits) == 3


def test_assign_partition_at_boundary_goes_to_next_partition():

    limits = [datetime(2026, 1, 10), datetime(2026, 1, 20)]

    assert assign_partition(datetime(2026, 1, 10), limits) == 2


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
