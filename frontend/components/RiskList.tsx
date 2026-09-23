import {ChevronRight,ShieldAlert} from "lucide-react";
import type {RiskRow} from "@/lib/types";
import {formatLabel,riskLabel,riskReasonLabel} from "@/lib/labels";

/** Who is dropping out of development, with the reasons and a format that has worked for them. */
export default function RiskList({rows,onOpen}:{rows:RiskRow[];onOpen:(id:string)=>void}){
  return <section className="card participation"><div className="section-title"><div><div className="eyebrow">04 / РИСК ВЫПАДЕНИЯ</div><h2>Кто выпадает из развития</h2><p>Пропуски, давность последнего завершения и отказы от назначений. Видно только HR.</p></div><span className="section-counter"><ShieldAlert size={12}/> {rows.length}</span></div>
    {rows.length?<div className="table-wrap"><table><thead><tr><th>СОТРУДНИК</th><th>РИСК</th><th>ПРИЧИНЫ</th><th>УЧАСТИЕ</th><th>ЧТО ПРЕДЛОЖИТЬ</th><th/></tr></thead><tbody>{rows.map(row=><tr key={row.employee_id}><td><b>{row.full_name||row.employee_id}</b><small>{row.employee_id} · {row.role} · {row.grade}</small></td><td><span className={`risk-badge ${row.risk.level}`}>{riskLabel(row.risk.level)} · {Math.round(row.risk.score*100)}</span></td><td>{row.risk.reasons.map(riskReasonLabel).join("; ")||"—"}</td><td>{row.participation.completed} выполнено · {row.participation.missed} пропущено<small>последняя активность {row.participation.last_activity_date||"—"}</small></td><td>{row.risk.suggested_format?`формат: ${formatLabel(row.risk.suggested_format)}`:"—"}</td><td><button className="text-button" onClick={()=>onOpen(row.employee_id)} aria-label="Открыть профиль"><ChevronRight size={16}/></button></td></tr>)}</tbody></table></div>:<div className="empty">Сотрудников со средним или высоким риском нет.</div>}
  </section>;
}
