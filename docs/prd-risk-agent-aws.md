# PRD: Risk-scoring agent, simulated AWS deployment

Status: locked for implementation.  
Audience: the agent on branch `feat/risk-agent-aws` only.  
Base: `main` of this repo. Do not start from another feature branch.  
If this file and `docs/prd.md` disagree, this file wins for this branch. Leave `docs/prd.md` unchanged. It is the previous lab.

Do not implement the on-prem deployment. Do not commit. Do not push. Do not create real AWS resources.

## 1. Purpose

Turn the current four-agent underwriting repo into a single runnable risk-scoring agent, and simulate deploying that agent to AWS. The container runs once, scores one prepared homeowners case, and exits.

AWS is simulated because this account cannot create IAM roles. The branch produces the documents ECS would have stored, and it runs the same image locally. It does not create a role, a repository, a cluster, a task, a subnet, or a security group in AWS.

## 2. Out of scope

Do not build a UI, a queue, a web service, or a long-running server. Do not keep the harness as the thing the container runs. Do not call S3, DynamoDB, CloudWatch, Secrets Manager, or ECR from the agent. Do not add those permissions to the task role. Do not install the AWS CLI as a step of this lab. Do not fall back to Ollama on this branch. Do not invent a risk score when Bedrock cannot be called.

## 3. Branch and result

Create `feat/risk-agent-aws` from current `main` if it does not already exist. All work stays on that branch.

When the branch is done, the repo runs one agent. Intake, enrichment, and recommendation are gone. The Dockerfile command runs the risk agent, not pytest. CI still runs pytest with a fake model and no network.

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

The file holds only the slice this agent reads. Copy the values from `tests/expected_cases/APP-APPROVE.json`:

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

This file is the only case the container runs. The on-prem branch uses the same bytes. Do not change them.

## 6. Entrypoint

Add `scripts/run_risk_agent.py`. It loads the test input, validates `application` and `enrichment` with the homeowners schemas, constructs `HomeownersPack`, calls `risk_scoring_agent` once with attempt `1` and a `BedrockAdapter`, and prints `risk.model_dump()` as JSON to stdout. Then it exits 0.

On `TimeoutError`, `RiskAuditError`, or a validation error, print the error and exit non-zero. Do not retry. Do not write a case file.

`APP-APPROVE` has a credit row. This script does not demonstrate the timeout fixture.

## 7. Bedrock adapter

Add `BedrockAdapter` in `src/underwriting/model.py`. Keep `FakeAdapter` and the `ModelAdapter` protocol. `FakeAdapter` stays offline.

`BedrockAdapter.complete` calls `bedrock-runtime` `InvokeModel` for this model only:

```text
qwen.qwen3-32b-v1:0
```

Region `us-east-1`. Send the prompt as the user message. Pass the schema the agent provides in `response_format.json_schema.schema`, and return the message content as `ModelResponse.text`. Map `prompt_tokens` and `completion_tokens` onto `ModelResponse`. If the body has no token counts, use `0`. Add `boto3` as a dependency on this branch.

Unit-test the adapter with a fake client. The test must not open a socket and must not require AWS credentials.

The task role that would allow this call is in section 8. A local run uses the developer identity, not that role. If credentials are missing or the call is denied, the script exits non-zero and prints the AWS error. Leave that result in the deployment notes. Do not substitute a canned score or Ollama.

## 8. Simulated AWS documents

Write these files. They are the deployment. Nothing in this section is applied to an AWS account.

### 8.1 Task role trust policy

`deploy/iam-trust-policy.json`

The principal is `ecs-tasks.amazonaws.com`. The action is `sts:AssumeRole`.

### 8.2 Task role permissions

`deploy/iam-permissions-policy.json`

One statement. Action `bedrock:InvokeModel`. Resource:

```text
arn:aws:bedrock:us-east-1::foundation-model/qwen.qwen3-32b-v1:0
```

No `*`. No S3, DynamoDB, logs, or ECR actions. The credit row, rubric, and test input are files in the image, so they need no AWS permission. The printed score goes to the process stdout.

### 8.3 Execution role

Do not write a second policy file. In `docs/aws-deployment.md`, name the execution role as the identity ECS would use to pull the image and write logs (`ecr:GetAuthorizationToken`, `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer`, `logs:CreateLogStream`, `logs:PutLogEvents`). State that the agent code never assumes it.

### 8.4 Task definition

`deploy/task-definition.json`

A Fargate task definition with:

| Field | Value |
| --- | --- |
| Family | `risk-scoring-agent` |
| CPU | `512` (0.5 vCPU) |
| Memory | `1024` (1 GB) |
| Network mode | `awsvpc` |
| Task role | `arn:aws:iam::123456789012:role/risk-scoring-agent` |
| Execution role | `arn:aws:iam::123456789012:role/risk-scoring-agent-execution` |
| Image | `123456789012.dkr.ecr.us-east-1.amazonaws.com/risk-scoring-agent:latest` |
| Command | `python`, `scripts/run_risk_agent.py` |

`123456789012` is a placeholder account. The image is local. It is not pushed.

### 8.5 Network

`deploy/network.md`

The task would run in a private subnet. The security group would have no inbound rules. Outbound would be TCP 443, so the task can reach Bedrock through a NAT gateway or a Bedrock VPC endpoint. State why: the task is started by hand, prints one score, and exits. Nothing on the internet connects to it.

## 9. Container

Change the Dockerfile command from `pytest` to:

```text
python scripts/run_risk_agent.py
```

The image still installs the package. It contains the test input, the pack, and the script.

Build it and run it with no published ports:

```bash
docker build -t risk-scoring-agent .
docker run --rm risk-scoring-agent
```

Save the build output and the run output under `deploy/build.log` and `deploy/run.log`. If the Bedrock call fails, `deploy/run.log` is that failure, and section 10 says the account did not allow the call. `pytest` must still pass.

## 10. Deployment notes

Write `docs/aws-deployment.md` with:

- The task role, every permission, and why each one is necessary. State that the paper policy was not created in IAM and was not enforced.
- The execution role, and why those permissions are not on the task role.
- The subnet and security group choice from `deploy/network.md`.
- What the container can change inside its own filesystem, and that the only external call is Bedrock.
- The live run result: the printed risk JSON, or the exact error if Bedrock was denied.

Do not write the on-prem comparison in this file. The other branch owns that.

Update `README.md` so the only run instructions are the risk-agent script, the Docker build, and `pytest`. Remove the four-agent harness instructions.

## 11. Done when

- The branch is `feat/risk-agent-aws`, based on `main`.
- `intake_agent`, `enrichment_agent`, `recommendation_agent`, the harness, and `scripts/run_traces.py` are gone.
- `risk_scoring_agent` still looks up credit, calls the model once, audits, and attaches the credit file.
- The container command is `python scripts/run_risk_agent.py`, and the test input is the `APP-APPROVE` slice in section 5.
- `deploy/iam-trust-policy.json`, `deploy/iam-permissions-policy.json`, `deploy/task-definition.json`, and `deploy/network.md` match section 8.
- The permissions policy contains only `bedrock:InvokeModel` on `qwen.qwen3-32b-v1:0`.
- `docker build` succeeded. `deploy/build.log` and `deploy/run.log` exist.
- `docs/aws-deployment.md` and the README match this branch.
- `pytest` passes without AWS and without Ollama.
- No commit and no push.
