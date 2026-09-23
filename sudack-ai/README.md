# Sudack AI

Backend-only FastAPI foundation for text generation through OpenAI or NVIDIA. The service selects a provider strategy at runtime and keeps HTTP handling separate from provider transport.

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```powershell
uv sync
Copy-Item .env.example .env
```

Set `OPENAI_API_KEY` and/or `NVIDIA_API_KEY` in `.env`. Choose `DEFAULT_PROVIDER=openai` or `DEFAULT_PROVIDER=nvidia`. No live key is needed for tests or the health endpoint. A generation request to a provider without a key returns HTTP 503.

```powershell
uv run uvicorn main:app --reload
uv run pytest
```

## API

The full request and response contract, examples, and error codes are in [docs/api.md](docs/api.md). Repository agents must keep that file current when endpoint behavior changes; see [AGENTS.md](AGENTS.md).

`GET /health` returns `{"status":"ok"}`. `POST /v1/generate` accepts:

```json
{"prompt":"Write a short greeting", "provider":"nvidia"}
```

The `provider` field is optional and uses `DEFAULT_PROVIDER` when omitted. A successful response contains `provider` and `text`. The API also exposes generated OpenAPI documentation at `/docs`.

## Structure

- `app/api.py`: HTTP contract and application assembly
- `app/config.py`: environment configuration
- `app/generation.py`: generation interface, strategy, and selection service
- `tests/`: unit and HTTP tests using fakes and an in-memory HTTP transport

Add a new provider by implementing `GenerationStrategy` and registering it in application assembly. Tests use injected strategies and never call a live provider.
