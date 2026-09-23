# AI-сервис (Python / FastAPI)

## Зона ответственности

- Скоринг активностей для сотрудника (детерминированный, объяснимый).
- Выбор 1–3 шагов и объяснение через LLM.
- Фолбэк без LLM.
- Batch-скоринг для HR.

**Stateless.** БД нет, весь контекст присылает Go. Сервис не знает про роли и права — это задача Go.

## Стек

- Python 3.11+, FastAPI, Pydantic v2, uvicorn
- `openai` SDK (креды хакатона); NVIDIA — запасной LLM через тот же SDK со сменой `base_url`
- Порт: `8001`

## Структура

```
ai-service/
  app/
    main.py          # FastAPI, роуты
    models.py        # Pydantic-схемы (из /contracts)
    scoring.py       # вся математика
    explain.py       # LLM + шаблонный фолбэк
    cache.py         # dict-кэш по хэшу
    config.py        # env: OPENAI_API_KEY, LLM_MODEL, LLM_TIMEOUT=8
  tests/
    test_trap_profiles.py
  Dockerfile
  requirements.txt
```

## Эндпоинты

### `POST /recommend`

**Вход:**

```json
{
  "employee": {
    "employee_id": "E0028",
    "role": "Backend Engineer",
    "grade": "Middle",
    "tenure_months": 52,
    "skills": {"SK_PYTHON": 3, "SK_SYSTEM_DESIGN": 2, "SK_PUBLIC_SPEAKING": 2}
  },
  "next_grade": "Senior",
  "next_grade_requirements": {"SK_SYSTEM_DESIGN": 4, "SK_PYTHON": 4},
  "skills_meta": {"SK_SYSTEM_DESIGN": {"name": "System Design", "category": "hard"}},
  "history": [{"event_id": "EV12", "date": "2025-03", "status": "skipped"}],
  "events": [{
    "event_id": "EV07",
    "title": "System Design Workshop",
    "type": "workshop",
    "audience": {"roles": ["Backend Engineer"], "grades": ["Middle"]},
    "skills": {"SK_SYSTEM_DESIGN": {"gain": 1, "max_level": 4}}
  }],
  "lang": "ru"
}
```

**Выход:**

```json
{
  "recommendations": [{
    "event_id": "EV07",
    "title": "System Design Workshop",
    "score": 0.82,
    "reason": "System Design — 2 при требуемых 4 для Senior; воркшоп поднимет до 3. Две предыдущие технические активности вы прошли в срок.",
    "factors": [
      {"type": "grade_requirement", "text": "Критичен для перехода Middle → Senior"},
      {"type": "skill_gap", "skill": "SK_SYSTEM_DESIGN", "current": 2, "required": 4},
      {"type": "history", "text": "2 из 2 похожих активностей пройдены"},
      {"type": "effective_gain", "skill": "SK_SYSTEM_DESIGN", "from": 2, "to": 3}
    ],
    "calculation": {"gap_closed": 1.5, "engagement": 0.75, "formula": "1.5 · 0.75^0.7 · 1.0"}
  }],
  "readiness": {"current": 0.61, "after_top": 0.72},
  "source": "llm"
}
```

`source`: `"llm"` | `"fallback"`. Поле `calculation` фронт показывает в блоке «Как рассчитано».

### `POST /score/batch`

- Вход: `{"items": [<тот же объект, что в /recommend, без lang>]}`.
- Выход: `{"results": [{"employee_id": "E0028", "top": [{"event_id": "EV07", "score": 0.82}], "readiness": 0.61}]}`.
- **Без LLM.** Должен укладываться примерно в 1 с на 200 сотрудников.

### `GET /health`

Возвращает `{"status": "ok"}`.

## Логика скоринга (`scoring.py`)

