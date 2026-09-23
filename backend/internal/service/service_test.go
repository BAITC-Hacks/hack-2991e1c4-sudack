package service

import (
	"context"
	"database/sql"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/bootstrap"
	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/domain/career"
	"github.com/BAITC-Hacks/hack-2991e1c4-sudack/internal/repository/sqlite"
	_ "github.com/mattn/go-sqlite3"
)

// fakeAI answers like Sudack AI and checks how the catalog is sent.
func fakeAI(t *testing.T) *httptest.Server {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		var payload map[string]any
		if err := json.Unmarshal(body, &payload); err != nil {
			t.Errorf("invalid JSON sent to AI: %v", err)
		}
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/recommend":
			if _, ok := payload["events"]; !ok {
				t.Errorf("/recommend must carry the event catalog")
			}
			_, _ = w.Write([]byte(`{"recommendations":[{"event_id":"EV_006","title":"Designing High-Load Systems","score":2.1,"reason":"r","reason_source":"template","factors":[],"calculation":{"gap_closed":2.5,"engagement":0.5,"formula":"f"}}],"readiness":{"current":0.6,"after_top":0.7},"gaps":{"SK_SYSTEM_DESIGN":2},"applied_progress":[],"rejected":[],"source":"fallback","llm_provider":null,"llm_model":null}`))
		case "/score/batch", "/events/impact":
			if _, ok := payload["events"]; !ok {
				t.Errorf("%s must carry the shared catalog", r.URL.Path)
			}
			items, _ := payload["items"].([]any)
			results := make([]map[string]any, 0, len(items))
			for index, raw := range items {
				item := raw.(map[string]any)
				if _, has := item["events"]; has {
					t.Errorf("batch items must not repeat the catalog")
				}
				employee := item["employee"].(map[string]any)
				level := "low"
				if index == 0 {
					level = "high"
				}
				results = append(results, map[string]any{
					"employee_id":   employee["employee_id"],
					"top":           []any{map[string]any{"event_id": "EV_006", "score": 1.0, "primary_skill": "SK_SYSTEM_DESIGN"}},
					"readiness":     0.5,
					"gaps":          map[string]int{"SK_SYSTEM_DESIGN": 1},
					"participation": map[string]any{"completed": 1, "missed": 0, "in_progress": 0, "total": 1, "last_activity_date": nil},
					"risk":          map[string]any{"score": 0.7, "level": level, "reasons": []any{}, "suggested_format": nil},
				})
			}
			if r.URL.Path == "/events/impact" {
				_ = json.NewEncoder(w).Encode(map[string]any{"event_id": "EV_DRAFT", "gap_closing_count": len(items)})
				return
			}
			_ = json.NewEncoder(w).Encode(map[string]any{"results": results})
		default:
			http.Error(w, "unexpected path "+r.URL.Path, http.StatusNotFound)
		}
	}))
	t.Cleanup(server.Close)
	return server
}

func newTestService(t *testing.T) (*Service, string) {
	t.Helper()
	repoRoot, err := filepath.Abs(filepath.Join("..", "..", ".."))
	if err != nil {
		t.Fatal(err)
	}
	data := filepath.Join(repoRoot, "sudack-ai", "docs", "data")
	if _, err := os.Stat(filepath.Join(data, "employees.json")); err != nil {
		t.Skip("starter kit not available")
	}
	dbPath := filepath.Join(t.TempDir(), "test.db")
	created, err := bootstrap.Initialize(context.Background(), dbPath, data)
	if err != nil || !created {
		t.Fatalf("initialize: created=%v err=%v", created, err)
	}
	db, err := sql.Open("sqlite3", dbPath+"?_foreign_keys=on&_busy_timeout=5000")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { db.Close() })
	repo, _ := sqlite.NewRepository(db)
	svc, _ := NewService(repo, fakeAI(t).URL)
	return svc, filepath.Join(repoRoot, "docs", "jury-profiles")
}

func TestProfileHasFrontendShape(t *testing.T) {
	svc, _ := newTestService(t)
	profile, err := svc.Profile(context.Background(), "E0028", "")
	if err != nil {
		t.Fatal(err)
	}
	gaps, ok := profile["gaps"].([]career.GapView)
	if !ok || len(gaps) == 0 {
		t.Fatalf("gaps must be a non-empty table, got %T", profile["gaps"])
	}
	if gaps[0].Name == "" || gaps[0].Name == gaps[0].SkillID {
		t.Errorf("gap rows must carry skill names, got %+v", gaps[0])
	}
	if !gaps[0].Critical {
		t.Errorf("critical skills must sort first, got %+v", gaps[0])
	}
	if profile["next_grade"] != "Senior" {
		t.Errorf("E0028 is Middle, next grade must be Senior, got %v", profile["next_grade"])
	}
	percent, ok := profile["readiness_percent"].(float64)
	if !ok || percent <= 0 || percent > 100 {
		t.Errorf("readiness_percent must be in (0, 100], got %v", profile["readiness_percent"])
	}
}

