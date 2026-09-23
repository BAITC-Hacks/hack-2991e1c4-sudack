package service

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"net/http"
	"sort"
	"time"

	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/domain/career"
	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/domain/errs"
	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/repository/sqlite"
)

func (s *Service) request(ctx context.Context, employeeID, lang string, catalog *sqlite.Catalog) (*career.Request, error) {
	if catalog == nil {
		var err error
		catalog, err = s.repository.LoadCatalog(ctx)
		if err != nil {
			return nil, err
		}
	}
	request, err := s.repository.LoadRequest(ctx, employeeID, catalog)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, errs.NewError(http.StatusNotFound, "EMPLOYEE_NOT_FOUND", "employee not found")
	}
	if err != nil {
		return nil, fmt.Errorf("load employee context: %w", err)
	}
	if lang != "" {
		if lang != "ru" && lang != "kk" && lang != "en" {
			return nil, errs.ErrInvalidParameter
		}
		request.Lang = lang
	}
	return request, nil
}

// effectiveSkills applies completions recorded after the last assessment, exactly like the AI service.
func effectiveSkills(request *career.Request) map[string]int {
	skills := make(map[string]int, len(request.Employee.Skills))
	for id, level := range request.Employee.Skills {
		skills[id] = level
	}
	catalog := make(map[string]career.Event, len(request.Events))
	for _, event := range request.Events {
		catalog[event.ID] = event
	}
	for _, entry := range request.History {
		if entry.Status != "completed" || entry.Date <= request.Employee.LastReviewDate {
			continue
		}
		event, ok := catalog[entry.EventID]
		if !ok {
			continue
		}
		for id, gain := range event.Skills {
			next := skills[id] + gain.Gain
			if next > gain.MaxLevel {
				next = gain.MaxLevel
			}
			if next > skills[id] {
				skills[id] = next
			}
		}
	}
	return skills
}

// readiness mirrors the AI service: critical gaps weigh 2.5, other required skills 1.5.
func readiness(request *career.Request, skills map[string]int) float64 {
	var earned, total float64
	critical := make(map[string]bool, len(request.CriticalSkills))
	for _, id := range request.CriticalSkills {
		critical[id] = true
	}
	for id, required := range request.NextGradeRequirements {
		if required <= 0 {
			continue
		}
		weight := 1.5
		if critical[id] {
			weight = 2.5
		}
		total += float64(required) * weight
		level := skills[id]
		if level > required {
			level = required
		}
		earned += float64(level) * weight
	}
	if total == 0 {
		return 0
	}
	return earned / total
}

func gapViews(request *career.Request, skills map[string]int) []career.GapView {
	critical := make(map[string]bool, len(request.CriticalSkills))
	for _, id := range request.CriticalSkills {
		critical[id] = true
	}
	views := make([]career.GapView, 0, len(request.NextGradeRequirements))
	for id, required := range request.NextGradeRequirements {
		name := id
		if meta, ok := request.SkillsMeta[id]; ok && meta.Name != "" {
			name = meta.Name
		}
		views = append(views, career.GapView{
			SkillID: id, Name: name, Current: skills[id], Required: required,
			Gap: max(0, required-skills[id]), Critical: critical[id],
		})
	}
	sort.Slice(views, func(i, j int) bool {
		if views[i].Critical != views[j].Critical {
			return views[i].Critical
		}
		if views[i].Gap != views[j].Gap {
			return views[i].Gap > views[j].Gap
		}
		return views[i].SkillID < views[j].SkillID
	})
	return views
}

