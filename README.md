# Multi-agent underwriting pipeline

This project takes one insurance application and walks it through four steps. It cleans up the application, looks up extra facts, scores the risk, and recommends approve, deny, or refer.

Those four steps are always the same. The claim type is what changes. Homeowners is the claim type included in this repo. Another claim type, such as auto or renters, uses the same steps. You supply that type as a **pack**: the form fields, the instructions, the lookup tables, and the scoring rules for that type.

A pack has to follow one checklist, called the contract, in `src/underwriting/products/contract.py`. If the pack has every piece on that checklist, the pipeline can run it. The pipeline code does not contain homeowners rules. Roof age, territory, credit, and the approve/deny cutoffs live in the pack.

The rest of this page follows one application from start to finish, then lists every piece a pack must supply and where that piece is used.

## How one application runs

A small runner calls the four steps in order. It keeps one case record and is the only thing that writes to it. Each step sees only the facts it needs for its job, and returns one section. The runner saves that section on the case. One step cannot overwrite another step's section.

```text
sample application
    → 1. Intake           saves application
    → 2. Enrichment       saves enrichment
    → 3. Risk             saves risk
    → 4. Recommendation   saves decision
```

Each step asks a model to do one reasoning job. In a live run that model is local Ollama (`qwen3:8b`). In tests it is a fake model that returns canned answers, so the tests need no network.

### 1. Intake

Intake turns the raw application into a clean `application`.

The pack supplies the sample file, the form shape, and the intake instructions. The model copies each value through. Unknown values stay null, and their field names are listed under `missing`. The model does not guess a missing roof age or any other blank.

The runner checks that every null input is still null and is listed in `missing`. Then it saves `application` on the case.

### 2. Enrichment

Enrichment adds reference facts the application did not include.

The pack supplies a lookup function, `enrichment_lookup`, and the enrichment instructions. The runner calls that lookup with the cleaned application. The pack decides which fields to read. For homeowners, it reads the state and returns a wind-and-hail band and a wildfire band.

The model writes a short note that restates those lookup results. The runner copies the lookup results onto the enrichment section and saves the note with them. If the state is missing or unknown, the lookup returns empty bands. That is a normal result. The model does not invent a band.

### 3. Risk

Risk looks up the person's credit, then scores the application from 0 to 100.

The pack supplies `credit_lookup`, a point table called the rubric, and the risk instructions. The lookup runs first. Two results are both normal, and the model still scores the case:

- **found** — a credit row exists
- **no_file** — no row exists

The model sees the application, the enrichment, the credit result, and the pack's point table. It cites the lines that apply and returns a score and a short assessment. The runner then checks the arithmetic:

- every cited line id exists in the pack's table
- the points on each cited line match that table
- the score equals the sum of those points, and the sum cannot go above the pack's cap

If that check passes, the runner saves the score and attaches the credit result. The check does not add a line the model left out, and it does not rescore the case.

If the check fails, the runner does not save a risk score and does not ask the model again. The case is escalated for a person.

A pack may also mark some sample applications so the credit lookup times out. That switch lives in the pack, in front of the credit query. The homeowners pack times out `APP-RETRY` on the first try only, and `APP-TIMEOUT` on both tries. The runner waits 0.2 seconds and tries once more. If the second try works, scoring continues. If it also times out, the runner saves no score and does not continue to recommendation.

### 4. Recommendation

Recommendation explains the decision. It does not choose it.

The pack supplies a band table: score ranges for approve, refer, and deny. The runner looks up the validated score in that table and sets the outcome. Then the model writes the rationale. The runner saves the outcome, the score, and that rationale together as the decision.

For the homeowners pack the bands are:

| Score | Outcome |
| --- | --- |
| below 30 | approve |
| 30 through 59 | refer |
| 60 and above | deny |

### What the finished case means

| Result | What happened |
| --- | --- |
| `completed` + `approve`, `refer`, or `deny` | The score passed the arithmetic check, and the band table produced an outcome. |
| `escalated` | The credit lookup timed out twice, or the risk score failed the arithmetic check. `risk` and `decision` are empty. |

`refer` is a finished decision. The score landed in the middle band, so a person should underwrite it. `escalated` means the pipeline stopped. A timeout is stored as `escalated`. It is never stored as `refer`.

## What a pack must supply

These are the contract pieces, in the order the runner uses them. Homeowners is the example. Another claim type supplies the same kinds of pieces, with its own fields, tables, and instructions.

A new pack does not inherit the homeowners applicant ids, the homeowners point values, or the homeowners timeout list. `load_pack` checks that a registered pack has every piece below. Today the runner builds the homeowners pack. To run another claim type, point the runner at that pack.

