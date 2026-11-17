from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

MAX_RETRY_AFTER_SECONDS = 60.0


class RateGate:
    """
    Pausa compartida entre hilos que usan el mismo cliente HTTP. Cuando una
    respuesta llega con 429, todos los workers esperan antes de su próxima
    llamada en vez de seguir golpeando la API cada uno por su cuenta.
    """

    def __init__(self, sleep: Callable[[float], None] = time.sleep) -> None:
        self._lock = threading.Lock()
        self._until = 0.0
        self._sleep = sleep

    def pause(self, seconds: float) -> None:
        with self._lock:
            self._until = max(self._until, time.monotonic() + seconds)

    def wait(self) -> None:
        while True:
            with self._lock:
                delay = self._until - time.monotonic()
            if delay <= 0:
                return
            self._sleep(delay)


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """
    Lee la cabecera Retry-After (segundos o fecha HTTP). None si no viene o
    no se entiende.
    """

    value = response.headers.get("Retry-After")

    if not value:
        return None

    try:
        seconds = float(value)
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        seconds = (when - datetime.now(timezone.utc)).total_seconds()

    return min(max(seconds, 0.0), MAX_RETRY_AFTER_SECONDS)


def _backoff(attempt: int, base: float, maximum: float) -> float:
    """
    Backoff exponencial con jitter (50%-100% del valor): 1, 2, 4, 8... s.
    El jitter evita que los workers reintenten todos en el mismo instante.
    """

    delay = min(maximum, base * 2 ** (attempt - 1))

    return delay * random.uniform(0.5, 1.0)


def request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    max_attempts: int = 5,
    backoff_seconds: float = 1.0,
    max_backoff_seconds: float = 30.0,
    gate: RateGate | None = None,
    sleep: Callable[[float], None] = time.sleep,
    **kwargs,
) -> httpx.Response:
    """
    Reintenta una llamada HTTP ante errores transitorios (timeouts, conexión
    caída, 429/5xx) con backoff exponencial. Respeta Retry-After y, si se
    pasa un RateGate, comparte la pausa del 429 con los demás hilos. Errores
    4xx (salvo 429) no se reintentan porque no son transitorios.
    """

    for attempt in range(1, max_attempts + 1):

        if gate is not None:
            gate.wait()

        try:
            response = client.request(method, url, **kwargs)

        except httpx.TransportError as ex:

            if attempt == max_attempts:
                raise

            delay = _backoff(attempt, backoff_seconds, max_backoff_seconds)

            logger.warning(
                "[RETRY] %s %s -> %s (intento %d/%d, espera %.1fs)",
                method, url, type(ex).__name__, attempt, max_attempts, delay,
            )

            sleep(delay)

            continue

        if response.status_code not in RETRYABLE_STATUS_CODES or attempt == max_attempts:
            return response

        delay = _retry_after_seconds(response)

        if delay is None:
            delay = _backoff(attempt, backoff_seconds, max_backoff_seconds)

        logger.warning(
            "[RETRY] %s %s -> HTTP %d (intento %d/%d, espera %.1fs)",
            method, url, response.status_code, attempt, max_attempts, delay,
        )

        if response.status_code == 429 and gate is not None:
            gate.pause(delay)
            continue

        sleep(delay)

    raise AssertionError("unreachable")
