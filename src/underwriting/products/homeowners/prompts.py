"""Prompt text sent with each homeowners agent step."""

RISK_PROMPT = """
Score this homeowners application using only the facts you were given. Do not invent a roof age, a year built, a claim, a credit file, or a territory band.

When year_built is present, building age is 2026 - year_built.

Start the score at 10.

Walk the rubric. A line applies only when its Apply when condition is true for these facts. Cite at most one roof line and at most one building-age line. Do not cite no_credit_file together with delinquencies or bureau_score_below_620.


If a line applies, copy its points from the rubric, add those points to the score, and include the line with an evidence field that states the fact that made it apply. Leave out every line that does not apply.

Write assessment as a short explanation of that score.

Rubric:
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

Return lines (id, points, evidence), score, and assessment.

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
        "Write the rationale for the outcome and score already chosen. For each "
        "cited risk line, name the application or enrichment fact that supports "
        "it. Do not "
        "add lines the risk section omitted. Do not change the outcome or the "
        "score."
    ),
}
