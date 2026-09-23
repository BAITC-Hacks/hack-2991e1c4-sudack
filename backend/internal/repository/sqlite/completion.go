package sqlite

import (
	"context"
	"database/sql"
	"errors"
	"fmt"

	"github.com/mattn/go-sqlite3"
)

var ErrCompletionConflict = errors.New("activity already completed or idempotency key reused")

func (r *Repository) CompletionByKey(ctx context.Context, employeeID, key string) (string, bool, error) {
	var eventID string
	err := r.db.QueryRowContext(ctx,
		"SELECT event_id FROM activity_history WHERE employee_id = ? AND idempotency_key = ?",
		employeeID, key).Scan(&eventID)
	if errors.Is(err, sql.ErrNoRows) {
		return "", false, nil
	}
	if err != nil {
		return "", false, fmt.Errorf("lookup completion key: %w", err)
	}
	return eventID, true, nil
}

func (r *Repository) Complete(ctx context.Context, employeeID, eventID, key, date string, recurring bool) (bool, error) {
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return false, fmt.Errorf("begin completion: %w", err)
	}
	defer tx.Rollback()

	var previousEvent string
	err = tx.QueryRowContext(ctx,
		"SELECT event_id FROM activity_history WHERE employee_id = ? AND idempotency_key = ?",
		employeeID, key).Scan(&previousEvent)
	if err == nil {
		if previousEvent == eventID {
			return true, nil
		}
		return false, ErrCompletionConflict
	}
	if !errors.Is(err, sql.ErrNoRows) {
		return false, fmt.Errorf("lookup completion key: %w", err)
	}

	if !recurring {
		var completed int
		err = tx.QueryRowContext(ctx,
			"SELECT EXISTS(SELECT 1 FROM activity_history WHERE employee_id = ? AND event_id = ? AND status = 'completed')",
			employeeID, eventID).Scan(&completed)
		if err != nil {
			return false, fmt.Errorf("check previous completion: %w", err)
		}
		if completed != 0 {
			return false, ErrCompletionConflict
		}
	}

	_, err = tx.ExecContext(ctx,
		"INSERT INTO activity_history(employee_id, event_id, occurred_at, status, completion_pct, assigned_by, source, idempotency_key) VALUES (?, ?, ?, 'completed', 100, 'app', 'app', ?)",
		employeeID, eventID, date, key)
	if err != nil {
		var sqliteErr sqlite3.Error
		if errors.As(err, &sqliteErr) && sqliteErr.Code == sqlite3.ErrConstraint {
			return false, ErrCompletionConflict
		}
		return false, fmt.Errorf("insert completion: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return false, fmt.Errorf("commit completion: %w", err)
	}
	return false, nil
}
