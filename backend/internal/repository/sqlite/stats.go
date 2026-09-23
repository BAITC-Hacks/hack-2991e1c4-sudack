package sqlite

import (
	"context"
	"fmt"
)

func (r *Repository) ActivityStats(ctx context.Context) ([]map[string]any, error) {
	rows, err := r.db.QueryContext(ctx, `
        SELECT e.id, e.title_en,
            SUM(CASE WHEN h.status = 'completed' THEN 1 ELSE 0 END),
            SUM(CASE WHEN h.status = 'no_show' THEN 1 ELSE 0 END),
            SUM(CASE WHEN h.status = 'dropped' THEN 1 ELSE 0 END),
            SUM(CASE WHEN h.status = 'declined' THEN 1 ELSE 0 END),
            SUM(CASE WHEN h.status = 'in_progress' THEN 1 ELSE 0 END),
            SUM(CASE WHEN h.status = 'overdue' THEN 1 ELSE 0 END)
        FROM events e LEFT JOIN activity_history h ON h.event_id = e.id
        GROUP BY e.id ORDER BY e.id
    `)
	if err != nil {
		return nil, fmt.Errorf("activity stats: %w", err)
	}
	defer rows.Close()
	result := make([]map[string]any, 0)
	for rows.Next() {
		var id, title string
		var completed, noShow, dropped, declined, inProgress, overdue int
		if err := rows.Scan(&id, &title, &completed, &noShow, &dropped, &declined, &inProgress, &overdue); err != nil {
			return nil, err
		}
		result = append(result, map[string]any{
			"event_id": id, "title": title, "completed": completed, "no_show": noShow,
			"dropped": dropped, "declined": declined, "in_progress": inProgress, "overdue": overdue,
		})
	}
	return result, rows.Err()
}
