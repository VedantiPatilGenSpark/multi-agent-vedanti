"""Run the five homeowners fixtures and write cases/ and traces/.

OLLAMA_HOST is the Ollama base URL. The default is
http://host.docker.internal:11434 so a dev container can reach Ollama on the
host. Set OLLAMA_HOST=http://127.0.0.1:11434 when Ollama is on this machine.

Run with: uv run python scripts/run_traces.py
"""

import json
import sys
import time
from pathlib import Path

from underwriting.harness import PipelineStepError, run_case
from underwriting.model import OllamaAdapter
from underwriting.trace import format_trace_summary

FIXTURES = (
    "APP-APPROVE",
    "APP-REFER",
    "APP-DENY",
    "APP-RETRY",
    "APP-TIMEOUT",
)

_BAND_FIELDS = ("status", "wind_hail_band", "wildfire_band")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    return run_all(OllamaAdapter(), time.sleep, root, root / "tests" / "expected_cases")


def run_all(adapter, sleeper, root: Path, expected_dir: Path, applicant_ids=FIXTURES) -> int:
    """Run each fixture, write its files, and compare the stable case fields."""
    failures = 0
    for applicant_id in applicant_ids:
        try:
            case, trace = run_case(applicant_id, adapter, sleeper=sleeper)
        except PipelineStepError as exc:
            _write_json(root / "traces" / f"{applicant_id}.json", _trace_payload(applicant_id, exc.trace))
            print(format_trace_summary(applicant_id, exc.trace.entries))
            print(f"{applicant_id}: {exc}")
            failures += 1
            continue
        except ValueError as exc:
            print(f"{applicant_id}: {exc}")
            failures += 1
            continue
        _write_json(root / "cases" / f"{applicant_id}.json", case)
        _write_json(root / "traces" / f"{applicant_id}.json", _trace_payload(applicant_id, trace))
        print(format_trace_summary(applicant_id, trace.entries))
        expected = json.loads((expected_dir / f"{applicant_id}.json").read_text())
        problems = stable_mismatches(case, expected)
        if problems:
            print(f"stable check {applicant_id}: mismatch")
            for problem in problems:
                print(problem)
            failures += 1
        else:
            print(f"stable check {applicant_id}: pass")
        print()
    return 1 if failures else 0


def stable_mismatches(case: dict, expected: dict) -> list[str]:
    """Return differences in the fields the fixture and the lookups own."""
    problems = []
    _compare(problems, "status", case.get("status"), expected.get("status"))
    _compare(problems, "escalation", case.get("escalation"), expected.get("escalation"))
    _compare(problems, "application", case.get("application"), expected.get("application"))
    actual_enrichment = case.get("enrichment") or {}
    expected_enrichment = expected.get("enrichment") or {}
    for field in _BAND_FIELDS:
        _compare(
            problems,
            f"enrichment.{field}",
            actual_enrichment.get(field),
            expected_enrichment.get(field),
        )
    _compare(problems, "risk.credit", _credit(case), _credit(expected))
    _compare(problems, "decision.outcome", _outcome(case), _outcome(expected))
    return problems


def _credit(case: dict):
    risk = case.get("risk")
    if risk is None:
        return None
    return risk.get("credit")


def _outcome(case: dict):
    decision = case.get("decision")
    if decision is None:
        return None
    return decision.get("outcome")


def _compare(problems: list[str], label: str, actual, expected) -> None:
    if actual != expected:
        problems.append(f"  {label}: expected {expected!r}, got {actual!r}")


def _trace_payload(applicant_id: str, trace) -> dict:
    return {
        "applicant_id": applicant_id,
        "entries": [entry.to_dict() for entry in trace.entries],
    }


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


if __name__ == "__main__":
    sys.exit(main())
