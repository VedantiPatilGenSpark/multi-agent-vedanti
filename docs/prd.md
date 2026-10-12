# PRD: Multi-agent homeowners underwriting pipeline

Status: locked for implementation.  
Audience: an implementing agent.  
The public overview is `README.md`. This file is the build spec. `docs/write-up-draft.md` keeps the homeowners rubric, timeout behavior, and cost notes behind that README. If this file and the write-up disagree, this file wins.

## 1. Purpose

Build a four-step underwriting pipeline that an insurance product pack plugs into. This lab ships one pack, homeowners. The harness never branches on product line.

The pipeline captures a raw application, adds reference facts, produces a 0–100 risk score, and records approve, deny, or refer. When the credit lookup times out, or the risk reply fails an arithmetic audit, the pipeline escalates the case for a person. It does not crash, and it does not invent a score.

The lab requires each agent to call a model for its reasoning step, a trace of every step, a cost and latency write-up from real runs, a demonstrated timeout with retry then escalation, unit tests, and a green CI run.

## 2. Out of scope

Do not build a UI, a CLI form, an MCP server, webhooks, queues, event-driven agents, a credit-bureau HTTP client, or a second product pack. Do not store the case in SQLite. Do not hardcode roofs, claims, territory, credit, or band cutoffs in the harness.

## 3. Architecture

```text
fixture JSON
    → intake agent        writes application
    → enrichment agent    reads application, calls the pack's enrichment_lookup, writes enrichment
    → risk agent          reads application + enrichment, queries the pack credit table, writes risk
    → recommendation      reads application + enrichment + risk, writes decision
```

State pattern: shared state store, decided before any agent is wired. The store is one in-memory case dict, the case record from the lab. Risk reads `application` and `enrichment` from that record. Recommendation reads `application`, `enrichment`, and `risk` from that record. Message passing, as the lab defines it, would keep no case record and would hand each agent only the previous output. This pipeline keeps the record, so the pattern is the shared store.

The harness is the only writer. Each agent still reads from the store and writes one section: the harness passes that agent's slice and assigns the returned dict to exactly one key. Agent functions do not receive the case dict, so one step cannot overwrite another key. Extra keys in a return value are ignored. A call that raises writes nothing.

Agents treat arguments as read-only. Do not deep-copy for defense. Do not mutate inputs.

The live script prints measured tokens, simulated cost, and latency for the case and for each step. It then compares the stable case fields with `tests/expected_cases/{applicant_id}.json`. It writes the case and the trace as JSON at the end of the run. The trace is a separate object.

### 3.1 Case record

| Key | Written by | Contents |
| --- | --- | --- |
| `raw_application` | harness, before intake | The fixture, unchanged |
| `application` | intake | Normalized fields. Missing inputs stay null and are listed in `missing` |
| `enrichment` | enrichment | Territory result plus the model’s note |
| `risk` | risk, only after a passing audit | Credit result, cited lines, score, assessment |
| `decision` | recommendation, only after a validated score | `outcome`, `rationale`, `score` |
| `status` | harness | `running`, then `completed` or `escalated` |
| `escalation` | harness, only on escalate | `null` on success |

`decision.outcome` is only `approve`, `deny`, or `refer`, and only when `status` is `completed`. `refer` is a completed recommendation: a person should underwrite a case whose validated score fell in the middle band. `escalated` is the lab's failure flag for a person. An escalated case has `decision: null`, `risk: null`, and `status: escalated`. A timeout is stored as `escalated`, never as `refer`.

### 3.2 Harness sequence

1. Load the product pack and the fixture by `applicant_id`.
2. Set `status` to `running` and store `raw_application`.
3. Call intake. On success, set `application`.
4. Call enrichment. On success, set `enrichment`.
5. Call the risk step in a retry loop (section 7). On a passing result, set `risk`.
6. If `risk` was written, call recommendation. Code chooses `outcome` from the pack band table before the model writes the rationale, and copies the validated score onto the decision. Set `status` to `completed`.
7. If the risk step escalates, do not call recommendation. Set `status` to `escalated`.
8. Append a trace entry for every model call and every credit attempt.
9. Return the case and the trace.

## 4. Product pack contract

`run_case` constructs `HomeownersPack` and runs it. The harness must not import homeowners field names. `load_pack` checks that a registered pack fills the slots below. A second product is another pack. The four-step sequence stays the same, and `run_case` is pointed at that pack. A pack provides:

