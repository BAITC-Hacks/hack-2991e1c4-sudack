from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from sudack_ai.config import Settings
from sudack_ai.generation import (
    ChatCompletionsStrategy,
    GenerationService,
    ProviderNotConfigured,
    UnknownProvider,
    UpstreamProviderError,
)


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    provider: str | None = None


class GenerateResponse(BaseModel):
    provider: str
    text: str


def create_app(service: GenerationService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if service is not None:
            app.state.generation_service = service
            yield
            return

        settings = Settings()
        async with httpx.AsyncClient(timeout=30.0) as client:
            app.state.generation_service = GenerationService(
                {
                    "openai": ChatCompletionsStrategy(
                        "openai", settings.openai_api_key, settings.openai_model,
                        settings.openai_base_url, client,
                    ),
                    "nvidia": ChatCompletionsStrategy(
                        "nvidia", settings.nvidia_api_key, settings.nvidia_model,
                        settings.nvidia_base_url, client,
                    ),
                },
                default_provider=settings.default_provider,
            )
            yield

    app = FastAPI(title="Sudack AI", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/generate", response_model=GenerateResponse)
    async def generate(body: GenerateRequest, request: Request) -> GenerateResponse:
        if not body.prompt.strip():
            raise HTTPException(status_code=422, detail="Prompt must not be blank")
        try:
            provider, text = await request.app.state.generation_service.generate(
                body.prompt, body.provider
            )
        except UnknownProvider as exc:
            raise HTTPException(status_code=400, detail=f"Unknown provider '{exc.args[0]}'") from exc
        except ProviderNotConfigured as exc:
            raise HTTPException(
                status_code=503, detail=f"Provider '{exc.args[0]}' is not configured"
            ) from exc
        except UpstreamProviderError as exc:
            raise HTTPException(status_code=502, detail="AI provider request failed") from exc
        return GenerateResponse(provider=provider, text=text)

    return app
