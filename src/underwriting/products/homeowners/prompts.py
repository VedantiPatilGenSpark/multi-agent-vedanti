"""Prompt text sent with each homeowners agent step."""

RISK_PROMPT = """
Score this homeowners application. Building age as of 2026 is 2026 - year_built when year_built is present. Choose the lines yourself. Roof lines are mutually exclusive. Building-age lines are mutually exclusive. Do not combine no_credit_file with bureau or delinquency lines.

base = 10
cap = 100
The combination adjustment is an integer from -10 through +10.
Use a non-zero adjustment only when two cited lines compound or overlap, and name those two ids in combination_reason; otherwise use 0 and an empty reason.

| Id | Points | Apply when |
| --- | --- | --- |
| roof_missing_or_25_plus | 20 | roof_age is null, or roof_age >= 25 |
| roof_15_to_24 | 10 | roof_age is 15 through 24 |
| year_built_missing | 10 | year_built is null |
| building_age_40_to_60 | 8 | age is 40 through 60 |
| building_age_over_60 | 15 | age is greater than 60 |
| water_claim_since_2021 | 25 | a claim has peril water and year >= 2021 |
| other_prior_claim | 10 | any other claim |
| no_credit_file | 15 | file_status is no_file |
| delinquencies | 15 | delinquencies >= 1 |
| bureau_score_below_620 | 10 | bureau score is present and < 620 |
| wildfire_high | 15 | wildfire band is high |
| wind_hail_high | 10 | wind-and-hail band is high |
| territory_unknown | 10 | territory status is unknown |

Return lines (id, points, evidence), combination_adjustment, combination_reason, score, and assessment.
""".strip()

PROMPTS = {
    "intake": (
        "Normalize the raw application. Copy each value through. Leave unknown "
        "scalars null. Set missing to the names of null required facts. Do not "
        "invent values."
    ),
    "enrichment": (
        "Write a short human-readable note that restates only the status, wind_hail_band, and "
        "wildfire_band returned by the territory lookup. Do not fill null "
        "application fields. Do not propose a band when the "
        "status is unknown."
    ),
    "risk": RISK_PROMPT,
    "recommendation": (
        "Write the rationale for this decision. The outcome and score are "
        "already chosen from the band table."
    ),
}
