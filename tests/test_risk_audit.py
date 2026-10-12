import pytest

from underwriting.audit import RiskAuditError, audit_risk_reply
from underwriting.products.contract import Rubric


def _rubric(**overrides) -> Rubric:
    fields = {
        "base": 10,
        "cap": 100,
        "adjustment_min": -10,
        "adjustment_max": 10,
        "points_by_id": {"alpha": 5, "beta": 7},
    }
    fields.update(overrides)
    return Rubric(**fields)


def _line(line_id: str, points: int | None = None, evidence: str = "cited") -> dict:
    if points is None:
        points = {"alpha": 5, "beta": 7}[line_id]
    return {"id": line_id, "points": points, "evidence": evidence}


def _reply(lines, adjustment=0, reason="", score=15) -> dict:
    return {
        "lines": lines,
        "combination_adjustment": adjustment,
        "combination_reason": reason,
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


@pytest.mark.parametrize("adjustment", [11, -11, 1.5, True])
def test_adjustment_must_be_an_integer_in_range(adjustment):
    reply = _reply(
        [_line("alpha"), _line("beta")],
        adjustment=adjustment,
        reason="alpha beta",
        score=32,
    )
    with pytest.raises(RiskAuditError):
        audit_risk_reply(reply, _rubric())


@pytest.mark.parametrize(
    ("adjustment", "score"),
    [(10, 32), (-10, 12)],
)
def test_adjustment_on_the_boundary_passes(adjustment, score):
    reply = _reply(
        [_line("alpha"), _line("beta")],
        adjustment=adjustment,
        reason="alpha beta",
        score=score,
    )
    audit_risk_reply(reply, _rubric())


def test_nonzero_adjustment_requires_two_cited_ids_in_the_reason():
    reply = _reply(
        [_line("alpha"), _line("beta")],
        adjustment=4,
        reason="only alpha",
        score=26,
    )
    with pytest.raises(RiskAuditError):
        audit_risk_reply(reply, _rubric())


def test_zero_adjustment_allows_an_empty_reason():
    reply = _reply([_line("alpha")], adjustment=0, reason="", score=15)
    audit_risk_reply(reply, _rubric())


def test_score_must_equal_the_clamped_total():
    reply = _reply([_line("alpha")], score=16)
    with pytest.raises(RiskAuditError):
        audit_risk_reply(reply, _rubric())


def test_score_above_the_raw_total_must_use_the_cap():
    reply = _reply(
        [_line("alpha"), _line("beta")],
        adjustment=10,
        reason="alpha beta",
        score=20,
    )
    audit_risk_reply(reply, _rubric(cap=20))
    reply["score"] = 32
    with pytest.raises(RiskAuditError):
        audit_risk_reply(reply, _rubric(cap=20))


def test_negative_total_must_clamp_to_zero():
    rubric = _rubric(base=0, points_by_id={"alpha": 1, "beta": 1})
    reply = _reply(
        [_line("alpha", points=1), _line("beta", points=1)],
        adjustment=-10,
        reason="alpha beta",
        score=0,
    )
    audit_risk_reply(reply, rubric)
    reply["score"] = -8
    with pytest.raises(RiskAuditError):
        audit_risk_reply(reply, rubric)


def test_evidence_is_not_checked():
    reply = _reply([_line("alpha", evidence="this fact is wrong")], score=15)
    audit_risk_reply(reply, _rubric())
