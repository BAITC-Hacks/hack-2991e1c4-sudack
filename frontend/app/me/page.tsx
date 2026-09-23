"use client";
import {Suspense,useCallback,useEffect,useState} from "react";
import {useRouter,useSearchParams} from "next/navigation";
import {ArrowLeft,ArrowRight,CheckCircle2,Compass,Flag,History,RefreshCw,Sparkles,Target,TrendingUp} from "lucide-react";
import Shell from "@/components/Shell";
import SkillsChart from "@/components/SkillsChart";
import RecommendationCard from "@/components/RecommendationCard";
import WhyNot from "@/components/WhyNot";
import RoadmapView from "@/components/RoadmapView";
import {complete,getSession,profile,recommendations,roadmap,useAi} from "@/lib/api";
import {eventTitle,skillName} from "@/lib/mocks";
import {statusLabel} from "@/lib/labels";
import type {Profile,RecResponse,Roadmap} from "@/lib/types";

function EmployeePage(){
  const router=useRouter();const params=useSearchParams();const requested=params.get("id");
  const [data,setData]=useState<Profile|null>(null);const [recs,setRecs]=useState<RecResponse|null>(null);const [road,setRoad]=useState<Roadmap|null>(null);
  const [error,setError]=useState("");const [recError,setRecError]=useState("");const [busy,setBusy]=useState("");const [toast,setToast]=useState("");const [loading,setLoading]=useState(true);
  const [session,setCurrent]=useState<ReturnType<typeof getSession>>(null);
  const id=session?.role==="hr"&&requested?requested:session?.employee_id;const readOnly=session?.role==="hr";
  const loadRecs=useCallback((employeeId:string)=>{recommendations(employeeId).then(setRecs).catch(e=>setRecError(e.status===503?"Рекомендации временно недоступны":e.message));roadmap(employeeId).then(setRoad).catch(()=>setRoad(null));},[]);
  const load=useCallback(async()=>{if(!id)return;setLoading(true);setRecs(null);setRoad(null);setError("");setRecError("");profile(id).then(setData).catch(e=>setError(e.message)).finally(()=>setLoading(false));loadRecs(id);},[id,loadRecs]);
  useEffect(()=>{const current=getSession();setCurrent(current);if(!current)router.replace("/login")},[router]);
  useEffect(()=>{if(session)load()},[session,id,load]);
  async function onComplete(eventId:string){if(!id)return;setBusy(eventId);const before=data;try{const updated=await complete(id,eventId);setData(updated);setRecs(null);setRoad(null);const changed=Object.entries(updated.employee.skills).filter(([skill,n])=>n>(before?.employee.skills[skill]||0)).map(([skill,n])=>`${skillName(skill)} ${before?.employee.skills[skill]||0} → ${n}`);const delta=Math.round((updated.readiness_percent||0)-(before?.readiness_percent||0));setToast(`${changed.join(", ")||"Активность завершена"}${delta>0?`, готовность +${delta} п.п.`:""}`);setTimeout(()=>setToast(""),5000);loadRecs(id);}catch(e){setToast(e instanceof Error?e.message:"Не удалось сохранить результат")}finally{setBusy("")}}
  const employee=data?.employee;
  const providerLabel=recs?.source==="llm"&&recs.llm_model?`${recs.llm_model}${recs.llm_provider?` (${recs.llm_provider})`:""}`:undefined;
  const critical=data?.gaps.filter(g=>g.gap>0&&g.critical)||[];
  return <Shell>
    {readOnly&&<button className="back-link" onClick={()=>router.push("/hr")}><ArrowLeft size={17}/> Вернуться к HR аналитике</button>}
    <div className="page-heading"><div><div className="eyebrow">ПЕРСОНАЛЬНАЯ ТРАЕКТОРИЯ</div><h1>{readOnly?"Профиль сотрудника":"Мой путь развития"}</h1><p>Следующий шаг основан на навыках, цели и истории участия.</p></div><span className="heading-icon"><Compass size={25}/></span></div>
    {error?<div className="error-card">{error}<button onClick={load}>Повторить</button></div>:loading||!data?<div className="skeleton card" style={{height:250}}/>:<>
      <section className="profile-card"><div className="profile-identity"><span className="profile-avatar">{employee?.full_name?.split(" ").map(w=>w[0]).slice(0,2).join("")||employee?.employee_id.slice(0,2)}</span><div><span className="subtle">ПРОФИЛЬ СОТРУДНИКА · {employee?.employee_id}</span><h2>{employee?.full_name||employee?.employee_id}</h2><p>{employee?.role} <span className="dot-sep">•</span> {employee?.department||"Сотрудник"}</p></div></div><div className="profile-pills"><span><b>{employee?.grade}</b> текущий грейд</span><ArrowRight size={17}/><span><b>{data.next_grade||"Цель достигнута"}</b> следующий грейд</span><span className="tenure">{employee?.tenure_months} мес. в компании</span></div></section>
      <div className="overview-grid">
        <section className="card readiness-card"><div className="card-label"><Target size={18}/> ГОТОВНОСТЬ К СЛЕДУЮЩЕМУ ГРЕЙДУ</div><div className="readiness-number">{data.readiness_percent===null?"—":`${Math.round(data.readiness_percent)}%`}<span>{data.next_grade?`к ${data.next_grade}`:"Верхний грейд"}</span></div><div className="progress-track"><span style={{width:`${data.readiness_percent||0}%`}}/></div><p>Доля требований следующего грейда, покрытая вашими навыками.</p></section>
        <section className="card summary-card"><div className="card-label"><Sparkles size={18}/> ВАШ ФОКУС</div><h3>{critical.length?"Ключевые навыки для роста":"Продолжайте развитие"}</h3><p>{critical.length?`Сейчас важно закрыть ${critical.map(g=>g.name).slice(0,2).join(" и ")}. Рекомендации ниже учитывают этот приоритет.`:"Навыки целевого грейда близки к нужному уровню. Выбирайте полезный следующий шаг."}</p><div className="summary-mark"><TrendingUp size={30}/></div></section>
      </div>
      <div className="section-grid">
        <section className="card skills-card"><div className="section-title"><div><div className="eyebrow">01 / КОМПЕТЕНЦИИ</div><h2>Навыки для {data.next_grade||"развития"}</h2></div><span className="section-counter">{data.gaps.filter(g=>g.gap>0).length} разрывов</span></div>{data.gaps.length?<SkillsChart gaps={data.gaps}/>:<p className="empty">Для текущего грейда нет следующей цели.</p>}<div className="chart-legend"><span><i className="legend-current"/>Текущий уровень</span><span><i className="legend-target"/>Требуется</span></div></section>
        <section className="card history-card"><div className="section-title"><div><div className="eyebrow">02 / ИСТОРИЯ</div><h2>Ваша траектория</h2></div><History size={20}/></div><div className="timeline"><div className="timeline-item next"><span className="timeline-dot"><Flag size={15}/></span><div><small>СЛЕДУЮЩИЙ ШАГ</small><b>{recs?.recommendations[0]?.title||"Подбираем активность"}</b></div></div>{data.history.slice(0,5).map((h,i)=><div className="timeline-item" key={`${h.record_id||h.event_id}-${i}`}><span className={`timeline-dot ${h.status==="completed"?"done":"missed"}`}>{h.status==="completed"?<CheckCircle2 size={15}/>:"–"}</span><div><small>{h.date} · {statusLabel(h.status)}</small><b>{eventTitle(h.event_id)}</b></div></div>)}</div></section>
      </div>
      <section className="recommendations-section">
        <div className="section-title"><div><div className="eyebrow">03 / ПЕРСОНАЛЬНЫЙ ПЛАН</div><h2>Рекомендуем следующие шаги</h2><p>Каждый шаг объясняет, как он влияет на вашу цель.</p></div><div style={{display:"flex",gap:8,alignItems:"center"}}>{recs?.source==="llm"?<span className="ai-badge">✦ Объяснения: {providerLabel}</span>:recs?.ai_error?<span className="section-counter" title={recs.ai_error}>AI недоступен · шаблон</span>:null}<span className="section-counter">{recs?.recommendations.length||0} активности</span></div></div>
        {recError?<div className="error-card">{recError}<button onClick={()=>{if(!id)return;setRecError("");loadRecs(id)}}><RefreshCw size={15}/> Повторить</button></div>
          :!recs?<div className="rec-grid">{[0,1,2].map(i=><div className="skeleton rec-card" key={i}><span>{useAi?"Спрашиваем AI-сервис…":"Подбираем шаги…"}</span></div>)}</div>
          :recs.recommendations.length?<div className="rec-grid">{recs.recommendations.map((r,i)=><RecommendationCard key={r.event_id} recommendation={r} index={i} readiness={recs.readiness} loading={busy===r.event_id} onComplete={onComplete} readOnly={readOnly} providerLabel={recs.llm_model||undefined}/>)}</div>
          :<div className="empty card">Подходящих шагов сейчас нет. Для нового направления развития обратитесь к HR.</div>}
        {recs?.applied_progress?.length?<p className="muted" style={{marginTop:12}}>Учтены завершения после последней аттестации: {recs.applied_progress.map(p=>`${skillName(p.skill)} ${p.from}→${p.to}`).join(", ")}.</p>:null}
      </section>
      {recs?.rejected?.length?<WhyNot items={recs.rejected}/>:null}
      {road&&<RoadmapView roadmap={road}/>}
    </>}
    {toast&&<div className="toast"><CheckCircle2 size={20}/>{toast}</div>}
  </Shell>;
}
export default function Page(){return <Suspense fallback={<div className="skeleton" style={{minHeight:"100vh"}}>Загружаем профиль…</div>}><EmployeePage/></Suspense>}