```python
def skill_gaps(skills, reqs) -> dict:
    return {s: max(0, req - skills.get(s, 0)) for s, req in reqs.items()}

def skill_weight(skill, reqs, skills_meta) -> float:
    if skill in reqs:   return 1.5    # нужен для следующего грейда
    return 0.3                         # прочие (можно 1.0 для навыков роли, если есть в данных)

def effective_gain(event, skills) -> dict:
    out = {}
    for s, g in event["skills"].items():
        cur = skills.get(s, 0)
        new = min(cur + g["gain"], g["max_level"])
        if new > cur:
            out[s] = (cur, new)
    return out

def eligible_events(employee, events, history) -> list:
    done = {h.event_id for h in history if h.status == "completed"}
    # аудитория по роли/грейду; уже пройденные исключаем; нулевой effective_gain исключаем

def engagement(history, event, events_by_id) -> float:
    similar = [h for h in history if is_similar(events_by_id[h.event_id], event)]
    # is_similar: тот же type ИЛИ пересечение по навыкам
    completed = sum(h.status == "completed" for h in similar)
    return (completed + 1) / (len(similar) + 2)          # Лаплас: без истории → 0.5

def score_event(event, ctx) -> tuple[float, list, dict]:
    gains = effective_gain(event, ctx.skills)
    gap_closed = sum(ctx.w[s] * min(new - cur, ctx.gaps.get(s, 0) or 0.2)
                     for s, (cur, new) in gains.items())
    eng = engagement(ctx.history, event, ctx.events_by_id)
    score = gap_closed * eng ** 0.7
    # factors собираем здесь же — LLM получает готовые факты
    return score, factors, calculation

def readiness(skills, reqs) -> float:
    total = sum(1.5 * r for r in reqs.values())
    missing = sum(1.5 * g for g in skill_gaps(skills, reqs).values())
    return round(1 - missing / total, 2) if total else 1.0
```

**Диверсификация топа:** после сортировки не берём два события на один и тот же навык подряд (мягкий штраф ×0.8 за повтор навыка). Отдаём в LLM топ-5.

## LLM-слой (`explain.py`)

- Модель — самая сильная из доступных. Бюджет позволяет.
- `temperature=0`, structured outputs (JSON-схема: `[{event_id, reason}]`, от 1 до 3 элементов).
- Таймаут 8 с через `asyncio.wait_for`.
- **Валидация:** каждый `event_id` должен входить в кандидатов, `reason` не пустой. Иначе фолбэк.

### Системный промпт (черновик)

```
Ты — карьерный навигатор. Выбери 1–3 активности из списка кандидатов для сотрудника.
Правила:
- Используй ТОЛЬКО факты из поля factors. Не придумывай цифры.
- В обосновании каждой активности минимум три фактора: требование следующего грейда,
  разрыв по навыку, история участия, реальный прирост.
- Если сотрудник раньше пропускал похожие активности — учти это и скажи прямо, но без упрёка.
- Пиши кратко (2–3 предложения), на языке: {lang}. Обращение на «вы».
- Не упоминай других сотрудников и не сравнивай с ними.
- Порядок — по пользе для перехода на {next_grade}, не обязательно по score.
```

### Фолбэк `template_explain`

```
«{skill}: {current} при требуемых {required} для {next_grade}; активность поднимет до {to}.
{history_text}.»
```

## Кэш

Словарь `{sha1(json(employee, history, lang)): response}`. После «выполнено» у сотрудника меняется история, поэтому хэш сам по себе становится другим, и инвалидировать ничего не нужно.

## Чеклист

| Время | Задача |
|---|---|
| 0:30–1:00 | Pydantic-модели по реальному стартовому киту, `/health`, Dockerfile |
| 1:00–1:45 | `scoring.py` + `/score/batch` + `/recommend` с `template_explain` |
| 1:45–2:30 | LLM-слой, валидация, таймаут. **К 2:30 `/recommend` работает с Go** |
| 2:30–3:15 | `tests/test_trap_profiles.py`: 3 своих ловушечных профиля |
| 3:15–3:45 | Тюнинг весов и промпта, казахский язык в `reason` |
| 3:45+ | Раздел README про скоринг с примером расчёта |

## Ловушечные профили для тестов

1. **Минимальный навык не критичен.** Public Speaking = 1, трижды skipped похожие активности, для грейда критичен System Design = 2/4. Ожидаем System Design.
2. **Навык на потолке.** Самый большой разрыв по навыку X, но все активности по X имеют `max_level` ≤ текущего уровня. Ожидаем, что X **не** рекомендуется.
3. **Нет истории.** Новый сотрудник: engagement = 0.5 по всем активностям, решают разрывы до следующего грейда.

## Definition of Done

- На трёх ловушечных профилях результат совпадает с ожиданием.
- В каждой рекомендации три и больше factors.
- Время `/recommend` меньше 10 с, при недоступной LLM сервис всё равно отвечает (`source: "fallback"`).
- `/score/batch` на 200 профилей укладывается примерно в 1 с.
