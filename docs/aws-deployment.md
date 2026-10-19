# Simulated AWS deployment of the risk-scoring agent

This account cannot create IAM roles. The lab's path was a real task role, an ECR push, and an ECS Fargate task started under that role. That path is not available here. The files under `deploy/` are the stand-in for those screenshots. Nothing in `deploy/` was applied to an AWS account.

The container did call Bedrock. `deploy/run.log` is the risk JSON for `APP-APPROVE`. The paper task role was not created and was not what allowed the call. The call used a short-term Bedrock API key for the developer identity.

## Real steps and what this branch did

| Step | What you would do in AWS | What this branch simulated |
| --- | --- | --- |
| 1. Task role | Create a role whose trust policy allows `ecs-tasks.amazonaws.com` to assume it. Attach a policy with one statement: `bedrock:InvokeModel` on the one model ARN. No S3, no database, no logs, no ECR, no `*`. | `deploy/iam-trust-policy.json` and `deploy/iam-permissions-policy.json`. These files are the screenshot of the role. The reason for the one permission is below. JSON has no place for that comment. |
| 2. Execution role | A separate role ECS itself uses to pull the image and write logs: `ecr:GetAuthorizationToken`, `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer`, `logs:CreateLogStream`, `logs:PutLogEvents`. The agent code never assumes this role. | Named here so the task role stays narrow. There is no second policy file. |
| 3. Image | `docker build`, create an ECR repository, `docker push`. | The same image was built locally and tagged `risk-scoring-agent`. `deploy/build.log` is the build transcript. There is no repository and no push. |
| 4. Task definition | Register a Fargate task definition: the image, `taskRoleArn` set to the role from step 1, command set to the one-shot risk-agent script. | `deploy/task-definition.json`. The account `123456789012` is a placeholder. The task role ARN is `arn:aws:iam::123456789012:role/risk-scoring-agent`. |
| 5. Network | Run the task in a private subnet. Security group: no inbound rules. Outbound TCP 443 only, so the task can reach Bedrock through a NAT gateway or a Bedrock VPC endpoint. | `deploy/network.md` states that choice. The local stand-in is `docker run` with no published ports, so nothing outside the machine can connect to the container. |
| 6. Run | Start the task. Read the risk JSON from the task logs. | The image was run locally against `APP-APPROVE-risk-input.json`. `deploy/run.log` is the printed risk JSON. On ECS, that stdout would have been the CloudWatch log stream. No log group was created. |
| 7. Model call | Code inside the container calls Bedrock. The task role is what makes that call allowed. | The policy in step 1 was not created in IAM and was not enforced. The process still called `qwen.qwen3-32b-v1:0` in `us-east-1` and printed a score. The developer API key allowed it. |

## Task role

The trust policy allows `ecs-tasks.amazonaws.com` to call `sts:AssumeRole`. ECS needs that so it can start the task with this identity.

The permissions policy has one statement.

| Action | Resource | Why it is necessary |
| --- | --- | --- |
| `bedrock:InvokeModel` | `arn:aws:bedrock:us-east-1::foundation-model/qwen.qwen3-32b-v1:0` | The agent calls this model once. The credit row, the rubric, and the test input are files in the image, so they need no AWS permission. The score is printed to stdout. |

No other action is on this role. A wildcard resource would let the task call every model. S3, DynamoDB, CloudWatch, and ECR are not on this role.

This policy was not created in IAM and was not enforced during the run.

## Execution role

The execution role would be `arn:aws:iam::123456789012:role/risk-scoring-agent-execution`. ECS would assume it to pull the image and write the task logs. The permissions for that job are `ecr:GetAuthorizationToken`, `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer`, `logs:CreateLogStream`, and `logs:PutLogEvents`.

Those permissions are not on the task role. Pulling an image and writing logs happen around the process, before the agent code is the caller. Putting them on the task role would let the agent process do that work. The agent code never assumes the execution role. Its only AWS call is `InvokeModel`.

## Network

The task would run in a private subnet. Its security group would have no inbound rules. Outbound traffic would be TCP 443, so the task can reach Bedrock through a NAT gateway or a Bedrock VPC endpoint. The task is started by hand, prints one score, and exits. Nothing on the internet connects to it.

The local run used the same idea: `docker run --rm` with no published ports.

## What the container can change

The process can write files inside its own container filesystem. The script prints the score to stdout. A direct run also writes `deploy/metrics.log` with the model id, input tokens, output tokens, `InvokeModel` latency, and the us-east-1 on-demand list price for `qwen.qwen3-32b-v1:0` ($0.15 per million input tokens and $0.60 per million output tokens). `docker run --rm` deletes the container filesystem, so the run mounts `deploy/` and the metrics file remains on the host.

The only call that leaves the container is `bedrock-runtime` `InvokeModel` for `qwen.qwen3-32b-v1:0` in `us-east-1`.

## Live run

`deploy/run.log` for `APP-APPROVE`:

```json
{"lines": [{"id": "roof_age_0_to_25", "points": 10, "evidence": "roof_age is 8"}, {"id": "building_age_0_to_40", "points": 4, "evidence": "building age is 2026 - 2015 = 11"}], "score": 14, "assessment": "The score is 14. The applicant has a roof that is 8 years old (adding 10 points) and a building that is 11 years old (adding 4 points). No other lines in the rubric apply based on the provided facts.", "credit": {"applicant_id": "APP-APPROVE", "file_status": "found", "bureau_score": 740, "delinquencies": 0}}
```

The cited lines match the homeowners rubric for this input: roof age 8 is 10 points, building age 11 is 4 points, and the score is 14. The credit block is the seed row for `APP-APPROVE`. The agent attached it after the arithmetic check passed.
