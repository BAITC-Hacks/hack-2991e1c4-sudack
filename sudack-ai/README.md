# Sudack AI

Stateless FastAPI service for employee development recommendations. It scores activities deterministically, asks an LLM to select and explain up to three, and returns a template explanation when no LLM is available. The original generic text generation endpoint remains available.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```powershell
uv sync
Copy-Item .env.example .env
```

Set `OPENAI_API_KEY` and/or `NVIDIA_API_KEY` in `.env`. Recommendation uses OpenAI first, then NVIDIA if configured, then a deterministic template. `LLM_MODEL` overrides the OpenAI model for recommendations; `LLM_TIMEOUT` defaults to eight seconds for the complete LLM attempt. No key is needed for scoring, tests, or health checks. `DEFAULT_PROVIDER` applies to the separate `/v1/generate` endpoint.

```powershell
uv run uvicorn main:app --reload --port 8001
uv run pytest
```

## API

The full request and response contract, examples, and error codes are in [docs/api.md](docs/api.md). Repository agents must keep that file current when endpoint behavior changes; see [AGENTS.md](AGENTS.md).

`POST /recommend` accepts one employee, next-grade requirements, history, and an activity catalog. It returns up to three recommendations with scores, factual factors, a calculation, readiness, and `source` (`llm` or `fallback`). `POST /score/batch` scores many employees without any LLM call. Go supplies all context; this service has no database or authorization rules. See [docs/data-integration.md](docs/data-integration.md) for the supplied Career Quest dataset.

`GET /health` returns `{"status":"ok"}`. `POST /v1/generate` accepts:

```json
{"prompt":"Write a short greeting", "provider":"nvidia"}
```

The `provider` field is optional and uses `DEFAULT_PROVIDER` when omitted. A successful response contains `provider` and `text`. The API also exposes generated OpenAPI documentation at `/docs`.

## Structure

- `app/api.py`: HTTP contract and application assembly
- `app/config.py`: environment configuration
- `app/generation.py`: generation interface, strategy, and selection service
- `app/models.py`: request and response models, including starter-kit event adaptation
- `app/scoring.py`: pure scoring and eligibility logic
- `app/explain.py`: OpenAI SDK provider strategies and multilingual fallback
- `app/recommendation.py`: recommendation orchestration and LLM validation
- `app/cache.py`: bounded, process-local response cache
- `tests/`: unit and HTTP tests using fakes and an in-memory HTTP transport

Add a new provider by implementing `GenerationStrategy` and registering it in application assembly. Tests use injected strategies and never call a live provider.

## Scoring example

If an employee has System Design level 2 and the next grade requires level 4, a workshop that raises it to 3 closes one level of the gap. Its weighted gain is `1.5 × 1 = 1.5`. With no similar history, engagement is `(0 + 1) / (0 + 2) = 0.5`, so its raw score is `1.5 × 0.5^0.7 ≈ 0.9234`. Readiness measures how much of the next-grade skill requirements is met; `after_top` applies only the first recommendation's gains.

The score is a ranking value, not a probability. Results with repeated primary skills receive a 0.8 ordering penalty, while the reported score and calculation remain the raw values.

To audit one starter-kit employee with a single paid OpenAI call, run `uv run python scripts/audit_verdict.py --live E0002`. The script disables SDK retries and NVIDIA failover. Its output shows the top scored candidates and the accepted verdict; run it only when an API call is intended.

The [two-case verdict audit](docs/VERDICT_AUDIT.md) records the observed live outputs and the resulting validation and explanation fixes.