| Slot | Pack provides | Harness uses it for |
| --- | --- | --- |
| Application schema | Pydantic model of the raw fixture | Parsing fixtures and intake output |
| Section schemas | Pydantic models for `application`, `enrichment`, `risk`, `decision` | `model_validate` on each return value |
| Prompts | One string per agent | Sent with that step’s slice |
| Enrichment lookup | `enrichment_lookup(application) -> EnrichmentReference` | Enrichment. The pack decides which fields of `application` to read and what reference data to return. The harness does not name that data. |
| Credit lookup | `credit_lookup(applicant_id, attempt) -> CreditFile` | Risk. This name stays on the pack interface. Every product’s risk step looks up the person’s credit history. The pack supplies the rows and the timeout switch. It does not rename the tool. |
| Rubric | Cap, line id → points | Risk prompt and the audit |
| Band table | Ordered cutoffs | Mapping a validated score to an outcome |
| Fixtures | JSON files keyed by `applicant_id` | Runs and tests |

Lookup and rubric failures that are business results (`no_file`, unknown territory) return data. They do not raise. Only the timeout switch and a failed audit escalate.

### 4.1 Generic risk audit

Run this only on a model reply, never instead of one. Do not compute a homeowners score in Python.

Let `cited` be the returned lines, `score` the returned integer, and `cap` and `points_by_id` come from the pack.

The reply passes only if all of the following are true:

- Every cited line id is in `points_by_id`.
- Every cited line’s `points` equal `points_by_id[id]`.
- No duplicate line ids.
- `score == min(sum(cited points), cap)`.

Evidence strings are stored and traced. Code does not check them against the case. A reply that omits a line the facts would support still passes. Code does not add the missing line and does not rescore.

If the audit fails, or Pydantic validation fails:

- Do not write `risk`.
- Do not retry the model.
- Do not call recommendation.
- Escalate with `escalation.reason` = `risk score unusable`, `escalation.source` = `unusable_score`, `escalation.attempts` = `1`.

## 5. Homeowners pack

This is the only pack in the lab. Its numbers are pack data, not harness constants.

### 5.1 Raw application

Required keys: `applicant_id`, `name`, `state`, `year_built`, `roof_age`, `construction`, `coverage_amount`, `prior_claims`.

`prior_claims` is a list of `{year, peril, amount}`. Use JSON `null` for an unknown scalar. Do not omit the key.

Intake’s model normalizes this into `application` and sets `missing` to the names of null required facts. It must not invent values. The harness checks that every null input is listed in `missing` and that no missing field was filled with a guessed value. That check is “null stays null,” not a homeowners rating rule.

### 5.2 Reference database

Commit a SQL seed. Load it into SQLite at startup. Do not commit a requirement that CI call a network.

`territory(state, wind_hail_band, wildfire_band)`:

| state | wind_hail_band | wildfire_band |
| --- | --- | --- |
| WI | low | low |
| OK | high | low |
| CO | high | high |

Bands are `low` or `high` in this lab. The homeowners pack implements `enrichment_lookup(application)` by reading `state` and querying this table. There is no `territory_lookup` on the pack interface. The harness and the enrichment agent call `enrichment_lookup` only.

That implementation returns the two bands and `status: found`. If `state` is null or not in the table, it returns null bands and `status: unknown`. It does not raise. A different product implements the same function against its own reference data.

`credit(applicant_id, bureau_score, delinquencies)` has one row each for `APP-APPROVE`, `APP-REFER`, and `APP-RETRY`: bureau score 740, delinquencies 0. `APP-DENY` has no row. `APP-TIMEOUT` may have a row, but the timeout switch must raise before the query, so that row is never read.

`credit_lookup` returns:

```json
{"applicant_id": "APP-APPROVE", "file_status": "found", "bureau_score": 740, "delinquencies": 0}
```

or, when no row exists:

```json
{"applicant_id": "APP-DENY", "file_status": "no_file", "bureau_score": null, "delinquencies": null}
```

`no_file` is a successful lookup. The risk model still runs.

### 5.3 Timeout switch

This is fixture configuration for two ids, not a rubric line and not a harness branch. Check it before the `SELECT`.

| applicant_id | Attempts that raise `TimeoutError` |
| --- | --- |
| `APP-TIMEOUT` | 1 and 2 |
| `APP-RETRY` | 1 only |

Every other id queries immediately. The harness passes the attempt number, starting at 1. There is no global counter inside the lookup.

### 5.4 Rubric

The risk prompt contains this table and the instruction that building age as of 2026 is `2026 - year_built` when `year_built` is present. The model chooses the lines. The harness does not evaluate them.