func (s *Service) Profile(ctx context.Context, employeeID, lang string) (map[string]any, error) {
	request, err := s.request(ctx, employeeID, lang, nil)
	if err != nil {
		return nil, err
	}
	name, department, err := s.repository.EmployeeDetails(ctx, employeeID)
	if err != nil {
		return nil, fmt.Errorf("load employee details: %w", err)
	}
	current := effectiveSkills(request)
	titles := make(map[string]string, len(request.Events))
	for _, event := range request.Events {
		titles[event.ID] = event.Title
	}
	progress := make([]map[string]any, 0)
	for id, after := range current {
		before := request.Employee.Skills[id]
		if after > before {
			progress = append(progress, map[string]any{
				"skill_id": id, "from": before, "to": after,
				"source": "completed_activities_after_review",
			})
		}
	}
	sort.Slice(progress, func(i, j int) bool {
		return progress[i]["skill_id"].(string) < progress[j]["skill_id"].(string)
	})
	completed := make([]map[string]any, 0)
	for _, entry := range request.History {
		if entry.Status == "completed" {
			completed = append(completed, map[string]any{
				"event_id": entry.EventID, "title": titles[entry.EventID], "date": entry.Date,
			})
		}
	}
	// Newest first for the timeline.
	history := make([]career.HistoryEntry, len(request.History))
	copy(history, request.History)
	sort.SliceStable(history, func(i, j int) bool { return history[i].Date > history[j].Date })

	ready := readiness(request, current)
	var nextGrade any
	var readinessPercent any
	if request.NextGrade != "" {
		nextGrade = request.NextGrade
		readinessPercent = math.Round(ready*1000) / 10
	}
	return map[string]any{
		"employee_id":          employeeID,
		"full_name":            name,
		"department":           department,
		"role":                 request.Employee.Role,
		"grade":                request.Employee.Grade,
		"tenure_months":        request.Employee.TenureMonths,
		"preferred_language":   request.Employee.PreferredLanguage,
		"last_review_date":     request.Employee.LastReviewDate,
		"next_grade":           nextGrade,
		"skills":               current,
		"assessment_skills":    request.Employee.Skills,
		"skills_meta":          request.SkillsMeta,
		"required_skills":      request.NextGradeRequirements,
		"critical_skills":      request.CriticalSkills,
		"gaps":                 gapViews(request, current),
		"readiness":            ready,
		"readiness_percent":    readinessPercent,
		"completed_activities": completed,
		"applied_progress":     progress,
		"history":              history,
	}, nil
}

// Recommend forwards the AI verdict and adds catalog facts (type, format, hours) the UI shows on each card.
func (s *Service) Recommend(ctx context.Context, employeeID, lang string) (json.RawMessage, error) {
	request, err := s.request(ctx, employeeID, lang, nil)
	if err != nil {
		return nil, err
	}
	if request.NextGrade == "" {
		return json.RawMessage(`{"recommendations":[],"readiness":{"current":1,"after_top":1},"gaps":{},"applied_progress":[],"rejected":[],"source":"fallback","llm_provider":null,"llm_model":null,"reason":"no_next_grade"}`), nil
	}
	raw, err := s.callAI(ctx, "/recommend", request)
	if err != nil {
		return nil, err
	}
	return enrichRecommendations(raw, request.Events)
}

func enrichRecommendations(raw json.RawMessage, events []career.Event) (json.RawMessage, error) {
	var payload map[string]any
	if err := json.Unmarshal(raw, &payload); err != nil {
		return raw, nil
	}
	items, ok := payload["recommendations"].([]any)
	if !ok {
		return raw, nil
	}
	byID := make(map[string]career.Event, len(events))
	for _, event := range events {
		byID[event.ID] = event
	}
	for _, item := range items {
		entry, ok := item.(map[string]any)
		if !ok {
			continue
		}
		id, _ := entry["event_id"].(string)
		if event, found := byID[id]; found {
			entry["type"] = event.Type
			entry["format"] = event.Format
			entry["duration_hours"] = event.DurationHours
			entry["upcoming_sessions"] = event.UpcomingSessions
		}
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		return raw, nil
	}
	return encoded, nil
}

func (s *Service) Simulate(ctx context.Context, employeeID, lang string) (json.RawMessage, error) {
	request, err := s.request(ctx, employeeID, lang, nil)
	if err != nil {
		return nil, err
	}
	if request.NextGrade == "" {
		return nil, errs.NewError(http.StatusConflict, "NO_NEXT_GRADE", "employee has no target grade")
	}
	return s.callAI(ctx, "/simulate", request)
}

