package service

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"sort"

	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/domain/career"
	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/domain/errs"
	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/repository/sqlite"
)

type batchResult struct {
	EmployeeID    string            `json:"employee_id"`
	Top           []json.RawMessage `json:"top"`
	Gaps          map[string]int    `json:"gaps"`
	Readiness     float64           `json:"readiness"`
	Participation json.RawMessage   `json:"participation"`
	Risk          json.RawMessage   `json:"risk"`
}

type riskLevel struct {
	Score float64 `json:"score"`
	Level string  `json:"level"`
}

// allRequests loads every employee with a target grade. Events and skills metadata are stripped
// from each item so the batch payload carries the catalog once (the AI service supports that).
func (s *Service) allRequests(ctx context.Context) (*sqlite.Catalog, []*career.Request, error) {
	catalog, err := s.repository.LoadCatalog(ctx)
	if err != nil {
		return nil, nil, err
	}
	ids, err := s.repository.EmployeeIDs(ctx)
	if err != nil {
		return nil, nil, err
	}
	requests := make([]*career.Request, 0, len(ids))
	for _, id := range ids {
		request, err := s.repository.LoadRequest(ctx, id, catalog)
		if err != nil {
			return nil, nil, fmt.Errorf("load employee %s for HR: %w", id, err)
		}
		if request.NextGrade == "" {
			continue
		}
		request.Events = nil
		request.SkillsMeta = nil
		requests = append(requests, request)
	}
	return catalog, requests, nil
}

func sharedPayload(catalog *sqlite.Catalog, requests []*career.Request, extra map[string]any) map[string]any {
	payload := map[string]any{
		"events":      catalog.Events,
		"skills_meta": catalog.SkillsMeta,
		"items":       requests,
	}
	for key, value := range extra {
		payload[key] = value
	}
	return payload
}

