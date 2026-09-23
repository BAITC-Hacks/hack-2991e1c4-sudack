package career

type Employee struct {
	ID                string         `json:"employee_id"`
	Role              string         `json:"role"`
	Grade             string         `json:"grade"`
	TenureMonths      int            `json:"tenure_months"`
	PreferredLanguage string         `json:"preferred_language"`
	LastReviewDate    string         `json:"last_review_date"`
	Skills            map[string]int `json:"skills"`
}

type SkillMeta struct {
	Name     string `json:"name"`
	Category string `json:"category"`
}

type SkillGain struct {
	Gain     int `json:"gain"`
	MaxLevel int `json:"max_level"`
}

type Audience struct {
	Roles  []string `json:"roles"`
	Grades []string `json:"grades"`
}

type Event struct {
	ID               string               `json:"event_id"`
	Title            string               `json:"title"`
	Type             string               `json:"type"`
	Description      string               `json:"description"`
	Format           string               `json:"format"`
	DurationHours    float64              `json:"duration_hours"`
	UpcomingSessions []string             `json:"upcoming_sessions"`
	Audience         Audience             `json:"audience"`
	Skills           map[string]SkillGain `json:"skills"`
	Mandatory        bool                 `json:"mandatory"`
	Prerequisites    map[string]int       `json:"prerequisites"`
	Recurring        bool                 `json:"recurring"`
}

type HistoryEntry struct {
	EventID string `json:"event_id"`
	Status  string `json:"status"`
	Date    string `json:"date"`
}

type Request struct {
	Employee              Employee             `json:"employee"`
	NextGrade             string               `json:"next_grade"`
	NextGradeRequirements map[string]int       `json:"next_grade_requirements"`
	CriticalSkills        []string             `json:"critical_skills"`
	SkillsMeta            map[string]SkillMeta `json:"skills_meta"`
	History               []HistoryEntry       `json:"history"`
	Events                []Event              `json:"events"`
	Lang                  string               `json:"lang"`
	AsOf                  string               `json:"as_of"`
}

type SkillProgress struct {
	SkillID   string `json:"skill_id"`
	Before    int    `json:"before"`
	After     int    `json:"after"`
	Required  int    `json:"required"`
	GapBefore int    `json:"gap_before"`
	GapAfter  int    `json:"gap_after"`
}
