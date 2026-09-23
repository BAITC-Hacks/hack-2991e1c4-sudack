from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from openai import AsyncOpenAI

from app.config import Settings
from app.explain import FailoverExplanationStrategy, SDKExplanationStrategy
from app.insights import event_impact, simulate
from app.models import (
    BatchRequest, BatchResponse, ImpactRequest, ImpactResponse, RecommendRequest,
    RecommendResponse, SimulateResponse,
)
from app.recommendation import RecommendationService


def create_app(recommendation_service: RecommendationService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = Settings()
        providers: list[tuple[str, str, str, bool]] = []
        if settings.openai_api_key.strip():
            providers.append((
                settings.openai_api_key, settings.openai_base_url,
                settings.llm_model or settings.openai_model, True,
            ))
        if settings.nvidia_api_key.strip():
            providers.append((
                settings.nvidia_api_key, settings.nvidia_base_url, settings.nvidia_model, False,
            ))
        # The whole LLM attempt must fit in llm_timeout, so each provider gets an equal slice.
        attempt_timeout = settings.llm_timeout / max(1, len(providers))
        llm_clients: list[AsyncOpenAI] = []
        strategies = []
        for api_key, base_url, model, structured in providers:
            client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=attempt_timeout, max_retries=0)
            llm_clients.append(client)
            strategies.append(SDKExplanationStrategy(client, model, structured=structured))
        app.state.recommendation_service = recommendation_service or RecommendationService(
            explainer=FailoverExplanationStrategy(strategies, attempt_timeout) if strategies else None,
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

    # Plain `def`: pure CPU work runs in FastAPI's threadpool instead of blocking the event loop.
    @app.post("/score/batch", response_model=BatchResponse)
    def score_batch(body: BatchRequest, request: Request) -> BatchResponse:
        return request.app.state.recommendation_service.score_batch(body)

    @app.post("/simulate", response_model=SimulateResponse)
    def simulate_grade(body: RecommendRequest) -> SimulateResponse:
        return SimulateResponse(**simulate(body))

    @app.post("/events/impact", response_model=ImpactResponse)
    def impact(body: ImpactRequest) -> ImpactResponse:
        return ImpactResponse(**event_impact(body.event, body.items))

    return app