func (s *Service) Preview(ctx context.Context, employeeID, eventID string) (map[string]any, error) {
	request, err := s.request(ctx, employeeID, "", nil)
	if err != nil {
		return nil, err
	}
	current := effectiveSkills(request)
	event, err := eligibleEvent(request, current, eventID)
	if err != nil {
		return nil, err
	}
	after := make(map[string]int, len(current))
	for id, level := range current {
		after[id] = level
	}
	changes := make([]career.SkillProgress, 0, len(event.Skills))
	for skillID, gain := range event.Skills {
		before := current[skillID]
		next := before + gain.Gain
		if next > gain.MaxLevel {
			next = gain.MaxLevel
		}
		if next < before {
			next = before
		}
		after[skillID] = next
		required := request.NextGradeRequirements[skillID]
		gapBefore, gapAfter := max(0, required-before), max(0, required-next)
		changes = append(changes, career.SkillProgress{
			SkillID: skillID, Before: before, After: next, Required: required,
			GapBefore: gapBefore, GapAfter: gapAfter,
		})
	}
	sort.Slice(changes, func(i, j int) bool { return changes[i].SkillID < changes[j].SkillID })
	return map[string]any{
		"event_id":         eventID,
		"skill_effects":    changes,
		"readiness_before": readiness(request, current),
		"readiness_after":  readiness(request, after),
	}, nil
}

func eligibleEvent(request *career.Request, skills map[string]int, eventID string) (*career.Event, error) {
	for index := range request.Events {
		event := &request.Events[index]
		if event.ID != eventID {
			continue
		}
		if event.Mandatory || !containsOrEmpty(event.Audience.Roles, request.Employee.Role) ||
			!containsOrEmpty(event.Audience.Grades, request.Employee.Grade) {
			return nil, errs.NewError(http.StatusConflict, "EVENT_NOT_ELIGIBLE", "event is not available for this employee")
		}
		for id, required := range event.Prerequisites {
			if skills[id] < required {
				return nil, errs.NewError(http.StatusConflict, "PREREQUISITES_NOT_MET", "event prerequisites are not met")
			}
		}
		if event.Format != "self_paced" {
			scheduled := false
			for _, date := range event.UpcomingSessions {
				if date >= request.AsOf {
					scheduled = true
					break
				}
			}
			if !scheduled {
				return nil, errs.NewError(http.StatusConflict, "EVENT_UNSCHEDULED", "event has no upcoming session")
			}
		}
		for _, entry := range request.History {
			if entry.EventID != eventID {
				continue
			}
			if entry.Status == "in_progress" || entry.Status == "overdue" ||
				(entry.Status == "completed" && !event.Recurring) {
				return nil, errs.NewError(http.StatusConflict, "EVENT_ALREADY_TAKEN", "event is already completed or in progress")
			}
		}
		positive := false
		for id, gain := range event.Skills {
			if skills[id] < gain.MaxLevel && gain.Gain > 0 {
				positive = true
				break
			}
		}
		if !positive {
			return nil, errs.NewError(http.StatusConflict, "NO_SKILL_GAIN", "event cannot increase any current skill")
		}
		return event, nil
	}
	return nil, errs.NewError(http.StatusNotFound, "EVENT_NOT_FOUND", "event not found")
}

func containsOrEmpty(values []string, target string) bool {
	if len(values) == 0 {
		return true
	}
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

func (s *Service) Complete(ctx context.Context, employeeID, eventID, key string) (map[string]any, error) {
	if key == "" {
		return nil, errs.NewError(http.StatusBadRequest, "IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key is required")
	}
	previousEvent, found, err := s.repository.CompletionByKey(ctx, employeeID, key)
	if err != nil {
		return nil, err
	}
	if found {
		if previousEvent != eventID {
			return nil, errs.NewError(http.StatusConflict, "COMPLETION_CONFLICT", "idempotency key belongs to another event")
		}
		profile, err := s.Profile(ctx, employeeID, "")
		if err != nil {
			return nil, err
		}
		return map[string]any{"replayed": true, "profile": profile}, nil
	}
	request, err := s.request(ctx, employeeID, "", nil)
	if err != nil {
		return nil, err
	}
	current := effectiveSkills(request)
	event, err := eligibleEvent(request, current, eventID)
	if err != nil {
		return nil, err
	}
	// Completions are dated no earlier than the dataset snapshot so they count as progress after the last review.
	occurredAt := time.Now().UTC().Format("2006-01-02")
	if occurredAt < request.AsOf {
		occurredAt = request.AsOf
	}
	replayed, err := s.repository.Complete(ctx, employeeID, eventID, key, occurredAt, event.Recurring)
	if errors.Is(err, sqlite.ErrCompletionConflict) {
		return nil, errs.NewError(http.StatusConflict, "COMPLETION_CONFLICT", "event already completed")
	}
	if err != nil {
		return nil, err
	}
	profile, err := s.Profile(ctx, employeeID, "")
	if err != nil {
		return nil, err
	}
	return map[string]any{"replayed": replayed, "profile": profile}, nil
}