// HROverview returns the HR screen in the shape the frontend renders: weak skills, employees
// without a useful step, participation per activity, and dropout risk. No public ranking.
func (s *Service) HROverview(ctx context.Context) (map[string]any, error) {
	catalog, requests, err := s.allRequests(ctx)
	if err != nil {
		return nil, err
	}
	summaries, err := s.repository.EmployeeSummaries(ctx)
	if err != nil {
		return nil, err
	}
	stats, err := s.repository.ActivityStats(ctx)
	if err != nil {
		return nil, err
	}
	participation := make([]map[string]any, 0, len(stats))
	for _, row := range stats {
		completed := row["completed"].(int)
		skipped := row["no_show"].(int) + row["dropped"].(int) + row["overdue"].(int)
		declined := row["declined"].(int)
		decided := completed + skipped + declined
		if decided == 0 {
			continue
		}
		participation = append(participation, map[string]any{
			"event_id": row["event_id"], "title": row["title"],
			"completed": completed, "skipped": skipped, "declined": declined,
			"in_progress": row["in_progress"], "no_show": row["no_show"], "dropped": row["dropped"], "overdue": row["overdue"],
			"completion_rate": int(math.Round(100 * float64(completed) / float64(decided))),
		})
	}
	sort.Slice(participation, func(i, j int) bool {
		return participation[i]["completion_rate"].(int) < participation[j]["completion_rate"].(int)
	})

	overview := map[string]any{
		"employee_count":    len(summaries),
		"event_count":       len(catalog.Events),
		"employees_scored":  0,
		"weak_skills":       []any{},
		"no_recommendation": []any{},
		"risks":             []any{},
		"participation":     participation,
		"ai":                false,
	}
	if len(requests) == 0 {
		return overview, nil
	}
	raw, err := s.callAI(ctx, "/score/batch", sharedPayload(catalog, requests, nil))
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
	noStep := make([]map[string]any, 0)
	type riskRow struct {
		row   map[string]any
		score float64
	}
	riskRows := make([]riskRow, 0)
	for _, item := range batch.Results {
		for skill, gap := range item.Gaps {
			counts[skill]++
			missing[skill] += gap
		}
		who := summaries[item.EmployeeID]
		if len(item.Top) == 0 {
			noStep = append(noStep, map[string]any{
				"employee_id": item.EmployeeID, "full_name": who.FullName, "role": who.Role, "grade": who.Grade,
				"reason": "no_eligible_gap_closing_event",
			})
		}
		var level riskLevel
		_ = json.Unmarshal(item.Risk, &level)
		if level.Level != "" && level.Level != "low" {
			riskRows = append(riskRows, riskRow{score: level.Score, row: map[string]any{
				"employee_id": item.EmployeeID, "full_name": who.FullName, "role": who.Role, "grade": who.Grade,
				"readiness": item.Readiness, "participation": item.Participation, "risk": item.Risk,
			}})
		}
	}
	sort.Slice(riskRows, func(i, j int) bool {
		if riskRows[i].score != riskRows[j].score {
			return riskRows[i].score > riskRows[j].score
		}
		return riskRows[i].row["employee_id"].(string) < riskRows[j].row["employee_id"].(string)
	})
	risks := make([]map[string]any, 0, len(riskRows))
	for _, item := range riskRows {
		risks = append(risks, item.row)
	}

	weak := make([]map[string]any, 0, len(counts))
	for id, count := range counts {
		name := id
		if meta, ok := catalog.SkillsMeta[id]; ok && meta.Name != "" {
			name = meta.Name
		}
		weak = append(weak, map[string]any{
			"skill_id": id, "name": name, "employee_count": count, "missing_levels": missing[id],
		})
	}
	sort.Slice(weak, func(i, j int) bool {
		left, right := weak[i]["employee_count"].(int), weak[j]["employee_count"].(int)
		if left != right {
			return left > right
		}
		return weak[i]["skill_id"].(string) < weak[j]["skill_id"].(string)
	})

	overview["employees_scored"] = len(batch.Results)
	overview["weak_skills"] = weak
	overview["no_recommendation"] = noStep
	overview["risks"] = risks
	overview["ai"] = true
	return overview, nil
}

// EventImpact forwards a draft event (compact or starter-kit shape) to the AI service with the whole workforce.
func (s *Service) EventImpact(ctx context.Context, event json.RawMessage) (json.RawMessage, error) {
	catalog, requests, err := s.allRequests(ctx)
	if err != nil {
		return nil, err
	}
	return s.callAI(ctx, "/events/impact", sharedPayload(catalog, requests, map[string]any{"event": event}))
}

func (s *Service) EmployeeIDs(ctx context.Context) ([]string, error) {
	return s.repository.EmployeeIDs(ctx)
}

// EmployeeSummaries lists every employee with display fields (name, department, role, grade).
func (s *Service) EmployeeSummaries(ctx context.Context) (map[string]sqlite.EmployeeSummary, error) {
	return s.repository.EmployeeSummaries(ctx)
}

// Import appends jury profiles and history in the starter-kit format. Existing rows are left untouched.
func (s *Service) Import(ctx context.Context, employeesJSON, historyCSV []byte) (map[string]any, error) {
	if len(bytes.TrimSpace(employeesJSON)) == 0 && len(bytes.TrimSpace(historyCSV)) == 0 {
		return nil, errs.NewError(http.StatusBadRequest, "IMPORT_EMPTY", "attach employees.json and/or activity_history.csv")
	}
	report, err := s.repository.AppendDataset(ctx, employeesJSON, historyCSV)
	if err != nil {
		return nil, errs.NewError(http.StatusUnprocessableEntity, "IMPORT_REJECTED", err.Error())
	}
	return map[string]any{
		"imported":  map[string]int{"employees": report.EmployeesAdded, "history": report.HistoryAdded},
		"unchanged": map[string]int{"employees": report.EmployeesUnchanged, "history": report.HistoryUnchanged},
	}, nil
}
