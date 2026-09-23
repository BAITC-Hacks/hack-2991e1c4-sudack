-- name: GetEmployee :one
SELECT id, role, grade, tenure_months FROM employees WHERE id = ?;

-- name: ListEmployeeSkills :many
SELECT es.skill_id, s.name_en, s.name_ru, s.name_kk, s.category, es.level
FROM employee_skills es JOIN skills s ON s.id = es.skill_id
WHERE es.employee_id = ? ORDER BY es.skill_id;

-- name: GetNextGrade :one
SELECT next.grade, next.rank FROM employees e
JOIN grade_levels current ON current.role = e.role AND current.grade = e.grade
JOIN grade_levels next ON next.role = current.role AND next.rank = current.rank + 1
WHERE e.id = ?;

-- name: ListGradeGaps :many
SELECT r.skill_id, s.name_en, s.name_ru, s.name_kk,
       r.required_level, COALESCE(es.level, 0) AS current_level,
       MAX(0, r.required_level - COALESCE(es.level, 0)) AS gap
FROM grade_requirements r
JOIN skills s ON s.id = r.skill_id
JOIN employees e ON e.id = ? AND e.role = r.role
LEFT JOIN employee_skills es ON es.employee_id = e.id AND es.skill_id = r.skill_id
WHERE r.grade = ?
ORDER BY gap DESC, r.skill_id;

-- name: ListEmployeeHistory :many
SELECT h.id, h.event_id, e.title_en, e.title_ru, e.title_kk, e.type,
       h.occurred_at, h.status
FROM activity_history h JOIN events e ON e.id = h.event_id
WHERE h.employee_id = ? ORDER BY h.occurred_at DESC, h.id DESC;

-- name: ListHistoryEvidence :many
SELECT h.id AS history_id, h.event_id, e.type, h.occurred_at, h.status, ef.skill_id
FROM activity_history h
JOIN events e ON e.id = h.event_id
JOIN event_skill_effects ef ON ef.event_id = e.id
WHERE h.employee_id = ?
ORDER BY h.occurred_at DESC, h.id DESC, ef.skill_id;

-- name: ListEligibleEvents :many
SELECT e.id, e.title_en, e.title_ru, e.title_kk, e.type
FROM employees person JOIN events e ON e.active = 1
WHERE person.id = ?
  AND (NOT EXISTS (SELECT 1 FROM event_audience_roles ar WHERE ar.event_id = e.id)
       OR EXISTS (SELECT 1 FROM event_audience_roles ar WHERE ar.event_id = e.id AND ar.role = person.role))
  AND (NOT EXISTS (SELECT 1 FROM event_audience_grades ag WHERE ag.event_id = e.id)
       OR EXISTS (SELECT 1 FROM event_audience_grades ag WHERE ag.event_id = e.id AND ag.grade = person.grade))
  AND NOT EXISTS (SELECT 1 FROM activity_history h
                  WHERE h.employee_id = person.id AND h.event_id = e.id AND h.status = 'completed')
ORDER BY e.id;

-- name: ListEventEffects :many
SELECT ef.skill_id, ef.gain, ef.max_level, COALESCE(es.level, 0) AS current_level,
       MAX(COALESCE(es.level, 0), MIN(ef.max_level, COALESCE(es.level, 0) + ef.gain)) AS projected_level
FROM event_skill_effects ef
LEFT JOIN employee_skills es ON es.employee_id = ? AND es.skill_id = ef.skill_id
WHERE ef.event_id = ? ORDER BY ef.skill_id;

-- name: GetEvent :one
SELECT id, title_en, title_ru, title_kk, type, active FROM events WHERE id = ?;

-- name: GetHistoryByIdempotencyKey :one
SELECT id, employee_id, event_id, status FROM activity_history
WHERE employee_id = ? AND idempotency_key = ?;

