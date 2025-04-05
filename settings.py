import urllib.parse
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from utility.logging_config import setup_logging

# Setup logging with environment variables
logger = setup_logging()

SUPREME_COURT_CASE_COLLECTION = "supreme_court_cases"


class Settings(BaseSettings):
    openai_api_key: str
    db_addr: str
    db_user: str
    db_pass: str
    qdrant_filepath: str
    port: int = 8080
    log_level: str = "INFO"
    json_logs: bool = False

    # Security settings
    api_key: str = ""
    allowed_hosts: str = "localhost,127.0.0.1"
    cors_origins: str = "*"
    rate_limit: int = 60
    environment: str = "development"

    model_config = SettingsConfigDict(env_file=".env", extra="allow")


@lru_cache
def get_settings():
    settings = Settings()
    settings.db_user = urllib.parse.quote(settings.db_user)
    settings.db_pass = urllib.parse.quote(settings.db_pass)

    # Configure logging based on settings
    setup_logging(settings.log_level, settings.json_logs)

    return settings
