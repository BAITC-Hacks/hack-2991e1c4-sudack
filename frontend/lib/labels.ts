// Russian labels for machine-readable codes returned by the AI service.
export const statusLabel=(status:string)=>({completed:"Выполнено",in_progress:"В процессе",declined:"Отказ",no_show:"Не пришёл",dropped:"Прервано",overdue:"Просрочено",skipped:"Пропущено"} as Record<string,string>)[status]||"Пропущено";
export const formatLabel=(format:string|null|undefined)=>format?({online:"онлайн",offline:"офлайн",self_paced:"самостоятельно"} as Record<string,string>)[format]||format:"";
export const blockedLabel=(reason:string)=>({
  no_event_for_skill:"нет события в каталоге",
  audience:"события есть, но не для этой роли или грейда",
  ceiling:"события не поднимают выше текущего уровня",
  prerequisites:"не выполнены предусловия",
  already_completed:"единственное подходящее событие уже пройдено",
  step_limit:"не уместилось в 8 шагов",
  unscheduled:"нет будущих сессий",
} as Record<string,string>)[reason]||reason;
export function riskReasonLabel(reason:{code:string}&Record<string,unknown>):string{
  switch(reason.code){
    case "high_miss_rate":return `пропущено ${reason.missed} из ${reason.decided} активностей`;
    case "recent_misses":return `${reason.count} пропуска за ${reason.window_days} дней`;
    case "inactive":return reason.days_since_completion==null?"нет завершённых активностей":`${reason.days_since_completion} дней без завершений`;
    case "stale_in_progress":return `зависших активностей: ${reason.count}`;
    case "declined_assignments":return `отказов от назначений: ${reason.count}`;
    case "no_history":return "истории участия нет";
    default:return reason.code;
  }
}
export const riskLabel=(level:string)=>({high:"Высокий",medium:"Средний",low:"Низкий"} as Record<string,string>)[level]||level;
