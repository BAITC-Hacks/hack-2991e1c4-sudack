package bootstrap

import "encoding/json"

type skillDataset struct {
	Meta             json.RawMessage `json:"meta"`
	ProficiencyScale json.RawMessage `json:"proficiency_scale"`
	Skills           []skill         `json:"skills"`
	RoleProfiles     []roleProfile   `json:"role_profiles"`
}

type skill struct {
	ID          string `json:"skill_id"`
	Name        string `json:"name"`
	Type        string `json:"type"`
	Category    string `json:"category"`
	Description string `json:"description"`
}

type roleProfile struct {
	Role           string         `json:"role"`
	Grade          string         `json:"grade"`
	RequiredSkills map[string]int `json:"required_skills"`
	CriticalSkills []string       `json:"critical_skills"`
}

type employeeDataset struct {
	Meta      json.RawMessage `json:"meta"`
	Employees []employee      `json:"employees"`
}

type employee struct {
	ID                string         `json:"employee_id"`
	FullName          string         `json:"full_name"`
	Department        string         `json:"department"`
	Role              string         `json:"role"`
	Grade             string         `json:"grade"`
	ManagerID         *string        `json:"manager_id"`
	HireDate          string         `json:"hire_date"`
	TenureMonths      int            `json:"tenure_months"`
	WorkFormat        string         `json:"work_format"`
	PreferredLanguage string         `json:"preferred_language"`
	CareerGoal        *careerGoal    `json:"career_goal"`
	Skills            map[string]int `json:"skills"`
	LastReviewDate    string         `json:"last_review_date"`
}

type careerGoal struct {
	TargetRole  string `json:"target_role"`
	TargetGrade string `json:"target_grade"`
}

type eventDataset struct {
	Meta   json.RawMessage `json:"meta"`
	Events []event         `json:"events"`
}

type event struct {
	ID               string         `json:"event_id"`
	Title            string         `json:"title"`
	Description      string         `json:"description"`
	Type             string         `json:"type"`
	Format           string         `json:"format"`
	DurationHours    float64        `json:"duration_hours"`
	Mandatory        bool           `json:"mandatory"`
	TargetRoles      []string       `json:"target_roles"`
	TargetGrades     []string       `json:"target_grades"`
	DevelopsSkills   []eventEffect  `json:"develops_skills"`
	Prerequisites    map[string]int `json:"prerequisites"`
	UpcomingSessions []string       `json:"upcoming_sessions"`
}

type eventEffect struct {
	SkillID  string `json:"skill_id"`
	Gain     int    `json:"gain"`
	MaxLevel int    `json:"max_level"`
}
