"use client";
import {useEffect,useMemo,useState} from "react";
import {useRouter} from "next/navigation";
import {ArrowRight,BriefcaseBusiness,Search,Sparkles,UserRound} from "lucide-react";
import {employees,getSession,setSession,useMocks} from "@/lib/api";
import type {Employee} from "@/lib/types";

export default function Login(){
  const router=useRouter();
  const [role,setRole]=useState<"employee"|"hr">("employee");
  const [list,setList]=useState<Employee[]>([]);
  const [query,setQuery]=useState("");
  const [selected,setSelected]=useState("E0028");
  const [token,setToken]=useState("");
  useEffect(()=>{employees().then(setList);const session=getSession();if(session)router.replace(session.role==="hr"?"/hr":"/me")},[router]);
  const matches=useMemo(()=>list.filter(e=>`${e.employee_id} ${e.full_name} ${e.role} ${e.grade}`.toLowerCase().includes(query.toLowerCase())).slice(0,5),[list,query]);
  const enteredId=/^E\d+$/i.test(query.trim())?query.trim().toUpperCase():"";
  function login(nextRole=role){const id=enteredId||selected;if(nextRole==="employee"&&!id)return;setSession({role:nextRole,employee_id:nextRole==="employee"?id:undefined,token:useMocks?undefined:token.trim()});router.push(nextRole==="hr"?"/hr":"/me")}
  function chooseRole(nextRole:"employee"|"hr"){setRole(nextRole);if(useMocks)login(nextRole)}
  return <div className="login-page"><div className="login-art"><div className="login-brand"><span className="brand-mark"><Sparkles size={24}/></span>career<span>quest</span></div><div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="login-art-content"><div className="eyebrow light">НАВИГАТОР КАРЬЕРЫ</div><h1>У каждого шага<br/>есть <em>смысл.</em></h1><p>Персональная траектория развития, в которой видно, что делать дальше и как это приблизит к следующему грейду.</p><div className="art-stats"><div><strong>200</strong><span>сотрудников</span></div><div><strong>40</strong><span>активностей</span></div><div><strong>60</strong><span>навыков</span></div></div></div><div className="art-footer">CAREER QUEST × HACKALEM AI</div></div><div className="login-panel"><div className="login-form"><div className="eyebrow">НАЧНИТЕ СВОЙ ПУТЬ</div><h2>Добро пожаловать</h2><p className="muted">{useMocks?"Выберите сотрудника ниже и нажмите на роль для входа.":"Выберите роль и укажите токен доступа."}</p><div className="role-picker"><button className={role==="employee"?"selected":""} onClick={()=>chooseRole("employee")}><UserRound size={21}/><span>Я сотрудник<small>Мой профиль и шаги</small></span></button><button className={role==="hr"?"selected":""} onClick={()=>chooseRole("hr")}><BriefcaseBusiness size={21}/><span>Я HR<small>Командная аналитика</small></span></button></div>{role==="employee"&&<div className="employee-picker"><label htmlFor="employee-search">Найти сотрудника</label><div className="search-field"><Search size={18}/><input id="employee-search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="ID, имя, роль или грейд"/></div><div className="employee-results">{matches.map(e=><button className={selected===e.employee_id?"chosen":""} key={e.employee_id} onClick={()=>{setSelected(e.employee_id);setQuery("")}}><span className="employee-avatar">{e.full_name?.split(" ").map(w=>w[0]).slice(0,2).join("")||"CQ"}</span><span><b>{e.full_name||e.employee_id}</b><small>{e.employee_id} · {e.role} · {e.grade}</small></span>{selected===e.employee_id&&<span className="selected-dot"/>}</button>)}</div><div className="selected-caption">Выбран: {enteredId||selected}</div></div>}{!useMocks&&<div className="employee-picker"><label htmlFor="api-token">Тестовый bearer-токен {role==="hr"?"HR":"сотрудника"}</label><div className="search-field"><input id="api-token" type="password" value={token} onChange={e=>setToken(e.target.value)} placeholder="Токен локального API"/></div></div>}<button className="primary login-submit" disabled={!useMocks&&!token.trim()} onClick={()=>login()}>Открыть пространство <ArrowRight size={19}/></button><p className="login-note">{useMocks?"Демо на синтетических данных. Бэк для входа не требуется.":"Доступ к данным проверяет API по bearer-токену."}</p></div></div></div>
}
