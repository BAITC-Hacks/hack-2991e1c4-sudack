from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.config import Settings
from app.explain import FailoverExplanationStrategy, SDKExplanationStrategy
from app.generation import (
    ChatCompletionsStrategy,
    GenerationService,
    ProviderNotConfigured,
    UnknownProvider,
    UpstreamProviderError,
)
from app.models import BatchRequest, BatchResponse, RecommendRequest, RecommendResponse
from app.recommendation import RecommendationService


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    provider: str | None = None


class GenerateResponse(BaseModel):
    provider: str
    text: str


def create_app(
    service: GenerationService | None = None,
    recommendation_service: RecommendationService | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = Settings()
        async with httpx.AsyncClient(timeout=30.0) as client:
            app.state.generation_service = service or GenerationService(
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
            llm_clients: list[AsyncOpenAI] = []
            strategies = []
            if settings.openai_api_key.strip():
                openai_client = AsyncOpenAI(
                    api_key=settings.openai_api_key,
                    base_url=settings.openai_base_url,
                    timeout=settings.llm_timeout,
                    max_retries=0,
                )
                llm_clients.append(openai_client)
                strategies.append(SDKExplanationStrategy(
                    openai_client, settings.llm_model or settings.openai_model, structured=True
                ))
            if settings.nvidia_api_key.strip():
                nvidia_client = AsyncOpenAI(
                    api_key=settings.nvidia_api_key,
                    base_url=settings.nvidia_base_url,
                    timeout=settings.llm_timeout,
                    max_retries=0,
                )
                llm_clients.append(nvidia_client)
                strategies.append(SDKExplanationStrategy(
                    nvidia_client, settings.nvidia_model, structured=False
                ))
            app.state.recommendation_service = recommendation_service or RecommendationService(
                explainer=FailoverExplanationStrategy(strategies) if strategies else None,
                timeout=settings.llm_timeout,
            )
            try:
                yield
            finally:
                for llm_client in llm_clients:
                    await llm_client.close()

    app = FastAPI(title="Sudack AI", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/recommend", response_model=RecommendResponse)
    async def recommend(body: RecommendRequest, request: Request) -> RecommendResponse:
        return await request.app.state.recommendation_service.recommend(body)

    @app.post("/score/batch", response_model=BatchResponse)
    async def score_batch(body: BatchRequest, request: Request) -> BatchResponse:
        return request.app.state.recommendation_service.score_batch(body)

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
