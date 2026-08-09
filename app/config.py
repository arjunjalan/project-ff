from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    espn_league_id: int
    espn_season_year: int
    espn_s2: str
    espn_swid: str
    data_dir: str = "data"
    cors_origins: str = "http://localhost:8000"
    openrouter_api_key: str
    llm_model: str = "openrouter/free"


settings = Settings()
