package sqlite

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/domain/career"
)

type Catalog struct {
	Events     []career.Event
	SkillsMeta map[string]career.SkillMeta
	AsOf       string
}

func (r *Repository) EmployeeIDs(ctx context.Context) ([]string, error) {
	rows, err := r.db.QueryContext(ctx, "SELECT id FROM employees ORDER BY id")
	if err != nil {
		return nil, fmt.Errorf("list employees: %w", err)
	}
	defer rows.Close()
	ids := make([]string, 0)
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return nil, fmt.Errorf("scan employee: %w", err)
		}
		ids = append(ids, id)
	}
	return ids, rows.Err()
}

func (r *Repository) LoadCatalog(ctx context.Context) (*Catalog, error) {
	catalog := &Catalog{
		Events:     make([]career.Event, 0),
		SkillsMeta: make(map[string]career.SkillMeta),
		AsOf:       time.Now().UTC().Format("2006-01-02"),
	}
	var asOf sql.NullString
	err := r.db.QueryRowContext(ctx, "SELECT json_extract(value_json, '$.as_of_date') FROM dataset_metadata WHERE key = 'employees_meta'").Scan(&asOf)
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return nil, fmt.Errorf("load dataset date: %w", err)
	}
	if asOf.Valid && asOf.String != "" {
		catalog.AsOf = asOf.String
	}

	rows, err := r.db.QueryContext(ctx, "SELECT id, name_en, category_detail FROM skills")
	if err != nil {
		return nil, fmt.Errorf("load skills metadata: %w", err)
	}
	for rows.Next() {
		var id, name, category string
		if err := rows.Scan(&id, &name, &category); err != nil {
			rows.Close()
			return nil, fmt.Errorf("scan skill metadata: %w", err)
		}
		catalog.SkillsMeta[id] = career.SkillMeta{Name: name, Category: category}
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return nil, err
	}
	rows.Close()

	rows, err = r.db.QueryContext(ctx, "SELECT id, title_en, type, description, format, duration_hours, mandatory, upcoming_sessions_json FROM events WHERE active = 1 ORDER BY id")
	if err != nil {
		return nil, fmt.Errorf("load events: %w", err)
	}
	index := make(map[string]int)
	for rows.Next() {
		var event career.Event
		var mandatory int
		var sessions string
		if err := rows.Scan(&event.ID, &event.Title, &event.Type, &event.Description, &event.Format, &event.DurationHours, &mandatory, &sessions); err != nil {
			rows.Close()
			return nil, fmt.Errorf("scan event: %w", err)
		}
		if err := json.Unmarshal([]byte(sessions), &event.UpcomingSessions); err != nil {
			rows.Close()
			return nil, fmt.Errorf("decode event %s sessions: %w", event.ID, err)
		}
		event.Mandatory = mandatory != 0
		event.Recurring = event.ID == "EV_036"
		event.Audience = career.Audience{Roles: []string{}, Grades: []string{}}
		event.Skills = make(map[string]career.SkillGain)
		event.Prerequisites = make(map[string]int)
		index[event.ID] = len(catalog.Events)
		catalog.Events = append(catalog.Events, event)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return nil, err
	}
	rows.Close()

	if err := r.loadAudience(ctx, catalog, index, "event_audience_roles", true); err != nil {
		return nil, err
	}
	if err := r.loadAudience(ctx, catalog, index, "event_audience_grades", false); err != nil {
		return nil, err
	}
	rows, err = r.db.QueryContext(ctx, "SELECT event_id, skill_id, gain, max_level FROM event_skill_effects")
	if err != nil {
		return nil, fmt.Errorf("load event effects: %w", err)
	}
	for rows.Next() {
		var eventID, skillID string
		var effect career.SkillGain
		if err := rows.Scan(&eventID, &skillID, &effect.Gain, &effect.MaxLevel); err != nil {
			rows.Close()
			return nil, err
		}
		if position, ok := index[eventID]; ok {
			catalog.Events[position].Skills[skillID] = effect
		}
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return nil, err
	}
	rows.Close()

	rows, err = r.db.QueryContext(ctx, "SELECT event_id, skill_id, required_level FROM event_prerequisites")
	if err != nil {
		return nil, fmt.Errorf("load event prerequisites: %w", err)
	}
	for rows.Next() {
		var eventID, skillID string
		var level int
		if err := rows.Scan(&eventID, &skillID, &level); err != nil {
			rows.Close()
			return nil, err
		}
		if position, ok := index[eventID]; ok {
			catalog.Events[position].Prerequisites[skillID] = level
		}
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return nil, err
	}
	rows.Close()
	return catalog, nil
}

