package bootstrap

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/csv"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"

	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/migrations"
	_ "github.com/mattn/go-sqlite3"
)

var gradeRanks = map[string]int{
	"Junior": 0,
	"Middle": 1,
	"Senior": 2,
	"Lead":   3,
}

// Initialize creates a complete database once. An existing file is never modified.
func Initialize(ctx context.Context, dbPath, dataDir string) (bool, error) {
	target, err := filepath.Abs(dbPath)
	if err != nil {
		return false, fmt.Errorf("database path: %w", err)
	}
	if info, err := os.Stat(target); err == nil {
		if info.IsDir() {
			return false, fmt.Errorf("database path is a directory: %s", target)
		}
		return false, nil
	} else if !errors.Is(err, os.ErrNotExist) {
		return false, fmt.Errorf("stat database: %w", err)
	}

	var skills skillDataset
	if err := readJSON(dataDir, "skills.json", &skills); err != nil {
		return false, err
	}
	var events eventDataset
	if err := readJSON(dataDir, "events.json", &events); err != nil {
		return false, err
	}
	var employees employeeDataset
	if err := readJSON(dataDir, "employees.json", &employees); err != nil {
		return false, err
	}
	history, err := os.ReadFile(filepath.Join(dataDir, "activity_history.csv"))
	if err != nil {
		return false, fmt.Errorf("read activity_history.csv: %w", err)
	}

	if err := os.MkdirAll(filepath.Dir(target), 0750); err != nil {
		return false, fmt.Errorf("create database directory: %w", err)
	}
	temporary, err := os.CreateTemp(filepath.Dir(target), ".careerquest-*.db")
	if err != nil {
		return false, fmt.Errorf("create temporary database: %w", err)
	}
	temporaryPath := temporary.Name()
	defer os.Remove(temporaryPath)
	if err := temporary.Close(); err != nil {
		return false, fmt.Errorf("close temporary database: %w", err)
	}

	db, err := sql.Open("sqlite3", temporaryPath+"?_foreign_keys=on&_busy_timeout=5000")
	if err != nil {
		return false, fmt.Errorf("open temporary database: %w", err)
	}
	defer db.Close()
	db.SetMaxOpenConns(1)

	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return false, fmt.Errorf("begin database initialization: %w", err)
	}
	defer tx.Rollback()

	if _, err := tx.ExecContext(ctx, migrations.InitSQL); err != nil {
		return false, fmt.Errorf("apply schema: %w", err)
	}
	if err := importMetadata(ctx, tx, skills, events, employees); err != nil {
		return false, err
	}
	if err := importSkills(ctx, tx, skills); err != nil {
		return false, err
	}
	if err := importEvents(ctx, tx, events); err != nil {
		return false, err
	}
	if err := importEmployees(ctx, tx, employees); err != nil {
		return false, err
	}
	if err := importHistory(ctx, tx, history); err != nil {
		return false, err
	}
	if _, err := tx.ExecContext(ctx, "PRAGMA user_version = 1"); err != nil {
		return false, fmt.Errorf("set schema version: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return false, fmt.Errorf("commit database initialization: %w", err)
	}
	if err := db.Close(); err != nil {
		return false, fmt.Errorf("close initialized database: %w", err)
	}
	if err := os.Link(temporaryPath, target); err != nil {
		if errors.Is(err, os.ErrExist) {
			return false, nil
		}
		return false, fmt.Errorf("publish database: %w", err)
	}
	return true, nil
}

func readJSON(dataDir, name string, target any) error {
	data, err := os.ReadFile(filepath.Join(dataDir, name))
	if err != nil {
		return fmt.Errorf("read %s: %w", name, err)
	}
	if err := json.Unmarshal(data, target); err != nil {
		return fmt.Errorf("parse %s: %w", name, err)
	}
	return nil
}

