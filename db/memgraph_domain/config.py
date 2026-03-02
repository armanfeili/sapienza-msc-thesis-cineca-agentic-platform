# db/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MG_HOST: str = "memgraph"
    MG_PORT: int = 7687
    MG_USER: str = ""
    MG_PASSWORD: str = ""

    # Defaults used by db/populate.py
    NUM_USERS: int = 200
    NUM_INSTITUTIONS: int = 50
    MAX_TASKS_PER_USER: int = 10
    MAX_INPUT_FILES: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
