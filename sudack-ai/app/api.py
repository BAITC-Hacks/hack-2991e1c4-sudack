from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI

from app.config import Settings
from app.explain import FailoverExplanationStrategy, SDKExplanationStrategy
from app.insights import event_impact, simulate
from app.models import (
    BatchRequest, BatchResponse, ImpactRequest, ImpactResponse, RecommendRequest,
    RecommendResponse, SimulateResponse,
)
from app.recommendation import RecommendationService


def configured_providers(settings: Settings) -> list[dict]:
    """Ordered LLM provider chain from LLM_PROVIDERS; providers without a key are skipped.
    Every provider speaks the OpenAI chat-completions protocol, so adding one is a base_url,
    a key and a model; `structured_output` says whether strict JSON schema mode is available."""
    catalog = {
        "openai": {
            "api_key": settings.openai_api_key, "base_url": settings.openai_base_url,
            "model": settings.llm_model or settings.openai_model, "structured_output": True,
        },
        "nvidia": {
            "api_key": settings.nvidia_api_key, "base_url": settings.nvidia_base_url,
            "model": settings.nvidia_model, "structured_output": False,
        },
    }
    chain = []
    for name in settings.provider_order():
        entry = catalog.get(name)
        if entry and entry["api_key"].strip():
            chain.append({"name": name, **entry})
    return chain


def create_app(recommendation_service: RecommendationService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = Settings()
        providers = configured_providers(settings)
        # One deadline (llm_timeout) for the whole chain: a fast failure hands the remaining time
        # to the next provider, a non-last provider is capped at 75% of what is left.
        llm_clients: list[AsyncOpenAI] = []
        strategies = []
        for entry in providers:
            client = AsyncOpenAI(
                api_key=entry["api_key"], base_url=entry["base_url"], timeout=settings.llm_timeout, max_retries=0,
            )
            llm_clients.append(client)
            strategies.append(SDKExplanationStrategy(
                client, entry["model"], structured=entry["structured_output"], name=entry["name"],
            ))
        app.state.providers = [
            {"name": e["name"], "model": e["model"], "base_url": e["base_url"],
             "structured_output": e["structured_output"]}
            for e in providers
        ]
        app.state.llm_budget_seconds = settings.llm_timeout
        app.state.recommendation_service = recommendation_service or RecommendationService(
            explainer=FailoverExplanationStrategy(strategies, budget=settings.llm_timeout) if strategies else None,
            timeout=settings.llm_timeout,
        )
        try:
            yield
        finally:
            for llm_client in llm_clients:
                await llm_client.close()

    app = FastAPI(title="Sudack AI", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=Settings().cors_origin_list(),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/providers")
    async def providers(request: Request) -> dict:
        chain = request.app.state.providers
        return {
            "providers": chain,
            "order": [item["name"] for item in chain],
            "budget_seconds": request.app.state.llm_budget_seconds,
            "primary_share": 0.75,
            "explanations": "llm_with_template_fallback" if chain else "template",
        }

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
