# Two-case verdict audit

This audit used exactly two live OpenAI requests, one for each synthetic starter-kit employee below. SDK retries and NVIDIA failover were disabled. The fixes described here were verified with offline tests and deterministic responses; no additional paid requests were made after the changes.

| Employee | Target | Live LLM verdict before fixes | Finding | Current deterministic fallback |
| --- | --- | --- | --- | --- |
| `E0001` | Junior → Middle, `kk` | Selected `EV_005` and `EV_036`. | Reasons were in English despite `lang=kk`. The old validator accepted them. | `EV_005` (1.8467), `EV_036` (0.9234); Kazakh reasons. Readiness 0.52 → 0.58 after the first activity. |
| `E0002` | Middle → Senior, `ru` | Selected `EV_005`, `EV_036`, and `EV_011`. | The choices were eligible and relevant, but several reasons omitted exact skill levels or gains. | Same three events (1.8467, 0.9234, 0.7898); Russian reasons with exact levels and history. Readiness 0.60 → 0.64 after the first activity. |

`EV_005` is a useful cross-check. For E0002, it raises both System Design and API Design from 1 to 2 against Senior requirements of 4. Each skill contributes 1.5 to `gap_closed`, totaling 3.0; engagement is 0.5 because 2 of 4 similar activities were completed. Thus `score = 3.0 × 0.5^0.7 = 1.8467`. Before the fix, factors showed only System Design despite the score including API Design. Factors and fallback prose now expose both gains.

For E0001, `EV_012` (Advanced Python) initially appeared as a low-scoring third fallback choice even though Python was already at the Middle requirement. The fallback now uses only gap-closing events when any are eligible, so it returns two steps for this profile. When no gap-closing event exists, it can still return broader development activities.

The live responses were produced before the stricter validation was added. Current code requires the requested language and the key numeric facts in an LLM reason; otherwise it returns `source: "fallback"`. Tests cover the observed English-for-Kazakh failure and vague reasons. This check does not prove that every future LLM sentence is factually correct, and the updated prompt has not been retested live because of the two-call limit.

## Update after code review

Validation is now per item: an ungrounded or unknown item is dropped and the remaining grounded items are kept, so one bad sentence no longer discards a good verdict. The required numeric facts are the current, required, and resulting skill levels; history counts may be stated in words. Only validated `llm` answers are cached, so a transient provider failure is not pinned as `fallback`. Scoring changed as well: critical skills weigh 2.5, similarity is skill-based with same-type history at 0.3, history older than a year at 0.6, and in-progress events are not recommended again. The live prompt has still not been re-run; do so with `uv run python scripts/audit_verdict.py --live E0002` before the demo.

## Live re-audit, 2026-09-23 (E0004 ru, E0005 kk, E0008 en, E0025 kk)

Round 1 on `gpt-4o-mini` with the previous prompt: every call returned `source: "llm"`, but the model quoted scoring weights as levels ("закроет 2.5 из 2"), copy-pasted one reason onto two events (E0005), called a required skill "not required" because it was not critical (E0005, E0008), and omitted the required level so the validator dropped the two best critical-gap picks for E0004 and left only Public Speaking Club.

Fixes: the LLM now receives a sanitized fact view (skill names, current/required/after, `critical`, `closes_gap`, event description, history counts, and a ready-made `fact` sentence per skill) and never sees weights; candidates are gap-closing first; the prompt defines required vs critical and forbids duplicate reasons; an ungrounded or duplicate reason is replaced by the template for that event instead of dropping the event; each recommendation reports `reason_source`.

Round 2 on `gpt-4o-mini`: E0004 and E0008 selections correct, one reason each templated (missing history mention or a false "not required" claim caught by the level check). E0005 initially fell back because both Kazakh reasons omitted the required level; with the `fact` sentences it passed with two `llm` reasons. Round 2 on `gpt-4o`: E0005 and E0008 returned all reasons as `llm`, mentioning the event title, all three levels, and history. `LLM_MODEL=gpt-4o` is now the documented default.

## Provider switching check, 2026-09-23

The chain is configurable (`LLM_PROVIDERS`), visible (`GET /providers`) and every `llm` response names its provider. Live results with the hackathon keys:

- `openai` / `gpt-4o`: E0028 answered in one call, `source: llm`, `llm_provider: openai`.
- `nvidia`: the key is accepted by `GET /v1/models` (82 models listed) but every chat completion returns `401 Authentication failed`, and the previous default `meta/llama-3.1-8b-instruct` is retired (`410 Gone`). The default is now `nvidia/llama-3.1-nemotron-70b-instruct`; the key itself needs to be checked in the NVIDIA build portal before NVIDIA can serve live explanations.
- `LLM_PROVIDERS=nvidia,openai` with both keys: NVIDIA fails within its time slice, OpenAI answers, the response reports `llm_provider: openai`. This is the failover path working end to end.
