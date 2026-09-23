import asyncio

import httpx
import pytest

from app.generation import (
    ChatCompletionsStrategy,
    GenerationService,
    ProviderNotConfigured,
    UpstreamProviderError,
)


def test_strategy_sends_bearer_token_and_reads_reply() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.test/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer secret"
        assert request.read().decode() == '{"model":"test-model","messages":[{"role":"user","content":"hello"}]}'
        return httpx.Response(200, json={"choices": [{"message": {"content": "world"}}]})

    async def run() -> str:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            strategy = ChatCompletionsStrategy("openai", "secret", "test-model", "https://example.test/v1", client)
            return await strategy.generate("hello")

    assert asyncio.run(run()) == "world"


def test_missing_key_does_not_call_upstream() -> None:
    async def run() -> None:
        async with httpx.AsyncClient() as client:
            strategy = ChatCompletionsStrategy("nvidia", "", "model", "https://example.test/v1", client)
            with pytest.raises(ProviderNotConfigured):
                await strategy.generate("hello")

    asyncio.run(run())


def test_upstream_error_is_normalized() -> None:
    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(429))) as client:
            strategy = ChatCompletionsStrategy("nvidia", "secret", "model", "https://example.test/v1", client)
            with pytest.raises(UpstreamProviderError):
                await strategy.generate("hello")

    asyncio.run(run())


def test_service_defaults_to_configured_provider() -> None:
    class FakeStrategy:
        name = "nvidia"

        async def generate(self, prompt: str) -> str:
            return prompt.upper()

    service = GenerationService({"nvidia": FakeStrategy()}, default_provider="nvidia")
    assert asyncio.run(service.generate("hello")) == ("nvidia", "HELLO")