| Id | Points | Model applies it when |
| --- | --- | --- |
| `roof_age_null` | 20 | `roof_age` is null |
| `roof_age_0_to_25` | 10 | `roof_age` is 0 through 25 |
| `roof_age_above_25` | 20 | `roof_age` is 26 or greater |
| `building_age_0_to_40` | 4 | age is 0 through 40 |
| `building_age_above_40` | 15 | age is 41 or greater |
| `water_claim_since_2021` | 25 | a claim has `peril == "water"` and `year >= 2021` |
| `no_credit_file` | 15 | `file_status == "no_file"` |
| `wildfire_high` | 15 | wildfire band is `high` |
| `wind_hail_high` | 10 | wind-and-hail band is `high` |

Pack constants: `cap = 100`.

The prompt tells the model to cite at most one roof line and at most one building-age line. Code does not enforce those exclusions.

The model returns:

- `lines`: `{id, points, evidence}[]`
- `score`: integer
- `assessment`: string

`credit` on the risk section is the lookup result, attached by the agent, not invented by the model.

### 5.5 Band table

| Validated score | `decision.outcome` |
| --- | --- |
| below 30 | `approve` |
| 30 through 59 | `refer` |
| 60 and above | `deny` |

Code chooses `outcome` from this table before the recommendation model is called, and copies `score` onto the decision. The model writes the rationale. The response schema asks only for that rationale.

### 5.6 Fixtures

Build the files so the rubric total sits inside the intended band. Claims use the structured `peril` field. There is no free-text claim description.

| Id | Intended result | Facts that set the total | Total |
| --- | --- | --- | --- |
| `APP-APPROVE` | completed approve | WI, `year_built` 2015, `roof_age` 8, no claims, credit row 740 / 0 delinquencies | 14 |
| `APP-REFER` | completed refer | OK, `year_built` 1960, `roof_age` null, no claims, credit row 740 / 0 | 45 |
| `APP-DENY` | completed deny | CO, `year_built` 1955, `roof_age` 28, one water claim in 2023 for 8000, no credit row | 100, and 75 even if the water line is omitted |
| `APP-RETRY` | timeout once, then completed approve | Same facts as `APP-APPROVE`, its own credit row | 14 |
| `APP-TIMEOUT` | escalated | Any valid homeowners facts | Score is never produced |

`name`, `construction`, and `coverage_amount` must be present and non-null on every fixture. Use distinct names. Coverage and construction do not add rubric points.

`APP-DENY` includes the water claim so the model has a real line to cite. The deny band does not depend on that citation: omitting it leaves 75.

## 6. Agent behavior

`intake_agent`, `enrichment_agent`, `risk_scoring_agent`, and `recommendation_agent` are standalone functions in `src/underwriting/agents.py`. They are separate from the harness. They are not closures over the case dict. Each takes the slice for its step and the model adapter. Unit tests call the function with a hardcoded input. They do not start the pipeline.

Each function calls the model exactly once per invocation. That call is the lab's reasoning step. `risk_scoring_agent` calls the model only after `credit_lookup` returns. The recommendation function still calls the model for the rationale. Code chooses `outcome` from the pack band table before that call and copies the validated score onto the decision. The function's return value is the decision the harness stores.

| Agent | Model sees | Model returns | Harness persists |
| --- | --- | --- | --- |
| Intake | Raw fixture and the intake prompt | Normalized application | `application` |
| Enrichment | `application`, the `enrichment_lookup` result, enrichment prompt | The note only. The response schema omits the lookup fields. Code copies those fields from the lookup. The note must not fill null application fields or invent reference facts | `enrichment`, including the lookup result |
| Risk | `application`, `enrichment`, credit result, rubric, risk prompt | Lines, score, assessment. The response schema omits `credit`. Code attaches the lookup result after the audit | `risk` only after the audit passes |
| Recommendation | `application`, `enrichment`, `risk`, the outcome already chosen, recommendation prompt | The rationale only. The response schema omits `outcome` and `score` | `decision`, with code-owned `outcome` and `score` |

Empty sections are not sent. Enrichment does not see the raw fixture or a null `risk`. Risk does not see `decision`.

If `credit_lookup` raises `TimeoutError`, the risk model is not called for that attempt.

## 7. Failure handling

The lab's simulated failure is the credit timeout on `risk_scoring_agent`. The underlying lookup raises `TimeoutError` on a specific fixture. The harness retries that call, then escalates if the retry fails. The process exits 0. The case has no recommendation and no invented score. `APP-RETRY` uses the same handler and recovers when the second attempt returns a credit file.

