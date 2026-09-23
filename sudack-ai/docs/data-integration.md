# Career Quest data integration

The supplied `docs/data` directory is a synthetic starter kit, not a runtime database. The service remains stateless: Go sends the relevant employee, next-grade profile, activity catalog, and that employee's history in every request. Tests load the starter kit directly to verify the contract and benchmark all 200 employees.

| File | Use in `/recommend` and `/score/batch` |
| --- | --- |
| `employees.json` | Send one `employees[]` object as `employee`, unchanged. Its `skills` values are levels 0–5; missing skills count as 0. `last_review_date` lets the service apply completions recorded after the last assessment. |
| `skills.json` | Select `role_profiles[]` by role and desired grade. Send `required_skills` as `next_grade_requirements` and `critical_skills` as `critical_skills`. Convert `skills[]` to a map keyed by `skill_id` for `skills_meta`. |
| `events.json` | Send `events[]` as the event catalog, unchanged. The API accepts `target_roles`, `target_grades`, `develops_skills`, `format`, `upcoming_sessions` and `description` directly; scheduled events with no upcoming session are skipped. |
| `activity_history.csv` | Filter rows by `employee_id` and send objects with at least `event_id` and `status`; send `date` too so recent participation weighs more. Include catalog entries for historical events so skill-based similarity can be calculated. |

The kit contains 200 employees, 40 events, 60 skills, 32 role-grade profiles, and 2,743 history rows. Its snapshot date is `2026-10-01`; scoring does not depend on the host clock. `EV_036` is explicitly repeatable in the kit and remains eligible after a prior completion. Other completed events, events currently `in_progress` or `overdue`, mandatory events, events outside the employee's role or grade, events with unmet prerequisites, and events with no possible skill gain are excluded. `critical_skills` from the target profile raise the weight of those gaps from 1.5 to 2.5, which is what makes the jury's "lowest skill is not the critical one" profile resolve correctly.

The current scoring contract needs the target grade and its requirements supplied by Go. Use `career_goal.target_grade` when set, otherwise the next grade in order. For employees already at Lead, Go should choose the desired target profile or decide that no promotion recommendation is needed. When `career_goal.target_role` differs from the current role, note that event audience filtering still uses the employee's current role, so Go should decide which role's events to send. The service does not infer career goals or access controls. New employee and history records in the documented starter-kit format can be sent without changing the service.

## Which dataset fields the service uses

| Field | Used for |
| --- | --- |
| `employees.role`, `grade` | Event audience filter |
| `employees.skills` | Gaps, gains, readiness |
| `employees.preferred_language` | Default `lang` |
| `employees.last_review_date` | Applying completions after the last assessment |
| `employees.career_goal` | Go chooses `next_grade` (and role) from it |
| `role_profiles.required_skills`, `critical_skills` | `next_grade_requirements`, weight 2.5 for critical gaps |
| `skills.name`, `category` | Readable factors and reasons (`skills_meta`) |
| `events.type` | Weak same-type similarity |
| `events.mandatory` | Excluded (not a recommendation target) |
| `events.target_roles`, `target_grades`, `prerequisites` | Eligibility |
| `events.develops_skills` (`gain`, `max_level`) | Effective gain, ceiling check |
| `events.format`, `upcoming_sessions` | Skip scheduled events without a session |
| `events.description` | Shown to the LLM for specific reasons |
| `history.status` | Completed / missed / in progress |
| `history.date` | Recency weighting, progress after review, last activity |

Not used by the AI service and left to Go or the UI: `full_name`, `department`, `manager_id`, `hire_date`, `work_format`, `duration_hours`, `record_id`, `due_date`, `completion_pct`, `score`, `feedback_rating`, `assigned_by`, and the skill `type` (hard/soft) and `description`. `assigned_by` and `feedback_rating` are natural next inputs for engagement (self-initiated completions as a stronger signal, low ratings as a weaker one).
