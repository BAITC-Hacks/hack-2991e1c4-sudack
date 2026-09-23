import {Map as MapIcon} from "lucide-react";
import type {Roadmap} from "@/lib/types";
import {blockedLabel,formatLabel} from "@/lib/labels";

/** Dated plan to the next grade with the readiness path and the skills the catalog cannot raise. */
export default function RoadmapView({roadmap}:{roadmap:Roadmap}){
  const steps=[...roadmap.steps].sort((a,b)=>(a.date||"9999").localeCompare(b.date||"9999"));
  const first=roadmap.readiness_path[0]??0;const last=roadmap.readiness_path[roadmap.readiness_path.length-1]??first;
  return <section className="card roadmap"><div className="section-title"><div><div className="eyebrow">05 / МАРШРУТ ДО ГРЕЙДА</div><h2>Как дойти до {roadmap.next_grade}</h2><p>Жадный план по каталогу: на каждом шаге событие, которое закрывает больше всего разрыва.</p></div><MapIcon size={20}/></div>
    <div className="roadmap-summary">
      <div><strong>{roadmap.reachable?"Достижим":"Частично"}</strong><span>{roadmap.reachable?"каталог закрывает все разрывы":`каталог закрывает ${Math.round(roadmap.coverage.ratio*100)}% разрыва`}</span></div>
      <div><strong>{steps.length}</strong><span>{steps.length===1?"шаг":steps.length<5?"шага":"шагов"}</span></div>
      <div><strong>{roadmap.total_hours} ч</strong><span>суммарно</span></div>
      <div><strong>{Math.round(first*100)}% → {Math.round(last*100)}%</strong><span>готовность</span></div>
      {roadmap.estimated_completion&&<div><strong>{roadmap.estimated_completion}</strong><span>последняя сессия</span></div>}
    </div>
    {roadmap.readiness_path.length>1&&<div className="path-bars" aria-hidden>{roadmap.readiness_path.map((v,i)=><i key={i} style={{height:`${Math.max(6,Math.round(v*100))}%`}} title={`${Math.round(v*100)}%`}/>)}</div>}
    {steps.length?<div className="roadmap-steps">{steps.map((step,i)=><div className="roadmap-step" key={`${step.event_id}-${i}`}><div className="date">{step.date||"в любое время"}</div><div><b>{step.title}</b><div className="changes">{[formatLabel(step.format),step.duration_hours?`${step.duration_hours} ч`:null].filter(Boolean).join(" · ")} · {step.skill_changes.map(c=>`${c.name} ${c.from}→${c.to}${c.required!=null?` (нужно ${c.required})`:""}`).join(", ")}</div></div><div className="after">{Math.round(step.readiness_after*100)}%</div></div>)}</div>:<p className="empty">Подходящих активностей в каталоге нет.</p>}
    {roadmap.blocked.length>0&&<><p className="muted" style={{marginTop:18}}>Каталог не поднимает до требования: сигнал HR, а не сотруднику.</p><div className="blocked-list">{roadmap.blocked.map(b=><span key={b.skill}>{b.name} {b.current}/{b.required}: {blockedLabel(b.reason)}</span>)}</div></>}
  </section>;
}
