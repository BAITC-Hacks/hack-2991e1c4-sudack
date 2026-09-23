package sqlite

import (
	"context"
	"fmt"

	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/bootstrap"
)

// EmployeeSummary is the display data the HR views need next to an employee ID.
type EmployeeSummary struct {
	ID         string `json:"employee_id"`
	FullName   string `json:"full_name"`
	Department string `json:"department"`
	Role       string `json:"role"`
	Grade      string `json:"grade"`
}

func (r *Repository) EmployeeSummaries(ctx context.Context) (map[string]EmployeeSummary, error) {
	rows, err := r.db.QueryContext(ctx, "SELECT id, full_name, department, role, grade FROM employees")
	if err != nil {
		return nil, fmt.Errorf("list employee summaries: %w", err)
	}
	defer rows.Close()
	result := make(map[string]EmployeeSummary)
	for rows.Next() {
		var item EmployeeSummary
		if err := rows.Scan(&item.ID, &item.FullName, &item.Department, &item.Role, &item.Grade); err != nil {
			return nil, fmt.Errorf("scan employee summary: %w", err)
		}
		result[item.ID] = item
	}
	return result, rows.Err()
}

// AppendDataset adds employees and history in the starter-kit format to the live database.
func (r *Repository) AppendDataset(ctx context.Context, employeesJSON, historyCSV []byte) (bootstrap.Report, error) {
	return bootstrap.AppendTo(ctx, r.db, employeesJSON, historyCSV)
}
