# Sudack AI

Stateless FastAPI service for employee development recommendations (Career Quest, HackAlem AI). It scores activities deterministically, asks an LLM to select and explain up to three, and returns a template explanation when no LLM is available.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```powershell
uv sync
Copy-Item .env.example .env
```

Set `OPENAI_API_KEY` and/or `NVIDIA_API_KEY` in `.env`. Recommendation uses OpenAI first, then NVIDIA if configured, then a deterministic template. `LLM_MODEL` overrides the OpenAI model for recommendations; set it to the strongest model the hackathon key allows. `LLM_TIMEOUT` defaults to eight seconds for the complete LLM attempt, shared equally between configured providers. No key is needed for scoring, tests, or health checks.

```powershell
uv run uvicorn main:app --reload --port 8001
uv run pytest
```

## API

The full request and response contract, examples, and error codes are in [docs/api.md](docs/api.md). Repository agents must keep that file current when endpoint behavior changes; see [AGENTS.md](AGENTS.md).

`POST /recommend` accepts one employee, next-grade requirements, history, and an activity catalog. It returns up to three recommendations with scores, factual factors, a calculation, readiness, and `source` (`llm` or `fallback`). `POST /score/batch` scores many employees without any LLM call. Go supplies all context; this service has no database or authorization rules. See [docs/data-integration.md](docs/data-integration.md) for the supplied Career Quest dataset.

`GET /health` returns `{"status":"ok"}`. The API also exposes generated OpenAPI documentation at `/docs`.

## Structure

- `app/api.py`: HTTP contract and application assembly
- `app/config.py`: environment configuration
- `app/models.py`: request and response models, including starter-kit event adaptation
- `app/scoring.py`: pure scoring and eligibility logic
- `app/explain.py`: OpenAI SDK provider strategies with failover, and the multilingual template fallback
- `app/recommendation.py`: recommendation orchestration and LLM output validation
- `app/cache.py`: bounded, process-local response cache for validated LLM answers
- `scripts/audit_verdict.py`: one-call live audit of a starter-kit employee
- `tests/`: unit, trap-profile, and HTTP tests using fakes; the dataset test runs all 200 kit employees

Add a new provider by implementing `ExplanationStrategy` and registering it in `create_app`. Tests use injected strategies and never call a live provider.

## Scoring example

If an employee has System Design level 2 and the next grade requires level 4, a workshop that raises it to 3 closes one level of the gap. Its weighted gain is `1.5 × 1 = 1.5`; if System Design is in the target profile's `critical_skills` the weight is 2.5 instead, and growth outside the requirements weighs 0.3. With no history on these skills, engagement is `(0 + 1) / (0 + 2) = 0.5`, so its raw score is `1.5 × 0.5^0.7 ≈ 0.9234`.

Engagement is a Laplace-smoothed completion rate. Past activities that develop any of the same skills count fully; activities of the same type but on unrelated skills count at 0.3; entries dated more than a year before the employee's latest history entry count at 0.6. So three missed public-speaking sessions strongly lower the public-speaking club's engagement, only slightly lower another workshop's, and leave a course untouched. Events with `in_progress` or `overdue` history are not recommended again; completed events are excluded unless recurring.

Readiness measures how much of the weighted next-grade skill requirements is met; `after_top` applies only the first recommendation's gains. The score is a ranking value, not a probability. Results with repeated primary skills receive a 0.8 ordering penalty, while the reported score and calculation remain the raw values.

To audit one starter-kit employee with a single paid OpenAI call, run `uv run python scripts/audit_verdict.py --live E0002`. The script disables SDK retries and NVIDIA failover. Its output shows the top scored candidates and the accepted verdict; run it only when an API call is intended.

The [two-case verdict audit](docs/VERDICT_AUDIT.md) records the observed live outputs and the resulting validation and explanation fixes.
