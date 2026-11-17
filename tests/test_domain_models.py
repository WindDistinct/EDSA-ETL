from datetime import datetime

import pytest

from domain.models import DateRange, Sentido, Trip, TripOutcome, TripStatus


def test_date_range_rejects_end_before_start():

    with pytest.raises(ValueError):
        DateRange(
            start=datetime(2026, 1, 2),
            end=datetime(2026, 1, 1),
        )


def test_date_range_allows_equal_start_and_end():

    dt = datetime(2026, 1, 1, 12, 0, 0)

    date_range = DateRange(start=dt, end=dt)

    assert date_range.start == dt
    assert date_range.end == dt


def test_trip_only_requires_plate_and_range():

    trip = Trip(placa="A0P736", date_range=DateRange(start=datetime(2026, 1, 1), end=datetime(2026, 1, 2)))

    assert trip.object_id is None and trip.sentido is None and trip.ref is None


def test_trip_outcome_of_copies_ref_and_plate():

    trip = Trip(placa="A0P736", date_range=DateRange(start=datetime(2026, 1, 1), end=datetime(2026, 1, 2)), ref="7")

    outcome = TripOutcome.of(trip, TripStatus.OK, points=3)

    assert (outcome.ref, outcome.placa, outcome.trip, outcome.points) == ("7", "A0P736", trip, 3)


# Sentido


@pytest.mark.parametrize("valor", ["IDA", "ida", " Ida ", "I", "i", 0, "0"])
def test_sentido_parse_ida(valor):

    assert Sentido.parse(valor) is Sentido.IDA


@pytest.mark.parametrize("valor", ["VUELTA", "vuelta", "V", 1, "1"])
def test_sentido_parse_vuelta(valor):

    assert Sentido.parse(valor) is Sentido.VUELTA


def test_sentido_representaciones():

    assert (Sentido.IDA.codigo, Sentido.IDA.letra) == (0, "I")
    assert (Sentido.VUELTA.codigo, Sentido.VUELTA.letra) == (1, "V")


@pytest.mark.parametrize("valor", [None, "", "X", 2, "IDA Y VUELTA"])
def test_sentido_invalido(valor):

    with pytest.raises(ValueError):
        Sentido.parse(valor)

    assert Sentido.try_parse(valor) is None


def test_trip_status_se_escribe_como_texto():

    assert str(TripStatus.SIN_PUNTOS) == "sin_puntos"
    assert f"{TripStatus.OK}" == "ok"
