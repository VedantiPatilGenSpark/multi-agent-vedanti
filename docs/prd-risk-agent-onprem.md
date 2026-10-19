# PRD: Risk-scoring agent, simulated on-prem deployment

Status: locked for implementation.  
Audience: the agent on branch `feat/risk-agent-onprem` only.  
Base: `main` of this repo. Do not start from another feature branch. Do not start from `feat/risk-agent-aws`.  
If this file and `docs/prd.md` disagree, this file wins for this branch. Leave `docs/prd.md` unchanged. It is the previous lab.

Do not implement the AWS simulation. Do not add a Bedrock adapter. Do not commit. Do not push. Do not create AWS resources.

## 1. Purpose

Turn the current four-agent underwriting repo into a single runnable risk-scoring agent, and run it against a local Ollama model. This is the simulated on-prem deployment. The model process is on the same machine as the agent. The prompt does not go to an external API.

The container runs once, scores one prepared homeowners case, and exits. Local `qwen3:8b` may score differently than hosted `qwen.qwen3-32b-v1:0`. Record that difference. Do not hide a bad score.

## 2. Out of scope

Do not build a UI, a queue, a web service, or a long-running server. Do not keep the harness as the thing the container runs. Do not call Bedrock, S3, DynamoDB, or any other AWS API. Do not write IAM policies, a task definition, or a VPC design on this branch. Do not invent a risk score if the local model returns invalid JSON. The live model is `qwen3:8b`. Do not point this branch at `qwen3:1.7b`, `qwen3:4b`, or `qwen3:32b`.

## 3. Branch and result

Create `feat/risk-agent-onprem` from current `main` if it does not already exist. All work stays on that branch.

When the branch is done, the repo runs one agent. Intake, enrichment, and recommendation are gone. The Dockerfile command runs the risk agent, not pytest. CI still runs pytest with a fake model and no network. The live run uses Ollama on the machine.

## 4. What the risk agent does

Keep `risk_scoring_agent` in `src/underwriting/agents.py`. Preserve this behavior:

1. Call `pack.credit_lookup(applicant_id, attempt)` first.
2. If that raises `TimeoutError`, do not call the model.
3. Otherwise call the model once with the risk prompt, the application, the enrichment, the credit file, and the rubric.
4. The model does not return `credit`. Attach the lookup result after `audit_risk_reply` passes.
5. If the audit or schema validation fails, raise. Do not retry the model. Do not invent a score.

Delete `intake_agent`, `enrichment_agent`, and `recommendation_agent`. Delete the harness (`src/underwriting/harness.py`), the trace module, and `scripts/run_traces.py`, and delete the tests that only cover those. Keep `src/underwriting/audit.py` and the homeowners pack, including `seed.sql`, the rubric, the risk prompt, and the credit lookup. Leave the pack contract in place, including the unused intake, enrichment, and recommendation prompt strings. Do not rewrite `docs/prd.md` or the pack to drop those slots.

Keep the existing risk unit tests that call `risk_scoring_agent` with `FakeAdapter` and a hardcoded input: valid reply, `no_file`, unusable arithmetic, and credit timeout. Delete tests that call the harness or the other three agents.

## 5. Test input

Add `src/underwriting/products/homeowners/fixtures/APP-APPROVE-risk-input.json`. Do not put it under `cases/`. That directory is gitignored.

The file holds only the slice this agent reads. Copy the values from `tests/expected_cases/APP-APPROVE.json`. The bytes must match the AWS branch:

```json
{
  "application": {
    "applicant_id": "APP-APPROVE",
    "name": "Morgan Ellis",
    "state": "WI",
    "year_built": 2015,
    "roof_age": 8,
    "construction": "frame",
    "coverage_amount": 350000,
    "prior_claims": [],
    "missing": []
  },
  "enrichment": {
    "status": "found",
    "wind_hail_band": "low",
    "wildfire_band": "low",
    "note": "Found. Wind and hail band is low. Wildfire band is low."
  }
}
```

This is the only case the container runs. Do not change these values.

## 6. Entrypoint

Add `scripts/run_risk_agent.py`. It loads the test input, validates `application` and `enrichment` with the homeowners schemas, constructs `HomeownersPack`, calls `risk_scoring_agent` once with attempt `1` and an `OllamaAdapter`, and prints `risk.model_dump()` as JSON to stdout. Then it exits 0.

