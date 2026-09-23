// Direct client for the AI service (sudack-ai). Used in the demo mode where the browser holds the
// starter kit locally and asks the AI service for recommendations, roadmaps, risk and impact.
// DEMO STOPGAP ONLY. The target architecture is frontend -> Go API -> AI service: Go owns data, access
// control and the AI call. Remove NEXT_PUBLIC_AI_URL once the Go endpoints from backend/BACKEND.md exist.
import * as mocks from "./mocks";
import eventsData from "@/data/events.json";
import skillsData from "@/data/skills.json";
import type {BatchResult,Employee,Event,Impact,ImpactDraft,ProviderInfo,RecResponse,Roadmap,RoleProfile,Skill} from "./types";

export const aiUrl=(process.env.NEXT_PUBLIC_AI_URL||"").replace(/\/$/,"");
export const aiConfigured=aiUrl.length>0;
export const SNAPSHOT="2026-10-01"; // the kit's "today"
const GRADES=["Junior","Middle","Senior","Lead"];
const EVENTS=eventsData.events as Event[];
const SKILLS=skillsData.skills as Skill[];
const PROFILES=skillsData.role_profiles as unknown as RoleProfile[];
const META=Object.fromEntries(SKILLS.map(s=>[s.skill_id,{name:s.name,category:s.category}]));

export const SKILL_OPTIONS=SKILLS.map(s=>({id:s.skill_id,name:s.name})).sort((a,b)=>a.name.localeCompare(b.name));
export const ROLE_OPTIONS=[...new Set(PROFILES.map(p=>p.role))].sort();
export const GRADE_OPTIONS=GRADES;
export const EVENT_TYPES=[...new Set(EVENTS.map(e=>e.type))].sort();
export const FORMATS=["online","offline","self_paced"];

export type AiRequest={
  employee:Employee; next_grade:string; next_grade_requirements:Record<string,number>; critical_skills:string[];
  skills_meta?:typeof META; history:{event_id:string;status:string;date?:string}[]; events?:Event[]; lang:string; as_of:string;
};

function targetGrade(employee:Employee):string|null{
  const current=GRADES.indexOf(employee.grade);
  const goal=employee.career_goal;
  if(goal?.target_grade&&(!goal.target_role||goal.target_role===employee.role)&&GRADES.indexOf(goal.target_grade)>current)return goal.target_grade;
  return current>=0?GRADES[current+1]||null:null;
}

/** Builds the /recommend body from the local kit. `shared=false` leaves out the catalog so a batch can send it once. */
export function buildRequest(id:string,shared=true):AiRequest|null{
  const employee=mocks.allEmployees().find(e=>e.employee_id===id);
  if(!employee)return null;
  const next=targetGrade(employee);
  if(!next)return null;
  const profile=PROFILES.find(p=>p.role===employee.role&&p.grade===next);
  if(!profile)return null;
  const history=mocks.allHistory().filter(h=>h.employee_id===id).map(h=>({event_id:h.event_id,status:h.status,date:h.date}));
  const request:AiRequest={
    employee:{...employee,full_name:undefined,department:undefined}, // no personal names leave the browser
    next_grade:next, next_grade_requirements:profile.required_skills, critical_skills:profile.critical_skills,
    history, lang:employee.preferred_language||"ru", as_of:SNAPSHOT,
  };
  if(shared){request.events=EVENTS;request.skills_meta=META}
  return request;
}

async function post<T>(path:string,body:unknown):Promise<T>{
  const response=await fetch(`${aiUrl}${path}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  if(!response.ok)throw Object.assign(new Error(`AI-сервис ответил ${response.status}`),{status:response.status});
  return response.json() as Promise<T>;
}

export async function recommend(id:string):Promise<RecResponse>{
  const request=buildRequest(id);
  if(!request)return {recommendations:[],readiness:{current:1,after_top:1},source:"fallback"};
  const raw=await post<RecResponse>("/recommend",request);
  return {...raw,recommendations:raw.recommendations.map(r=>{const event=EVENTS.find(e=>e.event_id===r.event_id);return {...r,type:event?.type,duration_hours:event?.duration_hours}})};
}

export async function roadmap(id:string):Promise<Roadmap|null>{
  const request=buildRequest(id);
  return request?post<Roadmap>("/simulate",request):null;
}

export async function batch():Promise<BatchResult[]>{
  const items=mocks.allEmployees().map(e=>buildRequest(e.employee_id,false)).filter((x):x is AiRequest=>!!x);
  const raw=await post<{results:BatchResult[]}>("/score/batch",{events:EVENTS,skills_meta:META,items});
  return raw.results;
}

export async function impact(draft:ImpactDraft):Promise<Impact>{
  const items=mocks.allEmployees().map(e=>buildRequest(e.employee_id,false)).filter((x):x is AiRequest=>!!x);
  const event={
    event_id:"EV_DRAFT", title:draft.title||"Новое событие", type:draft.type, format:draft.format, duration_hours:draft.duration_hours,
    audience:{roles:draft.roles,grades:draft.grades}, skills:{[draft.skill_id]:{gain:draft.gain,max_level:draft.max_level}},
  };
  return post<Impact>("/events/impact",{event,events:EVENTS,skills_meta:META,items});
}

export async function providers():Promise<ProviderInfo>{
  const response=await fetch(`${aiUrl}/providers`,{cache:"no-store"});
  if(!response.ok)throw new Error(`AI-сервис ответил ${response.status}`);
  return response.json() as Promise<ProviderInfo>;
}
