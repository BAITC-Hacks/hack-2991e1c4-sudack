import * as mocks from "./mocks";
import * as ai from "./ai";
import type {Employee,Factor,Gap,History,Impact,ImpactDraft,ImportReport,Overview,Profile,RecResponse,Recommendation,RiskRow,Roadmap,WeakSkill} from "./types";

// Three modes:
//   mocks + AI   NEXT_PUBLIC_USE_MOCKS=true and NEXT_PUBLIC_AI_URL set: local kit, live AI service (demo without Go)
//   mocks        NEXT_PUBLIC_USE_MOCKS=true, no AI URL: fully local, template explanations
//   api          NEXT_PUBLIC_USE_MOCKS=false: Go API with bearer tokens (production path)
export const useMocks=process.env.NEXT_PUBLIC_USE_MOCKS!=="false";
export const useAi=useMocks&&ai.aiConfigured;
const base=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8080";
export type Session={role:"employee"|"hr";employee_id?:string;token?:string};
const sessionKey="career-quest-session";
export function getSession():Session|null {if(typeof window==="undefined")return null;try{return JSON.parse(sessionStorage.getItem(sessionKey)||"null")}catch{return null}}
export function setSession(session:Session|null){if(session)sessionStorage.setItem(sessionKey,JSON.stringify(session));else sessionStorage.removeItem(sessionKey)}
async function request<T>(path:string,options:RequestInit={}):Promise<T>{const token=getSession()?.token;const response=await fetch(`${base}${path}`,{...options,headers:{...(token?{Authorization:`Bearer ${token}`}:{ }),...options.headers},cache:"no-store"});if(!response.ok){let message=`Ошибка ${response.status}`;try{const body=await response.json();message=body.message||message}catch{}throw Object.assign(new Error(message),{status:response.status})}return response.json() as Promise<T>}
const obj=(value:unknown):Record<string,unknown>=>value&&typeof value==="object"?value as Record<string,unknown>:{};
const arr=(value:unknown):Record<string,unknown>[]=>Array.isArray(value)?value.map(obj):[];
const num=(value:unknown)=>Number(value||0);

export async function employees():Promise<Employee[]>{return mocks.allEmployees()}
export async function profile(id:string):Promise<Profile>{
  if(useMocks)return mocks.getProfile(id);
  const raw=obj(await request(`/api/v1/employees/${encodeURIComponent(id)}?lang=ru`));
  const employee=obj(raw.employee||raw);
  const skills=obj(employee.skills);
  const gaps:Gap[]=arr(raw.gaps).map(g=>({skill_id:String(g.skill_id||""),name:String(g.name||mocks.skillName(String(g.skill_id||""))),current:num(g.current),required:num(g.required),gap:num(g.gap),critical:Boolean(g.critical)}));
  return {employee:{employee_id:String(employee.employee_id||id),full_name:String(employee.full_name||id),department:String(employee.department||""),role:String(employee.role||""),grade:String(employee.grade||""),tenure_months:num(employee.tenure_months),skills:skills as Record<string,number>},next_grade:raw.next_grade==null?null:String(raw.next_grade),readiness_percent:raw.readiness_percent==null?null:num(raw.readiness_percent),gaps,history:(Array.isArray(raw.history)?raw.history:[]) as History[]};
}
export async function recommendations(id:string):Promise<RecResponse>{
  if(useMocks){
    if(!useAi)return mocks.getRecommendations(id);
    try{return await ai.recommend(id)}
    catch(e){return {...mocks.getRecommendations(id),ai_error:e instanceof Error?e.message:"AI-сервис недоступен"}}
  }
  const raw=obj(await request(`/api/v1/employees/${encodeURIComponent(id)}/recommendations?lang=ru`));
  if(Array.isArray(raw.recommendations))return raw as unknown as RecResponse; // Go forwards the AI service response as is
  const steps=arr(raw.steps);const currentProfile=await profile(id);const current=(currentProfile.readiness_percent||0)/100;
  const recommendations:Recommendation[]=steps.map(step=>{const evidence=arr(step.evidence);const effects=arr(step.skill_effects);const factors:Factor[]=evidence.map(e=>({type:e.factor==="grade_gap"?"grade_requirement":e.factor==="skill_gain"?"effective_gain":e.factor==="history"?"history":"skill_gap",text:String(e.text||""),skill:e.skill_id?String(e.skill_id):undefined}));for(const effect of effects)factors.push({type:"effective_gain",skill:String(effect.skill_id||""),name:mocks.skillName(String(effect.skill_id||"")),from:num(effect.current),to:num(effect.projected),text:`${mocks.skillName(String(effect.skill_id||""))}: ${num(effect.current)} → ${num(effect.projected)}`});return {event_id:String(step.event_id||""),title:String(step.title||step.event_id||"Активность"),type:String(step.type||"Развитие"),score:num(step.score),reason:String(step.reason||step.explanation||evidence.map(e=>e.text).filter(Boolean).join(". ")||"Рекомендация основана на требованиях грейда, разрыве навыков и истории."),reason_source:String(raw.model_version||"").includes("llm")?"llm":"template",factors,calculation:{gap_closed:effects.reduce((sum,e)=>sum+num(e.gap_reduction),0),engagement:num(step.engagement),formula:String(step.formula||"Подробный расчёт возвращает API")}}});
  let afterTop=current;if(recommendations[0]){try{const preview=obj(await request(`/api/v1/employees/${encodeURIComponent(id)}/events/${encodeURIComponent(recommendations[0].event_id)}/preview`,{method:"POST"}));afterTop=num(preview.readiness_after)/100||current}catch{}}
  return {recommendations,readiness:{current,after_top:afterTop},source:recommendations.some(r=>r.reason_source==="llm")?"llm":"fallback"};
}
/** Roadmap to the next grade. Available when the AI service is reachable directly; the Go API does not expose it yet. */
export async function roadmap(id:string):Promise<Roadmap|null>{
  if(!useAi)return null;
  try{return await ai.roadmap(id)}catch{return null}
}
export async function complete(id:string,eventId:string):Promise<Profile>{if(useMocks)return mocks.complete(id,eventId);await request(`/api/v1/employees/${encodeURIComponent(id)}/events/${encodeURIComponent(eventId)}/completions`,{method:"POST",headers:{"Idempotency-Key":crypto.randomUUID()}});return profile(id)}
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
  const raw=obj(await request("/api/v1/hr/overview"));
  return {weak_skills:(raw.weak_skills||raw.skill_gaps||[]) as Overview["weak_skills"],no_recommendation:(raw.no_recommendation||raw.employees_without_step||[]) as Overview["no_recommendation"],participation:(raw.participation||raw.activity_participation||[]) as Overview["participation"],employee_count:num(raw.employee_count),event_count:num(raw.event_count)};
}
export async function impact(draft:ImpactDraft):Promise<Impact>{
  if(!useAi)throw new Error("Конструктор события работает при подключённом AI-сервисе");
  return ai.impact(draft);
}
export async function importFiles(files:{employees?:File;history?:File;events?:File;skills?:File}):Promise<ImportReport>{if(useMocks)return mocks.importData(files);const body=new FormData();for(const [key,file] of Object.entries(files))if(file)body.append(key,file);return request<ImportReport>("/api/v1/imports",{method:"POST",body})}
