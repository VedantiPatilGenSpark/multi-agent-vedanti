from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_dockerfile_runs_the_risk_agent():
    text = (ROOT / "Dockerfile").read_text()
    assert 'CMD ["python", "scripts/run_risk_agent.py"]' in text
    assert "COPY src ./src" in text
    assert "COPY scripts ./scripts" in text
    assert "pip install" in text


def test_deploy_logs_record_the_build_and_run():
    build = (ROOT / "deploy" / "build.log").read_text()
    run = (ROOT / "deploy" / "run.log").read_text()
    assert build.strip()
    assert run.strip()
