import * as mocks from "./mocks";
import * as ai from "./ai";
import type {Employee,Gap,History,Impact,ImpactDraft,ImportReport,Overview,Profile,RecResponse,Recommendation,RiskRow,Roadmap,WeakSkill} from "./types";

// Three modes:
//   api          NEXT_PUBLIC_USE_MOCKS=false (default): Go API with role tokens. Production path:
//                browser -> Go -> AI service.
//   mocks + AI   NEXT_PUBLIC_USE_MOCKS=true and NEXT_PUBLIC_AI_URL set: local kit, live AI service (demo stopgap)
//   mocks        NEXT_PUBLIC_USE_MOCKS=true, no AI URL: fully local, template explanations
export const useMocks=process.env.NEXT_PUBLIC_USE_MOCKS==="true";
export const useAi=useMocks&&ai.aiConfigured;
const base=(process.env.NEXT_PUBLIC_API_URL||"http://localhost:8080").replace(/\/$/,"");
export type Session={role:"employee"|"hr";employee_id?:string;token?:string};
const sessionKey="career-quest-session";
export function getSession():Session|null {if(typeof window==="undefined")return null;try{return JSON.parse(sessionStorage.getItem(sessionKey)||"null")}catch{return null}}
export function setSession(session:Session|null){if(session)sessionStorage.setItem(sessionKey,JSON.stringify(session));else sessionStorage.removeItem(sessionKey)}
async function request<T>(path:string,options:RequestInit={}):Promise<T>{
  const token=getSession()?.token;
  const response=await fetch(`${base}${path}`,{...options,headers:{...(token?{Authorization:`Bearer ${token}`}:{}),...options.headers},cache:"no-store"});
  if(!response.ok){let message=`Ошибка ${response.status}`;try{const body=await response.json();message=body.message||body.detail||message}catch{}throw Object.assign(new Error(message),{status:response.status})}
  return response.json() as Promise<T>;
}
const obj=(value:unknown):Record<string,unknown>=>value&&typeof value==="object"?value as Record<string,unknown>:{};
const num=(value:unknown)=>Number(value||0);

/** Demo login on the Go API (DEMO_AUTH=true): returns a signed role token for the chosen role and employee. */
export async function demoLogin(role:"employee"|"hr",employeeId?:string):Promise<string>{
  const body=await request<{access_token:string}>("/api/v1/auth/demo-token",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({role,employee_id:employeeId||""})});
  return body.access_token;
}

/** Login picker. In API mode the list comes from the Go database (so uploaded jury profiles appear); the bundled kit is the fallback. */
export async function employees():Promise<Employee[]>{
  if(useMocks)return mocks.allEmployees();
  try{
    const raw=await request<{employees:Employee[]}>("/api/v1/auth/demo-employees");
    return raw.employees.map(e=>({...e,tenure_months:num(e.tenure_months),skills:e.skills||{}}));
  }catch{return mocks.allEmployees()}
}

export async function profile(id:string):Promise<Profile>{
  if(useMocks)return mocks.getProfile(id);
  const raw=obj(await request(`/api/v1/employees/${encodeURIComponent(id)}?lang=ru`));
  const gaps=(Array.isArray(raw.gaps)?raw.gaps:[]) as Gap[];
  return {
    employee:{employee_id:String(raw.employee_id||id),full_name:String(raw.full_name||id),department:String(raw.department||""),role:String(raw.role||""),grade:String(raw.grade||""),tenure_months:num(raw.tenure_months),skills:obj(raw.skills) as Record<string,number>,preferred_language:raw.preferred_language as string|undefined,last_review_date:raw.last_review_date as string|undefined},
    next_grade:raw.next_grade==null?null:String(raw.next_grade),
    readiness_percent:raw.readiness_percent==null?null:num(raw.readiness_percent),
    gaps,
    history:(Array.isArray(raw.history)?raw.history:[]).map(h=>({...obj(h),employee_id:id})) as History[],
  };
}

export async function recommendations(id:string):Promise<RecResponse>{
  if(useMocks){
    if(!useAi)return mocks.getRecommendations(id);
    try{return await ai.recommend(id)}
    catch(e){return {...mocks.getRecommendations(id),ai_error:e instanceof Error?e.message:"AI-сервис недоступен"}}
  }
  // Go forwards the AI service verdict and adds catalog facts (type, format, hours) per recommendation.
  const raw=obj(await request(`/api/v1/employees/${encodeURIComponent(id)}/recommendations?lang=ru`));
  return {...raw,recommendations:(Array.isArray(raw.recommendations)?raw.recommendations:[]) as Recommendation[]} as unknown as RecResponse;
}

