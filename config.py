from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


# Cargar automáticamente el archivo .env ubicado en la raíz del proyecto
load_dotenv(Path(__file__).resolve().parent / ".env")


@dataclass(frozen=True)
class Settings:
    fmtrack_base_url: str
    fmtrack_api_key: str
    fmtrack_api_key_inter: str


settings = Settings(
    fmtrack_base_url=os.getenv("FMTRACK_BASE_URL", "").rstrip("/"),
    fmtrack_api_key=os.getenv("FMTRACK_API_KEY", ""),
    fmtrack_api_key_inter=os.getenv("FMTRACK_API_KEY_INTER", ""),
)