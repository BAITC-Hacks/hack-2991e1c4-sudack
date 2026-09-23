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
sudack-ai/
  main.py                 # точка входа uvicorn: app = create_app()
  app/
    api.py                # FastAPI, роуты, сборка провайдеров
    models.py             # Pydantic-схемы; принимает и компактный, и starter-kit формат событий
    scoring.py            # вся математика (веса, похожесть, engagement, readiness)
    recommendation.py     # оркестрация: скоринг → LLM → валидация → фолбэк → кэш; batch
    explain.py            # LLM-стратегии (OpenAI SDK, failover) + шаблонный фолбэк ru/kk/en
    cache.py              # LRU-кэш по хэшу запроса (только llm-ответы)
    config.py             # env: OPENAI_API_KEY, NVIDIA_API_KEY, LLM_MODEL, LLM_TIMEOUT=8
  scripts/audit_verdict.py  # один живой вызов LLM для проверки verdict
  tests/                  # трап-профили, контракт, датасет на 200 сотрудников
  docs/api.md             # HTTP-контракт (обязателен к обновлению, см. AGENTS.md)
  Dockerfile, pyproject.toml, uv.lock
```

Запуск: `uv sync && uv run uvicorn main:app --port 8001`, тесты: `uv run pytest`.

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

`source`: `"llm"` | `"fallback"`. У каждой рекомендации есть `reason_source`: `"llm"` — текст написан моделью и прошёл валидацию, `"template"` — детерминированный шаблон. Поле `calculation` фронт показывает в блоке «Как рассчитано». В ответе также `gaps` (навыки ниже требования) и `applied_progress` — приросты, применённые из завершённых после `last_review_date` активностей (так «отметить выполненным» двигает прогресс до следующей аттестации).

### `POST /score/batch`

- Вход: `{"items": [<тот же объект, что в /recommend, без lang>]}`.
- Выход: `{"results": [{"employee_id": "E0028", "top": [{"event_id": "EV07", "score": 0.82, "primary_skill": "SK_SYSTEM_DESIGN"}], "readiness": 0.61, "gaps": {"SK_SYSTEM_DESIGN": 2}}]}`.
- `gaps` — только навыки ниже требования (для HR-среза «какие навыки проседают»); пустой `top` — «нет рекомендованного шага».
- **Без LLM.** На 200 сотрудников стартового кита ~0.2 с.

### `POST /simulate` — симулятор перехода на грейд

Тот же вход, что у `/recommend` (плюс `as_of`). Жадный маршрут: на каждом шаге берём допустимое событие с максимальным взвешенным закрытием разрыва, применяем gain/max_level, ставим на первую свободную дату из `upcoming_sessions` (после шага, давшего prerequisites; self_paced — сразу; recurring может повторяться). Выход: `steps` с датами, часами и изменениями навыков, `readiness_path`, `total_hours`, `estimated_completion`, `coverage` (сколько уровней разрыва закрывает каталог), `remaining_gaps` и `blocked` с причиной, на которую HR может повлиять: `no_event_for_skill` | `audience` | `ceiling` | `prerequisites` | `already_completed` | `step_limit` | `unscheduled`. На ките ни один сотрудник не достигает грейда полностью — это свойство каталога из 40 событий, и это само по себе HR-инсайт.

### `POST /events/impact` — конструктор события с прогнозом эффекта

Вход: `{"event": <черновик события>, "items": [<как в /recommend>]}`. Без LLM, 200 сотрудников ~0.2 с. Выход: кто может участвовать, кто закроет разрыв, ожидаемое число завершений (сумма engagement по истории), уровней закрыто, `hours_per_gap_level` (стоимость результата в часах бюджета), разбивка по навыкам, `catalog_rank` и топ-5 существующих событий для сравнения.

### Дополнительно в `/recommend` и `/score/batch`

- `rejected` в `/recommend`: контрфактическое объяснение для ловушечных профилей — до двух альтернатив, которые выбрало бы однофакторное правило (самый большой разрыв, следующий по score), и почему каждая проиграла топу: пропуски по этому навыку, «критичный vs нет», вне требований, меньший вклад. Текст на `lang`.
- `risk` в `/score/batch`: риск выпадения из развития 0–1 с уровнем low/medium/high, кодами причин (`high_miss_rate`, `recent_misses`, `inactive`, `stale_in_progress`, `declined_assignments`) и `suggested_format`, если сотрудник завершает один формат и пропускает другой. Формула: `0.45·доля пропусков + 0.25·min(недавние пропуски/3, 1) + 0.2·неактивен 180 дней + 0.1·зависший in_progress`.

### `GET /health`

Возвращает `{"status": "ok"}`.

## Логика скоринга (`scoring.py`)

```python
def skill_gaps(skills, reqs) -> dict:
    return {s: max(0, req - skills.get(s, 0)) for s, req in reqs.items()}