func (r *Repository) loadAudience(ctx context.Context, catalog *Catalog, index map[string]int, table string, roles bool) error {
	column := "role"
	if !roles {
		column = "grade"
	}
	rows, err := r.db.QueryContext(ctx, "SELECT event_id, "+column+" FROM "+table)
	if err != nil {
		return fmt.Errorf("load %s: %w", table, err)
	}
	defer rows.Close()
	for rows.Next() {
		var eventID, value string
		if err := rows.Scan(&eventID, &value); err != nil {
			return err
		}
		if position, ok := index[eventID]; ok {
			if roles {
				catalog.Events[position].Audience.Roles = append(catalog.Events[position].Audience.Roles, value)
			} else {
				catalog.Events[position].Audience.Grades = append(catalog.Events[position].Audience.Grades, value)
			}
		}
	}
	return rows.Err()
}

func (r *Repository) LoadRequest(ctx context.Context, employeeID string, catalog *Catalog) (*career.Request, error) {
	request := &career.Request{
		Employee:              career.Employee{Skills: make(map[string]int)},
		NextGradeRequirements: make(map[string]int),
		CriticalSkills:        []string{},
		SkillsMeta:            catalog.SkillsMeta,
		History:               []career.HistoryEntry{},
		Events:                catalog.Events,
		AsOf:                  catalog.AsOf,
	}
	var goalRole, goalGrade sql.NullString
	err := r.db.QueryRowContext(ctx,
		"SELECT id, role, grade, tenure_months, preferred_language, last_review_date, career_goal_role, career_goal_grade FROM employees WHERE id = ?",
		employeeID).Scan(&request.Employee.ID, &request.Employee.Role, &request.Employee.Grade,
		&request.Employee.TenureMonths, &request.Employee.PreferredLanguage, &request.Employee.LastReviewDate,
		&goalRole, &goalGrade)
	if err != nil {
		return nil, err
	}
	request.Lang = request.Employee.PreferredLanguage
	if request.Lang != "ru" && request.Lang != "kk" && request.Lang != "en" {
		request.Lang = "ru"
	}

	rows, err := r.db.QueryContext(ctx, "SELECT skill_id, level FROM employee_skills WHERE employee_id = ?", employeeID)
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var id string
		var level int
		if err := rows.Scan(&id, &level); err != nil {
			rows.Close()
			return nil, err
		}
		request.Employee.Skills[id] = level
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return nil, err
	}
	rows.Close()

	targetRole := request.Employee.Role
	if goalRole.Valid && goalRole.String != "" {
		targetRole = goalRole.String
	}
	if goalGrade.Valid && goalGrade.String != "" {
		request.NextGrade = goalGrade.String
	} else {
		err := r.db.QueryRowContext(ctx,
			"SELECT next.grade FROM grade_levels current JOIN grade_levels next ON next.role = current.role AND next.rank = current.rank + 1 WHERE current.role = ? AND current.grade = ?",
			request.Employee.Role, request.Employee.Grade).Scan(&request.NextGrade)
		if err != nil && !errors.Is(err, sql.ErrNoRows) {
			return nil, err
		}
	}
	if request.NextGrade != "" {
		rows, err = r.db.QueryContext(ctx,
			"SELECT skill_id, required_level, critical FROM grade_requirements WHERE role = ? AND grade = ?",
			targetRole, request.NextGrade)
		if err != nil {
			return nil, err
		}
		for rows.Next() {
			var id string
			var level, critical int
			if err := rows.Scan(&id, &level, &critical); err != nil {
				rows.Close()
				return nil, err
			}
			request.NextGradeRequirements[id] = level
			if critical != 0 {
				request.CriticalSkills = append(request.CriticalSkills, id)
			}
		}
		if err := rows.Err(); err != nil {
			rows.Close()
			return nil, err
		}
		rows.Close()
	}

	rows, err = r.db.QueryContext(ctx,
		"SELECT event_id, status, occurred_at FROM activity_history WHERE employee_id = ? ORDER BY occurred_at, id",
		employeeID)
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var entry career.HistoryEntry
		if err := rows.Scan(&entry.EventID, &entry.Status, &entry.Date); err != nil {
			rows.Close()
			return nil, err
		}
		request.History = append(request.History, entry)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return nil, err
	}
	rows.Close()
	return request, nil
}

func (r *Repository) EmployeeDetails(ctx context.Context, id string) (string, string, error) {
	var name, department string
	err := r.db.QueryRowContext(ctx, "SELECT full_name, department FROM employees WHERE id = ?", id).Scan(&name, &department)
	return name, department, err
}
