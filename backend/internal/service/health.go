package service

import (
	"context"
	"fmt"

	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/domain/errs"
)

func (s *Service) Health(ctx context.Context) error {
	if err := s.repository.Health(ctx); err != nil {
		return fmt.Errorf("%w: %w", errs.ErrDatabaseUnavailable, err)
	}

	return nil
}
