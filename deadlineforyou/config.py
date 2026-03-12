from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DeadlineForYou"
    database_path: Path = Field(default=Path("data/deadlineforyou.db"))
    llm_provider: str = "local"
    local_model_path: Path = Field(default=Path("deadlineforyou/models/saya_rp_4b_v3"))
    local_device_map: str = "auto"
    local_max_new_tokens: int = 550
    local_temperature: float = 0.7
    translation_provider: str = "local"
    translation_local_model_path: Path = Field(default=Path("deadlineforyou/models/rosetta_4b"))
    translation_lazy_load: bool = True
    translation_local_max_new_tokens: int = 256
    translation_local_temperature: float = 0.2
    image_provider: str = "local"
    image_local_model_path: Path = Field(default=Path("deadlineforyou/models/sdxl_turbo"))
    image_lazy_load: bool = True
    image_unload_after_generation: bool = True
    image_enable_model_cpu_offload: bool = True
    image_release_translation_before_generation: bool = True
    image_device: str = "cuda"
    image_num_inference_steps: int = 4
    image_guidance_scale: float = 0.0
    image_negative_prompt: str = ""
    image_seed: int = 42
    image_output_dir: Path = Field(default=Path("data/generated_images"))
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
    settings.image_output_dir.mkdir(parents=True, exist_ok=True)
    return settings
