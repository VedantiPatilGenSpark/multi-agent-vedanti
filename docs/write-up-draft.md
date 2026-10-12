# Write-up

Detailed notes behind the public [README](../README.md). The README is the overview: what the pipeline is, how to run the five cases, and how another product plugs in. This file keeps the homeowners rubric, the timeout behavior, and how cost is simulated.

`docs/prd.md` is the build spec. If this file and the PRD disagree, the PRD wins.

## Product-neutral pipeline

The underwriting pipeline is product-neutral. The harness has no product router. It always runs the same sequence: intake, enrichment, risk scoring, then recommendation. Each agent reads a fixed slice of the case and returns one section. The harness is the only writer, and it stores that section under that agent’s key.

Only homeowners is filled in. `run_case` constructs `HomeownersPack`. The harness does not know about roofs, claims, territory, or credit, and it does not contain band cutoffs. A second product is another pack with the same slots, not a new orchestrator. `load_pack` checks that a registered pack fills those slots. This lab ships the seam and fills it with the homeowners pack only.

## Homeowners pack

This is the example of a product line pack. Each piece plugs into a fixed slot in the pipeline. Nothing in this list is hardcoded in the harness.

| Pack piece | What the homeowners pack contains | Pipeline slot |
| --- | --- | --- |
| Application schema | `applicant_id`, `name`, `state`, `year_built`, `roof_age`, `construction`, `coverage_amount`, `prior_claims` (`year`, `peril`, `amount`) | Intake reads a raw application of this shape and returns a normalized `application`. Missing values stay null. |
| Fixtures | JSON applications for approve, refer, deny, credit-lookup recovery, and credit-lookup timeout | The script and the tests load a fixture by `applicant_id` and pass it to intake. |
| Prompts | One prompt fragment per agent, written for homeowners | Each agent call receives that fragment plus the case slice for its step. |
| Territory table | SQLite rows keyed by state, with a wind-and-hail band and a wildfire band | Enrichment calls a lookup with the state from `application`. An unknown or missing state returns null bands. |
| Credit table | SQLite rows keyed by `applicant_id`, with a bureau score and a delinquency count. The deny fixture has no row. | The risk step calls `credit_lookup`. A missing row is `no_file`, which is a normal result. |
| Risk rubric | The point table below, including the cap | The risk model applies this table and returns the lines, a score, and an assessment. Generic code checks internal consistency only: cited line ids exist, points match those lines, and the score equals the sum of those points, capped at the maximum. A reply that omits a true line still passes. Code does not rescore. If the check fails, the harness does not retry the model and does not write `risk`. It escalates with the reason that the risk score was unusable. |
| Band table | Approve below 30, refer from 30 through 59, deny at 60 and above | Code chooses the outcome from this table before the recommendation model is called, and copies the validated score onto the decision. The model writes the rationale. |

### Homeowners risk rubric

The model adds each line that applies and caps the total at the maximum. Points below are the homeowners pack’s values, not pipeline constants.

| Line | Points |
| --- | --- |
| Roof age null | 20 |
| Roof age 0 through 25 | 10 |
| Roof age 26 or greater | 20 |
| Building age 0 through 40, as of 2026 | 4 |
| Building age 41 or greater | 15 |
| Water claim in 2021 or later | 25 |
| No credit file | 15 |
| Wildfire band high | 15 |
| Wind and hail band high | 10 |

The score cannot go above 100.

The model does not own every field on a section. Intake returns the normalized application. Enrichment’s model writes the note, and code copies the territory result from the lookup. Risk’s model writes the lines, the score, and the assessment, and code attaches the credit result after the audit. Recommendation’s model writes the rationale. Code sets the outcome and the score.

The lab’s timeout switch is fixture configuration for two homeowners applicant ids. It sits in front of the credit query and raises on chosen attempt numbers. It is not a harness branch, and it is not a rule in the rubric. A second product would not inherit those ids. A fixed 0.2s backoff sits between attempt 1 and attempt 2. When the second attempt also raises, `status` is `escalated`, `risk` stays empty, and the case has no approve, deny, or refer outcome. Recommendation is not called. `escalated` is the failure flag. It is separate from a completed `refer`.

Live traces use `qwen3:8b` for every agent, with thinking turned off. Dollar figures are simulated at $0.10 per 1M input tokens and $0.40 per 1M output tokens, applied to the measured token counts. The pipeline does not hardcode a token budget. Latency printed by the live script is the sum of each trace entry’s duration. The 0.2s backoff between credit attempts is a sleep between those entries. Simulated cost and latency for `APP-APPROVE`, `APP-REFER`, and `APP-DENY`, and the real-time versus overnight-batch conclusion, are recorded here after a live run. Those figures are not in this draft yet.

Prompts stay specific because the product text is data. A single generic prompt for “any insurance” would be too vague to score consistently. The agent functions stay generic because they receive the product’s fields, lookup results, and prompt fragment instead of hard-coding homeowners rules into the harness.
