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
| `as_of` | date string | No | "Today" for recency, dropout risk and roadmap scheduling. Defaults to the latest history date. The kit's snapshot is `2026-10-01`. |

An event requires `event_id`, `title`, and `type`. The compact shape uses `audience: {roles, grades}` and `skills: {skill_id: {gain, max_level}}`. The starter-kit shape uses `target_roles`, `target_grades`, and `develops_skills: [{skill_id, gain, max_level}]`. Both accept optional `mandatory` (default `false`), `prerequisites` (`skill_id → level`), `recurring` (default `false`), `description` (shown to the LLM), `format`, `duration_hours` and `upcoming_sessions`. A non-`self_paced` event whose `upcoming_sessions` is an empty list cannot be attended and is not recommended. `EV_036` is recognized as recurring from the supplied kit. Omitted audience lists allow all roles or grades.

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
  "rejected": [{
    "event_id": "EV_SPEAK", "title": "Public Speaking Club", "skill": "SK_PUBLIC_SPEAKING",
    "current": 0, "required": 2, "score": 0.4872, "recommended_position": 2,
    "reason": "Public Speaking: 0 при требуемых 2 для Senior, самый большой разрыв. Но: вы пропустили 3 из 3 активностей по этому навыку; System Design критичен для Senior, а Public Speaking нет."
  }],
  "source": "fallback"
}
```

`rejected` is the counterfactual for the jury's trap profiles: up to two alternatives a one-factor rule would put first (the skill with the largest gap, then the next best by score) and why each lost to the top recommendation. Each entry has the skill, its levels, the alternative event (or `event_id: null` with a reason when no eligible event develops that skill), the position it still holds in `recommendations` if any, and a sentence in `lang` built from the same factors: missed history on that skill, critical versus non-critical, outside the requirements, or a smaller weighted contribution.

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
{"results":[{"employee_id":"E0028","top":[{"event_id":"EV07","score":0.9234,"primary_skill":"SK_SYSTEM_DESIGN"}],"readiness":0.5,"gaps":{"SK_SYSTEM_DESIGN":2},"participation":{"completed":0,"missed":0,"in_progress":0,"total":0,"last_activity_date":null},"risk":{"score":0.0,"level":"low","reasons":[{"code":"no_history"}],"suggested_format":null}}]}
```

`top` contains up to three event IDs, raw scores, and the skill each event mainly develops, so an HR view can aggregate which skills are being recommended. It is empty when no event is eligible, which is how the HR view finds employees without a recommended step. `readiness` is the employee's current readiness for the supplied target requirements. `gaps` maps each required skill that is below the target level to the number of missing levels; skills already at or above the requirement are omitted. HR aggregates these to see which skills sag most often. `participation` summarises the supplied history (`completed`, `missed`, `in_progress`, `total`, `last_activity_date`) so the HR view can flag employees who are dropping out of development. `risk` is the dropout-risk estimate: `score` in 0–1, `level` `low` (below 0.3), `medium` or `high` (0.55 and above), machine-readable `reasons` for the UI to localize (`high_miss_rate`, `recent_misses` in the last 180 days, `inactive` with `days_since_completion`, `stale_in_progress`, `declined_assignments`, `no_history`), and `suggested_format` when the employee completes one event format (for example `self_paced`) but misses another. The score is `0.45 × miss rate + 0.25 × min(recent misses / 3, 1) + 0.2 × inactive + 0.1 × stale in-progress`. Recency uses `as_of`. On the 200-person kit this yields 170 low, 29 medium and 1 high. Errors: HTTP `422` with FastAPI's validation `detail` array when `items` is missing or an item is invalid. The supplied 200-person starter kit completed in about 0.21 seconds in a local in-process HTTP benchmark; production timing depends on hardware and request size.

## `POST /simulate`

Builds a roadmap to the next grade for one employee. Same body as `/recommend` (`lang` and `as_of` optional). No LLM call. At each step the service takes the eligible event that closes the most weighted gap, applies its gains with the dataset growth rule, and schedules it on the first free `upcoming_sessions` date on or after `as_of`; an event with prerequisites is scheduled after the step that satisfied them; self-paced events get the earliest possible date; a recurring event can repeat on later sessions. At most eight steps.

