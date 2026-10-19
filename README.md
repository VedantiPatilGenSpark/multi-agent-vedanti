# Risk-scoring agent

One homeowners case is scored once and the process exits. The agent looks up credit, asks a local Ollama model for a risk score, checks that the score adds up, and prints the result as JSON.

The model process is on the same machine. The prompt goes to Ollama on that machine. The live model is `qwen3:8b`.

Homeowners is the pack in this repo. Roof age, territory, credit, and the point table live in the pack. The pack contract in `src/underwriting/products/contract.py` still includes the intake, enrichment, and recommendation prompt strings. This run uses the risk prompt, the credit lookup, and the rubric.

There is no web app and no long-running server.

## How the repository is put together

The Python package `underwriting` lives under `src/`. Installing the project puts it on your path.

| Path | Role |
| --- | --- |
| `src/underwriting/agents.py` | `risk_scoring_agent`. Looks up credit, calls the model once, audits the reply, and attaches the credit file. |
| `src/underwriting/audit.py` | Checks that a risk score adds up. |
| `src/underwriting/model.py` | `OllamaAdapter` for a live model, and `FakeAdapter` for tests. |
| `src/underwriting/products/contract.py` | The checklist every pack must fill. `load_pack` checks a registered pack. |
| `src/underwriting/products/homeowners/` | The homeowners pack: forms, prompts, lookups, `seed.sql`, and the sample JSON files. |
| `src/underwriting/products/homeowners/fixtures/APP-APPROVE-risk-input.json` | The only case the script and the container score. |
| `scripts/run_risk_agent.py` | Live entry point. Scores that case and prints the risk JSON. |
| `tests/` | Pytest. Risk tests call `risk_scoring_agent` with `FakeAdapter` and a fixed input. |
| `Dockerfile` | Image that installs the package and runs `python scripts/run_risk_agent.py`. |
| `.github/workflows/ci.yml` | On every push and pull request, installs the package and runs pytest. No Ollama. |

| Entry point | When to use it |
| --- | --- |
| `pytest` | Check the agent with canned model replies. No Ollama. |
| `python scripts/run_risk_agent.py` | Score the prepared `APP-APPROVE` case with local Ollama. |

## How one case is scored

The script loads `APP-APPROVE-risk-input.json`, validates `application` and `enrichment` with the homeowners schemas, builds `HomeownersPack`, and calls `risk_scoring_agent` once with attempt `1`.

1. `credit_lookup` runs first. A `TimeoutError` skips the model. The script prints the error and exits non-zero. `APP-APPROVE` has a credit row, so this script does not demonstrate that timeout.
2. Otherwise the model is called once with the risk prompt, the application, the enrichment, the credit file, and the rubric. Thinking is off. The JSON schema is the response format.
3. The model does not return `credit`. After `audit_risk_reply` passes, the lookup result is attached.
4. If the audit or the schema check fails, the script prints the error and exits non-zero. It does not retry, and it does not invent a score.

A live run uses local Ollama (`qwen3:8b`). Tests use `FakeAdapter` with canned answers, so they need no network and no AWS.

The audit checks three things:

- every cited line id exists in the pack's table
- the points on each cited line match that table
- the score equals the sum of those points, and cannot go above the pack's cap

`found` means a credit row exists. `no_file` means no row exists. Both are normal, and the model still scores the case.

## The homeowners pack

The pack is `src/underwriting/products/homeowners/`. Reference rows load from `seed.sql` into memory at startup. The case record is not stored in a database.

The prepared input is Morgan Ellis in WI: year built 2015, roof age 8, frame construction, coverage 350000, no prior claims. Enrichment is found, with a low wind-and-hail band and a low wildfire band.

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

Python 3.11 or newer. The Docker image and GitHub Actions use 3.12. The runtime dependency is Pydantic. Tests add pytest.

### Tests

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
```

`pytest` uses `FakeAdapter`: no Ollama, API key, or network. GitHub Actions runs the same install, then `pytest`.

With uv, using `uv.lock`:

```bash
uv sync --extra dev
uv run pytest
```

### Live model on the host

Install [Ollama](https://ollama.com), pull the model, and start the server:

```bash
ollama pull qwen3:8b
```

With the virtualenv still active:

```bash
export OLLAMA_HOST=http://127.0.0.1:11434
python scripts/run_risk_agent.py
```

With uv: `uv run python scripts/run_risk_agent.py`.

`OLLAMA_HOST` is the Ollama address. The code default is `http://host.docker.internal:11434`, so a container can reach Ollama on the host. On the machine where Ollama is running, without Docker, use `http://127.0.0.1:11434`.

The script prints the risk JSON to stdout and exits 0. It does not write a case file. A direct run also writes `deploy/metrics.log` with the model name, input tokens, output tokens, model-call latency, and `invoiced_cost_usd: 0`. That file is gitignored.

### Docker

From the repository root, with Docker running and Ollama already serving `qwen3:8b` on the host:

```bash
docker build -t risk-scoring-agent .
docker run --rm \
  -e OLLAMA_HOST=http://host.docker.internal:11434 \
  -v "$(pwd)/deploy:/app/deploy" \
  risk-scoring-agent
```

The run publishes no ports. The image installs the package. It contains the test input, the pack, and the script. It does not contain the model weights. Ollama stays on the host. The volume keeps `deploy/metrics.log` after `docker run --rm` deletes the container.

On Linux, add `--add-host=host.docker.internal:host-gateway` so that hostname resolves. Docker Desktop on Mac and Windows already provides it.

### Dev container

`.devcontainer/devcontainer.json` is an Ubuntu workspace with Git and the GitHub CLI. Open the folder in Cursor or VS Code and choose **Dev Containers: Reopen in Container**. Docker Desktop must be running. The container does not install this package. Use the local Python commands above. Inside it, leave `OLLAMA_HOST` at the default so the script can reach Ollama on the host.
