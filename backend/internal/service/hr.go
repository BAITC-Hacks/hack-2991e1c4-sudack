package service

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"

	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/domain/career"
)

type batchResult struct {
	EmployeeID    string            `json:"employee_id"`
	Top           []json.RawMessage `json:"top"`
	Gaps          map[string]int    `json:"gaps"`
	Readiness     float64           `json:"readiness"`
	Participation json.RawMessage   `json:"participation"`
	Risk          json.RawMessage   `json:"risk"`
}

func (s *Service) allRequests(ctx context.Context) ([]*career.Request, error) {
	catalog, err := s.repository.LoadCatalog(ctx)
	if err != nil {
		return nil, err
	}
	ids, err := s.repository.EmployeeIDs(ctx)
	if err != nil {
		return nil, err
	}
	requests := make([]*career.Request, 0, len(ids))
	for _, id := range ids {
		request, err := s.repository.LoadRequest(ctx, id, catalog)
		if err != nil {
			return nil, fmt.Errorf("load employee %s for HR: %w", id, err)
		}
		if request.NextGrade != "" {
			requests = append(requests, request)
		}
	}
	return requests, nil
}

func (s *Service) HROverview(ctx context.Context) (map[string]any, error) {
	requests, err := s.allRequests(ctx)
	if err != nil {
		return nil, err
	}
	stats, err := s.repository.ActivityStats(ctx)
	if err != nil {
		return nil, err
	}
	if len(requests) == 0 {
		return map[string]any{
			"employees_scored": 0, "skills_below_target": []any{},
			"without_recommended_step": []string{}, "participation_by_event": stats,
		}, nil
	}
	raw, err := s.callAI(ctx, "/score/batch", map[string]any{"items": requests})
	if err != nil {
		return nil, err
	}
	var batch struct {
		Results []batchResult `json:"results"`
	}
	if err := json.Unmarshal(raw, &batch); err != nil {
		return nil, fmt.Errorf("decode AI batch response: %w", err)
	}
	counts := make(map[string]int)
	missing := make(map[string]int)
	without := make([]string, 0)
	risk := make([]map[string]any, 0, len(batch.Results))
	for _, item := range batch.Results {
		for skill, gap := range item.Gaps {
			counts[skill]++
			missing[skill] += gap
		}
		if len(item.Top) == 0 {
			without = append(without, item.EmployeeID)
		}
		risk = append(risk, map[string]any{
			"employee_id": item.EmployeeID, "readiness": item.Readiness,
			"participation": item.Participation, "risk": item.Risk,
		})
	}
	skills := make([]map[string]any, 0, len(counts))
	for id, count := range counts {
		skills = append(skills, map[string]any{
			"skill_id": id, "employees_below_target": count,
			"total_missing_levels": missing[id],
		})
	}
	sort.Slice(skills, func(i, j int) bool {
		left := skills[i]["employees_below_target"].(int)
		right := skills[j]["employees_below_target"].(int)
		if left != right {
			return left > right
		}
		return skills[i]["skill_id"].(string) < skills[j]["skill_id"].(string)
	})
	return map[string]any{
		"employees_scored":         len(batch.Results),
		"skills_below_target":      skills,
		"without_recommended_step": without,
		"participation_by_event":   stats,
		"engagement_risk":          risk,
	}, nil
}

func (s *Service) EventImpact(ctx context.Context, event json.RawMessage) (json.RawMessage, error) {
	requests, err := s.allRequests(ctx)
	if err != nil {
		return nil, err
	}
	return s.callAI(ctx, "/events/impact", map[string]any{
		"event": event,
		"items": requests,
	})
}

func (s *Service) EmployeeIDs(ctx context.Context) ([]string, error) {
	return s.repository.EmployeeIDs(ctx)
}
