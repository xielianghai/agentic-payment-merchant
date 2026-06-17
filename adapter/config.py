from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    api_host: str = "127.0.0.1"
    api_port: int = 8200
    log_level: str = "INFO"

    merchant_mgmt_api: str = "http://127.0.0.1:9100"
    heg_flight_backend_url: str = "http://127.0.0.1:9000"
    heg_mcp_server_path: str = "/Users/ouyang/AI-coding/payment/heg_flight_mock/mcp/server.py"
    temp_db_dir: str = ".temp-db"

    @property
    def adapter_base_url(self) -> str:
        return f"http://{self.api_host}:{self.api_port}"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def demo_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
