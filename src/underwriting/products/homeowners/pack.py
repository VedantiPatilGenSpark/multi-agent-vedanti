"""Homeowners pack: schemas, prompts, fixtures, and reference lookups."""

import json
import sqlite3
from pathlib import Path

from pydantic import BaseModel

from underwriting.products.contract import Band, CreditFile, Rubric
from underwriting.products.homeowners.prompts import PROMPTS
from underwriting.products.homeowners.schemas import (
    Application,
    Decision,
    Enrichment,
    RawApplication,
    Risk,
    TerritoryReference,
)

_ROOT = Path(__file__).parent
_TIMEOUT_ATTEMPTS = {
    "APP-TIMEOUT": frozenset({1, 2}),
    "APP-RETRY": frozenset({1}),
}


class HomeownersPack:
    raw_application_schema = RawApplication
    application_schema = Application
    enrichment_schema = Enrichment
    risk_schema = Risk
    decision_schema = Decision
    prompts = PROMPTS
    rubric = Rubric(
        base=10,
        cap=100,
        points_by_id={
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
        },
    )
    bands = (
        Band(minimum=0, outcome="approve"),
        Band(minimum=40, outcome="refer"),
        Band(minimum=70, outcome="deny"),
    )

    def __init__(self) -> None:
        self._db = sqlite3.connect(":memory:")
        self._db.executescript((_ROOT / "seed.sql").read_text())

    def enrichment_lookup(self, application: BaseModel) -> TerritoryReference:
        state = application.state
        if state is None:
            return _unknown_territory()
        row = self._db.execute(
            "SELECT wind_hail_band, wildfire_band FROM territory WHERE state = ?",
            (state,),
        ).fetchone()
        if row is None:
            return _unknown_territory()
        wind_hail_band, wildfire_band = row
        return TerritoryReference(
            status="found",
            wind_hail_band=wind_hail_band,
            wildfire_band=wildfire_band,
        )

    def credit_lookup(self, applicant_id: str, attempt: int) -> CreditFile:
        if attempt in _TIMEOUT_ATTEMPTS.get(applicant_id, frozenset()):
            raise TimeoutError
        row = self._db.execute(
            """
            SELECT bureau_score, delinquencies
            FROM credit
            WHERE applicant_id = ?
            """,
            (applicant_id,),
        ).fetchone()
        if row is None:
            return CreditFile(
                applicant_id=applicant_id,
                file_status="no_file",
                bureau_score=None,
                delinquencies=None,
            )
        bureau_score, delinquencies = row
        return CreditFile(
            applicant_id=applicant_id,
            file_status="found",
            bureau_score=bureau_score,
            delinquencies=delinquencies,
        )

    def fixture(self, applicant_id: str) -> dict:
        path = _ROOT / "fixtures" / f"{applicant_id}.json"
        if not path.is_file():
            raise LookupError(f"unknown fixture: {applicant_id}")
        return json.loads(path.read_text())


def _unknown_territory() -> TerritoryReference:
    return TerritoryReference(
        status="unknown",
        wind_hail_band=None,
        wildfire_band=None,
    )