func importMetadata(ctx context.Context, tx *sql.Tx, skills skillDataset, events eventDataset, employees employeeDataset) error {
	values := []struct {
		key   string
		value json.RawMessage
	}{
		{"skills_meta", skills.Meta},
		{"proficiency_scale", skills.ProficiencyScale},
		{"events_meta", events.Meta},
		{"employees_meta", employees.Meta},
	}
	for _, item := range values {
		if _, err := tx.ExecContext(ctx, "INSERT INTO dataset_metadata(key, value_json) VALUES (?, ?)", item.key, string(item.value)); err != nil {
			return fmt.Errorf("import metadata %s: %w", item.key, err)
		}
	}
	return nil
}

func importSkills(ctx context.Context, tx *sql.Tx, data skillDataset) error {
	for _, skill := range data.Skills {
		_, err := tx.ExecContext(ctx,
			"INSERT INTO skills(id, name_en, category, category_detail, description) VALUES (?, ?, ?, ?, ?)",
			skill.ID, skill.Name, skill.Type, skill.Category, skill.Description)
		if err != nil {
			return fmt.Errorf("import skill %s: %w", skill.ID, err)
		}
	}

	for _, profile := range data.RoleProfiles {
		rank, ok := gradeRanks[profile.Grade]
		if !ok {
			return fmt.Errorf("unknown grade %q for role %q", profile.Grade, profile.Role)
		}
		if _, err := tx.ExecContext(ctx,
			"INSERT INTO grade_levels(role, grade, rank) VALUES (?, ?, ?)",
			profile.Role, profile.Grade, rank); err != nil {
			return fmt.Errorf("import grade %s/%s: %w", profile.Role, profile.Grade, err)
		}
		critical := make(map[string]bool, len(profile.CriticalSkills))
		for _, skillID := range profile.CriticalSkills {
			critical[skillID] = true
		}
		for skillID, required := range profile.RequiredSkills {
			if _, err := tx.ExecContext(ctx,
				"INSERT INTO grade_requirements(role, grade, skill_id, required_level, critical) VALUES (?, ?, ?, ?, ?)",
				profile.Role, profile.Grade, skillID, required, critical[skillID]); err != nil {
				return fmt.Errorf("import requirement %s/%s/%s: %w", profile.Role, profile.Grade, skillID, err)
			}
		}
	}
	return nil
}

func importEvents(ctx context.Context, tx *sql.Tx, data eventDataset) error {
	for _, event := range data.Events {
		sessions, err := json.Marshal(event.UpcomingSessions)
		if err != nil {
			return fmt.Errorf("encode sessions for event %s: %w", event.ID, err)
		}
		if _, err := tx.ExecContext(ctx,
			"INSERT INTO events(id, title_en, description, type, format, duration_hours, mandatory, upcoming_sessions_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
			event.ID, event.Title, event.Description, event.Type, event.Format, event.DurationHours, event.Mandatory, string(sessions)); err != nil {
			return fmt.Errorf("import event %s: %w", event.ID, err)
		}
		for _, role := range event.TargetRoles {
			if _, err := tx.ExecContext(ctx, "INSERT INTO event_audience_roles(event_id, role) VALUES (?, ?)", event.ID, role); err != nil {
				return fmt.Errorf("import event %s role %s: %w", event.ID, role, err)
			}
		}
		for _, grade := range event.TargetGrades {
			if _, err := tx.ExecContext(ctx, "INSERT INTO event_audience_grades(event_id, grade) VALUES (?, ?)", event.ID, grade); err != nil {
				return fmt.Errorf("import event %s grade %s: %w", event.ID, grade, err)
			}
		}
		for _, effect := range event.DevelopsSkills {
			if _, err := tx.ExecContext(ctx,
				"INSERT INTO event_skill_effects(event_id, skill_id, gain, max_level) VALUES (?, ?, ?, ?)",
				event.ID, effect.SkillID, effect.Gain, effect.MaxLevel); err != nil {
				return fmt.Errorf("import event %s effect %s: %w", event.ID, effect.SkillID, err)
			}
		}
		for skillID, level := range event.Prerequisites {
			if _, err := tx.ExecContext(ctx,
				"INSERT INTO event_prerequisites(event_id, skill_id, required_level) VALUES (?, ?, ?)",
				event.ID, skillID, level); err != nil {
				return fmt.Errorf("import event %s prerequisite %s: %w", event.ID, skillID, err)
			}
		}
	}
	return nil
}

