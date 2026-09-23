export type Employee = { employee_id:string; full_name?:string; department?:string; role:string; grade:string; tenure_months:number; skills:Record<string,number>; preferred_language?:string; last_review_date?:string; career_goal?:{target_role:string;target_grade:string}|null };
export type Skill = { skill_id:string; name:string; type:string; category:string };
export type RoleProfile = { role:string; grade:string; required_skills:Record<string,number>; critical_skills:string[] };
export type Event = { event_id:string; title:string; description:string; type:string; format:string; duration_hours:number; mandatory:boolean; target_roles:string[]; target_grades:string[]; develops_skills:{skill_id:string;gain:number;max_level:number}[]; prerequisites:Record<string,number>; upcoming_sessions:string[] };
export type History = { record_id?:string; employee_id:string; event_id:string; date:string; status:string };
export type Gap = { skill_id:string; name:string; current:number; required:number; gap:number; critical:boolean };
export type Factor = { type:"grade_requirement"|"skill_gap"|"history"|"effective_gain"; text?:string; skill?:string; name?:string; current?:number; required?:number; from?:number; to?:number; completed?:number; total?:number; missed?:number; critical?:boolean };
export type Recommendation = { event_id:string; title:string; type?:string; duration_hours?:number; score:number; reason:string; reason_source?:"llm"|"template"; factors:Factor[]; calculation:{gap_closed:number;engagement:number;formula:string} };
export type Rejected = { event_id:string|null; title:string|null; skill:string; current:number; required:number|null; score:number|null; reason:string; recommended_position?:number|null };
export type AppliedProgress = { event_id:string; skill:string; from:number; to:number };
export type RecResponse = {
  recommendations:Recommendation[]; readiness:{current:number;after_top:number}; source:"llm"|"fallback";
  gaps?:Record<string,number>; applied_progress?:AppliedProgress[]; rejected?:Rejected[];
  llm_provider?:string|null; llm_model?:string|null; ai_error?:string;
};
export type Profile = { employee:Employee; next_grade:string|null; readiness_percent:number|null; gaps:Gap[]; history:History[] };

export type RoadmapStep = { event_id:string; title:string; type:string; format:string|null; date:string|null; duration_hours:number; skill_changes:{skill:string;name:string;from:number;to:number;required:number|null}[]; readiness_after:number };
export type Roadmap = {
  as_of:string|null; next_grade:string; reachable:boolean; steps:RoadmapStep[]; total_hours:number; estimated_completion:string|null;
  readiness_path:number[]; coverage:{gap_levels_total:number;gap_levels_closed:number;ratio:number};
  remaining_gaps:Record<string,number>; blocked:{skill:string;name:string;current:number;required:number;reason:string}[];
};

export type Risk = { score:number; level:"low"|"medium"|"high"; reasons:({code:string}&Record<string,unknown>)[]; suggested_format:string|null };
export type Participation = { event_id:string; title:string; completed:number; skipped:number; declined:number; completion_rate:number };
export type ParticipationSummary = { completed:number; missed:number; in_progress:number; total:number; last_activity_date:string|null };
export type BatchResult = { employee_id:string; top:{event_id:string;score:number;primary_skill:string}[]; readiness:number; gaps:Record<string,number>; participation:ParticipationSummary; risk:Risk };
export type RiskRow = { employee_id:string; full_name?:string; role:string; grade:string; risk:Risk; participation:ParticipationSummary };

export type WeakSkill = { skill_id:string; name:string; employee_count:number; missing_levels:number };
export type NoStep = { employee_id:string; full_name?:string; role:string; grade:string; reason:string };
export type Overview = { weak_skills:WeakSkill[]; no_recommendation:NoStep[]; participation:Participation[]; employee_count:number; event_count:number; risks?:RiskRow[]; ai?:boolean };
export type ImportReport = { imported:Record<string,number>; unchanged?:Record<string,number>; errors?:string[] };

export type ImpactDraft = { title:string; type:string; format:string; duration_hours:number; roles:string[]; grades:string[]; skill_id:string; gain:number; max_level:number };
export type Impact = { event_id:string; title:string; employees:number; audience_count:number; gap_closing_count:number; gap_closing_employees:string[]; expected_completions:number; gap_levels_closed:number; hours_per_gap_level:number|null; by_skill:Record<string,number>; catalog_rank:number; catalog_top:{event_id:string;title:string;gap_closing_count:number}[] };
export type ProviderInfo = { providers:{name:string;model:string;base_url:string;structured_output:boolean}[]; order:string[]; budget_seconds:number; explanations:string };
