from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    db_host: str = Field("127.0.0.1", validation_alias=AliasChoices("DB_HOST", "MYSQL_HOST"))
    db_port: int = Field(3306, validation_alias=AliasChoices("DB_PORT", "MYSQL_PORT"))
    db_user: str = Field("root", validation_alias=AliasChoices("DB_USER", "MYSQL_USER"))
    db_password: str = Field("12345678", validation_alias=AliasChoices("DB_PASSWORD", "MYSQL_PASSWORD"))
    db_name: str = Field(
        "agentic_merchant_mgmt",
        validation_alias=AliasChoices("DB_NAME", "MYSQL_DATABASE"),
    )
    db_connect_timeout_seconds: int = 10
    db_pool_timeout_seconds: int = 20

    api_host: str = "127.0.0.1"
    api_port: int = 9100
    log_level: str = "INFO"

    heg_flight_backend_url: str = "http://127.0.0.1:9000"
    heg_a2a_endpoint: str = "http://127.0.0.1:9000/a2a/heg_merchant_agent"
    heg_mcp_server_path: str = "/Users/ouyang/AI-coding/payment/heg_flight_mock/mcp/server.py"
    adapter_base_url: str = "http://127.0.0.1:8200"

    @property
    def database_url(self) -> str:
        user = quote_plus(self.db_user)
        password = quote_plus(self.db_password)
        return f"mysql+aiomysql://{user}:{password}@{self.db_host}:{self.db_port}/{self.db_name}"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
