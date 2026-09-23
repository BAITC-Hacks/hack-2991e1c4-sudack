from fastapi.testclient import TestClient

from sudack_ai.api import create_app
from sudack_ai.generation import GenerationService, ProviderNotConfigured, UpstreamProviderError


class FakeStrategy:
    name = "openai"

    async def generate(self, prompt: str) -> str:
        return f"answer: {prompt}"


def test_health() -> None:
    with TestClient(create_app(GenerationService({"openai": FakeStrategy()}))) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_generate_uses_selected_strategy() -> None:
    with TestClient(create_app(GenerationService({"openai": FakeStrategy()}))) as client:
        response = client.post("/v1/generate", json={"prompt": "hello", "provider": "openai"})
    assert response.status_code == 200
    assert response.json() == {"provider": "openai", "text": "answer: hello"}


def test_invalid_prompt_is_rejected() -> None:
    with TestClient(create_app(GenerationService({"openai": FakeStrategy()}))) as client:
        response = client.post("/v1/generate", json={"prompt": "   "})
    assert response.status_code == 422


def test_unknown_provider_is_rejected() -> None:
    with TestClient(create_app(GenerationService({"openai": FakeStrategy()}))) as client:
        response = client.post("/v1/generate", json={"prompt": "hi", "provider": "other"})
    assert response.status_code == 400


def test_explicit_provider_selects_its_strategy() -> None:
    class NvidiaStrategy(FakeStrategy):
        name = "nvidia"

        async def generate(self, prompt: str) -> str:
            return f"nvidia: {prompt}"

    service = GenerationService({"openai": FakeStrategy(), "nvidia": NvidiaStrategy()})
    with TestClient(create_app(service)) as client:
        response = client.post("/v1/generate", json={"prompt": "hi", "provider": "nvidia"})
    assert response.json() == {"provider": "nvidia", "text": "nvidia: hi"}


def test_missing_credentials_are_not_exposed() -> None:
    class MissingKeyStrategy(FakeStrategy):
        async def generate(self, prompt: str) -> str:
            raise ProviderNotConfigured("openai")

    with TestClient(create_app(GenerationService({"openai": MissingKeyStrategy()}))) as client:
        response = client.post("/v1/generate", json={"prompt": "hi"})
    assert response.status_code == 503
    assert response.json() == {"detail": "Provider 'openai' is not configured"}


def test_upstream_failure_returns_gateway_error() -> None:
    class FailingStrategy(FakeStrategy):
        async def generate(self, prompt: str) -> str:
            raise UpstreamProviderError("openai")

    with TestClient(create_app(GenerationService({"openai": FailingStrategy()}))) as client:
        response = client.post("/v1/generate", json={"prompt": "hi"})
    assert response.status_code == 502
    assert response.json() == {"detail": "AI provider request failed"}
