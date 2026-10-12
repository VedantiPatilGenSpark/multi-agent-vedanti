"""Prompt text sent with each homeowners agent step."""

RISK_PROMPT = """
Score this homeowners application using only the facts you were given. Do not invent a roof age, a year built, a claim, a credit file, or a territory band.

When year_built is present, building age is 2026 - year_built.

Walk the rubric. A line applies only when its Apply when condition is true for these facts. Cite at most one roof line and at most one building-age line.

If a line applies, copy its points from the rubric and include the line with an evidence field that states the fact that made it apply. Leave out every line that does not apply.

Set the score to the sum of the cited lines' points. If that sum is over 100, the score is 100.

Write assessment as a short explanation of that score.

Rubric:
| Id | Points | Apply when |
| --- | --- | --- |
| roof_age_null | 20 | roof_age is null |
| roof_age_0_to_25 | 10 | roof_age is 0 through 25 |
| roof_age_above_25 | 20 | roof_age is 26 or greater |
| building_age_0_to_40 | 4 | age is 0 through 40 |
| building_age_above_40 | 15 | age is 41 or greater |
| water_claim_since_2021 | 25 | a claim has peril water and year >= 2021 |
| no_credit_file | 15 | file_status is no_file |
| wildfire_high | 15 | wildfire band is high |
| wind_hail_high | 10 | wind-and-hail band is high |

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