/** Roadmap to the next grade: Go proxies the AI simulator; the bundled-data mode calls the AI service directly. */
export async function roadmap(id:string):Promise<Roadmap|null>{
  if(useMocks){if(!useAi)return null;try{return await ai.roadmap(id)}catch{return null}}
  try{return await request<Roadmap>(`/api/v1/employees/${encodeURIComponent(id)}/roadmap`)}catch{return null}
}

export async function complete(id:string,eventId:string):Promise<Profile>{
  if(useMocks)return mocks.complete(id,eventId);
  await request(`/api/v1/employees/${encodeURIComponent(id)}/events/${encodeURIComponent(eventId)}/completions`,{method:"POST",headers:{"Idempotency-Key":crypto.randomUUID()}});
  return profile(id);
}

export async function overview():Promise<Overview>{
  if(useMocks){
    const local=mocks.getOverview();
    if(!useAi)return local;
    try{
      const results=await ai.batch();
      const people=new Map(mocks.allEmployees().map(e=>[e.employee_id,e]));
      const gapMap=new Map<string,WeakSkill>();
      for(const r of results)for(const [skill_id,gap] of Object.entries(r.gaps)){const row=gapMap.get(skill_id)||{skill_id,name:mocks.skillName(skill_id),employee_count:0,missing_levels:0};row.employee_count++;row.missing_levels+=gap;gapMap.set(skill_id,row)}
      const weak_skills=[...gapMap.values()].sort((a,b)=>b.employee_count-a.employee_count).slice(0,10);
      const no_recommendation=results.filter(r=>!r.top.length).map(r=>{const e=people.get(r.employee_id);return {employee_id:r.employee_id,full_name:e?.full_name,role:e?.role||"",grade:e?.grade||"",reason:"Нет доступной активности, закрывающей разрывы"}});
      const risks:RiskRow[]=results.filter(r=>r.risk.level!=="low").sort((a,b)=>b.risk.score-a.risk.score).map(r=>{const e=people.get(r.employee_id);return {employee_id:r.employee_id,full_name:e?.full_name,role:e?.role||"",grade:e?.grade||"",risk:r.risk,participation:r.participation}});
      return {...local,weak_skills,no_recommendation,risks,ai:true};
    }catch{return {...local,ai:false}}
  }
  // The Go HR overview already has this shape: weak_skills, no_recommendation, participation, risks, counts, ai.
  const raw=obj(await request("/api/v1/hr/overview"));
  return {
    weak_skills:((Array.isArray(raw.weak_skills)?raw.weak_skills:[]) as WeakSkill[]).slice(0,10),
    no_recommendation:(Array.isArray(raw.no_recommendation)?raw.no_recommendation:[]) as Overview["no_recommendation"],
    participation:(Array.isArray(raw.participation)?raw.participation:[]) as Overview["participation"],
    risks:(Array.isArray(raw.risks)?raw.risks:[]) as RiskRow[],
    employee_count:num(raw.employee_count),event_count:num(raw.event_count),ai:Boolean(raw.ai),
  };
}

function draftToEvent(draft:ImpactDraft){
  return {event_id:"EV_DRAFT",title:draft.title||"Новое событие",type:draft.type,format:draft.format,duration_hours:draft.duration_hours,
    audience:{roles:draft.roles,grades:draft.grades},skills:{[draft.skill_id]:{gain:draft.gain,max_level:draft.max_level}}};
}
export async function impact(draft:ImpactDraft):Promise<Impact>{
  if(useMocks){if(!useAi)throw new Error("Конструктор события работает при подключённом AI-сервисе");return ai.impact(draft)}
  return request<Impact>("/api/v1/hr/events/impact",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(draftToEvent(draft))});
}

export async function importFiles(files:{employees?:File;history?:File}):Promise<ImportReport>{
  if(useMocks)return mocks.importData(files);
  const body=new FormData();
  for(const [key,file] of Object.entries(files))if(file)body.append(key,file);
  return request<ImportReport>("/api/v1/imports",{method:"POST",body});
}