func TestRecommendationsAreEnrichedWithCatalogFacts(t *testing.T) {
	svc, _ := newTestService(t)
	raw, err := svc.Recommend(context.Background(), "E0028", "")
	if err != nil {
		t.Fatal(err)
	}
	var payload struct {
		Recommendations []map[string]any `json:"recommendations"`
	}
	if err := json.Unmarshal(raw, &payload); err != nil {
		t.Fatal(err)
	}
	if len(payload.Recommendations) != 1 {
		t.Fatalf("expected the AI recommendation to pass through, got %d", len(payload.Recommendations))
	}
	item := payload.Recommendations[0]
	if item["type"] != "workshop" || item["format"] != "offline" || item["duration_hours"] == nil {
		t.Errorf("recommendation must carry type, format and duration from the catalog, got %v", item)
	}
}

func TestHROverviewMatchesFrontendShape(t *testing.T) {
	svc, _ := newTestService(t)
	overview, err := svc.HROverview(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if overview["employee_count"] != 200 || overview["event_count"] != 40 {
		t.Errorf("counts: %v employees, %v events", overview["employee_count"], overview["event_count"])
	}
	weak := overview["weak_skills"].([]map[string]any)
	if len(weak) == 0 || weak[0]["name"] == "" {
		t.Fatalf("weak_skills must be named rows, got %v", weak)
	}
	risks := overview["risks"].([]map[string]any)
	if len(risks) != 1 || risks[0]["full_name"] == "" {
		t.Errorf("only non-low risks with names are listed, got %v", risks)
	}
	participation := overview["participation"].([]map[string]any)
	if len(participation) == 0 || participation[0]["completion_rate"] == nil {
		t.Errorf("participation rows need completion_rate, got %v", participation)
	}
}

func TestImportAppendsJuryProfilesIdempotently(t *testing.T) {
	svc, juryDir := newTestService(t)
	employees, err := os.ReadFile(filepath.Join(juryDir, "employees.json"))
	if err != nil {
		t.Skip("jury profiles not available")
	}
	history, _ := os.ReadFile(filepath.Join(juryDir, "activity_history.csv"))

	first, err := svc.Import(context.Background(), employees, history)
	if err != nil {
		t.Fatal(err)
	}
	imported := first["imported"].(map[string]int)
	if imported["employees"] != 3 || imported["history"] != 11 {
		t.Errorf("first import should add 3 employees and 11 rows, got %v", imported)
	}
	second, err := svc.Import(context.Background(), employees, history)
	if err != nil {
		t.Fatal(err)
	}
	unchanged := second["unchanged"].(map[string]int)
	if second["imported"].(map[string]int)["employees"] != 0 || unchanged["employees"] != 3 || unchanged["history"] != 11 {
		t.Errorf("second import must be a no-op, got %v / %v", second["imported"], unchanged)
	}
	profile, err := svc.Profile(context.Background(), "E0901", "")
	if err != nil {
		t.Fatal(err)
	}
	if profile["next_grade"] != "Senior" {
		t.Errorf("jury profile E0901 must target Senior, got %v", profile["next_grade"])
	}
	if _, err := svc.Import(context.Background(), []byte(`{"employees":[{"employee_id":"E0999"}]}`), nil); err == nil {
		t.Errorf("an incomplete employee must be rejected")
	}
}

func TestCompletionMovesProgressOnce(t *testing.T) {
	svc, _ := newTestService(t)
	ctx := context.Background()
	before, _ := svc.Profile(ctx, "E0028", "")
	result, err := svc.Complete(ctx, "E0028", "EV_037", "key-1")
	if err != nil {
		t.Fatal(err)
	}
	if result["replayed"] != false {
		t.Errorf("first completion must not be a replay")
	}
	after := result["profile"].(map[string]any)
	if after["readiness"].(float64) <= before["readiness"].(float64) {
		t.Errorf("completing a gap-closing event must raise readiness: %v -> %v", before["readiness"], after["readiness"])
	}
	replay, err := svc.Complete(ctx, "E0028", "EV_037", "key-1")
	if err != nil || replay["replayed"] != true {
		t.Errorf("same key must replay, got %v err=%v", replay, err)
	}
	if _, err := svc.Complete(ctx, "E0028", "EV_037", "key-2"); err == nil {
		t.Errorf("a non-recurring event cannot be completed twice")
	}
}
