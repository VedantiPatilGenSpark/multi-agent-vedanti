# Multi-agent underwriting pipeline

One insurance application goes through four steps: clean it up, look up extra facts, score the risk, and recommend approve, deny, or refer.

The steps stay the same. The claim type changes. Homeowners is the type in this repo. Another type, such as auto or renters, uses the same steps when you supply it as a **pack**: form fields, instructions, lookup tables, and scoring rules.

The pack must follow the contract in `src/underwriting/products/contract.py`. Roof age, territory, credit, and the approve/deny cutoffs live in the pack, not in the pipeline code.

There is no web app and no server. You run the tests, or one script that sends the sample applications through the four steps.

## How the repository is put together

The Python package `underwriting` lives under `src/`. Installing the project puts it on your path.

| Path | Role |
| --- | --- |
| `src/underwriting/harness.py` | The runner. `run_case(applicant_id, adapter)` loads one sample and calls the four steps. |
| `src/underwriting/agents.py` | The four steps: `intake_agent`, `enrichment_agent`, `risk_scoring_agent`, `recommendation_agent`. |
| `src/underwriting/audit.py` | Checks that a risk score adds up. |
| `src/underwriting/model.py` | `OllamaAdapter` for a live model, and `FakeAdapter` for tests. |
| `src/underwriting/trace.py` | Records each model call and credit attempt, then computes simulated cost and latency. |
| `src/underwriting/products/contract.py` | The checklist every pack must fill. `load_pack` checks a registered pack. |
| `src/underwriting/products/homeowners/` | The homeowners pack: forms, prompts, lookups, `seed.sql`, and the five sample JSON files. |
| `scripts/run_traces.py` | Live entry point. Runs all five samples and writes `cases/` and `traces/`. |
| `tests/` | Pytest. Pipeline tests call `run_case`. Step tests call one agent with a fixed input. |
| `tests/expected_cases/` | The stable fields the live script compares after each sample. |
| `Dockerfile` | Image that installs the package and runs pytest. |
| `.github/workflows/ci.yml` | On every push and pull request, installs the package and runs pytest. No Ollama. |

Importing the homeowners pack registers it as `homeowners`. `run_case` builds `HomeownersPack` directly. To run another claim type, point `run_case` at that pack.

| Entry point | When to use it |
| --- | --- |
| `pytest` | Check the pipeline with canned model replies. No Ollama. |
| `python scripts/run_traces.py` | Run the five homeowners samples against a local model and write the case and trace files. |
| `run_case` from Python | Run one sample. Pass an applicant id and a model adapter. |

```python
from underwriting.harness import run_case
from underwriting.model import OllamaAdapter

case, trace = run_case("APP-APPROVE", OllamaAdapter())
```

Tests pass a `FakeAdapter` instead of `OllamaAdapter`.

## How one application runs

The runner calls the four steps in order and is the only writer of the case. Each step sees only the facts it needs and returns one section. The runner saves that section. One step cannot overwrite another.

```text
sample application
    → 1. Intake           saves application
    → 2. Enrichment       saves enrichment
    → 3. Risk             saves risk
    → 4. Recommendation   saves decision
```

Each step asks a model to do one reasoning job. A live run uses local Ollama (`qwen3:8b`). Tests use a fake model with canned answers, so they need no network.

### 1. Intake

Intake turns the raw application into a clean `application`.

The pack supplies the sample file, the form shape, and the intake instructions. The model copies each value through. Unknown values stay null, and their names are listed under `missing`. It does not guess a blank roof age or any other missing value.

The runner checks that every null input is still null and listed in `missing`, then saves `application`.

### 2. Enrichment

Enrichment adds reference facts the application did not include.

The pack supplies `enrichment_lookup` and the enrichment instructions. The runner calls the lookup with the cleaned application. The pack chooses which fields to read. For homeowners, it reads the state and returns a wind-and-hail band and a wildfire band.

The model writes a short note restating those results. The runner saves the lookup results and the note together. A missing or unknown state returns empty bands. That is a normal result. The model does not invent a band.

