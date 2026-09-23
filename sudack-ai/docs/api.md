# HTTP API contract

Run the service from the repository root with `uv run uvicorn main:app --reload`. The examples below use `http://127.0.0.1:8000`. FastAPI also serves an interactive OpenAPI page at `/docs` and the schema at `/openapi.json`.

The API currently has no caller authentication. Generation requires a configured key for the selected upstream provider. Put `OPENAI_API_KEY` and/or `NVIDIA_API_KEY` in the local `.env` file. `DEFAULT_PROVIDER` determines the provider when a request omits it; its default is `openai`.

## `GET /health`

Checks that the API process can serve requests. No request body, parameters, or special headers are required. It does not test connectivity to AI providers.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Success: HTTP `200`, `application/json`:

```json
{"status":"ok"}
```

## `POST /v1/generate`

Generates a text reply from the selected AI provider. Send `Content-Type: application/json`.

| JSON field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `prompt` | string | Yes | Text sent as the user message. It must contain at least one non-whitespace character. |
| `provider` | string or `null` | No | `openai` or `nvidia`. Omit it or send `null` to use `DEFAULT_PROVIDER`. |

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/v1/generate -Method Post -ContentType 'application/json' -Body '{"prompt":"Write a short greeting","provider":"nvidia"}'
```

Success: HTTP `200`, `application/json`:

```json
{"provider":"nvidia","text":"Hello!"}
```

`provider` is the strategy that handled the request. `text` is the provider's generated reply; its wording varies on each call.

| Status | Response example | When it occurs |
| --- | --- | --- |
| `400` | `{"detail":"Unknown provider 'other'"}` | `provider` is not registered. |
| `422` | `{"detail":"Prompt must not be blank"}` | `prompt` contains only whitespace. Missing fields, wrong JSON types, or malformed JSON also return `422` with FastAPI's validation `detail` array. |
| `502` | `{"detail":"AI provider request failed"}` | The selected provider is unavailable, returns an unsuccessful response, or returns an unusable reply. |
| `503` | `{"detail":"Provider 'openai' is not configured"}` | The selected provider's API key or model is empty. |

The service does not currently retry a failed upstream request. A `502` does not include the upstream response body or credentials.