def skill_weight(skill, reqs, critical) -> float:
    if skill in critical and skill in reqs: return 2.5   # critical_skills целевого грейда
    if skill in reqs:   return 1.5                        # прочие требования следующего грейда
    return 0.3                                            # рост вне требований

def effective_gain(event, skills) -> dict:
    out = {}
    for s, g in event["skills"].items():
        cur = skills.get(s, 0)
        new = min(cur + g["gain"], g["max_level"])
        if new > cur:
            out[s] = (cur, new)
    return out

def eligible_events(employee, events, history) -> list:
    done   = {h.event_id for h in history if h.status == "completed"}
    active = {h.event_id for h in history if h.status in {"in_progress", "overdue"}}
    # исключаем: mandatory; active; done (кроме recurring, EV_036); не та роль/грейд;
    # невыполненные prerequisites; нулевой effective_gain

def engagement(history, event, events_by_id, latest_date) -> float:
    # похожесть по НАВЫКАМ — основной сигнал; тот же type без общих навыков — слабый (×0.3);
    # записи старше года от последней даты истории — ×0.6 (без даты — вес 1.0)
    w = done = 0.0
    for h in history:
        if h.status == "in_progress": continue  # исход ещё неизвестен
        past = events_by_id[h.event_id]
        tier = 1.0 if past.skills & event.skills else 0.3 if past.type == event.type else None
        if tier is None: continue
        weight = tier * (1.0 if recent(h.date, latest_date) else 0.6)
        w += weight; done += weight * (h.status == "completed")
    return (done + 1) / (w + 2)                            # Лаплас: без истории → 0.5
    # Пропуски = no_show, declined, dropped, overdue (skipped принимается для совместимости)

def score_event(event, ctx) -> tuple[float, list, dict]:
    gains = effective_gain(event, ctx.skills)
    gap_closed = sum(ctx.w[s] * min(new - cur, ctx.gaps.get(s, 0) or 0.2)
                     for s, (cur, new) in gains.items())
    eng = engagement(ctx.history, event, ctx.events_by_id)
    score = gap_closed * eng ** 0.7
    # factors собираем здесь же — LLM получает готовые факты
    return score, factors, calculation

def readiness(skills, reqs, critical) -> float:
    total = sum(skill_weight(s, reqs, critical) * r for s, r in reqs.items())
    missing = sum(skill_weight(s, reqs, critical) * g for s, g in skill_gaps(skills, reqs).items())
    return round(1 - missing / total, 2) if total else 1.0
```

Почему так: у жюри профиль, где самый низкий навык (Public Speaking) трижды пропущен, а для грейда критичен System Design. Вес 2.5 на critical выводит System Design вперёд даже при равных разрывах, а похожесть по навыкам не «размазывает» пропуски Public Speaking на все воркшопы — history-фактор у System Design остаётся честным («0 из 0 по этим навыкам»).

**Диверсификация топа:** после сортировки не берём два события на один и тот же навык подряд (мягкий штраф ×0.8 за повтор навыка). Отдаём в LLM топ-5.

## LLM-слой (`explain.py`)

- Модель — самая сильная из доступных. Бюджет позволяет.
- `temperature=0`, structured outputs (JSON-схема: `[{event_id, reason}]`, от 1 до 3 элементов).
- Таймаут 8 с через `asyncio.wait_for`; при двух провайдерах (OpenAI → NVIDIA) каждому достаётся половина бюджета, чтобы зависший первый не съел время второго.
- **Что видит LLM:** только факты — название/описание события, по каждому навыку `fact` вида «System Design: current 2, required 4 for Senior (critical), after this activity 3», флаги `critical` и `closes_gap`, счётчики истории. Веса и score модели не показываем (иначе пишет «закроет 2.5 из 2»).
- **Кандидаты для LLM:** до 5 событий, закрывающих разрыв; события «для развития» добавляются, только если таких меньше трёх.
- **Валидация (по каждому элементу):** `event_id` из кандидатов, язык `reason` совпадает с `lang` (kk — по казахским буквам), упомянута история участия, в тексте есть точные числа текущего/требуемого/итогового уровня, текст не дублирует другой reason. Невалидный reason заменяется шаблоном для этого же события (`reason_source: "template"`); если ни один reason модели не прошёл — полный фолбэк.
- **Модель:** `gpt-4o` (в живой проверке 2026-09-23 `gpt-4o-mini` регулярно терял требуемый уровень и путал «не критичный» с «не требуется»).

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

LRU на 512 записей `{sha1(json(полный запрос)): response}`. Кэшируются только ответы `source: "llm"` — фолбэк из-за временного сбоя провайдера не должен «залипать». После «выполнено» у сотрудника меняется история, поэтому хэш сам по себе становится другим, и инвалидировать ничего не нужно.

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
