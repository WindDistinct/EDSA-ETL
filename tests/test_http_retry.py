from __future__ import annotations

import httpx
import pytest

from infrastructure.http_retry import request_with_retry


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
