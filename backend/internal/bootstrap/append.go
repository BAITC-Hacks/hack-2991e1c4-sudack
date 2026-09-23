package bootstrap

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	_ "github.com/mattn/go-sqlite3"
)

// Report counts what an append did. Unchanged rows already existed (same employee ID or record ID).
type Report struct {
	EmployeesAdded     int `json:"employees_added"`
	EmployeesUnchanged int `json:"employees_unchanged"`
	HistoryAdded       int `json:"history_added"`
	HistoryUnchanged   int `json:"history_unchanged"`
}

// Append adds new employee IDs and history rows from a directory to an initialized database.
// Existing employee snapshots and earned progress remain untouched.
func Append(ctx context.Context, dbPath, dataDir string) (int, error) {
	target, err := filepath.Abs(dbPath)
	if err != nil {
		return 0, fmt.Errorf("database path: %w", err)
	}
	if _, err := os.Stat(target); err != nil {
		return 0, fmt.Errorf("database must exist before append: %w", err)
	}
	employees, err := os.ReadFile(filepath.Join(dataDir, "employees.json"))
	if err != nil {
		return 0, fmt.Errorf("read employees.json: %w", err)
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
	report, err := AppendTo(ctx, db, employees, history)
	return report.EmployeesAdded, err
}

// AppendTo is the same operation on an open database with in-memory files, used by the HTTP import.
// Either input may be empty. employees.json is accepted as {"employees": [...]} or a bare array.
func AppendTo(ctx context.Context, db *sql.DB, employeesJSON, historyCSV []byte) (Report, error) {
	var report Report
	employees, err := parseEmployees(employeesJSON)
	if err != nil {
		return report, err
	}
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return report, fmt.Errorf("begin append: %w", err)
	}
	defer tx.Rollback()

	for index, employee := range employees {
		if employee.ID == "" || employee.Role == "" || employee.Grade == "" || employee.Skills == nil {
			return report, fmt.Errorf("employees.json: entry %d is missing employee_id, role, grade or skills", index+1)
		}
		if _, ok := gradeRanks[employee.Grade]; !ok {
			return report, fmt.Errorf("employees.json: entry %d (%s) has unknown grade %q", index+1, employee.ID, employee.Grade)
		}
		var exists int
		if err := tx.QueryRowContext(ctx, "SELECT EXISTS(SELECT 1 FROM employees WHERE id = ?)", employee.ID).Scan(&exists); err != nil {
			return report, fmt.Errorf("check employee %s: %w", employee.ID, err)
		}
		if exists != 0 {
			report.EmployeesUnchanged++
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
		lastReview := employee.LastReviewDate
		if lastReview == "" {
			lastReview = employee.HireDate
		}
		_, err = tx.ExecContext(ctx,
			"INSERT INTO employees(id, full_name, department, role, grade, manager_id, hire_date, tenure_months, work_format, preferred_language, career_goal_role, career_goal_grade, last_review_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
			employee.ID, employee.FullName, employee.Department, employee.Role, employee.Grade, managerID,
			employee.HireDate, employee.TenureMonths, employee.WorkFormat, employee.PreferredLanguage,
			goalRole, goalGrade, lastReview)
		if err != nil {
			return report, fmt.Errorf("employees.json: %s: %w", employee.ID, err)
		}
		for skillID, level := range employee.Skills {
			if _, err := tx.ExecContext(ctx,
				"INSERT INTO employee_skills(employee_id, skill_id, level) VALUES (?, ?, ?)",
				employee.ID, skillID, level); err != nil {
				return report, fmt.Errorf("employees.json: %s skill %s: %w", employee.ID, skillID, err)
			}
		}
		report.EmployeesAdded++
	}
	if len(bytes.TrimSpace(historyCSV)) > 0 {
		added, skipped, err := importHistoryCount(ctx, tx, historyCSV, true)
		if err != nil {
			return report, err
		}
		report.HistoryAdded, report.HistoryUnchanged = added, skipped
	}
	if err := tx.Commit(); err != nil {
		return report, fmt.Errorf("commit append: %w", err)
	}
	return report, nil
}

func parseEmployees(data []byte) ([]employee, error) {
	if len(bytes.TrimSpace(data)) == 0 {
		return nil, nil
	}
	var wrapped employeeDataset
	if err := json.Unmarshal(data, &wrapped); err == nil && wrapped.Employees != nil {
		return wrapped.Employees, nil
	}
	var list []employee
	if err := json.Unmarshal(data, &list); err != nil {
		return nil, fmt.Errorf("employees.json: expected {\"employees\": [...]} or an array of employees: %w", err)
	}
	return list, nil
}
