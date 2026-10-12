import pytest
from pydantic import ValidationError

from underwriting.products.contract import load_pack, register_pack
from underwriting.products.homeowners import HomeownersPack

APPLICANT_IDS = (
    "APP-APPROVE",
    "APP-REFER",
    "APP-DENY",
    "APP-RETRY",
    "APP-TIMEOUT",
)

RUBRIC_POINTS = {
    "roof_missing_or_25_plus": 20,
    "roof_15_to_24": 10,
    "year_built_missing": 10,
    "building_age_40_to_60": 8,
    "building_age_over_60": 15,
    "water_claim_since_2021": 25,
    "other_prior_claim": 10,
    "no_credit_file": 15,
    "delinquencies": 15,
    "bureau_score_below_620": 10,
    "wildfire_high": 15,
    "wind_hail_high": 10,
    "territory_unknown": 10,
}


@pytest.fixture
def pack():
    instance = HomeownersPack()
    register_pack("homeowners", instance)
    return instance


def _application(pack, applicant_id, **overrides):
    raw = dict(pack.fixture(applicant_id))
    raw.update(overrides)
    missing = [
        key
        for key in ("state", "year_built", "roof_age")
        if raw.get(key) is None
    ]
    return pack.application_schema.model_validate({**raw, "missing": missing})


def test_homeowners_pack_satisfies_the_contract(pack):
    assert load_pack("homeowners") is pack


def test_rubric_and_bands_are_pack_data(pack):
    assert pack.rubric.base == 10
    assert pack.rubric.cap == 100
    assert pack.rubric.points_by_id == RUBRIC_POINTS
    assert sorted((band.minimum, band.outcome) for band in pack.bands) == [
        (0, "approve"),
        (40, "refer"),
        (70, "deny"),
    ]


def test_risk_prompt_contains_the_rubric_and_age_rule(pack):
    prompt = pack.prompts["risk"]
    assert "2026 - year_built" in prompt
    assert "at most one roof line" in prompt
    assert "at most one building-age line" in prompt
    for line_id in RUBRIC_POINTS:
        assert line_id in prompt


@pytest.mark.parametrize(
    ("applicant_id", "wind_hail_band", "wildfire_band"),
    [
        ("APP-APPROVE", "low", "low"),
        ("APP-REFER", "high", "low"),
        ("APP-DENY", "high", "high"),
    ],
)
def test_enrichment_lookup_returns_known_territory(
    pack, applicant_id, wind_hail_band, wildfire_band
):
    result = pack.enrichment_lookup(_application(pack, applicant_id))
    assert result.status == "found"
    assert result.wind_hail_band == wind_hail_band
    assert result.wildfire_band == wildfire_band


@pytest.mark.parametrize("state", [None, "TX"])
def test_enrichment_lookup_unknown_state_returns_null_bands(pack, state):
    result = pack.enrichment_lookup(_application(pack, "APP-APPROVE", state=state))
    assert result.status == "unknown"
    assert result.wind_hail_band is None
    assert result.wildfire_band is None


@pytest.mark.parametrize("applicant_id", ["APP-APPROVE", "APP-REFER"])
def test_credit_lookup_found(pack, applicant_id):
    credit = pack.credit_lookup(applicant_id, 1)
    assert credit.applicant_id == applicant_id
    assert credit.file_status == "found"
    assert credit.bureau_score == 740
    assert credit.delinquencies == 0


def test_credit_lookup_no_file(pack):
    credit = pack.credit_lookup("APP-DENY", 1)
    assert credit.applicant_id == "APP-DENY"
    assert credit.file_status == "no_file"
    assert credit.bureau_score is None
    assert credit.delinquencies is None


def test_credit_lookup_retry_times_out_on_the_first_attempt_only(pack):
    with pytest.raises(TimeoutError):
        pack.credit_lookup("APP-RETRY", 1)
    credit = pack.credit_lookup("APP-RETRY", 2)
    assert credit.file_status == "found"
    assert credit.bureau_score == 740
    assert credit.delinquencies == 0


@pytest.mark.parametrize("attempt", [1, 2])
def test_credit_lookup_timeout_raises_before_returning_a_file(pack, attempt):
    with pytest.raises(TimeoutError):
        pack.credit_lookup("APP-TIMEOUT", attempt)


@pytest.mark.parametrize("applicant_id", APPLICANT_IDS)
def test_fixture_matches_the_raw_schema(pack, applicant_id):
    raw = pack.fixture(applicant_id)
    pack.raw_application_schema.model_validate(raw)
    assert raw["applicant_id"] == applicant_id
    assert raw["name"]
    assert raw["construction"]
    assert raw["coverage_amount"] is not None


def test_fixture_names_are_distinct(pack):
    names = [pack.fixture(applicant_id)["name"] for applicant_id in APPLICANT_IDS]
    assert len(names) == len(set(names))


def test_approve_refer_deny_and_retry_facts(pack):
    approve = pack.fixture("APP-APPROVE")
    assert approve["state"] == "WI"
    assert approve["year_built"] == 2015
    assert approve["roof_age"] == 8
    assert approve["prior_claims"] == []

    refer = pack.fixture("APP-REFER")
    assert refer["state"] == "OK"
    assert refer["year_built"] == 1960
    assert "roof_age" in refer
    assert refer["roof_age"] is None
    assert refer["prior_claims"] == []

    deny = pack.fixture("APP-DENY")
    assert deny["state"] == "CO"
    assert deny["year_built"] == 1955
    assert deny["roof_age"] == 28
    assert deny["prior_claims"] == [{"year": 2023, "peril": "water", "amount": 8000}]

    retry = pack.fixture("APP-RETRY")
    for key in (
        "state",
        "year_built",
        "roof_age",
        "construction",
        "coverage_amount",
        "prior_claims",
    ):
        assert retry[key] == approve[key]
    assert retry["name"] != approve["name"]


def test_raw_schema_keeps_null_scalars_and_requires_keys(pack):
    raw = dict(pack.fixture("APP-APPROVE"))
    raw["roof_age"] = None
    pack.raw_application_schema.model_validate(raw)
    del raw["roof_age"]
    with pytest.raises(ValidationError):
        pack.raw_application_schema.model_validate(raw)


def test_unknown_fixture_raises(pack):
    with pytest.raises(LookupError):
        pack.fixture("APP-MISSING")


def test_section_schemas_accept_lookup_results(pack):
    application = _application(pack, "APP-APPROVE")
    reference = pack.enrichment_lookup(application)
    pack.enrichment_schema.model_validate({**reference.model_dump(), "note": "note"})
    credit = pack.credit_lookup("APP-APPROVE", 1)
    pack.risk_schema.model_validate(
        {
            "lines": [{"id": "wind_hail_high", "points": 10, "evidence": "band is high"}],
            "score": 10,
            "assessment": "low",
            "credit": credit.model_dump(),
        }
    )
    pack.decision_schema.model_validate(
        {"outcome": "approve", "rationale": "within the band", "score": 10}
    )