```powershell
$body = Get-Content docs/examples/recommend-request.json -Raw
Invoke-RestMethod -Uri http://127.0.0.1:8001/simulate -Method Post -ContentType 'application/json' -Body $body
```

Success: HTTP `200`:

```json
{
  "as_of": "2026-10-01", "next_grade": "Senior", "reachable": false,
  "steps": [{
    "event_id": "EV_005", "title": "System Design Fundamentals", "type": "course", "format": "online",
    "date": "2026-11-23", "duration_hours": 12,
    "skill_changes": [{"skill": "SK_SYSTEM_DESIGN", "name": "System Design", "from": 1, "to": 2, "required": 4}],
    "readiness_after": 0.64
  }],
  "total_hours": 44, "estimated_completion": "2026-12-17",
  "readiness_path": [0.58, 0.64, 0.72, 0.77, 0.79, 0.81],
  "coverage": {"gap_levels_total": 16, "gap_levels_closed": 6, "ratio": 0.375},
  "remaining_gaps": {"SK_PYTHON": 1, "SK_CLOUD": 1},
  "blocked": [{"skill": "SK_CLOUD", "name": "Cloud Platforms", "current": 1, "required": 2, "reason": "no_event_for_skill"}]
}
```

`steps` are in priority order; sort by `date` for a timeline. `readiness_path` starts with the current readiness and adds one value per step. `coverage` says how many missing skill levels the current catalog can close. `blocked` explains every skill the catalog cannot raise to the requirement, with a reason HR can act on: `no_event_for_skill`, `audience` (events exist but not for this role or grade), `ceiling` (events exist but their `max_level` is at or below the current level), `prerequisites`, or `unscheduled` (no future session). On the supplied kit no employee is fully reachable, which is a property of the 40-event catalog, not of the employees. Errors: HTTP `422` for an invalid body.

## `POST /events/impact`

Estimates what a draft HR event would do across the workforce before it is created. Body: `{"event": <event in either accepted shape>, "items": [<the same object as /recommend>]}`. No LLM call; the kit's 200 employees take about 0.2 s.

```powershell
$items = Get-Content docs/examples/recommend-request.json -Raw | ConvertFrom-Json
$draft = @{ event_id = "EV_NEW"; title = "Architecture clinic"; type = "workshop"; format = "online"; duration_hours = 4;
            audience = @{ roles = @("Backend Engineer"); grades = @() };
            skills = @{ SK_SYSTEM_DESIGN = @{ gain = 1; max_level = 4 } } }
$body = @{ event = $draft; items = @($items) } | ConvertTo-Json -Depth 12
Invoke-RestMethod -Uri http://127.0.0.1:8001/events/impact -Method Post -ContentType 'application/json' -Body $body
```

Success: HTTP `200`:

```json
{
  "event_id": "EV_NEW", "title": "Architecture clinic", "employees": 200,
  "audience_count": 56, "gap_closing_count": 16, "gap_closing_employees": ["E0002", "E0005"],
  "expected_completions": 8.8, "gap_levels_closed": 16, "hours_per_gap_level": 4.0,
  "by_skill": {"SK_SYSTEM_DESIGN": 16},
  "catalog_rank": 9,
  "catalog_top": [{"event_id": "EV_036", "title": "Public Speaking Club", "gap_closing_count": 85}]
}
```

`audience_count` is who may attend (role, grade, prerequisites). `gap_closing_count` is who would actually close a next-grade gap; `expected_completions` sums those employees' engagement rates, i.e. the predicted number who finish given their history. `hours_per_gap_level` is `duration_hours × gap-closing employees / gap levels closed`, a cost-per-outcome figure for the development budget. `catalog_rank` places the draft among the existing non-mandatory events by `gap_closing_count`, and `catalog_top` lists the five strongest existing events for comparison. Errors: HTTP `422` for an invalid body.

