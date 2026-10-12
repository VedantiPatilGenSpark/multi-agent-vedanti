"""Generic arithmetic audit for a risk-model reply."""

from underwriting.products.contract import Rubric


class RiskAuditError(Exception):
    """The model reply failed the arithmetic audit."""


def audit_risk_reply(reply: dict, rubric: Rubric) -> None:
    """Raise RiskAuditError when the reply fails. Leave the reply unchanged."""
    lines = reply["lines"]
    score = reply["score"]

    cited_ids = [line["id"] for line in lines]
    if len(cited_ids) != len(set(cited_ids)):
        raise RiskAuditError("duplicate line ids")

    for line in lines:
        line_id = line["id"]
        if line_id not in rubric.points_by_id:
            raise RiskAuditError(f"unknown line id: {line_id}")
        if line["points"] != rubric.points_by_id[line_id]:
            raise RiskAuditError(f"points do not match the rubric for {line_id}")

    total = rubric.base + sum(line["points"] for line in lines)
    expected = min(rubric.cap, max(0, total))
    if score != expected:
        raise RiskAuditError("score does not match the clamped total")
