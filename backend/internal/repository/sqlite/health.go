package sqlite

import (
	"context"
	"fmt"
)

func (r *Repository) Health(ctx context.Context) error {
	value, err := New(r.db).Select1(ctx)
	if err != nil {
		return fmt.Errorf("sqlite health check: %w", err)
	}

	if value != 1 {
		return fmt.Errorf("sqlite health check: unexpected result %d", value)
	}

	return nil
}
