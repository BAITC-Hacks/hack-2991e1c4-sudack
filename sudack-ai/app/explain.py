"""Provider strategies and deterministic multilingual explanation fallback."""

import asyncio
import json
import time
from typing import Any, Protocol

from app.models import RecommendRequest
from app.scoring import Candidate


class ExplanationStrategy(Protocol):
    async def select(self, request: RecommendRequest, candidates: list[Candidate]) -> list[dict[str, str]]: ...


class Proposal(list):
    """LLM items plus the name of the provider that produced them."""

    provider: str | None = None
    model: str | None = None


class SDKExplanationStrategy:
    """OpenAI SDK client; any OpenAI-compatible provider works through base_url
    (OpenAI, NVIDIA NIM, a local vLLM or Ollama endpoint)."""

    def __init__(self, client: Any, model: str, structured: bool = True, name: str = "openai") -> None:
        self._client = client
        self._model = model
        self._structured = structured
        self.name = name
        self.model = model

    async def select(self, request: RecommendRequest, candidates: list[Candidate]) -> list[dict[str, str]]:
        language_instruction = {
            "ru": "Write every reason in Russian using Cyrillic.",
            "kk": "Write every reason in Kazakh using Kazakh Cyrillic, not English or Russian.",
            "en": "Write every reason in English.",
        }[request.lang]
        example = {
            "ru": "System Design: сейчас 2, требуется 4 для Senior (критичный навык), после активности 3. "
                  "По этим навыкам вы завершили 1 из 2 активностей и пропустили 1. "
                  "Это главный разрыв для перехода на Senior.",
            "kk": "System Design: қазір 2, Senior үшін 4 қажет (шешуші дағды), шарадан кейін 3. "
                  "Осы дағдылар бойынша 2 шараның 1-ін аяқтадыңыз, 1-ін өткізіп алдыңыз. "
                  "Бұл Senior-ға өту үшін басты алшақтық.",
            "en": "System Design: current 2, required 4 for Senior (critical), after this activity 3. "
                  "You completed 1 of 2 activities on these skills and missed 1. "
                  "This is the main gap for Senior.",
        }[request.lang]
        prompt = {
            "employee": {"role": request.employee.role, "grade": request.employee.grade},
            "next_grade": request.next_grade,
            "lang": request.lang,
            "candidates": [llm_view(request, item) for item in candidates],
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
            "max_tokens": 700,  # three short reasons; keeps gpt-4o inside the time budget
            "messages": [
                {"role": "system", "content": (
                    "You are a career navigator. Return JSON with 1 to 3 recommendations, ordered by usefulness "
                    "for reaching the next grade. Select only candidate event IDs. Prefer candidates with "
                    "closes_gap=true; include a closes_gap=false candidate only when fewer than three gap-closing "
                    "candidates exist, and say plainly that it is optional growth. Returning 1 or 2 items is fine. "
                    "Use only the facts provided; never invent figures and never mention scores, weights or "
                    "internal values. For each skill state the exact current level, the exact required level "
                    "(when required is not null) and the exact level after the activity: translate each skill's "
                    "`fact` string into the target language and keep all three numbers. "
                    "Vocabulary: a skill with required != null is REQUIRED for the next grade; critical=true means "
                    "it is additionally CRITICAL for promotion. A required skill that is not critical is still "
                    "required, so never say it is 'not required' or 'not important'. Use skill names and grade "
                    "names exactly as given. Describe participation history from the history facts: activities on "
                    "the same skills (completed/total/missed) matter most; same-type activities on other skills "
                    "are weaker evidence; mention missed activities tactfully and never blame. Each reason must be "
                    "specific to its event and different from the other reasons. STRUCTURE of every reason, in this "
                    "order: (1) the `fact` line of each skill translated with all three numbers kept; (2) one sentence "
                    "on participation history from the history counts; (3) one sentence on why it matters for the next "
                    f"grade. Example of the expected shape: \"{example}\" Address the employee respectfully. "
                    f"{language_instruction} Do not compare employees."
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
        proposal = Proposal(result["recommendations"])
        proposal.provider, proposal.model = self.name, self._model
        return proposal


class FailoverExplanationStrategy:
    """Try providers in order against one deadline. A provider that fails fast hands all of the
    remaining time to the next one; a provider that is not last is capped at `primary_share`
    of what is left, so a hanging primary cannot starve the secondary."""

    def __init__(
        self,
        strategies: list[ExplanationStrategy],
        attempt_timeout: float | None = None,
        budget: float | None = None,
        primary_share: float = 0.75,
    ) -> None:
        self._strategies = strategies
        self._attempt_timeout = attempt_timeout
        self._budget = budget
        self._primary_share = primary_share

    def _timeout_for(self, index: int, deadline: float | None) -> float | None:
        timeout = self._attempt_timeout
        if deadline is not None:
            remaining = max(0.0, deadline - time.monotonic())
            is_last = index == len(self._strategies) - 1
            slice_ = remaining if is_last else remaining * self._primary_share
            timeout = slice_ if timeout is None else min(timeout, slice_)
        return timeout

    async def select(self, request: RecommendRequest, candidates: list[Candidate]) -> Proposal:
        deadline = time.monotonic() + self._budget if self._budget is not None else None
        for index, strategy in enumerate(self._strategies):
            timeout = self._timeout_for(index, deadline)
            if timeout is not None and timeout <= 0:
                break
            try:
                items = await asyncio.wait_for(strategy.select(request, candidates), timeout=timeout)
            except Exception:
                continue
            proposal = items if isinstance(items, Proposal) else Proposal(items)
            proposal.provider = proposal.provider or getattr(strategy, "name", None)
            proposal.model = proposal.model or getattr(strategy, "model", None)
            return proposal
        raise RuntimeError("No LLM provider returned a usable response")


def llm_view(request: RecommendRequest, candidate: Candidate) -> dict[str, Any]:
    """What the LLM is allowed to see: facts, not scoring internals."""
    history = next(factor for factor in candidate.factors if factor["type"] == "history")
    skills = []
    for skill, (current, new) in candidate.gains.items():
        required = request.next_grade_requirements.get(skill)
        name = request.skills_meta.get(skill).name if skill in request.skills_meta else skill
        critical = skill in request.critical_skills and required is not None
        if required is None:
            fact = f"{name}: current {current}, not required for {request.next_grade}, after this activity {new}"
        else:
            fact = (f"{name}: current {current}, required {required} for {request.next_grade}"
                    f"{' (critical)' if critical else ''}, after this activity {new}")
        skills.append({
            "skill_id": skill,
            "name": name,
            "current": current,
            "required": required,
            "after": new,
            "critical": critical,
            "closes_gap": required is not None and current < required,
            "fact": fact,
        })
    description = (candidate.event.description or "")[:240] or None
    return {
        "event_id": candidate.event.event_id,
        "title": candidate.event.title,
        "type": candidate.event.type,
        "description": description,
        "closes_gap": candidate.closes_gap,
        "skills": skills,
        "facts_sentence": "; ".join(item["fact"] for item in skills) + ". History: " + history["text"] + ".",
        "history": {key: value for key, value in history.items() if key != "type"},
    }


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
