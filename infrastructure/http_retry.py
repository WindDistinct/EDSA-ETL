from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    max_attempts: int = 3,
    backoff_seconds: float = 1.0,
    **kwargs,
) -> httpx.Response:
    """
    Reintenta una llamada HTTP ante errores transitorios (timeouts, conexión
    caída, 429/5xx) con backoff lineal. Errores 4xx (salvo 429) no se
    reintentan porque no son transitorios.
    """

    last_exception: Exception | None = None

    for attempt in range(1, max_attempts + 1):

        try:
            response = client.request(method, url, **kwargs)

        except httpx.TransportError as ex:

            last_exception = ex

            if attempt == max_attempts:
                raise

            logger.warning(
                "[RETRY] %s %s -> %s (intento %d/%d)",
                method, url, ex, attempt, max_attempts,
            )

            time.sleep(backoff_seconds * attempt)

            continue

        if response.status_code in RETRYABLE_STATUS_CODES and attempt < max_attempts:

            logger.warning(
                "[RETRY] %s %s -> HTTP %d (intento %d/%d)",
                method, url, response.status_code, attempt, max_attempts,
            )

            time.sleep(backoff_seconds * attempt)

            continue

        return response

    raise last_exception
