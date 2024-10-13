# Pydantic Settings Model
from pydantic_settings import BaseSettings
from pydantic import Field, ValidationError
import pyaudio
from loguru import logger
from functools import lru_cache


class Settings(BaseSettings):
    chunk_size: int = Field(default=1024)
    sample_rate: int = Field(default=24000)
    audio_format: int = Field(default=pyaudio.paInt16)
    openai_api_key: str
    websocket_url: str = Field(
        default="wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01",
    )
    mic_reengage_delay_ms: int = Field(default=500)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    try:
        settings = Settings()  # type: ignore
        return settings
    except ValidationError as e:
        logger.error(f"Configuration validation error: {e}")
        raise