### 3. Risk

Risk looks up credit, then scores the application from 0 to 100.

The pack supplies `credit_lookup`, a point table (the rubric), and the risk instructions. The lookup runs first. Both of these results are normal, and the model still scores the case:

- **found** — a credit row exists
- **no_file** — no row exists

The model sees the application, the enrichment, the credit result, and the point table. It cites the lines that apply and returns a score and a short assessment. The runner then checks:

- every cited line id exists in the pack's table
- the points on each cited line match that table
- the score equals the sum of those points, and cannot go above the pack's cap

If the check passes, the runner saves the score and attaches the credit result. It does not add a line the model left out, and it does not rescore.

If the check fails, the runner does not save a risk score and does not ask the model again. The case is escalated for a person.

A pack can mark sample applications so the credit lookup times out. That switch sits in the pack, in front of the credit query. Homeowners times out `APP-RETRY` on the first try only, and `APP-TIMEOUT` on both tries. The runner waits 0.2 seconds and tries once more. A successful second try continues into scoring. A second timeout saves no score and skips recommendation.

### 4. Recommendation

Recommendation explains the decision. The pack's band table chooses it.

The runner looks up the validated score and sets the outcome. The model writes the rationale. The runner saves the outcome, the score, and the rationale as the decision.

Homeowners bands:

| Score | Outcome |
| --- | --- |
| below 30 | approve |
| 30 through 59 | refer |
| 60 and above | deny |

### What the finished case means

| Result | What happened |
| --- | --- |
| `completed` + `approve`, `refer`, or `deny` | The score passed the arithmetic check, and the band table produced an outcome. |
| `escalated` | Credit lookup timed out twice, or the risk score failed the arithmetic check. `risk` and `decision` are empty. |

`refer` is a finished decision: the score landed in the middle band, so a person should underwrite it. `escalated` means the pipeline stopped. A timeout is stored as `escalated`, never as `refer`.

## What a pack must supply

These are the contract pieces, in the order the runner uses them. Another claim type supplies the same kinds of pieces, with its own fields, tables, and instructions. It does not inherit the homeowners applicant ids, point values, or timeout list.

`load_pack` checks that a registered pack has every piece below. Today the runner builds the homeowners pack. Point `run_case` at a new pack to run that claim type.

| Piece | What you put in the pack | How the pipeline uses it |
| --- | --- | --- |
| Sample applications | JSON files, one per applicant id | The runner loads one file and hands it to intake. Tests and the live script do this. |
| Application form | The raw application fields, and the cleaned `application` fields | Intake reads the raw form. The cleaned form adds `missing`, the names of null required facts. |
| Intake instructions | One prompt for this claim type | Sent to the model with the raw application. |
| Enrichment lookup | `enrichment_lookup(application)` and its reference table | Called before the enrichment model. The pack chooses which fields to read and what facts to return. The pipeline does not know those field names. |
| Enrichment form | The enrichment section, including a note | The runner stores the lookup result and the model's note in this shape. |
| Enrichment instructions | One prompt for this claim type | Tells the model to write the note from the lookup result only. |
| Credit lookup | `credit_lookup(applicant_id, attempt)` and the credit rows | Called at the start of risk, before the model. `found` and `no_file` both continue. A timeout raises, and the runner retries once. |
| Risk rubric | A maximum score, and line ids with points | Sent to the risk model. The runner uses the same list to check that the score adds up. |
| Risk form | Lines, score, assessment, and the credit result | The model fills the lines, score, and assessment. The runner attaches the credit result after the check passes. |
| Risk instructions | One prompt that includes this claim type's point table | Tells the model which lines apply and how to sum them. |
| Band table | Ordered score cutoffs for approve, refer, and deny | The runner maps a validated score to an outcome before the recommendation model is called. |
| Decision form | Outcome, score, and rationale | The runner fills outcome and score. The model fills the rationale. |
| Recommendation instructions | One prompt for this claim type | Tells the model to explain the outcome already chosen. |

