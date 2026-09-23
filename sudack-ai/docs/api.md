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
| `employee` | object | Yes | `employee_id`, `role`, `grade`, and `skills` (`skill_id → level 0–5`); `tenure_months`, `preferred_language` and `last_review_date` are optional. When `last_review_date` is present, completions dated after it are applied to the skills before scoring (see `applied_progress`). Extra starter-kit employee fields are accepted. |
| `next_grade` | string | Yes | Target grade label supplied by Go. |
| `next_grade_requirements` | object | Yes | Target `skill_id → required level 0–5`. |
| `critical_skills` | string array | No | IDs from the target role profile; defaults to `[]`. Gaps in these skills weigh 2.5 instead of 1.5 in scoring and readiness. |
| `skills_meta` | object | No | `skill_id → {name, category?}`; defaults to `{}`. Used for readable explanations. |
| `history` | object array | No | Entries need `event_id` and `status`; `date` (`YYYY-MM-DD` or `YYYY-MM`) is optional and enables recency weighting. Defaults to `[]`. |
| `events` | object array | Yes | Full candidate and historical event catalog. See accepted event shapes below. |
| `lang` | `ru`, `kk`, or `en` | No | Defaults to `employee.preferred_language` when present, otherwise `ru`. |

An event requires `event_id`, `title`, and `type`. The compact shape uses `audience: {roles, grades}` and `skills: {skill_id: {gain, max_level}}`. The starter-kit shape uses `target_roles`, `target_grades`, and `develops_skills: [{skill_id, gain, max_level}]`. Both accept optional `mandatory` (default `false`), `prerequisites` (`skill_id → level`), `recurring` (default `false`), `description` (shown to the LLM), `format` and `upcoming_sessions`. A non-`self_paced` event whose `upcoming_sessions` is an empty list cannot be attended and is not recommended. `EV_036` is recognized as recurring from the supplied kit. Omitted audience lists allow all roles or grades.

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
    "reason_source": "template",
    "factors": [
      {"type": "grade_requirement", "text": "System Design is required for Senior", "critical": false},
      {"type": "skill_gap", "skill": "SK_SYSTEM_DESIGN", "name": "System Design", "current": 2, "required": 4},
      {"type": "history", "text": "0 of 0 activities on the same skills completed; 0 missed",
       "completed": 0, "total": 0, "missed": 0,
       "same_type_completed": 0, "same_type_total": 0, "same_type_missed": 0},
      {"type": "effective_gain", "skill": "SK_SYSTEM_DESIGN", "from": 2, "to": 3, "weight": 1.5, "weighted_gap_closed": 1.5}
    ],
    "calculation": {"gap_closed": 1.5, "engagement": 0.5, "formula": "1.5000 * 0.5000^0.7"}
  }],
  "readiness": {"current": 0.5, "after_top": 0.75},
  "gaps": {"SK_SYSTEM_DESIGN": 2},
  "applied_progress": [],
  "source": "fallback"
}
```

`source` is `llm` when the LLM chose the events and at least one of its reasons passed validation; otherwise it is `fallback`. Each recommendation also carries `reason_source`: `llm` for validated LLM prose, `template` for the deterministic multilingual explanation. The service gives the LLM up to five gap-closing candidates (padded with enrichment events only when fewer than three close a gap) as plain facts: skill names, current/required/after levels, a `critical` flag, a `closes_gap` flag, the event description, and history counts; scoring weights are never shown to the model. A returned item must name a candidate ID; its reason must be in the requested language, mention participation history, contain the exact current, required and resulting levels, and not duplicate another reason. A reason that fails keeps the event but is replaced by the template for that event. When no LLM reason survives, or the LLM times out, the deterministic fallback returns up to three gap-closing events when any are eligible; otherwise it may offer broader development. `gaps` lists required skills still below the target level. `applied_progress` lists skill increases the service applied from completions dated after `employee.last_review_date`, each as `{event_id, skill, from, to}`; the profile skills plus these entries are the levels used in factors and readiness. The LLM attempt has an eight-second default budget, split equally between configured providers so a hanging first provider cannot starve the second. `score` is a raw ranking value, not a probability. For events that develop several skills, factors include each skill's weighted contribution; these sum to `calculation.gap_closed`. The `history` factor separates activities on the same skills (`completed`, `total`, `missed`) from same-type activities on other skills (`same_type_*`), which count with weight 0.3 in engagement. `in_progress` history is excluded from engagement until its outcome is known; `overdue` counts as missed. `readiness.after_top` applies the first recommendation's gains only. Only `llm` responses are cached per process, keyed by the full request context; a fallback answer is recomputed on the next call.

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
{"results":[{"employee_id":"E0028","top":[{"event_id":"EV07","score":0.9234,"primary_skill":"SK_SYSTEM_DESIGN"}],"readiness":0.5,"gaps":{"SK_SYSTEM_DESIGN":2},"participation":{"completed":0,"missed":0,"in_progress":0,"total":0,"last_activity_date":null}}]}
```

`top` contains up to three event IDs, raw scores, and the skill each event mainly develops, so an HR view can aggregate which skills are being recommended. It is empty when no event is eligible, which is how the HR view finds employees without a recommended step. `readiness` is the employee's current readiness for the supplied target requirements. `gaps` maps each required skill that is below the target level to the number of missing levels; skills already at or above the requirement are omitted. HR aggregates these to see which skills sag most often. `participation` summarises the supplied history (`completed`, `missed`, `in_progress`, `total`, `last_activity_date`) so the HR view can flag employees who are dropping out of development. Errors: HTTP `422` with FastAPI's validation `detail` array when `items` is missing or an item is invalid. The supplied 200-person starter kit completed in about 0.21 seconds in a local in-process HTTP benchmark; production timing depends on hardware and request size.