func importEmployees(ctx context.Context, tx *sql.Tx, data employeeDataset) error {
	for _, employee := range data.Employees {
		var goalRole, goalGrade any
		if employee.CareerGoal != nil {
			goalRole = employee.CareerGoal.TargetRole
			goalGrade = employee.CareerGoal.TargetGrade
		}
		var managerID any
		if employee.ManagerID != nil {
			managerID = *employee.ManagerID
		}
		if _, err := tx.ExecContext(ctx,
			"INSERT INTO employees(id, full_name, department, role, grade, manager_id, hire_date, tenure_months, work_format, preferred_language, career_goal_role, career_goal_grade, last_review_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
			employee.ID, employee.FullName, employee.Department, employee.Role, employee.Grade, managerID, employee.HireDate,
			employee.TenureMonths, employee.WorkFormat, employee.PreferredLanguage, goalRole, goalGrade, employee.LastReviewDate); err != nil {
			return fmt.Errorf("import employee %s: %w", employee.ID, err)
		}
		for skillID, level := range employee.Skills {
			if _, err := tx.ExecContext(ctx,
				"INSERT INTO employee_skills(employee_id, skill_id, level) VALUES (?, ?, ?)",
				employee.ID, skillID, level); err != nil {
				return fmt.Errorf("import employee %s skill %s: %w", employee.ID, skillID, err)
			}
		}
	}
	return nil
}

func importHistory(ctx context.Context, tx *sql.Tx, data []byte) error {
	return importHistoryMode(ctx, tx, data, false)
}

func importHistoryMode(ctx context.Context, tx *sql.Tx, data []byte, ignoreExisting bool) error {
	reader := csv.NewReader(bytes.NewReader(data))
	records, err := reader.ReadAll()
	if err != nil {
		return fmt.Errorf("parse activity_history.csv: %w", err)
	}
	if len(records) == 0 {
		return fmt.Errorf("activity_history.csv is empty")
	}
	positions := make(map[string]int, len(records[0]))
	for index, name := range records[0] {
		positions[name] = index
	}
	required := []string{"record_id", "employee_id", "event_id", "date", "due_date", "status", "completion_pct", "score", "feedback_rating", "assigned_by"}
	for _, name := range required {
		if _, ok := positions[name]; !ok {
			return fmt.Errorf("activity_history.csv: missing column %s", name)
		}
	}

	for index, record := range records[1:] {
		field := func(name string) string { return record[positions[name]] }
		completion, err := strconv.Atoi(field("completion_pct"))
		if err != nil {
			return fmt.Errorf("activity_history.csv row %d completion_pct: %w", index+2, err)
		}
		score, err := optionalInt(field("score"))
		if err != nil {
			return fmt.Errorf("activity_history.csv row %d score: %w", index+2, err)
		}
		rating, err := optionalInt(field("feedback_rating"))
		if err != nil {
			return fmt.Errorf("activity_history.csv row %d feedback_rating: %w", index+2, err)
		}
		recordID := field("record_id")
		query := "INSERT INTO activity_history(record_id, employee_id, event_id, occurred_at, due_date, status, completion_pct, score, feedback_rating, assigned_by, source, source_key) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'import', ?)"
		if ignoreExisting {
			query += " ON CONFLICT(source_key) DO NOTHING"
		}
		if _, err := tx.ExecContext(ctx,
			query,
			recordID, field("employee_id"), field("event_id"), field("date"), optionalText(field("due_date")),
			field("status"), completion, score, rating, field("assigned_by"), recordID); err != nil {
			return fmt.Errorf("activity_history.csv row %d (%s): %w", index+2, recordID, err)
		}
	}
	return nil
}

func optionalInt(value string) (any, error) {
	if value == "" {
		return nil, nil
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return nil, err
	}
	return parsed, nil
}

func optionalText(value string) any {
	if value == "" {
		return nil
	}
	return value
}
