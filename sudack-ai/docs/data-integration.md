# Career Quest data integration

The supplied `docs/data` directory is a synthetic starter kit, not a runtime database. The service remains stateless: Go sends the relevant employee, next-grade profile, activity catalog, and that employee's history in every request. Tests load the starter kit directly to verify the contract and benchmark all 200 employees.

| File | Use in `/recommend` and `/score/batch` |
| --- | --- |
| `employees.json` | Select one `employees[]` object for `employee`. Its `skills` values are levels 0–5; missing skills count as 0. |
| `skills.json` | Select `role_profiles[]` by role and desired grade. Send `required_skills` as `next_grade_requirements` and `critical_skills` as `critical_skills`. Convert `skills[]` to a map keyed by `skill_id` for `skills_meta`. |
| `events.json` | Send `events[]` as the event catalog. The API accepts `target_roles`, `target_grades`, and `develops_skills` directly. |
| `activity_history.csv` | Filter rows by `employee_id` and send objects with at least `event_id` and `status`; send `date` too so recent participation weighs more. Include catalog entries for historical events so skill-based similarity can be calculated. |

The kit contains 200 employees, 40 events, 60 skills, 32 role-grade profiles, and 2,743 history rows. Its snapshot date is `2026-10-01`; scoring does not depend on the host clock. `EV_036` is explicitly repeatable in the kit and remains eligible after a prior completion. Other completed events, events currently `in_progress` or `overdue`, mandatory events, events outside the employee's role or grade, events with unmet prerequisites, and events with no possible skill gain are excluded. `critical_skills` from the target profile raise the weight of those gaps from 1.5 to 2.5, which is what makes the jury's "lowest skill is not the critical one" profile resolve correctly.

The current scoring contract needs the target grade and its requirements supplied by Go. Use `career_goal.target_grade` when set, otherwise the next grade in order. For employees already at Lead, Go should choose the desired target profile or decide that no promotion recommendation is needed. When `career_goal.target_role` differs from the current role, note that event audience filtering still uses the employee's current role, so Go should decide which role's events to send. The service does not infer career goals or access controls. New employee and history records in the documented starter-kit format can be sent without changing the service.
