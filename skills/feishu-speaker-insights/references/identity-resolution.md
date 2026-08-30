# Identity resolution

Read this reference before extracting context evidence or explaining confidence.

## Evidence boundary

The acoustic stage owns Top-1, Top-2, similarity, thresholds, usable duration, segment votes, and mixed-speaker detection. Semantic analysis must not alter those values.

Context extraction is limited to transcript-grounded identity clues:

- `exact_named_label`: the Feishu transcript label exactly equals a person in the current candidate cohort; generated deterministically and strong.
- `self_identification`: explicit self-introduction by the target label; strong.
- `direct_address_response`: a person is named and the target label responds immediately; normally strong when adjacent and within 20 seconds.
- `explicit_address`: explicit naming that is not an immediate reply; medium or weak depending on ambiguity.
- `role_semantics`: statements consistent with a role; never sufficient by itself and normally weak.
- `third_party_reference`: another speaker describes or names the person; medium only when unambiguous.

## Deterministic precedence

| Acoustic state | Context state | Final state |
|---|---|---|
| High match | agree/none | Voiceprint matched, high |
| High match | strong conflict | Keep voice identity, medium, review required |
| Medium match | agree/none | Voiceprint matched, medium |
| Medium match | strong conflict | Keep voice identity, low, review required |
| Near threshold | strong context supports acoustic Top-1 | Context-assisted inference, medium |
| Any unaccepted acoustic result | strong, explicit context names a cohort person | Context-assisted identification, medium; preserve Top-1/Top-2 |
| Any unaccepted acoustic result | strong, explicit context names a person outside the cohort | Context-only identification outside voiceprint bank, medium; preserve Top-1/Top-2 |
| Any unaccepted acoustic result | weak/ambiguous context | Unknown or insufficient evidence; preserve Top-1/Top-2 |
| Mixed acoustic votes | any | Mixed/uncertain; do not merge |

A context identity is `strong` only when its weighted evidence clearly exceeds alternatives. Role semantics alone can never produce strong context.

## Report wording

- Say “声纹相似度” or “候选集中的声纹证据,” never “身份概率.”
- Distinguish `声纹已匹配` from `上下文辅助推断`.
- Distinguish both from `上下文识别（声纹库外）`; the latter is not a voiceprint match and must not create or update a profile.
- When context conflicts, state both identities and preserve the voiceprint result.
- A low confidence result is not an assertion that the person was absent.
- Top-1 and Top-2 are always ranking evidence, including for unknown outcomes. Thresholds remain internal and require no user configuration.
