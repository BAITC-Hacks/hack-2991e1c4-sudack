"use client";
import {useState} from "react";
import {FlaskConical} from "lucide-react";
import {impact} from "@/lib/api";
import {EVENT_TYPES,FORMATS,GRADE_OPTIONS,ROLE_OPTIONS,SKILL_OPTIONS} from "@/lib/ai";
import {formatLabel} from "@/lib/labels";
import type {Impact,ImpactDraft} from "@/lib/types";

/** HR drafts an event; the AI service predicts who it helps and what it costs per closed skill level. */
export default function ImpactForm(){
  const [draft,setDraft]=useState<ImpactDraft>({title:"Новый воркшоп",type:"workshop",format:"online",duration_hours:4,roles:[],grades:[],skill_id:SKILL_OPTIONS[0]?.id||"",gain:1,max_level:4});
  const [result,setResult]=useState<Impact|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const set=<K extends keyof ImpactDraft>(key:K,value:ImpactDraft[K])=>setDraft({...draft,[key]:value});
  const toggle=(key:"roles"|"grades",value:string)=>set(key,draft[key].includes(value)?draft[key].filter(x=>x!==value):[...draft[key],value]);
  async function run(){setBusy(true);setError("");try{setResult(await impact(draft))}catch(e){setError(e instanceof Error?e.message:"Не удалось оценить событие")}finally{setBusy(false)}}
  return <section className="card participation"><div className="section-title"><div><div className="eyebrow">05 / КОНСТРУКТОР СОБЫТИЯ</div><h2>Оценить событие до его создания</h2><p>Сколько сотрудников закроют разрыв, сколько завершат по истории и сколько часов бюджета уйдёт на один уровень навыка.</p></div><FlaskConical size={20}/></div>
    <div className="impact-form">
      <label className="wide">Название<input value={draft.title} onChange={e=>set("title",e.target.value)}/></label>
      <label>Тип<select value={draft.type} onChange={e=>set("type",e.target.value)}>{EVENT_TYPES.map(t=><option key={t} value={t}>{t}</option>)}</select></label>
      <label>Формат<select value={draft.format} onChange={e=>set("format",e.target.value)}>{FORMATS.map(f=><option key={f} value={f}>{formatLabel(f)}</option>)}</select></label>
      <label className="wide">Навык<select value={draft.skill_id} onChange={e=>set("skill_id",e.target.value)}>{SKILL_OPTIONS.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
      <label>Прирост<input type="number" min={1} max={5} value={draft.gain} onChange={e=>set("gain",Number(e.target.value)||1)}/></label>
      <label>Потолок<input type="number" min={1} max={5} value={draft.max_level} onChange={e=>set("max_level",Number(e.target.value)||1)}/></label>
      <label>Часы<input type="number" min={0} value={draft.duration_hours} onChange={e=>set("duration_hours",Number(e.target.value)||0)}/></label>
      <div className="wide"><span className="pick-label">Роли (пусто = все)</span><div className="pick-list">{ROLE_OPTIONS.map(r=><button type="button" key={r} className={draft.roles.includes(r)?"on":""} onClick={()=>toggle("roles",r)}>{r}</button>)}</div></div>
      <div><span className="pick-label">Грейды (пусто = все)</span><div className="pick-list">{GRADE_OPTIONS.map(g=><button type="button" key={g} className={draft.grades.includes(g)?"on":""} onClick={()=>toggle("grades",g)}>{g}</button>)}</div></div>
      <div style={{alignSelf:"end"}}><button className="primary" disabled={busy} onClick={run}>{busy?"Считаем...":"Оценить эффект"}</button></div>
    </div>
    {error&&<div className="import-error" style={{marginTop:14}}>{error}</div>}
    {result&&<><div className="impact-result">
      <div><strong>{result.audience_count}</strong><span>могут участвовать из {result.employees}</span></div>
      <div><strong>{result.gap_closing_count}</strong><span>закроют разрыв к грейду</span></div>
      <div><strong>{result.expected_completions}</strong><span>ожидаемых завершений по истории</span></div>
      <div><strong>{result.hours_per_gap_level==null?"—":`${result.hours_per_gap_level} ч`}</strong><span>бюджета на один уровень навыка</span></div>
    </div>
    <p className="muted" style={{marginTop:14}}>Место в каталоге по числу закрываемых разрывов: <b>#{result.catalog_rank}</b>. Сильнейшие существующие события: {result.catalog_top.map(c=>`${c.title} (${c.gap_closing_count})`).join(", ")}.</p></>}
  </section>;
}
