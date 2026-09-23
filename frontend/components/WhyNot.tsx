import {HelpCircle} from "lucide-react";
import type {Rejected} from "@/lib/types";

/** Counterfactual for the jury's trap profiles: why the largest-gap skill is not the first step. */
export default function WhyNot({items}:{items:Rejected[]}){
  if(!items.length)return null;
  return <section className="card whynot"><div className="section-title"><div><div className="eyebrow">04 / ПОЧЕМУ НЕ ДРУГОЙ НАВЫК</div><h2>Что проиграло первому шагу</h2><p>Однофакторное правило выбрало бы самый слабый навык. Вот почему рекомендация другая.</p></div><HelpCircle size={20}/></div>
    <div className="whynot-list">{items.map((item,i)=><div className="whynot-item" key={`${item.skill}-${i}`}><div><b>{item.title||"Нет подходящей активности"}</b><small>{item.required==null?`${item.current}`:`${item.current} из ${item.required}`}{item.score!=null?` · score ${item.score.toFixed(2)}`:""}</small>{item.recommended_position?<span className="position-pill">В плане под №{item.recommended_position}</span>:null}</div><p>{item.reason}</p></div>)}</div>
  </section>;
}
