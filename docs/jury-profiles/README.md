# Jury trap profiles

Three synthetic Backend Engineers (Middle, target Senior) in the exact starter-kit schema, built so that a one-factor rule ("recommend the lowest skill") gives the wrong answer. Load them together with the starter kit through the HR import screen (`employees.json` and `activity_history.csv`), or send them straight to the AI service as shown below. Employee IDs `E0901`–`E0903` and record IDs `R900001`–`R900011` do not collide with the kit. `manager_id` points to `E0050`, an existing Lead.

| Profile | Language | The trap | Expected answer |
| --- | --- | --- | --- |
| `E0901` | ru | Lowest skill is Public Speaking (0 of 2), but the employee skipped the Public Speaking Club three times in 2026. The critical skill for Senior is System Design (3 of 4). | Top step is a System Design event (`EV_006` Designing High-Load Systems). Public Speaking Club is third with score about 0.49 versus 2.08. The `rejected` block says: "Public Speaking: 0 при требуемых 2 для Senior, самый большой разрыв. Но: вы пропустили 3 из 3 активностей по этому навыку; System Design критичен для Senior, а Public Speaking нет." |
| `E0902` | kk | Biggest gap is SQL (1 of 4), but the only SQL event targets Data Analysts. Mentoring (1 of 3) can only be raised by Mentor Track, which is already completed and not repeatable. | Top step is `EV_009` Cloud Certification Prep (closes Cloud 1→2 and CI/CD 2→3). `rejected` reports SQL with `event_id: null`: no available event for this role. The roadmap marks SQL as `audience` and Mentoring as `already_completed`, which is a catalog gap for HR, not an employee problem. |
| `E0903` | en | New hire, three months, only mandatory onboarding in history. Every candidate has the same engagement (0.5), so the naive rule picks the largest gap (Problem Solving or Public Speaking). | Top step is `EV_006`, because it closes two critical gaps at once (System Design 2→3, API Design 3→4). `rejected` says: "Problem Solving: 3 against 4 needed for Senior, the largest gap. But: System Design is critical for Senior and Problem Solving is not." The roadmap reaches Senior in five activities and 38 hours. |

All three produce explanations with at least four factors (grade requirement, skill gap, participation history, effective gain) and a visible calculation. Readiness before and after the first step: 0.93→0.96, 0.84→0.87, 0.86→0.92.

## Sending a profile straight to the AI service

```powershell
# from the repository root, AI service running on :8001
$kit = "sudack-ai/docs/data"
$skills = Get-Content "$kit/skills.json" -Raw | ConvertFrom-Json
$events = (Get-Content "$kit/events.json" -Raw | ConvertFrom-Json).events
$emp = (Get-Content docs/jury-profiles/employees.json -Raw | ConvertFrom-Json).employees[0]
$profile = $skills.role_profiles | Where-Object { $_.role -eq $emp.role -and $_.grade -eq "Senior" }
$meta = @{}; foreach ($s in $skills.skills) { $meta[$s.skill_id] = @{ name = $s.name; category = $s.category } }
$history = Import-Csv docs/jury-profiles/activity_history.csv | Where-Object employee_id -eq $emp.employee_id |
           ForEach-Object { @{ event_id = $_.event_id; status = $_.status; date = $_.date } }
$body = @{ employee = $emp; next_grade = "Senior"; next_grade_requirements = $profile.required_skills;
           critical_skills = $profile.critical_skills; skills_meta = $meta; history = @($history);
           events = $events; lang = $emp.preferred_language; as_of = "2026-10-01" } | ConvertTo-Json -Depth 12
Invoke-RestMethod -Uri http://127.0.0.1:8001/recommend -Method Post -ContentType 'application/json' -Body $body
Invoke-RestMethod -Uri http://127.0.0.1:8001/simulate  -Method Post -ContentType 'application/json' -Body $body
```

The same request against `/simulate` returns the dated roadmap; wrapping several in `{"items": [...]}` and posting to `/score/batch` returns the HR view (gaps, participation, dropout risk).
