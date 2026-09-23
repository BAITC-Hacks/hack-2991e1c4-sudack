from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    nvidia_api_key: str = ""
    nvidia_model: str = "meta/llama-3.1-8b-instruct"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    llm_model: str | None = None
    llm_timeout: float = 8.0