-- name: HasCompletedEvent :one
SELECT EXISTS(SELECT 1 FROM activity_history
              WHERE employee_id = ? AND event_id = ? AND status = 'completed');

-- name: InsertCompletion :one
INSERT INTO activity_history(employee_id, event_id, occurred_at, status, source, idempotency_key)
VALUES (?, ?, ?, 'completed', 'app', ?) RETURNING id;

-- name: UpsertEmployeeSkill :exec
INSERT INTO employee_skills(employee_id, skill_id, level)
VALUES (?, ?, ?)
ON CONFLICT(employee_id, skill_id) DO UPDATE SET
level = excluded.level, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now');

-- name: HRSkillGaps :many
WITH targets AS (
  SELECT e.id AS employee_id, e.role, next.grade AS target_grade
  FROM employees e
  JOIN grade_levels current ON current.role = e.role AND current.grade = e.grade
  JOIN grade_levels next ON next.role = e.role AND next.rank = current.rank + 1
)
SELECT r.skill_id, s.name_en, s.name_ru, s.name_kk,
       COUNT(*) AS employees_below_target,
       SUM(r.required_level - COALESCE(es.level, 0)) AS total_missing_levels
FROM targets t
JOIN grade_requirements r ON r.role = t.role AND r.grade = t.target_grade
JOIN skills s ON s.id = r.skill_id
LEFT JOIN employee_skills es ON es.employee_id = t.employee_id AND es.skill_id = r.skill_id
WHERE COALESCE(es.level, 0) < r.required_level
GROUP BY r.skill_id ORDER BY employees_below_target DESC, total_missing_levels DESC, r.skill_id;

-- name: HRActivityParticipation :many
SELECT e.id AS event_id, e.title_en,
       SUM(CASE WHEN h.status = 'completed' THEN 1 ELSE 0 END) AS completed,
       SUM(CASE WHEN h.status = 'skipped' THEN 1 ELSE 0 END) AS skipped,
       SUM(CASE WHEN h.status = 'declined' THEN 1 ELSE 0 END) AS declined
FROM events e LEFT JOIN activity_history h ON h.event_id = e.id
GROUP BY e.id ORDER BY completed DESC, e.id;

-- name: HREmployeesWithoutStep :many
WITH targets AS (
  SELECT e.id AS employee_id, e.role, e.grade, next.grade AS target_grade
  FROM employees e
  JOIN grade_levels current ON current.role = e.role AND current.grade = e.grade
  JOIN grade_levels next ON next.role = e.role AND next.rank = current.rank + 1
)
SELECT t.employee_id
FROM targets t
WHERE NOT EXISTS (
  SELECT 1 FROM events ev
  JOIN event_skill_effects ef ON ef.event_id = ev.id
  JOIN grade_requirements r ON r.role = t.role AND r.grade = t.target_grade AND r.skill_id = ef.skill_id
  LEFT JOIN employee_skills es ON es.employee_id = t.employee_id AND es.skill_id = ef.skill_id
  WHERE ev.active = 1
    AND MAX(COALESCE(es.level, 0), MIN(ef.max_level, COALESCE(es.level, 0) + ef.gain)) > COALESCE(es.level, 0)
    AND COALESCE(es.level, 0) < r.required_level
    AND (NOT EXISTS (SELECT 1 FROM event_audience_roles ar WHERE ar.event_id = ev.id)
         OR EXISTS (SELECT 1 FROM event_audience_roles ar WHERE ar.event_id = ev.id AND ar.role = t.role))
    AND (NOT EXISTS (SELECT 1 FROM event_audience_grades ag WHERE ag.event_id = ev.id)
         OR EXISTS (SELECT 1 FROM event_audience_grades ag WHERE ag.event_id = ev.id AND ag.grade = t.grade))
    AND NOT EXISTS (SELECT 1 FROM activity_history h
                    WHERE h.employee_id = t.employee_id AND h.event_id = ev.id AND h.status = 'completed')
) ORDER BY t.employee_id;
