# On-prem deployment: risk-scoring agent

The container scored one prepared homeowners case, `APP-APPROVE`, and exited. The model was local Ollama. The saved run is `deploy/run.log`. The build log is `deploy/build.log`.

## Local model

Ollama is the macOS app at `/Applications/Ollama.app`. The CLI is the symlink `/usr/local/bin/ollama`, version 0.34.0. It was already installed on this machine. `qwen3:8b` was already pulled. This run did not pull another tag.

The model tag that produced `deploy/run.log` is `qwen3:8b`.

## Adapter call

`OllamaAdapter` posts to `{OLLAMA_HOST}/api/generate`.

| Setting | Value |
| --- | --- |
| Container host | `http://host.docker.internal:11434` |
| Host without Docker | `http://127.0.0.1:11434` |
| Model | `qwen3:8b` |
| Thinking | off (`think: false`) |
| Stream | off |
| Format | the risk JSON schema, with `credit` removed |

The container command was:

```bash
docker build -t risk-scoring-agent .
docker run --rm -e OLLAMA_HOST=http://host.docker.internal:11434 risk-scoring-agent
```

The run published no ports. The image contains the package, the test input, the pack, and `scripts/run_risk_agent.py`. It does not contain the model weights. Ollama stayed on the host.

## Architecture

The weights are on this machine, under the local Ollama store. The prompt goes to loopback when the script runs on the host, or to `host.docker.internal` when the script runs in the container. That name reaches Ollama on the same machine. The prompt does not go to a hosted API.

No task role exists. The process does not call an AWS API, so there is no IAM role to assume. Access is the local process being able to read `src/underwriting/products/homeowners/fixtures/APP-APPROVE-risk-input.json` and open a connection to Ollama.

## Printed risk JSON

`qwen3:8b` returned JSON that passed schema validation and `audit_risk_reply`. The script attached the credit lookup after the audit. `deploy/run.log` contains:

```json
{"lines": [{"id": "roof_age_0_to_25", "points": 10, "evidence": "roof_age is 8"}, {"id": "building_age_0_to_40", "points": 4, "evidence": "year_built is 2015, so building age is 2026 - 2015 = 11"}], "score": 14, "assessment": "The score is 14 because the roof age is between 0 and 25 (10 points) and the building age is between 0 and 40 (4 points).", "credit": {"applicant_id": "APP-APPROVE", "file_status": "found", "bureau_score": 740, "delinquencies": 0}}
```

The cited lines are `roof_age_0_to_25` for 10 points and `building_age_0_to_40` for 4 points. The score is 14. Credit is `found`, bureau score 740, delinquencies 0.

## Comparison

`docs/aws-deployment.md` is not on this branch, so this section uses the AWS design for the same script and the same `APP-APPROVE` input. That design calls `bedrock:InvokeModel` on `qwen.qwen3-32b-v1:0` in `us-east-1`. The task role allows that action on that model and nothing else. ECS would run the container as a Fargate task with 0.5 vCPU and 1 GB, in a private subnet, with no inbound rules and outbound TCP 443. That role is a document. It was not created in IAM. Applicant text would leave the container for Bedrock.

### Cost

This run spends local compute and creates no per-call invoice. The hosted model bills per token for `bedrock:InvokeModel` on `qwen.qwen3-32b-v1:0`.

### Complexity

This deployment is one local process: Ollama on the machine, and a container that reads the test file and calls that process. The AWS design adds ECR, a task definition, a task role, and a private subnet.

### Output quality

This run's score is 14. The lines are `roof_age_0_to_25` (10) and `building_age_0_to_40` (4).

```text
AWS_RUN_SCORE: pending
```

A real AWS run log is not on this branch. This note does not invent that score. When the log exists, replace the marker with the AWS score and lines for the same input and update this paragraph.

## Recommendation

Give this on-prem deployment to a client who cannot let applicant data leave their network. The weights stay on the machine, and the prompt stays on loopback or `host.docker.internal`.

Give the AWS design to a client who can let applicant text leave the container. That deployment calls Bedrock `qwen.qwen3-32b-v1:0` from a private Fargate task under a role that allows only `bedrock:InvokeModel` on that model.
