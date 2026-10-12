"""Generic arithmetic audit for a risk-model reply."""

from underwriting.products.contract import Rubric


class RiskAuditError(Exception):
    """The model reply failed the arithmetic audit."""


def audit_risk_reply(reply: dict, rubric: Rubric) -> None:
    """Raise RiskAuditError when the reply fails. Leave the reply unchanged."""
    lines = reply["lines"]
    adjustment = reply["combination_adjustment"]
    reason = reply["combination_reason"]
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

    if not _is_integer(adjustment) or not (
        rubric.adjustment_min <= adjustment <= rubric.adjustment_max
    ):
        raise RiskAuditError("adjustment must be an integer inside the rubric range")

    if adjustment != 0:
        named = [line_id for line_id in set(cited_ids) if line_id in reason]
        if len(named) < 2:
            raise RiskAuditError("nonzero adjustment must name two cited ids")

    total = rubric.base + sum(line["points"] for line in lines) + adjustment
    expected = min(rubric.cap, max(0, total))
    if score != expected:
        raise RiskAuditError("score does not match the clamped total")


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
