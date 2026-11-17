"""Chequeo manual contra la API real de FM Track: cuántos vehículos ve cada key y
el detalle de una placa. No lo ejecuta pytest.

Uso:
    python tools/manual_check_objects.py [PLACA]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from infrastructure.fmtrack_client import FMTrackClient  # noqa: E402
from logging_config import configure_logging  # noqa: E402

configure_logging()

client = FMTrackClient()

try:
    objects = client.get_objects()
finally:
    client.close()

print(f"{len(objects)} vehículos")

placa = sys.argv[1] if len(sys.argv) > 1 else "A0P736"
print(objects.get(placa, f"{placa} no está en el catálogo"))