Prompts stay specific to the claim type. One vague prompt for "any insurance" does not score consistently. The four step functions stay the same. They receive that pack's fields, lookup results, and instructions.

## The homeowners pack

The pack is `src/underwriting/products/homeowners/`. Reference rows load from `seed.sql` into memory at startup. The case record is not stored in a database.

Application fields: `applicant_id`, `name`, `state`, `year_built`, `roof_age`, `construction`, `coverage_amount`, and `prior_claims` (`year`, `peril`, `amount`).

Territory rows are keyed by state and hold a wind-and-hail band and a wildfire band. Credit rows are keyed by applicant id and hold a bureau score and a delinquency count. The deny sample has no credit row, so the lookup returns `no_file` and scoring still runs.

These point values belong to homeowners. The cap is 100. Building age is `2026 - year_built` when a year built is present.

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

## Set up and run

Python 3.11 or newer. The Docker image and GitHub Actions use 3.12. The runtime dependency is Pydantic. Tests add pytest. The fake-model run needs nothing else.

### Local Python

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
```

The install is editable and includes pytest. `pytest` uses the fake model: no Ollama, API key, or network. It runs the five samples below, plus checks for each step, the score arithmetic, and the trace. GitHub Actions runs the same install, then `pytest`.

With uv, using `uv.lock`:

```bash
uv sync --extra dev
uv run pytest
```

### Live model

Install [Ollama](https://ollama.com), pull the model, and start the server:

```bash
ollama pull qwen3:8b
```

With the virtualenv still active:

```bash
export OLLAMA_HOST=http://127.0.0.1:11434
python scripts/run_traces.py
```

With uv: `uv run python scripts/run_traces.py`.

`OLLAMA_HOST` is the Ollama address. The code default is `http://host.docker.internal:11434`, so a container can reach Ollama on the host. On the machine where Ollama is running, use `http://127.0.0.1:11434`.

The script runs every sample, prints token counts, simulated cost, and latency, and writes:

- `cases/{applicant_id}.json` — the case record
- `traces/{applicant_id}.json` — one entry per model call and per credit attempt

Both folders are gitignored. Simulated cost is measured tokens times $0.10 per 1M input tokens and $0.40 per 1M output tokens. Ollama does not bill you. Every dollar figure is labeled simulated. Latency is the sum of the timed steps. The 0.2 second pause between credit attempts is not included.

### Docker

From the repository root, with Docker running:

```bash
docker build -t underwriting .
docker run --rm underwriting
```

The image installs the package and the test tools. Its default command is `pytest`. It does not contain Ollama or the model.

For the live script, Ollama must already be running on the host with `qwen3:8b` pulled. The volume mounts write `cases/` and `traces/` on the host:

```bash
docker run --rm \
  -e OLLAMA_HOST=http://host.docker.internal:11434 \
  --add-host=host.docker.internal:host-gateway \
  -v "$PWD/cases:/app/cases" \
  -v "$PWD/traces:/app/traces" \
  underwriting \
  python scripts/run_traces.py
```

`--add-host=host.docker.internal:host-gateway` makes that hostname resolve on Linux. Docker Desktop on Mac and Windows already provides it.

### Dev container

`.devcontainer/devcontainer.json` is an Ubuntu workspace with Git and the GitHub CLI. Open the folder in Cursor or VS Code and choose **Dev Containers: Reopen in Container**. Docker Desktop must be running. The container does not install this package. Use the local Python commands above. Inside it, leave `OLLAMA_HOST` at the default so the script can reach Ollama on the host.

### Sample cases

| Sample | What you should see |
| --- | --- |
| `APP-APPROVE` | Completed, outcome approve |
| `APP-REFER` | Completed, outcome refer |
| `APP-DENY` | Completed, outcome deny. No credit row, so the lookup returns `no_file` and scoring still runs |
| `APP-RETRY` | The first credit lookup times out, the second succeeds, and the case completes as approve |
| `APP-TIMEOUT` | Both credit lookups time out. Status is `escalated`. No score and no decision |
