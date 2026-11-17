from __future__ import annotations

import httpx
import pytest

from infrastructure.http_retry import RateGate, request_with_retry


def test_request_with_retry_retries_on_5xx_then_succeeds():

    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1

        if attempts["count"] < 3:
            return httpx.Response(503)

        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))

    response = request_with_retry(client, "GET", "/x", max_attempts=3, backoff_seconds=0)

    assert response.status_code == 200
    assert attempts["count"] == 3


def test_request_with_retry_retries_on_transport_error_then_succeeds():

    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1

        if attempts["count"] < 2:
            raise httpx.ConnectError("boom", request=request)

        return httpx.Response(200, json={"ok": True})

    client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))

    response = request_with_retry(client, "GET", "/x", max_attempts=3, backoff_seconds=0)

    assert response.status_code == 200
    assert attempts["count"] == 2


def test_request_with_retry_gives_up_after_max_attempts():

    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        raise httpx.ConnectError("boom", request=request)

    client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))

    with pytest.raises(httpx.ConnectError):
        request_with_retry(client, "GET", "/x", max_attempts=3, backoff_seconds=0)

    assert attempts["count"] == 3


def test_request_with_retry_does_not_retry_client_errors():

    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(404)

    client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))

    response = request_with_retry(client, "GET", "/x", max_attempts=3, backoff_seconds=0)

    assert response.status_code == 404
    assert attempts["count"] == 1


def test_request_with_retry_honors_retry_after():

    responses = iter([httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200)])

    client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(lambda r: next(responses)))

    sleeps: list[float] = []

    response = request_with_retry(client, "GET", "/x", sleep=sleeps.append)

    assert response.status_code == 200
    assert sleeps == [7.0]


def test_request_with_retry_backoff_is_exponential():

    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(503)

    client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))

    sleeps: list[float] = []

    response = request_with_retry(client, "GET", "/x", max_attempts=4, backoff_seconds=1, sleep=sleeps.append)

    assert response.status_code == 503
    assert attempts["count"] == 4
    # jitter: entre 50% y 100% de 1, 2, 4
    assert 0.5 <= sleeps[0] <= 1
    assert 1 <= sleeps[1] <= 2
    assert 2 <= sleeps[2] <= 4


def test_429_pauses_shared_gate_for_all_workers():

    responses = iter([httpx.Response(429, headers={"Retry-After": "5"}), httpx.Response(200)])

    client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(lambda r: next(responses)))

    gate_sleeps: list[float] = []

    gate = RateGate(sleep=lambda s: (gate_sleeps.append(s), setattr(gate, "_until", 0.0)))

    response = request_with_retry(client, "GET", "/x", gate=gate, sleep=lambda s: None)

    assert response.status_code == 200
    # el segundo intento esperó en la puerta compartida (~5 s), no en un sleep local
    assert len(gate_sleeps) == 1 and 4 <= gate_sleeps[0] <= 5
