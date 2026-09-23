from typing import Protocol

import httpx


class ProviderNotConfigured(Exception):
    pass


class UnknownProvider(Exception):
    pass


class UpstreamProviderError(Exception):
    pass


class GenerationStrategy(Protocol):
    name: str

    async def generate(self, prompt: str) -> str: ...


class ChatCompletionsStrategy:
    """A configured strategy for an OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        name: str,
        api_key: str,
        model: str,
        base_url: str,
        client: httpx.AsyncClient,
    ) -> None:
        self.name = name
        self._api_key = api_key
        self._model = model
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._client = client

    async def generate(self, prompt: str) -> str:
        if not self._api_key.strip() or not self._model.strip():
            raise ProviderNotConfigured(self.name)

        try:
            response = await self._client.post(
                self._url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "messages": [{"role": "user", "content": prompt}]},
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content:
                raise ValueError("Empty response")
            return content
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise UpstreamProviderError(self.name) from exc


class GenerationService:
    def __init__(
        self,
        strategies: dict[str, GenerationStrategy],
        default_provider: str = "openai",
    ) -> None:
        self._strategies = strategies
        self._default_provider = default_provider

    async def generate(self, prompt: str, provider: str | None = None) -> tuple[str, str]:
        selected = provider or self._default_provider
        strategy = self._strategies.get(selected)
        if strategy is None:
            raise UnknownProvider(selected)
        return selected, await strategy.generate(prompt)
