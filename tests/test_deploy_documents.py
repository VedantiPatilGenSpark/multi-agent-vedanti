import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
DEPLOY = ROOT / "deploy"
MODEL_ARN = "arn:aws:bedrock:us-east-1::foundation-model/qwen.qwen3-32b-v1:0"
ACCOUNT = "123456789012"


def _load(name: str) -> dict:
    return json.loads((DEPLOY / name).read_text())


def test_task_role_trusts_ecs_tasks():
    statement = _load("iam-trust-policy.json")["Statement"]
    assert len(statement) == 1
    assert statement[0]["Effect"] == "Allow"
    assert statement[0]["Principal"] == {"Service": "ecs-tasks.amazonaws.com"}
    assert statement[0]["Action"] == "sts:AssumeRole"


def test_task_role_can_invoke_only_qwen():
    policy = _load("iam-permissions-policy.json")
    statement = policy["Statement"]
    assert len(statement) == 1
    assert statement[0]["Effect"] == "Allow"
    assert statement[0]["Action"] == "bedrock:InvokeModel"
    assert statement[0]["Resource"] == MODEL_ARN
    assert "*" not in json.dumps(policy)


def test_task_definition_is_the_fargate_risk_agent():
    task = _load("task-definition.json")
    assert task["family"] == "risk-scoring-agent"
    assert task["cpu"] == "512"
    assert task["memory"] == "1024"
    assert task["networkMode"] == "awsvpc"
    assert task["requiresCompatibilities"] == ["FARGATE"]
    assert task["taskRoleArn"] == f"arn:aws:iam::{ACCOUNT}:role/risk-scoring-agent"
    assert (
        task["executionRoleArn"]
        == f"arn:aws:iam::{ACCOUNT}:role/risk-scoring-agent-execution"
    )
    container = task["containerDefinitions"][0]
    assert (
        container["image"]
        == f"{ACCOUNT}.dkr.ecr.us-east-1.amazonaws.com/risk-scoring-agent:latest"
    )
    assert container["command"] == ["python", "scripts/run_risk_agent.py"]


def test_network_note_describes_a_private_one_shot_task():
    text = (DEPLOY / "network.md").read_text().lower()
    assert "private subnet" in text
    assert "no inbound" in text
    assert "443" in text
    assert "nat gateway" in text
    assert "vpc endpoint" in text
    assert "started by hand" in text
    assert "exits" in text
    assert "nothing on the internet connects" in text
