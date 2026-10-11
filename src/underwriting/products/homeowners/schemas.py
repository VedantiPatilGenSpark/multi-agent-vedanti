"""Homeowners section schemas."""

from typing import Literal

from pydantic import BaseModel

from underwriting.products.contract import CreditFile, EnrichmentReference


class Claim(BaseModel):
    year: int
    peril: str
    amount: int


class RawApplication(BaseModel):
    applicant_id: str
    name: str | None
    state: str | None
    year_built: int | None
    roof_age: int | None
    construction: str | None
    coverage_amount: int | None
    prior_claims: list[Claim]


class Application(RawApplication):
    missing: list[str]


class TerritoryReference(EnrichmentReference):
    status: Literal["found", "unknown"]
    wind_hail_band: Literal["low", "high"] | None
    wildfire_band: Literal["low", "high"] | None


class Enrichment(BaseModel):
    status: Literal["found", "unknown"]
    wind_hail_band: Literal["low", "high"] | None
    wildfire_band: Literal["low", "high"] | None
    note: str


class RiskLine(BaseModel):
    id: str
    points: int
    evidence: str


class Risk(BaseModel):
    lines: list[RiskLine]
    combination_adjustment: int
    combination_reason: str
    score: int
    assessment: str
    credit: CreditFile


class Decision(BaseModel):
    outcome: Literal["approve", "refer", "deny"]
    rationale: str
    score: int
