# Frontend (Next.js)

## Зона ответственности

- Экран сотрудника: профиль, траектория, рекомендации с объяснением, «выполнено».
- Экран HR: проседающие навыки, «нет шага», участие, импорт.
- Логин с выбором роли.

Главная цель — **сделать объяснимость видимой**: жюри должно за 5 секунд понять, почему предложен шаг.

## Стек

- Next.js (App Router), TypeScript, Tailwind
- Графики: `recharts`
- Данные: `SWR` или простой `fetch` + `useState`
- UI-кит по желанию: shadcn/ui
- Порт `3000`, API: `NEXT_PUBLIC_API_URL=http://localhost:8080`

## Структура

```
frontend/
  app/
    login/page.tsx
    me/page.tsx
    hr/page.tsx
    layout.tsx
  components/
    ProfileHeader.tsx
    ReadinessBar.tsx
    SkillsChart.tsx
    Trajectory.tsx
    RecommendationCard.tsx
    FactorChip.tsx
    HowCalculated.tsx
    CompleteDeltaToast.tsx
    hr/WeakSkillsChart.tsx
    hr/NoRecommendationList.tsx
    hr/ParticipationTable.tsx
    hr/ImportButton.tsx
  lib/
    api.ts          # fetch-обёртка с токеном
    mocks.ts        # моки из /contracts — работа до 2:30
    types.ts
  Dockerfile
```

> До 2:30 работаем на `mocks.ts`. Переключение на реальный API — флаг `NEXT_PUBLIC_USE_MOCKS`.

## Экраны

### `/login`

- Две кнопки: «Я сотрудник» и «Я HR».
- Для сотрудника — селект с поиском по `employee_id`, роли и грейду.
- После логина токен сохраняется в state/cookie, затем редирект.

### `/me`

Используемые запросы: `GET /api/me`, `GET /api/me/recommendations`, `POST /api/me/activities/{id}/complete`.

**Раскладка сверху вниз:**

1. **ProfileHeader** — роль, грейд → следующий грейд, стаж.
2. **ReadinessBar** — «Готовность к Senior: 61%». После complete анимированно растёт.
3. **SkillsChart** — горизонтальные бары по навыкам следующего грейда: текущий уровень заливкой, требуемый — маркером. Разрыв подсвечен.
4. **RecommendationCard × 1–3** (главный блок):
   - название активности и тип;
   - `reason` крупным текстом;
   - чипсы `factors` с иконками: 🎯 требование грейда, 📉 разрыв, 🕘 история, ⬆️ прирост;
   - прогноз: «System Design 2 → 3», «Готовность 61% → 72%»;
   - `HowCalculated` (раскрывашка): формула и цифры из `calculation`;
   - бейдж «AI» или «Базовое объяснение» в зависимости от `source`;
   - кнопка **«Отметить выполненной»**.
5. **Trajectory** — таймлайн истории: ✅ пройдено, ⏭ пропущено, ✖ отказ. Сверху «следующий шаг» из рекомендаций.

**Поток «выполнено»:**
- Кнопка переходит в loading, затем POST.
- `CompleteDeltaToast`: «System Design 2 → 3, готовность +11%».
- Рефетч `/me` и `/recommendations`, рекомендации показываются скелетоном.

**Производительность (ТЗ: UI ≤2 с, AI ≤10 с):**
- `/me` и `/recommendations` грузятся параллельно. Профиль рендерится сразу, рекомендации — через скелетон с текстом «Подбираем шаги…».
- При `503` показывается «Рекомендации временно недоступны» и кнопка повтора.

### `/hr`

Используемые запросы: `/api/hr/weak-skills`, `/api/hr/no-recommendation`, `/api/hr/participation`, `/api/hr/import`.

1. **WeakSkillsChart** — бар-чарт топ-10 навыков по числу сотрудников с разрывом.
2. **NoRecommendationList** — таблица: сотрудник, роль, грейд, причина. Клик открывает карточку (read-only версию `/me` через `/api/hr/employees/{id}`).
3. **ParticipationTable** — активность, completed / skipped / declined, completion rate. Сортировка по rate, чтобы было видно слабые программы.
4. **ImportButton** — загрузка `employees.json` или `activity_history.csv`, затем тост с отчётом `imported / updated / errors`, после чего все блоки рефетчатся.

**Рейтингов сотрудников нет ни в каком виде.** Это прямой запрет ТЗ.

## Типы (`lib/types.ts`)

```ts
type Factor = {
  type: "grade_requirement" | "skill_gap" | "history" | "effective_gain";
  text?: string; skill?: string; current?: number; required?: number; from?: number; to?: number;
};
type Recommendation = {
  event_id: string; title: string; score: number; reason: string;
  factors: Factor[];
  calculation: { gap_closed: number; engagement: number; formula: string };
};
type RecResponse = {
  recommendations: Recommendation[];
  readiness: { current: number; after_top: number };
  source: "llm" | "fallback";
};
```

## Чеклист

| Время | Задача |
|---|---|
| 0:30–1:00 | Каркас, роутинг, `api.ts`, `mocks.ts` из `/contracts`, логин |
| 1:00–2:00 | `/me`: header, readiness, skills chart, карточки рекомендаций |
| 2:00–2:30 | Поток «выполнено». **К 2:30 — переключение на реальный API** |
| 2:30–3:15 | `/hr`: три блока |
| 3:15–3:45 | Импорт, `HowCalculated`, скелетоны, обработка ошибок |
| 3:45+ | Полировка, скриншоты для README, ru/kk (опционально) |

## Definition of Done

- Открывается произвольный сотрудник и видны роль, грейд, навыки, пройденные активности и следующие шаги.
- В каждой карточке рекомендации видны `reason`, три и больше факторов и блок «как рассчитано».
- «Выполнено» сдвигает навык и готовность без перезагрузки страницы.
- На HR-экране работают все три блока и импорт.
- Сценарий демо проходит без консольных ошибок.