A failed risk audit (section 7.2) is an additional guard. It does not replace the timeout demo. The audit does not get a second model call: the reply already failed a deterministic check, and a second call would be a chance to store a score the audit already rejected.

### 7.1 Credit timeout

Attempts: 2. Backoff: a fixed 0.2 seconds between attempt 1 and attempt 2. Inject the sleeper so unit tests do not wait. The live script uses the real 0.2s sleep.

Each attempt writes a trace entry and does not write `risk`.

- Attempt 2 returns a credit file (`APP-RETRY`): continue with the risk model, the audit, and recommendation. The final status is `completed`. The trace shows the timeout and then the successful attempt.
- Attempt 2 raises (`APP-TIMEOUT`): set `risk` null, `decision` null, `status` `escalated`, and

```json
"escalation": {
  "reason": "credit lookup timed out after 2 attempts",
  "source": "credit_timeout",
  "attempts": 2
}
```

Do not call recommendation.

### 7.2 Unusable risk reply

One model call. No second model call. Same case shape as the timeout escalation, with:

```json
"escalation": {
  "reason": "risk score unusable",
  "source": "unusable_score",
  "attempts": 1
}
```

Intake and enrichment sections already written stay on the case.

## 8. Model

`ModelAdapter` is a small protocol: send a prompt and a JSON schema, return the text plus input-token count and output-token count.

- `OllamaAdapter` calls `qwen3:8b` with thinking off. Base URL is `OLLAMA_HOST`, default `http://host.docker.internal:11434` so the dev container reaches Ollama on the Mac. Map Ollama `prompt_eval_count` and `eval_count` to the token counts. Pass the Pydantic JSON schema as the response format.
- `FakeAdapter` is used by unit tests and CI. It returns a canned section and canned token counts. It must not open a network connection.

Every live agent uses `qwen3:8b`. Do not route some agents to `mistral:7b`.

Intake parses the model text with `model_validate_json`. Enrichment, risk, and recommendation parse the model text as JSON, keep the fields the model owns, and validate the merged section. A Pydantic validation failure on the risk step is an unusable risk reply: escalate, and do not retry the model. On intake, enrichment, or recommendation, a Pydantic validation failure raises `PipelineStepError` after tracing the attempt. Do not continue with a partial section. Those schema failures are not the lab’s required escalation demo. Only the risk audit, a risk-step validation failure, and the credit timeout use the escalation record.

## 9. Trace, cost, and latency

The trace is not the case. One entry per model call and one entry per credit attempt:

| Field | Required |
| --- | --- |
| `step` | `intake`, `enrichment`, `credit_lookup`, `risk`, or `recommendation` |
| `agent` | `intake_agent`, `enrichment_agent`, `risk_scoring_agent`, or `recommendation_agent`. Credit attempts use `risk_scoring_agent` |
| `input` | The slice sent, or the lookup id and attempt |
| `output` | The section returned, the credit file, or the error |
| `duration_ms` | Wall time of that call |
| `input_tokens` | Ollama prompt tokens, or the fake’s canned count. `0` for a credit lookup |
| `output_tokens` | Ollama completion tokens. `0` for a credit lookup |
| `timestamp` | ISO-8601 UTC |

Simulated dollars, labeled simulated on every figure:

```text
cost = (input_tokens / 1_000_000) * 0.10 + (output_tokens / 1_000_000) * 0.40
```

Do not hardcode a token budget or a real-time-versus-batch verdict. The dry run in section 12 records the per-step token totals. Record those numbers in the write-up after that run, then run the official traces.

The implementation prints measured input tokens, measured output tokens, simulated cost, and latency per case and per step. Simulated cost is the lab's cost calculation for this setup. Local Ollama sends no invoice, so dollars are the measured token counts times the rates above. Every figure is labeled simulated. Latency is the sum of each trace entry’s `duration_ms`, including a failed credit attempt. The 0.2s backoff is a sleep between attempts. It is not a trace entry.

The write-up then uses the three completed official traces (`APP-APPROVE`, `APP-REFER`, `APP-DENY`). For each case it states the simulated cost and the total latency, and it concludes whether those measurements are acceptable for a real-time use case or for an overnight batch use case, with the reasoning taken from the traces. Do not put that verdict in code.

The live script writes:

- `cases/{applicant_id}.json`
- `traces/{applicant_id}.json`

Gitignore both directories.

## 10. Tests and CI

