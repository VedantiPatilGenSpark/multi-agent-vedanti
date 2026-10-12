import pytest

from underwriting.audit import RiskAuditError, audit_risk_reply
from underwriting.products.contract import Rubric


def _rubric(**overrides) -> Rubric:
    fields = {
        "cap": 100,
        "points_by_id": {"alpha": 5, "beta": 7},
    }
    fields.update(overrides)
    return Rubric(**fields)


def _line(line_id: str, points: int | None = None, evidence: str = "cited") -> dict:
    if points is None:
        points = {"alpha": 5, "beta": 7}[line_id]
    return {"id": line_id, "points": points, "evidence": evidence}


def _reply(lines, score=5) -> dict:
    return {
        "lines": lines,
        "score": score,
        "assessment": "note",
    }


def test_matching_reply_passes_and_is_not_rescored():
    reply = _reply([_line("alpha")], score=5)
    audit_risk_reply(reply, _rubric())
    assert reply["score"] == 5
    assert reply["lines"] == [_line("alpha")]


def test_unknown_line_id_fails():
    reply = _reply([_line("gamma", points=5)], score=5)
    with pytest.raises(RiskAuditError):
        audit_risk_reply(reply, _rubric())


def test_points_must_match_the_rubric():
    reply = _reply([_line("alpha", points=4)], score=4)
    with pytest.raises(RiskAuditError):
        audit_risk_reply(reply, _rubric())


def test_duplicate_line_ids_fail():
    reply = _reply([_line("alpha"), _line("alpha")], score=10)
    with pytest.raises(RiskAuditError):
        audit_risk_reply(reply, _rubric())


def test_score_must_equal_the_clamped_total():
    reply = _reply([_line("alpha")], score=6)
    with pytest.raises(RiskAuditError):
        audit_risk_reply(reply, _rubric())


def test_score_above_the_raw_total_must_use_the_cap():
    reply = _reply([_line("alpha"), _line("beta")], score=10)
    audit_risk_reply(reply, _rubric(cap=10))
    reply["score"] = 12
    with pytest.raises(RiskAuditError):
        audit_risk_reply(reply, _rubric(cap=10))


def test_evidence_is_not_checked():
    reply = _reply([_line("alpha", evidence="this fact is wrong")], score=5)
    audit_risk_reply(reply, _rubric())