On `TimeoutError`, `RiskAuditError`, or a validation error, print the error and exit non-zero. Do not retry. Do not write a case file.

`APP-APPROVE` has a credit row. This script does not demonstrate the timeout fixture.

## 7. Local model

Keep `OllamaAdapter` in `src/underwriting/model.py`. Keep `FakeAdapter` offline for tests.

Leave the adapter's model at `qwen3:8b`. Keep thinking off, and keep passing the JSON schema as the response format. `OLLAMA_HOST` stays overridable. The default for a container on this Mac is `http://host.docker.internal:11434`, which is Ollama on the same machine. Document that a run on the host without Docker uses `http://127.0.0.1:11434`.

Pull `qwen3:8b` before the live run. If that model does not return JSON that passes schema validation and `audit_risk_reply`, record the failure in the deployment notes. Do not switch models. Do not invent a score.

Do not send the prompt to a hosted API.

## 8. Container

Change the Dockerfile command from `pytest` to:

```text
python scripts/run_risk_agent.py
```

The image still installs the package. It contains the test input, the pack, and the script. It does not contain the model weights. Ollama stays outside the container, on the host.

Build and run with no published ports, so nothing outside the machine accepts connections for this agent:

```bash
docker build -t risk-scoring-agent .
docker run --rm -e OLLAMA_HOST=http://host.docker.internal:11434 risk-scoring-agent
```

Save the build output and the run output under `deploy/build.log` and `deploy/run.log`. The run log must contain the printed risk JSON for `APP-APPROVE`. `pytest` must still pass, and CI must not need Ollama.

## 9. Deployment notes

Write `docs/onprem-deployment.md` with:

- How Ollama was installed and which model was pulled. Include the model tag that produced the saved run.
- The adapter call: host, model name, thinking off, JSON schema as the format.
- The architectural difference from a hosted model. The weights are on this machine. The prompt goes to loopback or `host.docker.internal`. No task role exists, because the process does not call an AWS API. Access is the local process being able to read the test file and open a connection to Ollama.
- The printed risk JSON.
- A comparison section with three labeled parts: cost, complexity, and output quality. Cost is local compute and no per-call invoice, against a hosted model that bills per token. Complexity is one local process, against ECR, a task definition, a task role, and a private subnet. Output quality compares this run's score and lines with the AWS branch's result for the same input.
- A recommendation: which deployment to give a client who cannot let applicant data leave their network, and which to give a client who can.

The AWS branch may not exist yet, and its Bedrock call may have been denied. If `docs/aws-deployment.md` is not on this branch, write the comparison against the AWS design in section 10 and leave this marker where the AWS score would go:

```text
AWS_RUN_SCORE: pending
```

Do not invent the AWS score. When a real AWS run log exists, replace the marker with that score and update the quality paragraph.

## 10. AWS design to compare against

Use this description if the AWS branch is not available. Do not create these resources.

The other deployment runs the same script and the same `APP-APPROVE` input. The model call is `bedrock:InvokeModel` on `qwen.qwen3-32b-v1:0` in `us-east-1`. The task role allows that action on that model and nothing else. ECS would run it as a Fargate task with 0.5 vCPU and 1 GB, in a private subnet, with no inbound rules and outbound TCP 443. That role is a document. It was not created in IAM. Applicant text would leave the container for Bedrock.

## 11. Done when

- The branch is `feat/risk-agent-onprem`, based on `main`.
- `intake_agent`, `enrichment_agent`, `recommendation_agent`, the harness, and `scripts/run_traces.py` are gone.
- `risk_scoring_agent` still looks up credit, calls the model once, audits, and attaches the credit file.
- The container command is `python scripts/run_risk_agent.py`, and the test input matches section 5.
- The live model is local Ollama `qwen3:8b`. The saved run names that tag.
- `docker build` succeeded. `deploy/run.log` contains a risk JSON for `APP-APPROVE`.
- `docs/onprem-deployment.md` covers the local model, the missing IAM role, the loopback network, the cost and complexity comparison, and a recommendation for a client with a data-residency requirement and a client without one.
- `pytest` passes without Ollama and without AWS.
- The README describes this one-agent run and no longer tells the reader to run the four-agent harness.
- No commit and no push.
