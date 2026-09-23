"""Request and response contracts for the stateless recommendation API."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator


SkillLevel = Annotated[int, Field(ge=0, le=5)]
Language = Literal["ru", "kk", "en"]


class Employee(BaseModel):
    employee_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    grade: str = Field(min_length=1)
    tenure_months: int | None = Field(default=None, ge=0)
    preferred_language: Language | None = None
    last_review_date: str | None = None
    skills: dict[str, SkillLevel]


class SkillMeta(BaseModel):
    name: str
    category: str | None = None


class HistoryEntry(BaseModel):
    event_id: str
    status: str
    date: str | None = None


class Audience(BaseModel):
    roles: list[str] = Field(default_factory=list)
    grades: list[str] = Field(default_factory=list)


class SkillGain(BaseModel):
    gain: int = Field(gt=0)
    max_level: SkillLevel


class Event(BaseModel):
    event_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    type: str
    description: str | None = None
    format: str | None = None
    duration_hours: float | None = Field(default=None, ge=0)
    upcoming_sessions: list[str] | None = None
    audience: Audience = Field(default_factory=Audience)
    skills: dict[str, SkillGain] = Field(default_factory=dict)
    mandatory: bool = False
    prerequisites: dict[str, SkillLevel] = Field(default_factory=dict)
    recurring: bool = False

    @model_validator(mode="before")
    @classmethod
    def accept_dataset_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        result = value.copy()
        if "audience" not in result and ("target_roles" in result or "target_grades" in result):
            result["audience"] = {
                "roles": result.get("target_roles", []),
                "grades": result.get("target_grades", []),
            }
        if "skills" not in result and "develops_skills" in result:
            if not isinstance(result["develops_skills"], list):
                raise ValueError("develops_skills must be a list")
            converted = {}
            for item in result["develops_skills"]:
                if not isinstance(item, dict) or not {"skill_id", "gain", "max_level"} <= item.keys():
                    raise ValueError("Each developed skill needs skill_id, gain and max_level")
                converted[item["skill_id"]] = {"gain": item["gain"], "max_level": item["max_level"]}
            result["skills"] = converted
        # The starter kit marks EV_036 as repeatable in its data documentation.
        if result.get("event_id") == "EV_036" and "recurring" not in result:
            result["recurring"] = True
        return result


class RecommendRequest(BaseModel):
    employee: Employee
    next_grade: str = Field(min_length=1)
    next_grade_requirements: dict[str, SkillLevel]
    critical_skills: list[str] = Field(default_factory=list)
    skills_meta: dict[str, SkillMeta] = Field(default_factory=dict)
    history: list[HistoryEntry] = Field(default_factory=list)
    events: list[Event]
    lang: Language = "ru"
    as_of: str | None = None  # "today" for scheduling and recency; defaults to the latest history date

    @model_validator(mode="before")
    @classmethod
    def default_employee_language(cls, value: Any) -> Any:
        if isinstance(value, dict) and "lang" not in value:
            employee = value.get("employee")
            language = employee.get("preferred_language") if isinstance(employee, dict) else None
            if language:
                return {**value, "lang": language}
        return value


class Readiness(BaseModel):
    current: float
    after_top: float


class Calculation(BaseModel):
    gap_closed: float
    engagement: float
    formula: str


class Recommendation(BaseModel):
    event_id: str
    title: str
    score: float
    reason: str
    reason_source: Literal["llm", "template"] = "template"
    factors: list[dict[str, Any]]
    calculation: Calculation


class RecommendResponse(BaseModel):
    recommendations: list[Recommendation]
    readiness: Readiness
    gaps: dict[str, int] = Field(default_factory=dict)
    applied_progress: list[dict[str, Any]] = Field(default_factory=list)
    rejected: list[dict[str, Any]] = Field(default_factory=list)
    source: Literal["llm", "fallback"]
    llm_provider: str | None = None
    llm_model: str | None = None


class BatchRequest(BaseModel):
    items: list[RecommendRequest]


class BatchTopItem(BaseModel):
    event_id: str
    score: float
    primary_skill: str


class BatchResult(BaseModel):
    employee_id: str
    top: list[BatchTopItem]
    readiness: float
    gaps: dict[str, int] = Field(default_factory=dict)
    participation: dict[str, Any] = Field(default_factory=dict)
    risk: dict[str, Any] = Field(default_factory=dict)


class BatchResponse(BaseModel):
    results: list[BatchResult]


class SimulateResponse(BaseModel):
    as_of: str | None
    next_grade: str
    reachable: bool
    steps: list[dict[str, Any]]
    total_hours: float
    estimated_completion: str | None
    readiness_path: list[float]
    coverage: dict[str, float]
    remaining_gaps: dict[str, int]
    blocked: list[dict[str, Any]]


class ImpactRequest(BaseModel):
    event: Event
    items: list[RecommendRequest]


class ImpactResponse(BaseModel):
    event_id: str
    title: str
    employees: int
    audience_count: int
    gap_closing_count: int
    gap_closing_employees: list[str]
    expected_completions: float
    gap_levels_closed: int
    hours_per_gap_level: float | None
    by_skill: dict[str, int]
    catalog_rank: int
    catalog_top: list[dict[str, Any]]
