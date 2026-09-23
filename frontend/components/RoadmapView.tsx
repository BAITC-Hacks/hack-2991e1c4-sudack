import {Map as MapIcon} from "lucide-react";
import type {Roadmap} from "@/lib/types";
import {blockedLabel,formatLabel} from "@/lib/labels";

/** Dated plan to the next grade with the readiness path and the skills the catalog cannot raise. */
export default function RoadmapView({roadmap}:{roadmap:Roadmap}){
  const path=roadmap.readiness_path;
  const first=path[0]??0;const last=path[path.length-1]??first;
  // Steps arrive in plan (priority) order; the readiness gain of each step is the difference along that path.
  // Gains are attached before sorting by date, so the timeline stays chronological and the numbers stay honest.
  const withGain=roadmap.steps.map((step,i)=>({...step,gain:Math.round(((path[i+1]??path[i]??0)-(path[i]??0))*100)}));
  const steps=[...withGain].sort((a,b)=>(a.date||"9999").localeCompare(b.date||"9999"));
  const plural=steps.length===1?"шаг":steps.length<5?"шага":"шагов";
  return <section className="card roadmap"><div className="section-title"><div><div className="eyebrow">05 / МАРШРУТ ДО ГРЕЙДА</div><h2>Как дойти до {roadmap.next_grade}</h2><p>Жадный план по каталогу: на каждом шаге событие, которое закрывает больше всего разрыва. Порядок в списке хронологический, вклад каждого шага в готовность показан справа.</p></div><MapIcon size={20}/></div>
    <div className="roadmap-summary">
      <div><strong>{roadmap.reachable?"Достижим":"Частично"}</strong><span>{roadmap.reachable?"каталог закрывает все разрывы":`каталог закрывает ${Math.round(roadmap.coverage.ratio*100)}% разрыва`}</span></div>
      <div><strong>{steps.length}</strong><span>{plural}</span></div>
      <div><strong>{roadmap.total_hours} ч</strong><span>суммарно</span></div>
      <div><strong>{Math.round(first*100)}% → {Math.round(last*100)}%</strong><span>готовность после плана</span></div>
      {roadmap.estimated_completion&&<div><strong>{roadmap.estimated_completion}</strong><span>последняя сессия</span></div>}
    </div>
    {steps.length?<div className="roadmap-steps">{steps.map((step,i)=><div className="roadmap-step" key={`${step.event_id}-${i}`}><div className="date">{step.date||"в любое время"}</div><div><b>{step.title}</b><div className="changes">{[formatLabel(step.format),step.duration_hours?`${step.duration_hours} ч`:null].filter(Boolean).join(" · ")} · {step.skill_changes.map(c=>`${c.name} ${c.from}→${c.to}${c.required!=null?` (нужно ${c.required})`:""}`).join(", ")}</div></div><div className="after" title="Вклад шага в готовность к грейду">{step.gain>0?`+${step.gain} п.п.`:"—"}</div></div>)}</div>:<p className="empty">Подходящих активностей в каталоге нет.</p>}
    {roadmap.blocked.length>0&&<><p className="muted" style={{marginTop:18}}>Каталог не поднимает эти навыки до требования. Это сигнал HR о пробелах каталога, а не задача сотруднику.</p><div className="blocked-list">{roadmap.blocked.map(b=><span key={b.skill}>{b.name} {b.current}/{b.required}: {blockedLabel(b.reason)}</span>)}</div></>}
  </section>;
}
