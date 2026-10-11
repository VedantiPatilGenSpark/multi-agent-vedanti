"""Product pack contract loaded by the harness."""

from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import BaseModel

Outcome = Literal["approve", "refer", "deny"]

PROMPT_NAMES = ("intake", "enrichment", "risk", "recommendation")
SCHEMA_NAMES = (
    "raw_application_schema",
    "application_schema",
    "enrichment_schema",
    "risk_schema",
    "decision_schema",
)
CALLABLE_NAMES = ("enrichment_lookup", "credit_lookup", "fixture")


class Rubric(BaseModel):
    base: int
    cap: int
    adjustment_min: int
    adjustment_max: int
    points_by_id: dict[str, int]


class Band(BaseModel):
    """Inclusive lower bound. The highest matching minimum wins."""

    minimum: int
    outcome: Outcome


class CreditFile(BaseModel):
    applicant_id: str
    file_status: Literal["found", "no_file"]
    bureau_score: int | None = None
    delinquencies: int | None = None


class EnrichmentReference(BaseModel):
    """Pack-specific reference data. The harness does not read these fields."""


class ProductPack(Protocol):
    raw_application_schema: type[BaseModel]
    application_schema: type[BaseModel]
    enrichment_schema: type[BaseModel]
    risk_schema: type[BaseModel]
    decision_schema: type[BaseModel]
    prompts: dict[str, str]
    rubric: Rubric
    bands: Sequence[Band]

    def enrichment_lookup(self, application: BaseModel) -> EnrichmentReference: ...

    def credit_lookup(self, applicant_id: str, attempt: int) -> CreditFile: ...

    def fixture(self, applicant_id: str) -> dict: ...


PACKS: dict[str, ProductPack] = {}


def outcome_for_score(bands: Sequence[Band], score: int) -> Outcome:
    """Return the outcome for the highest inclusive cutoff the score still meets."""
    for band in sorted(bands, key=lambda item: item.minimum, reverse=True):
        if score >= band.minimum:
            return band.outcome
    raise ValueError(f"score {score} is below every cutoff")


def register_pack(name: str, pack: ProductPack) -> None:
    PACKS[name] = pack


def load_pack(name: str) -> ProductPack:
    try:
        pack = PACKS[name]
    except KeyError:
        raise LookupError(f"unknown product pack: {name}") from None
    _validate_pack(pack)
    return pack


def _validate_pack(pack: ProductPack) -> None:
    for name in SCHEMA_NAMES:
        schema = getattr(pack, name, None)
        if not isinstance(schema, type) or not issubclass(schema, BaseModel):
            raise TypeError(f"{name} must be a Pydantic model")
    prompts = getattr(pack, "prompts", None)
    if not isinstance(prompts, dict):
        raise ValueError("prompts must be a mapping of agent name to prompt text")
    for name in PROMPT_NAMES:
        text = prompts.get(name)
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"missing prompt: {name}")
    if not isinstance(getattr(pack, "rubric", None), Rubric):
        raise TypeError("rubric must be a Rubric")
    bands = getattr(pack, "bands", None)
    if (
        not isinstance(bands, Sequence)
        or isinstance(bands, (str, bytes))
        or len(bands) == 0
        or any(not isinstance(band, Band) for band in bands)
    ):
        raise ValueError("bands must be a non-empty sequence of Band")
    for name in CALLABLE_NAMES:
        if not callable(getattr(pack, name, None)):
            raise ValueError(f"{name} must be callable")
