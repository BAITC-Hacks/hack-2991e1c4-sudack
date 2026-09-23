"""Provider strategies and deterministic multilingual explanation fallback."""

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
                    "Explain next-grade requirements, skill gaps, participation history, and real gains. "
                    "Mention missed similar activities tactfully. Write 2-3 short sentences in the requested "
                    "language (ru, kk, or en), addressing the employee respectfully. Do not compare employees."
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
    def __init__(self, strategies: list[ExplanationStrategy]) -> None:
        self._strategies = strategies

    async def select(self, request: RecommendRequest, candidates: list[Candidate]) -> list[dict[str, str]]:
        for strategy in self._strategies:
            try:
                return await strategy.select(request, candidates)
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

    if request.lang == "kk":
        if required is None:
            first = f"{name} дағдысы {current} деңгейінен {new} деңгейіне өседі."
        else:
            first = (f"{request.next_grade} деңгейі үшін {name} дағдысы {required} болуы керек; "
                     f"қазір {current}, ал бұл шарадан кейін {new} болады.")
        second = (f"Ұқсас {total} шараның {completed} аяқталды, {missed} өткізіліп алынды."
                  if total else "Ұқсас шараларға қатысу тарихы жоқ.")
    elif request.lang == "en":
        if required is None:
            first = f"{name} will improve from {current} to {new}."
        else:
            first = (f"{name} is {current} against the {required} needed for {request.next_grade}; "
                     f"this activity raises it to {new}.")
        second = (f"You completed {completed} of {total} similar activities and missed {missed}."
                  if total else "You have no history of similar activities.")
    else:
        if required is None:
            first = f"Навык {name} вырастет с {current} до {new}."
        else:
            first = (f"Для {request.next_grade} нужен уровень {required} по навыку {name}; "
                     f"сейчас {current}, после активности будет {new}.")
        second = (f"Вы завершили {completed} из {total} похожих активностей и пропустили {missed}."
                  if total else "У вас пока нет истории похожих активностей.")
    return f"{first} {second}"