| Piece | What you put in the pack | How the pipeline uses it |
| --- | --- | --- |
| Sample applications | JSON files, one per applicant id | The runner loads one file and hands it to intake. Tests and the live script do this. |
| Application form | The fields on a raw application, and the fields on the cleaned `application` | Intake reads the raw form. The cleaned form adds `missing`, the names of null required facts. |
| Intake instructions | One prompt written for this claim type | Sent to the model with the raw application. |
| Enrichment lookup | `enrichment_lookup(application)`, plus the reference table behind it | Called before the enrichment model. The pack chooses which application fields to read and what facts to return. The pipeline does not know those field names. |
| Enrichment form | The shape of the enrichment section, including a note | The runner stores the lookup result and the model's note in this shape. |
| Enrichment instructions | One prompt written for this claim type | Tells the model to write the note from the lookup result only. |
| Credit lookup | `credit_lookup(applicant_id, attempt)`, plus the credit rows | Called at the start of risk, before the model. `found` and `no_file` both continue. A timeout raises, and the runner retries once. |
| Risk rubric | A maximum score, and a list of line ids with points | Sent to the risk model. The runner uses the same list to check that the returned score adds up. |
| Risk form | Lines, score, assessment, and the credit result | The model fills the lines, score, and assessment. The runner attaches the credit result after the check passes. |
| Risk instructions | One prompt that includes this claim type's point table | Tells the model which lines apply and how to sum them. |
| Band table | Ordered score cutoffs for approve, refer, and deny | The runner maps a validated score to an outcome before the recommendation model is called. |
| Decision form | Outcome, score, and rationale | The runner fills outcome and score. The model fills the rationale. |
| Recommendation instructions | One prompt written for this claim type | Tells the model to explain the outcome that was already chosen. |

The instructions stay specific to the claim type. One vague prompt for "any insurance" does not score consistently. The four step functions stay the same for every pack. They receive that pack's fields, lookup results, and instructions.

## The homeowners pack

The filled-in pack is `src/underwriting/products/homeowners/`. Its reference rows are loaded from `seed.sql` into memory at startup. The case record itself is not stored in a database.

The application fields are `applicant_id`, `name`, `state`, `year_built`, `roof_age`, `construction`, `coverage_amount`, and `prior_claims` (`year`, `peril`, `amount`).

Territory rows are keyed by state and hold a wind-and-hail band and a wildfire band. Credit rows are keyed by applicant id and hold a bureau score and a delinquency count. The deny sample has no credit row, so the lookup returns `no_file` and scoring still runs.

The point values below belong to homeowners. The cap is 100. Building age is `2026 - year_built` when a year built is present.

| Line | Points |
| --- | --- |
| Roof age null | 20 |
| Roof age 0 through 25 | 10 |
| Roof age 26 or greater | 20 |
| Building age 0 through 40 | 4 |
| Building age 41 or greater | 15 |
| Water claim in 2021 or later | 25 |
| No credit file | 15 |
| Wildfire band high | 15 |
| Wind and hail band high | 10 |

## Run the sample cases

Python 3.11 or newer.

```bash
pip install -e ".[dev]"
pytest
```

`pytest` uses the fake model. It does not need Ollama, an API key, or the network. It runs the five sample applications below, plus checks for each step, the score arithmetic, and the trace. GitHub Actions runs the same tests.

To run against a real local model, start Ollama, then:

```bash
python scripts/run_traces.py
```

`OLLAMA_HOST` is the Ollama address. The default is `http://host.docker.internal:11434`, which lets a dev container reach Ollama on the host machine. When Ollama is on the same machine as the script, set `OLLAMA_HOST=http://127.0.0.1:11434`.

The script runs every sample, prints token counts, a simulated cost, and latency, and writes:

- `cases/{applicant_id}.json` — the case record
- `traces/{applicant_id}.json` — one entry per model call and per credit attempt

Both folders are gitignored. The simulated cost is the measured token counts times $0.10 per 1M input tokens and $0.40 per 1M output tokens. Ollama does not bill you. Every dollar figure is labeled simulated. Latency is the sum of the timed steps. The 0.2 second pause between credit attempts is not included in that sum.

| Sample | What you should see |
| --- | --- |
| `APP-APPROVE` | Completed, outcome approve |
| `APP-REFER` | Completed, outcome refer |
| `APP-DENY` | Completed, outcome deny. No credit row, so the lookup returns `no_file` and scoring still runs |
| `APP-RETRY` | The first credit lookup times out, the second succeeds, and the case completes as approve |
| `APP-TIMEOUT` | Both credit lookups time out. Status is `escalated`. No score and no decision |
