import pytest

from underwriting.audit import RiskAuditError, audit_risk_reply
from underwriting.products.contract import Rubric


def _rubric(**overrides) -> Rubric:
    fields = {
        "base": 10,
        "cap": 100,
        "points_by_id": {"alpha": 5, "beta": 7},
    }
    fields.update(overrides)
    return Rubric(**fields)


def _line(line_id: str, points: int | None = None, evidence: str = "cited") -> dict:
    if points is None:
        points = {"alpha": 5, "beta": 7}[line_id]
    return {"id": line_id, "points": points, "evidence": evidence}


def _reply(lines, score=15) -> dict:
    return {
        "lines": lines,
        "score": score,
        "assessment": "note",
    }


def test_matching_reply_passes_and_is_not_rescored():
    reply = _reply([_line("alpha")], score=15)
    audit_risk_reply(reply, _rubric())
    assert reply["score"] == 15
    assert reply["lines"] == [_line("alpha")]


def test_unknown_line_id_fails():
    reply = _reply([_line("gamma", points=5)], score=15)
    with pytest.raises(RiskAuditError):
        audit_risk_reply(reply, _rubric())


def test_points_must_match_the_rubric():
    reply = _reply([_line("alpha", points=4)], score=14)
    with pytest.raises(RiskAuditError):
        audit_risk_reply(reply, _rubric())


def test_duplicate_line_ids_fail():
    reply = _reply([_line("alpha"), _line("alpha")], score=20)
    with pytest.raises(RiskAuditError):
        audit_risk_reply(reply, _rubric())


def test_score_must_equal_the_clamped_total():
    reply = _reply([_line("alpha")], score=16)
    with pytest.raises(RiskAuditError):
        audit_risk_reply(reply, _rubric())


def test_score_above_the_raw_total_must_use_the_cap():
    reply = _reply([_line("alpha"), _line("beta")], score=20)
    audit_risk_reply(reply, _rubric(cap=20))
    reply["score"] = 22
    with pytest.raises(RiskAuditError):
        audit_risk_reply(reply, _rubric(cap=20))


def test_negative_total_must_clamp_to_zero():
    rubric = _rubric(base=-20, points_by_id={"alpha": 5})
    reply = _reply([_line("alpha")], score=0)
    audit_risk_reply(reply, rubric)
    reply["score"] = -15
    with pytest.raises(RiskAuditError):
        audit_risk_reply(reply, rubric)


def test_evidence_is_not_checked():
    reply = _reply([_line("alpha", evidence="this fact is wrong")], score=15)
    audit_risk_reply(reply, _rubric())
