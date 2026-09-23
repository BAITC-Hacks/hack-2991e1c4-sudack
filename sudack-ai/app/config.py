from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    nvidia_api_key: str = ""
    nvidia_model: str = "nvidia/llama-3.1-nemotron-70b-instruct"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    llm_model: str | None = None
    llm_timeout: float = 8.0
    # Ordered failover chain. A provider without a key is skipped; an unknown name is ignored.
    llm_providers: str = "openai,nvidia"

    def provider_order(self) -> list[str]:
        return [name.strip() for name in self.llm_providers.split(",") if name.strip()]
