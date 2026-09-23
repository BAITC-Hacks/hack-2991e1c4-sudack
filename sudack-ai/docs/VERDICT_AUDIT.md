# Two-case verdict audit

This audit used exactly two live OpenAI requests, one for each synthetic starter-kit employee below. SDK retries and NVIDIA failover were disabled. The fixes described here were verified with offline tests and deterministic responses; no additional paid requests were made after the changes.

| Employee | Target | Live LLM verdict before fixes | Finding | Current deterministic fallback |
| --- | --- | --- | --- | --- |
| `E0001` | Junior → Middle, `kk` | Selected `EV_005` and `EV_036`. | Reasons were in English despite `lang=kk`. The old validator accepted them. | `EV_005` (1.8467), `EV_036` (0.9234); Kazakh reasons. Readiness 0.52 → 0.58 after the first activity. |
| `E0002` | Middle → Senior, `ru` | Selected `EV_005`, `EV_036`, and `EV_011`. | The choices were eligible and relevant, but several reasons omitted exact skill levels or gains. | Same three events (1.8467, 0.9234, 0.7898); Russian reasons with exact levels and history. Readiness 0.60 → 0.64 after the first activity. |

`EV_005` is a useful cross-check. For E0002, it raises both System Design and API Design from 1 to 2 against Senior requirements of 4. Each skill contributes 1.5 to `gap_closed`, totaling 3.0; engagement is 0.5 because 2 of 4 similar activities were completed. Thus `score = 3.0 × 0.5^0.7 = 1.8467`. Before the fix, factors showed only System Design despite the score including API Design. Factors and fallback prose now expose both gains.

For E0001, `EV_012` (Advanced Python) initially appeared as a low-scoring third fallback choice even though Python was already at the Middle requirement. The fallback now uses only gap-closing events when any are eligible, so it returns two steps for this profile. When no gap-closing event exists, it can still return broader development activities.

The live responses were produced before the stricter validation was added. Current code requires the requested language and the key numeric facts in an LLM reason; otherwise it returns `source: "fallback"`. Tests cover the observed English-for-Kazakh failure and vague reasons. This check does not prove that every future LLM sentence is factually correct, and the updated prompt has not been retested live because of the two-call limit.
