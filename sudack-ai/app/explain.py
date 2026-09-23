"""Provider strategies and deterministic multilingual explanation fallback."""

import asyncio
import json
from typing import Any, Protocol

from app.models import RecommendRequest
from app.scoring import Candidate


class ExplanationStrategy(Protocol):
    async def select(self, request: RecommendRequest, candidates: list[Candidate]) -> list[dict[str, str]]: ...


class SDKExplanationStrategy:
    """OpenAI SDK client; compatible providers can use a different base_url."""

    def __init__(self, client: Any, model: str, structured: bool = True) -> None:
        self._client = client
        self._model = model
        self._structured = structured

    async def select(self, request: RecommendRequest, candidates: list[Candidate]) -> list[dict[str, str]]:
        language_instruction = {
            "ru": "Write every reason in Russian using Cyrillic.",
            "kk": "Write every reason in Kazakh using Kazakh Cyrillic, not English or Russian.",
            "en": "Write every reason in English.",
        }[request.lang]
        prompt = {
            "next_grade": request.next_grade,
            "lang": request.lang,
            "candidates": [
                {"event_id": item.event.event_id, "title": item.event.title,
                 "factors": item.factors}
                for item in candidates
            ],
        }
        schema = {
            "type": "object",
            "properties": {"recommendations": {"type": "array", "items": {
                "type": "object", "properties": {
                    "event_id": {"type": "string"}, "reason": {"type": "string"},
                }, "required": ["event_id", "reason"], "additionalProperties": False,
            }}},
            "required": ["recommendations"], "additionalProperties": False,
        }
        args: dict[str, Any] = {
            "model": self._model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": (
                    "You are a career navigator. Return JSON with 1 to 3 recommendations. "
                    "Select only candidate event IDs. Use only facts provided in factors; never invent figures. "
                    "In each reason state the exact current and required skill levels and the exact level after "
                    "the activity. Describe participation history from the history factor: activities on the "
                    "same skills (completed/total/missed) matter most; same-type activities on other skills are "
                    "weaker evidence. Say when a skill is critical for the next grade. "
                    "Explain the next-grade requirement, skill gap, participation history, and real gain. "
                    "Mention missed activities tactfully and never blame. Write 2-3 short sentences, addressing "
                    f"the employee respectfully. {language_instruction} Do not compare employees."
                )},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
        }
        if self._structured:
            args["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "career_recommendations", "strict": True, "schema": schema,
            }}
        # NVIDIA's OpenAI-compatible models differ in structured-output support.
        # The prompt still requires JSON; local validation protects the API contract.
        completion = await self._client.chat.completions.create(**args)
        content = completion.choices[0].message.content
        result = json.loads(content)
        if not isinstance(result, dict) or not isinstance(result.get("recommendations"), list):
            raise ValueError("Invalid recommendation response")
        return result["recommendations"]


class FailoverExplanationStrategy:
    """Try providers in order; each attempt gets its own slice of the time budget
    so a hanging first provider cannot starve the second one."""

    def __init__(self, strategies: list[ExplanationStrategy], attempt_timeout: float | None = None) -> None:
        self._strategies = strategies
        self._attempt_timeout = attempt_timeout

    async def select(self, request: RecommendRequest, candidates: list[Candidate]) -> list[dict[str, str]]:
        for strategy in self._strategies:
            try:
                return await asyncio.wait_for(
                    strategy.select(request, candidates), timeout=self._attempt_timeout
                )
            except Exception:
                continue
        raise RuntimeError("No LLM provider returned a usable response")


def template_explain(request: RecommendRequest, candidate: Candidate) -> str:
    primary = candidate.primary_skill
    current, new = candidate.gains[primary]
    name = request.skills_meta.get(primary).name if primary in request.skills_meta else primary
    required = request.next_grade_requirements.get(primary)
    history = next(factor for factor in candidate.factors if factor["type"] == "history")
    total, completed, missed = history["total"], history["completed"], history["missed"]
    type_total, type_completed = history["same_type_total"], history["same_type_completed"]
    critical = primary in request.critical_skills and required is not None
    other_gains = []
    for skill, (old, improved) in candidate.gains.items():
        if skill == primary:
            continue
        other_name = request.skills_meta.get(skill).name if skill in request.skills_meta else skill
        other_required = request.next_grade_requirements.get(skill)
        other_gains.append((other_name, old, improved, other_required))

    if request.lang == "kk":
        if required is None:
            first = f"{name} дағдысы {current} деңгейінен {new} деңгейіне өседі."
        else:
            first = (f"{request.next_grade} деңгейі үшін {name} дағдысы {required} болуы керек"
                     f"{' (бұл дағды грейд үшін шешуші)' if critical else ''}; "
                     f"қазір {current}, ал бұл шарадан кейін {new} болады.")
        second = (f"Осы дағдылар бойынша {total} шараның {completed} аяқталды, {missed} өткізіліп алынды."
                  if total else "Осы дағдылар бойынша қатысу тарихы жоқ.")
        if type_total:
            second += f" Осындай форматтағы басқа {type_total} шараның {type_completed} аяқталды."
        extra = ("Қосымша өсім: " + ", ".join(
            f"{name} {old}→{improved}" + (f" (қажет {needed})" if needed is not None else "")
            for name, old, improved, needed in other_gains
        ) + ".") if other_gains else None
    elif request.lang == "en":
        if required is None:
            first = f"{name} will improve from {current} to {new}."
        else:
            first = (f"{name} is {current} against the {required} needed for {request.next_grade}"
                     f"{' and is critical for that grade' if critical else ''}; "
                     f"this activity raises it to {new}.")
        second = (f"You completed {completed} of {total} activities on these skills and missed {missed}."
                  if total else "You have no history of activities on these skills.")
        if type_total:
            second += f" You completed {type_completed} of {type_total} other activities of the same format."
        extra = ("Other gains: " + ", ".join(
            f"{name} {old}→{improved}" + (f" (required {needed})" if needed is not None else "")
            for name, old, improved, needed in other_gains
        ) + ".") if other_gains else None
    else:
        if required is None:
            first = f"Навык {name} вырастет с {current} до {new}."
        else:
            first = (f"Для {request.next_grade} нужен уровень {required} по навыку {name}"
                     f"{' (критичный навык для грейда)' if critical else ''}; "
                     f"сейчас {current}, после активности будет {new}.")
        second = (f"Вы завершили {completed} из {total} активностей по этим навыкам и пропустили {missed}."
                  if total else "У вас пока нет истории активностей по этим навыкам.")
        if type_total:
            second += f" Из других активностей того же формата вы завершили {type_completed} из {type_total}."
        extra = ("Другие улучшения: " + ", ".join(
            f"{name} {old}→{improved}" + (f" (требуется {needed})" if needed is not None else "")
            for name, old, improved, needed in other_gains
        ) + ".") if other_gains else None
    return " ".join(part for part in (first, extra, second) if part)
