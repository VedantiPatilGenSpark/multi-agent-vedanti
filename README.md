# Risk-scoring agent

This branch scores one prepared homeowners case. The agent looks up credit, calls Bedrock once, checks that the score matches the rubric, and prints the result. The simulated AWS deployment is described in `docs/aws-deployment.md`.

## How the repository is put together

The Python package `underwriting` lives under `src/`.

| Path | Role |
| --- | --- |
| `src/underwriting/agents.py` | `risk_scoring_agent`. Credit lookup, one model call, arithmetic check, then the credit file is attached. |
| `src/underwriting/audit.py` | Checks that a risk score matches the rubric. |
| `src/underwriting/model.py` | `BedrockAdapter` for a live call, and `FakeAdapter` for tests. |
| `src/underwriting/products/homeowners/` | The homeowners pack: schemas, prompts, rubric, `seed.sql`, and the risk input. |
| `scripts/run_risk_agent.py` | Loads `APP-APPROVE-risk-input.json`, scores it, and prints JSON. |
| `deploy/` | The paper IAM policies, task definition, network note, and the build and run logs. |
| `tests/` | Pytest. Risk tests call the agent with `FakeAdapter`. |
| `Dockerfile` | Image that installs the package and runs the risk-agent script. |
| `.github/workflows/ci.yml` | On every push and pull request, installs the package and runs pytest. No AWS. |

## Set up and run

Python 3.11 or newer. The Docker image and GitHub Actions use 3.12. Runtime dependencies are Pydantic and boto3. Tests add pytest.

### Tests

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
```

`pytest` uses `FakeAdapter`. It does not call AWS and does not need credentials.

With uv, using `uv.lock`:

```bash
uv sync --extra dev
uv run pytest
```

### One case

`scripts/run_risk_agent.py` reads `src/underwriting/products/homeowners/fixtures/APP-APPROVE-risk-input.json` and calls `qwen.qwen3-32b-v1:0` in `us-east-1`. Set a Bedrock API key or AWS credentials in the environment first.

```bash
export AWS_BEARER_TOKEN_BEDROCK='paste-the-key-here'
export AWS_DEFAULT_REGION=us-east-1
python scripts/run_risk_agent.py
```

A successful run prints the risk JSON and exits 0. A direct run also writes `deploy/metrics.log`. That file is gitignored. A timeout, an audit failure, a validation error, or an AWS denial is printed and the process exits non-zero. The metrics file is not written on those failures.

### Docker

Docker Desktop has to be running. Build and run from the host terminal, in the repository root. The dev container does not include the `docker` command.

```bash
docker build -t risk-scoring-agent .
docker run --rm risk-scoring-agent
```

The image command is `python scripts/run_risk_agent.py`. No ports are published. Pass a Bedrock API key when you want a live score, and save the output:

```bash
export AWS_BEARER_TOKEN_BEDROCK='paste-the-key-here'
docker run --rm \
  -e AWS_BEARER_TOKEN_BEDROCK \
  -e AWS_DEFAULT_REGION=us-east-1 \
  -v "$(pwd)/deploy:/app/deploy" \
  risk-scoring-agent > deploy/run.log 2>&1
```

`deploy/build.log` is the saved build transcript. `deploy/run.log` is the saved score. `deploy/metrics.log` is the token and cost log for that same run. The volume is required because `docker run --rm` deletes the container filesystem.
