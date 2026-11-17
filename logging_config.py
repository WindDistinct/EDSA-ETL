import logging
import re

# FM Track recibe la api_key como query param: cualquier URL que llegue a un
# log la expondría.
_SECRET_RE = re.compile(r"(api_key=)[^&\s'\"]+", re.IGNORECASE)


class RedactSecretsFilter(logging.Filter):
    """
    Reemplaza api_key=... por api_key=*** en el mensaje ya formateado.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = _SECRET_RE.sub(r"\1***", message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    for handler in logging.getLogger().handlers:
        handler.addFilter(RedactSecretsFilter())

    # httpx registra cada URL completa (con la api_key) a nivel INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
