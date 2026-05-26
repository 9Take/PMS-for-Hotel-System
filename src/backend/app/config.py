"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/oms"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    secret_key: str = "dev-secret-key-change-in-production"
    debug: bool = True

    # SlipOK
    slipok_api_url: str = "https://api.slipok.com/api/line/apikey"
    slipok_branch_id: str = ""
    slipok_api_key: str = ""

    # LINE
    line_channel_access_token: str = ""
    line_channel_secret: str = ""

    # Villa Info (for PDFs)
    villa_name: str = "My Pool Villa"
    villa_address: str = ""
    villa_phone: str = ""
    villa_line_id: str = ""
    villa_tax_id: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
