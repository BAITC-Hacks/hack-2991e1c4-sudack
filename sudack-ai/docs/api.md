# HTTP API contract

Run the service from the repository root with `uv run uvicorn main:app --reload --port 8001`. The examples below use `http://127.0.0.1:8001`. FastAPI also serves an interactive OpenAPI page at `/docs` and the schema at `/openapi.json`.

The API currently has no caller authentication; Go handles access control. Recommendations and batch scoring need no provider credentials. Recommendation responses use a template when configured LLM providers fail or time out. The legacy generic generation endpoint requires a configured upstream key. Put `OPENAI_API_KEY` and/or `NVIDIA_API_KEY` in the local `.env` file.

## `GET /health`

Checks that the API process can serve requests. No request body, parameters, or special headers are required. It does not test connectivity to AI providers.

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
```

Success: HTTP `200`, `application/json`:

```json
{"status":"ok"}
```

## `POST /recommend`

Scores development activities for one employee and returns up to three explanations. Send `Content-Type: application/json`. All context is in the body; there are no query or path parameters. The response may contain zero recommendations when nothing is eligible.

| JSON field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `employee` | object | Yes | `employee_id`, `role`, `grade`, and `skills` (`skill_id → level 0–5`); `tenure_months` and `preferred_language` are optional. Extra starter-kit employee fields are accepted. |
| `next_grade` | string | Yes | Target grade label supplied by Go. |
| `next_grade_requirements` | object | Yes | Target `skill_id → required level 0–5`. |
| `critical_skills` | string array | No | IDs from the target role profile; defaults to `[]`. |
| `skills_meta` | object | No | `skill_id → {name, category?}`; defaults to `{}`. Used for readable explanations. |
| `history` | object array | No | Entries need `event_id` and `status`; `date` is optional. Defaults to `[]`. |
| `events` | object array | Yes | Full candidate and historical event catalog. See accepted event shapes below. |
| `lang` | `ru`, `kk`, or `en` | No | Defaults to `employee.preferred_language` when present, otherwise `ru`. |

An event requires `event_id`, `title`, and `type`. The compact shape uses `audience: {roles, grades}` and `skills: {skill_id: {gain, max_level}}`. The starter-kit shape uses `target_roles`, `target_grades`, and `develops_skills: [{skill_id, gain, max_level}]`. Both accept optional `mandatory` (default `false`), `prerequisites` (`skill_id → level`), and `recurring` (default `false`). `EV_036` is recognized as recurring from the supplied kit. Omitted audience lists allow all roles or grades.

```powershell
$body = Get-Content docs/examples/recommend-request.json -Raw
Invoke-RestMethod -Uri http://127.0.0.1:8001/recommend -Method Post -ContentType 'application/json' -Body $body
```

Success: HTTP `200`, `application/json`. Example with the template fallback:

```json
{
  "recommendations": [{
    "event_id": "EV07", "title": "System Design Workshop", "score": 0.9234,
    "reason": "System Design is 2 against the 4 needed for Senior; this activity raises it to 3. You have no history of similar activities.",
    "factors": [
      {"type": "grade_requirement", "text": "System Design is required for Senior"},
      {"type": "skill_gap", "skill": "SK_SYSTEM_DESIGN", "current": 2, "required": 4},
      {"type": "history", "text": "0 of 0 similar activities completed; 0 missed", "completed": 0, "total": 0, "missed": 0},
      {"type": "effective_gain", "skill": "SK_SYSTEM_DESIGN", "from": 2, "to": 3}
    ],
    "calculation": {"gap_closed": 1.5, "engagement": 0.5, "formula": "1.5000 * 0.5000^0.7"}
  }],
  "readiness": {"current": 0.5, "after_top": 0.75},
  "source": "fallback"
}
```

`source` is `llm` only when a validated LLM selection is returned; otherwise it is `fallback`. The service gives the LLM the top five deterministic candidates, validates its 1–3 selected IDs and nonempty reasons, and falls back on invalid output or a timeout. The LLM attempt has an eight-second default budget across configured providers. `score` is a raw ranking value, not a probability. `readiness.after_top` applies the first recommendation's gains only. Responses are cached per process using the full request context.

Errors: HTTP `422` with FastAPI's validation `detail` array for malformed JSON, missing fields, invalid skill levels, or unsupported `lang`. No upstream failure status is returned by this endpoint because LLM failures use the fallback.

## `POST /score/batch`

Scores up to many employees without an LLM call. Send `Content-Type: application/json` and `{"items": [<the same object as /recommend>]}`. Each item may omit `lang`. The service does not fetch employee data; Go supplies every item. The response keeps input order.

```powershell
$item = Get-Content docs/examples/recommend-request.json -Raw | ConvertFrom-Json
$batchBody = @{ items = @($item) } | ConvertTo-Json -Depth 12
Invoke-RestMethod -Uri http://127.0.0.1:8001/score/batch -Method Post -ContentType 'application/json' -Body $batchBody
```

Success: HTTP `200`, `application/json`:

```json
{"results":[{"employee_id":"E0028","top":[{"event_id":"EV07","score":0.9234}],"readiness":0.5}]}
```

`top` contains up to three event IDs and raw scores. It is empty when no event is eligible. `readiness` is the employee's current readiness for the supplied target requirements. Errors: HTTP `422` with FastAPI's validation `detail` array when `items` is missing or an item is invalid. The supplied 200-person starter kit completed in about 0.21 seconds in a local in-process HTTP benchmark; production timing depends on hardware and request size.

## `POST /v1/generate`

Legacy generic text generation from the selected AI provider. Send `Content-Type: application/json`. `DEFAULT_PROVIDER` chooses the provider when the request omits it; its default is `openai`.

| JSON field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `prompt` | string | Yes | Text sent as the user message. It must contain at least one non-whitespace character. |
| `provider` | string or `null` | No | `openai` or `nvidia`. Omit it or send `null` to use `DEFAULT_PROVIDER`. |

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8001/v1/generate -Method Post -ContentType 'application/json' -Body '{"prompt":"Write a short greeting","provider":"nvidia"}'
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
