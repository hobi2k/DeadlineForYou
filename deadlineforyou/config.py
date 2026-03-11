from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DeadlineForYou"
    database_path: Path = Field(default=Path("data/deadlineforyou.db"))
    llm_provider: str = "openai"
    llm_model: str = "gpt-4.1-mini"
    openai_api_key: str | None = None
    local_model_path: Path = Field(default=Path("deadlineforyou/models/saya_rp_4b_v3"))
    local_device_map: str = "auto"
    local_max_new_tokens: int = 220
    local_temperature: float = 0.7
    telegram_bot_token: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="DFY_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """get_settings

    Returns:
        Settings: 환경 변수와 기본값이 합쳐진 설정 객체.
    """
    # 데이터 디렉터리를 먼저 보장해 두면 이후 로직은 경로 존재 여부를 다시 확인할 필요가 없다.
    settings = Settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
