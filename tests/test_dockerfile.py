from pathlib import Path


def test_container_command_runs_the_risk_agent():
    dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()
    assert 'CMD ["python", "scripts/run_risk_agent.py"]' in dockerfile
