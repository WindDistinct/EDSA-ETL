"""El CLI arma los clientes correctos para cada comando y los cierra."""

from __future__ import annotations

import pytest

import main
from application.run_trips import RunReport


class FakeClient:
    instances: list[FakeClient] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False
        FakeClient.instances.append(self)

    def close(self):
        self.closed = True


class FakeFM(FakeClient):
    pass


class FakeLuca(FakeClient):
    pass


@pytest.fixture
def calls(monkeypatch):

    FakeClient.instances = []
    recorded: dict = {}

    def fake_command(name):
        def run(*args, **kwargs):
            recorded["command"] = name
            recorded["args"] = args
            recorded["kwargs"] = kwargs
            return RunReport()
        return run

    monkeypatch.setattr(main, "FMTrackClient", FakeFM)
    monkeypatch.setattr(main, "LucaClient", FakeLuca)
    for name in ("despachos", "rango_fijo", "reconsideracion"):
        monkeypatch.setattr(main.commands, name, fake_command(name))

    return recorded


def test_despachos_uses_luca_for_dispatch_and_fmtrack_for_gps(calls):

    main.main(["despachos", "--luca-empresa", "10", "--luca-ruta", "6", "--start", "2026-08-01", "--end", "2026-08-02", "--output", "x.xlsx"])

    dispatch, track = calls["args"]
    assert isinstance(dispatch, FakeLuca) and dispatch.kwargs == {"empresa": 10, "ruta": 6}
    assert isinstance(track, FakeFM)
    assert all(c.closed for c in FakeClient.instances)


def test_despachos_with_provider_luca_reuses_the_same_client(calls):

    main.main(["despachos", "--luca-empresa", "10", "--luca-ruta", "6", "--start", "2026-08-01", "--end", "2026-08-02",
               "--output", "x.xlsx", "--provider", "luca"])

    dispatch, track = calls["args"]
    assert dispatch is track
    assert len(FakeClient.instances) == 1


def test_fixed_range_without_input_lists_vehicles_from_luca(calls):

    main.main(["fixed-range", "--output", "x.xlsx", "--start", "2026-08-01", "--end", "2026-08-02",
               "--luca-empresa", "10", "--luca-ruta", "6"])

    (track,) = calls["args"]
    assert isinstance(track, FakeFM)
    assert isinstance(calls["kwargs"]["vehicle_source"], FakeLuca)
    assert calls["kwargs"]["codigo_ruta"] == 6


def test_fixed_range_without_input_requires_luca_ids(calls):

    with pytest.raises(SystemExit):
        main.main(["fixed-range", "--output", "x.xlsx", "--start", "2026-08-01", "--end", "2026-08-02"])


def test_reconsideracion_defaults(calls):

    main.main(["reconsideracion", "--input", "rechazados.xlsx", "--limite", "5"])

    (track,) = calls["args"]
    assert isinstance(track, FakeFM)
    assert calls["kwargs"] == {
        "input_file": "rechazados.xlsx",
        "output_dir": "output/reconsideracion",
        "workers": 8,
        "limite": 5,
    }
