package bootstrap

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"path/filepath"

	_ "github.com/mattn/go-sqlite3"
)

// Append adds new employee IDs and history rows to an initialized database.
// Existing employee snapshots and earned progress remain untouched.
func Append(ctx context.Context, dbPath, dataDir string) (int, error) {
	target, err := filepath.Abs(dbPath)
	if err != nil {
		return 0, fmt.Errorf("database path: %w", err)
	}
	if _, err := os.Stat(target); err != nil {
		return 0, fmt.Errorf("database must exist before append: %w", err)
	}
	var employees employeeDataset
	if err := readJSON(dataDir, "employees.json", &employees); err != nil {
		return 0, err
	}
	history, err := os.ReadFile(filepath.Join(dataDir, "activity_history.csv"))
	if err != nil {
		return 0, fmt.Errorf("read activity_history.csv: %w", err)
	}

	db, err := sql.Open("sqlite3", target+"?_foreign_keys=on&_busy_timeout=5000&_txlock=immediate")
	if err != nil {
		return 0, fmt.Errorf("open database: %w", err)
	}
	defer db.Close()
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return 0, fmt.Errorf("begin append: %w", err)
	}
	defer tx.Rollback()

	added := 0
	for _, employee := range employees.Employees {
		var exists int
		err := tx.QueryRowContext(ctx, "SELECT EXISTS(SELECT 1 FROM employees WHERE id = ?)", employee.ID).Scan(&exists)
		if err != nil {
			return 0, fmt.Errorf("check employee %s: %w", employee.ID, err)
		}
		if exists != 0 {
			continue
		}
		var managerID, goalRole, goalGrade any
		if employee.ManagerID != nil {
			managerID = *employee.ManagerID
		}
		if employee.CareerGoal != nil {
			goalRole = employee.CareerGoal.TargetRole
			goalGrade = employee.CareerGoal.TargetGrade
		}
		_, err = tx.ExecContext(ctx,
			"INSERT INTO employees(id, full_name, department, role, grade, manager_id, hire_date, tenure_months, work_format, preferred_language, career_goal_role, career_goal_grade, last_review_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
			employee.ID, employee.FullName, employee.Department, employee.Role, employee.Grade, managerID,
			employee.HireDate, employee.TenureMonths, employee.WorkFormat, employee.PreferredLanguage,
			goalRole, goalGrade, employee.LastReviewDate)
		if err != nil {
			return 0, fmt.Errorf("append employee %s: %w", employee.ID, err)
		}
		for skillID, level := range employee.Skills {
			if _, err := tx.ExecContext(ctx,
				"INSERT INTO employee_skills(employee_id, skill_id, level) VALUES (?, ?, ?)",
				employee.ID, skillID, level); err != nil {
				return 0, fmt.Errorf("append employee %s skill %s: %w", employee.ID, skillID, err)
			}
		}
		added++
	}
	if err := importHistoryMode(ctx, tx, history, true); err != nil {
		return 0, err
	}
	if err := tx.Commit(); err != nil {
		return 0, fmt.Errorf("commit append: %w", err)
	}
	return added, nil
}
