# HTTP API contract

Run the service from the repository root with `uv run uvicorn main:app --reload --port 8001`. The examples below use `http://127.0.0.1:8001`. FastAPI also serves an interactive OpenAPI page at `/docs` and the schema at `/openapi.json`.

The API currently has no caller authentication; Go handles access control. Recommendations and batch scoring need no provider credentials. Recommendation responses use a template when no LLM provider is configured or every configured provider fails, times out, or returns ungrounded text. Put `OPENAI_API_KEY` and/or `NVIDIA_API_KEY` in the local `.env` file to enable LLM explanations.

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
| `critical_skills` | string array | No | IDs from the target role profile; defaults to `[]`. Gaps in these skills weigh 2.5 instead of 1.5 in scoring and readiness. |
| `skills_meta` | object | No | `skill_id → {name, category?}`; defaults to `{}`. Used for readable explanations. |
| `history` | object array | No | Entries need `event_id` and `status`; `date` (`YYYY-MM-DD` or `YYYY-MM`) is optional and enables recency weighting. Defaults to `[]`. |
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
    "reason": "System Design is 2 against the 4 needed for Senior; this activity raises it to 3. You have no history of activities on these skills.",
    "factors": [
      {"type": "grade_requirement", "text": "System Design is required for Senior", "critical": false},
      {"type": "skill_gap", "skill": "SK_SYSTEM_DESIGN", "current": 2, "required": 4},
      {"type": "history", "text": "0 of 0 activities on the same skills completed; 0 missed",
       "completed": 0, "total": 0, "missed": 0,
       "same_type_completed": 0, "same_type_total": 0, "same_type_missed": 0},
      {"type": "effective_gain", "skill": "SK_SYSTEM_DESIGN", "from": 2, "to": 3, "weight": 1.5, "weighted_gap_closed": 1.5}
    ],
    "calculation": {"gap_closed": 1.5, "engagement": 0.5, "formula": "1.5000 * 0.5000^0.7"}
  }],
  "readiness": {"current": 0.5, "after_top": 0.75},
  "source": "fallback"
}
```

`source` is `llm` only when at least one LLM item passed validation; otherwise it is `fallback`. The service gives the LLM the top five deterministic candidates. Each returned item must name a candidate ID, be written in the requested language, mention participation history, and contain the exact current, required, and resulting skill levels from the factors. Items that fail are dropped; the remaining items (at most three) are returned in the LLM's order. When nothing survives, or the LLM times out, the deterministic fallback returns up to three gap-closing events when any are eligible; otherwise it may offer broader development. The LLM attempt has an eight-second default budget, split equally between configured providers so a hanging first provider cannot starve the second. `score` is a raw ranking value, not a probability. For events that develop several skills, factors include each skill's weighted contribution; these sum to `calculation.gap_closed`. The `history` factor separates activities on the same skills (`completed`, `total`, `missed`) from same-type activities on other skills (`same_type_*`), which count with weight 0.3 in engagement. `in_progress` history is excluded from engagement until its outcome is known; `overdue` counts as missed. `readiness.after_top` applies the first recommendation's gains only. Only `llm` responses are cached per process, keyed by the full request context; a fallback answer is recomputed on the next call.

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
{"results":[{"employee_id":"E0028","top":[{"event_id":"EV07","score":0.9234,"primary_skill":"SK_SYSTEM_DESIGN"}],"readiness":0.5,"gaps":{"SK_SYSTEM_DESIGN":2}}]}
```

`top` contains up to three event IDs, raw scores, and the skill each event mainly develops, so an HR view can aggregate which skills are being recommended. It is empty when no event is eligible, which is how the HR view finds employees without a recommended step. `readiness` is the employee's current readiness for the supplied target requirements. `gaps` maps each required skill that is below the target level to the number of missing levels; skills already at or above the requirement are omitted. HR aggregates these to see which skills sag most often. Errors: HTTP `422` with FastAPI's validation `detail` array when `items` is missing or an item is invalid. The supplied 200-person starter kit completed in about 0.21 seconds in a local in-process HTTP benchmark; production timing depends on hardware and request size.