Python and pytest. GitHub Actions runs pytest only. CI uses `FakeAdapter` for model calls. Credit lookups use the homeowners pack’s in-memory SQLite tables, including the timeout switch. CI must not require Ollama, a key, or the network.

Agent tests call that agent function with a hardcoded input. They do not call the harness. Pipeline tests call the harness. Pipeline tests also assert that the trace has one entry per model call and per credit attempt, and that each entry includes `agent`, `input`, `output`, `duration_ms`, `input_tokens`, and `output_tokens`.

| Test | Assert |
| --- | --- |
| Intake | Null `roof_age` stays null and is listed in `missing` |
| Enrichment | Unknown state yields null bands. The section does not invent a band or a roof age |
| Risk, happy path | Fake model reply that satisfies the audit is returned unchanged |
| Risk, `no_file` | Lookup result is `no_file` and the model is still called |
| Risk, unusable arithmetic | No section is returned. Caller can see the failure. The model is invoked once |
| Recommendation | A score of 55 becomes `refer` even if the fake rationale claims approve |
| Pipeline, `APP-APPROVE` | `completed`, outcome `approve` |
| Pipeline, `APP-TIMEOUT` | Two credit attempts, no `risk`, no `decision`, `escalated`, process exits 0 |
| Pipeline, `APP-RETRY` | First attempt times out, second completes, `completed` |

The live script is not part of CI. It is the source of the three success traces (`APP-APPROVE`, `APP-REFER`, `APP-DENY`) and the failure traces (`APP-TIMEOUT`, `APP-RETRY`).

## 11. Suggested layout

```text
src/underwriting/harness.py
src/underwriting/agents.py
src/underwriting/audit.py
src/underwriting/trace.py
src/underwriting/model.py
src/underwriting/products/contract.py
src/underwriting/products/homeowners/   pack, schemas, prompts, seed.sql, fixtures
tests/
scripts/run_traces.py
.github/workflows/ci.yml
README.md
```

The dev container already exists. Do not replace it. `OLLAMA_HOST` is documented in the script docstring and in `README.md`.

## 12. Dry run after implementation

Ship the pipeline first with one model call per agent invocation. The only retry in that build is the credit-lookup loop in section 7.1. Do not add a retry loop or any other loop inside an agent while implementing.

When that build is complete and `pytest` is green, run one live dry run of all five fixtures against `qwen3:8b` before the official traces. The dry run has two jobs.

Diagnose what actually failed. For each fixture, record whether intake, enrichment, the credit lookup, the risk model, the risk audit, or recommendation failed, and the error or invalid output. Separate schema mismatches, audit failures, timeouts, and wrong bands. These notes are the evidence for any later change.

Then decide, from that evidence only, whether any agent needs a model-call retry or an internal loop:

- Add a model retry only for an agent whose dry-run failures were transient schema or transport failures, and only around that agent’s model call. The risk audit stays a single call. A reply that fails section 4.1 still escalates with no second model call.
- Add a loop inside an agent only if the dry run shows that one call cannot finish that step’s job. Do not add a loop because it might be useful later.
- If the five fixtures complete as specified in section 5.6, add neither. Record that the dry run did not justify a retry or a loop.

The credit-lookup retry is not part of this decision. It stays as specified even if the dry run is clean.

Use the same run to record the per-step token totals for the budget in section 9. After any retry or loop change justified above, re-run the dry run, then run the official traces.

## 13. Done when

- The harness has no homeowners field checks and no literals `40` or `70`.
- The five fixtures behave as in section 5.6 under the fake model, and the three success fixtures plus both failure fixtures run against local `qwen3:8b`.
- A timeout trace shows two attempts, a 0.2s backoff on the live run, an empty `risk`, and `status: escalated`.
- A business refer has a filled `risk` and `decision.outcome: refer`.
- Traces contain step, agent, input, output, duration, token counts, and timestamp.
- Simulated cost uses the rates in section 9 and is labeled simulated.
- `intake_agent`, `enrichment_agent`, `risk_scoring_agent`, and `recommendation_agent` each have a passing unit test that calls the function with a hardcoded input and does not start the pipeline.
- The write-up states simulated cost and measured latency for `APP-APPROVE`, `APP-REFER`, and `APP-DENY`, and concludes real-time versus overnight batch from those traces.
- After the first green implementation, the section 12 dry run records per-fixture failures and an explicit decision on model retries and in-agent loops before the official traces.
- `pytest` passes in GitHub Actions without Ollama. The run includes the agent tests, the pipeline tests, and the trace assertions.
