import pytest
from pydantic import BaseModel

from underwriting.products.contract import (
    Band,
    CreditFile,
    EnrichmentReference,
    Rubric,
    load_pack,
    outcome_for_score,
    register_pack,
)


class _App(BaseModel):
    applicant_id: str


def _bands() -> list[Band]:
    return [
        Band(minimum=0, outcome="approve"),
        Band(minimum=40, outcome="refer"),
        Band(minimum=70, outcome="deny"),
    ]


class _StubPack:
    def __init__(self) -> None:
        self.raw_application_schema = _App
        self.application_schema = _App
        self.enrichment_schema = _App
        self.risk_schema = _App
        self.decision_schema = _App
        self.prompts = {
            "intake": "intake prompt",
            "enrichment": "enrichment prompt",
            "risk": "risk prompt",
            "recommendation": "recommendation prompt",
        }
        self.rubric = Rubric(
            cap=50,
            points_by_id={"line_a": 3},
        )
        self.bands = _bands()

    def enrichment_lookup(self, application: BaseModel) -> EnrichmentReference:
        return EnrichmentReference()

    def credit_lookup(self, applicant_id: str, attempt: int) -> CreditFile:
        return CreditFile(
            applicant_id=applicant_id,
            file_status="no_file",
            bureau_score=None,
            delinquencies=None,
        )

    def fixture(self, applicant_id: str) -> dict:
        return {"applicant_id": applicant_id}


@pytest.fixture(autouse=True)
def _clear_registry():
    from underwriting.products import contract

    contract.PACKS.clear()
    yield
    contract.PACKS.clear()


@pytest.mark.parametrize(
    ("score", "outcome"),
    [
        (0, "approve"),
        (39, "approve"),
        (40, "refer"),
        (69, "refer"),
        (70, "deny"),
        (100, "deny"),
    ],
)
def test_outcome_for_score_uses_highest_matching_cutoff(score, outcome):
    assert outcome_for_score(_bands(), score) == outcome


def test_outcome_for_score_is_independent_of_band_order():
    assert outcome_for_score(list(reversed(_bands())), 55) == "refer"


def test_outcome_for_score_rejects_a_score_below_every_cutoff():
    with pytest.raises(ValueError):
        outcome_for_score(_bands(), -1)


def test_load_pack_returns_a_validated_pack():
    pack = _StubPack()
    register_pack("stub", pack)
    assert load_pack("stub") is pack


def test_load_pack_unknown_name_raises():
    with pytest.raises(LookupError, match="unknown product pack: not-a-pack"):
        load_pack("not-a-pack")


def test_load_pack_rejects_a_pack_missing_a_prompt():
    pack = _StubPack()
    del pack.prompts["recommendation"]
    register_pack("stub", pack)
    with pytest.raises(ValueError, match="recommendation"):
        load_pack("stub")


def test_load_pack_rejects_a_pack_missing_enrichment_lookup():
    pack = _StubPack()
    pack.enrichment_lookup = None
    register_pack("stub", pack)
    with pytest.raises(ValueError, match="enrichment_lookup"):
        load_pack("stub")


def test_load_pack_rejects_a_non_model_schema():
    pack = _StubPack()
    pack.risk_schema = dict
    register_pack("stub", pack)
    with pytest.raises(TypeError, match="risk_schema"):
        load_pack("stub")


def test_load_pack_rejects_empty_bands():
    pack = _StubPack()
    pack.bands = []
    register_pack("stub", pack)
    with pytest.raises(ValueError, match="bands"):
        load_pack("stub")
