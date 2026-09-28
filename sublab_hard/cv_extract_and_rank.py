from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from jsonschema import ValidationError, validate
from openai import OpenAI

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
CANDIDATES_DIR = DATA_DIR / "candidates"

MODEL = "gpt-5.6-luna"

load_dotenv(ROOT_DIR / ".env")

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("OPENAI_API_KEY is not set.")

client = OpenAI()

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_text(path: Path) -> str:
    with path.open("r", encoding="utf-8") as file:
        return file.read()


RUBRIC = load_json(DATA_DIR / "candidate_rubric.json")

STORIES = {
    f"story-{i:02d}": load_text(
        CANDIDATES_DIR / f"story-{i:02d}.md"
    )
    for i in range(1, 7)
}

CV_SCHEMA = {
    "type": "object",
    "properties": {
        "candidate_id": {
            "type": "string"
        },
        "full_name": {
            "type": ["string", "null"]
        },
        "degree": {
            "type": ["string", "null"]
        },
        "graduation_year": {
            "type": ["integer", "null"]
        },
        "gpa_original_value": {
            "type": ["number", "null"]
        },
        "gpa_original_scale": {
            "type": ["number", "null"]
        },
        "gpa_4_scale": {
            "type": ["number", "null"]
        },
        "languages": {
            "type": "array",
            "items": {
                "type": "string"
            }
        },
        "published_peer_reviewed_outputs": {
            "type": "integer",
            "minimum": 0
        },
        "research_outputs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title_or_description": {
                        "type": "string"
                    },
                    "status": {
                        "type": "string"
                    },
                    "counts_as_published": {
                        "type": "boolean"
                    },
                    "evidence_quote": {
                        "type": "string"
                    }
                },
                "required": [
                    "title_or_description",
                    "status",
                    "counts_as_published",
                    "evidence_quote"
                ],
                "additionalProperties": False
            }
        },
        "total_countable_experience_months": {
            "type": ["integer", "null"],
            "minimum": 0
        },
        "experience_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string"
                    },
                    "months": {
                        "type": ["integer", "null"]
                    },
                    "evidence_quote": {
                        "type": "string"
                    }
                },
                "required": [
                    "description",
                    "months",
                    "evidence_quote"
                ],
                "additionalProperties": False
            }
        },
        "ambiguities": {
            "type": "array",
            "items": {
                "type": "string"
            }
        },
        "evidence": {
            "type": "object",
            "properties": {
                "full_name": {
                    "type": ["string", "null"]
                },
                "degree": {
                    "type": ["string", "null"]
                },
                "graduation_year": {
                    "type": ["string", "null"]
                },
                "gpa": {
                    "type": ["string", "null"]
                },
                "languages": {
                    "type": ["string", "null"]
                },
                "published_peer_reviewed_outputs": {
                    "type": ["string", "null"]
                },
                "total_countable_experience_months": {
                    "type": ["string", "null"]
                }
            },
            "required": [
                "full_name",
                "degree",
                "graduation_year",
                "gpa",
                "languages",
                "published_peer_reviewed_outputs",
                "total_countable_experience_months"
            ],
            "additionalProperties": False
        }
    },
    "required": [
        "candidate_id",
        "full_name",
        "degree",
        "graduation_year",
        "gpa_original_value",
        "gpa_original_scale",
        "gpa_4_scale",
        "languages",
        "published_peer_reviewed_outputs",
        "research_outputs",
        "total_countable_experience_months",
        "experience_items",
        "ambiguities",
        "evidence"
    ],
    "additionalProperties": False
}

EXTRACTION_SYSTEM = """
You extract a structured scholarship CV from one written application.

Follow these rules exactly.

GENERAL EVIDENCE RULE
- Use only facts stated in the supplied story.
- Never infer or estimate a missing fact.
- If the story does not state a fact, return null for a nullable scalar.
- Arrays must be present even when empty.
- Give a short direct evidence quote for every field you fill.
- Do not convert vague relative phrases such as "last year" into an
  absolute calendar year unless the story itself states the year.

GPA RULES
- Record the original GPA value and original scale when stated.
- Convert GPA to a 4.0 scale.
- Use this explicit proportional conversion:
      gpa_4_scale = original_gpa / original_scale * 4.0
- Round the converted GPA to two decimal places.
- If the GPA is already on a 4.0 scale, preserve the stated value.
- If no GPA is stated, all GPA value fields are null.
- Never infer GPA from degree, university, distinction, or general
  academic impression.

PUBLICATION RULES
- Count an output as published only if the story explicitly says
  "published" or "accepted" and it is peer-reviewed.
- "Submitted", "under review", "in preparation", "planned", and
  "in press" do NOT count as published.
- Record non-published outputs in research_outputs, but set
  counts_as_published=false.
- published_peer_reviewed_outputs must equal the number of
  research_outputs where counts_as_published=true.

EXPERIENCE RULES
- Count months, not jobs.
- Overlapping periods count only once.
- A period with no dates or explicit countable duration is not
  countable; record it with months=null.
- Do not invent dates.
- Use an explicitly stated month total when the story clearly gives one.

CONTRADICTION RULE
- If the story gives contradictory values for the same field, do not
  choose one, do not average them, and do not resolve the contradiction.
- Set the contradicted field to null.
- Record the contradiction in ambiguities with both conflicting claims.
- For GPA contradiction, gpa_original_value, gpa_original_scale and
  gpa_4_scale must be null if there is no single reliable GPA.
- For graduation-year contradiction, graduation_year must be null.

NAME / ID RULE
- candidate_id is supplied separately by the program. Copy it exactly.
- A full name may be taken from the application heading or signature
  when clearly identifying the applicant.

Return only the JSON object matching the schema.
""".strip()


def extraction_prompt(
    candidate_id: str,
    story: str,
) -> str:
    return f"""
CANDIDATE ID:
{candidate_id}

APPLICATION STORY:
------------------
{story}
------------------

Extract the structured CV according to the system rules.
""".strip()

def extract_candidate(
    candidate_id: str,
    story: str,
) -> dict[str, Any]:
    raw = ""
    parsed = None
    parsed_ok = False
    valid = False
    error = None

    try:
        response = client.responses.create(
            model=MODEL,
            input=[
                {
                    "role": "system",
                    "content": EXTRACTION_SYSTEM,
                },
                {
                    "role": "user",
                    "content": extraction_prompt(
                        candidate_id,
                        story,
                    ),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "candidate_cv",
                    "schema": CV_SCHEMA,
                    "strict": True,
                }
            },
            store=False,
        )

        raw = response.output_text.strip()

        try:
            parsed = json.loads(raw)
            parsed_ok = True
        except json.JSONDecodeError as exc:
            error = f"JSON parse error: {exc}"

        if parsed_ok:
            try:
                validate(
                    instance=parsed,
                    schema=CV_SCHEMA,
                )
                valid = True
            except ValidationError as exc:
                error = (
                    f"Schema validation error: "
                    f"{exc.message}"
                )

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    return {
        "candidate_id": candidate_id,
        "parsed": parsed_ok,
        "valid": valid,
        "cv": parsed,
        "raw": raw,
        "error": error,
    }

def consistency_warnings(
    cv: dict[str, Any],
) -> list[str]:
    warnings = []

    counted_outputs = sum(
        1
        for output in cv["research_outputs"]
        if output["counts_as_published"]
    )

    if (
        counted_outputs
        != cv["published_peer_reviewed_outputs"]
    ):
        warnings.append(
            "published count does not match "
            "research_outputs"
        )

    return warnings

def detect_traps(
    cv: dict[str, Any],
) -> list[str]:
    traps = []

    ambiguity_text = " ".join(
        cv["ambiguities"]
    ).casefold()

    # ---------------------------------------------
    # Trap 1: no GPA stated
    # ---------------------------------------------
    gpa_contradiction = any(
        "gpa" in item.casefold()
        and any(
            word in item.casefold()
            for word in (
                "contradict",
                "conflict",
                "inconsistent",
            )
        )
        for item in cv["ambiguities"]
    )

    if (
        cv["gpa_4_scale"] is None
        and not gpa_contradiction
    ):
        traps.append("no GPA stated")

    # ---------------------------------------------
    # Trap 2: GPA on another scale
    # ---------------------------------------------
    original_scale = cv["gpa_original_scale"]

    if (
        original_scale is not None
        and original_scale != 4
    ):
        traps.append("GPA on another scale")

    # ---------------------------------------------
    # Trap 3: paper is not published
    # ---------------------------------------------
    unpublished_statuses = (
        "submitted",
        "under review",
        "in preparation",
        "planned",
        "in press",
    )

    for item in cv["research_outputs"]:
        status = item["status"].casefold()

        if any(
            marker in status
            for marker in unpublished_statuses
        ):
            traps.append("paper not published")
            break

    # ---------------------------------------------
    # Trap 4: contradiction
    # ---------------------------------------------
    if any(
        word in ambiguity_text
        for word in (
            "contradict",
            "conflict",
            "inconsistent",
        )
    ):
        traps.append("contradiction")

    return traps

CORE_NULL_FIELDS = [
    "full_name",
    "degree",
    "graduation_year",
    "gpa_original_value",
    "gpa_original_scale",
    "gpa_4_scale",
    "total_countable_experience_months",
]


def null_fields(
    cv: dict[str, Any],
) -> list[str]:
    return [
        field
        for field in CORE_NULL_FIELDS
        if cv.get(field) is None
    ]

SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "academic": {
            "type": "number",
            "minimum": 0,
            "maximum": 5
        },
        "research": {
            "type": "number",
            "minimum": 0,
            "maximum": 5
        },
        "experience": {
            "type": "number",
            "minimum": 0,
            "maximum": 5
        }
    },
    "required": [
        "academic",
        "research",
        "experience"
    ],
    "additionalProperties": False
}


SCORING_SYSTEM = """
You score one extracted scholarship candidate against the supplied rubric.

Return exactly three numeric fields:
- academic
- research
- experience

Each must be from 0 to 5.

Rules:
- Use only the extracted structured CV and the supplied rubric.
- Do not change or repair the extraction.
- Do not invent missing evidence.
- Follow the rubric's counting rules exactly.
- A GPA that is null because no GPA was stated must follow the rubric's
  explicit no-GPA academic rule.
- If a field is null because the original story contradicted itself,
  do not reconstruct, average, or guess the value.
- For a contradicted field, use only the remaining unambiguous evidence
  when choosing a score. The rubric does not provide a special numeric
  anchor for contradiction.
- Only return the three criterion scores.
- Do not calculate a weighted total.
- Do not select a winner.
""".strip()


def score_candidate(
    cv: dict[str, Any],
) -> dict[str, Any]:
    response = client.responses.create(
        model=MODEL,
        input=[
            {
                "role": "system",
                "content": SCORING_SYSTEM,
            },
            {
                "role": "user",
                "content": (
                    "RUBRIC:\n"
                    + json.dumps(
                        RUBRIC,
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n\nEXTRACTED CV:\n"
                    + json.dumps(
                        cv,
                        ensure_ascii=False,
                        indent=2,
                    )
                ),
            },
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "candidate_scores",
                "schema": SCORE_SCHEMA,
                "strict": True,
            }
        },
        store=False,
    )

    raw = response.output_text.strip()
    parsed = json.loads(raw)

    validate(
        instance=parsed,
        schema=SCORE_SCHEMA,
    )

    return parsed

def rubric_weights() -> dict[str, float]:
    return {
        criterion["id"]: criterion["weight"]
        for criterion in RUBRIC["criteria"]
    }


WEIGHTS = rubric_weights()


def weighted_total(
    scores: dict[str, float],
) -> float:
    total = (
        scores["academic"] * WEIGHTS["academic"]
        + scores["research"] * WEIGHTS["research"]
        + scores["experience"] * WEIGHTS["experience"]
    )

    return round(total, 2)

def ask_prose_winner(
    extracted_cvs: dict[str, dict[str, Any]],
) -> str:
    prompt = f"""
Below are six extracted scholarship CVs and the scholarship rubric.

RUBRIC:
{json.dumps(RUBRIC, ensure_ascii=False, indent=2)}

CANDIDATES:
{json.dumps(extracted_cvs, ensure_ascii=False, indent=2)}

In prose, say which candidate you think should receive the one funded
scholarship and briefly explain why.

This is a separate qualitative judgement.
Do not rely on a winner previously computed by code.
""".strip()

    response = client.responses.create(
        model=MODEL,
        input=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        store=False,
    )

    return response.output_text.strip()

def cell(value: Any) -> str:
    if value is None:
        return "—"

    if isinstance(value, bool):
        return "yes" if value else "no"

    if isinstance(value, list):
        if not value:
            return "none"
        value = ", ".join(str(x) for x in value)

    return (
        str(value)
        .replace("|", "\\|")
        .replace("\n", " ")
    )


def print_table(
    headers: list[str],
    rows: list[list[Any]],
) -> None:
    print(
        "| "
        + " | ".join(headers)
        + " |"
    )

    print(
        "| "
        + " | ".join(["---"] * len(headers))
        + " |"
    )

    for row in rows:
        print(
            "| "
            + " | ".join(
                cell(value)
                for value in row
            )
            + " |"
        )

def main() -> None:

    extraction_results = {}
    extracted_cvs = {}

    print("=" * 72)
    print("Part 1 - extraction")
    print("=" * 72)

    for candidate_id, story in STORIES.items():
        print(f"Extracting {candidate_id}...")

        result = extract_candidate(
            candidate_id,
            story,
        )

        extraction_results[candidate_id] = result

        if not result["parsed"]:
            print("  PARSE FAILED")
            print(f'  {result["error"]}')
            continue

        if not result["valid"]:
            print("  VALIDATION FAILED")
            print(f'  {result["error"]}')
            continue

        cv = result["cv"]
        extracted_cvs[candidate_id] = cv

        warnings = consistency_warnings(cv)

        if warnings:
            print(
                "  WARNING: "
                + "; ".join(warnings)
            )
        else:
            print("  OK")

    print()
    print("### Part 1 — extraction")
    print()

    extraction_rows = []

    for candidate_id in STORIES:
        result = extraction_results[candidate_id]

        if result["cv"] is None:
            nulls = "unavailable"
            traps = "unavailable"
        else:
            nulls = null_fields(result["cv"])
            traps = detect_traps(result["cv"])

        extraction_rows.append(
            [
                candidate_id,
                result["parsed"],
                result["valid"],
                nulls,
                traps,
            ]
        )

    print_table(
        [
            "Story",
            "Parsed?",
            "Valid?",
            "Fields that came back `null`",
            "Traps hit",
        ],
        extraction_rows,
    )

    print()
    print("### Extraction for story-06")
    print()

    story_06 = extraction_results["story-06"]["cv"]

    if story_06 is None:
        print("Extraction failed.")
    else:
        print("```json")
        print(
            json.dumps(
                story_06,
                ensure_ascii=False,
                indent=2,
            )
        )
        print("```")

    # Stop scoring if any extraction is unavailable.
    if len(extracted_cvs) != len(STORIES):
        print()
        print(
            "Cannot score all candidates because at least "
            "one extraction failed."
        )
        return

    print()
    print("=" * 72)
    print("PART 2 — SCORING")
    print("=" * 72)

    scores = {}

    for candidate_id, cv in extracted_cvs.items():
        print(f"Scoring {candidate_id}...")

        try:
            candidate_scores = score_candidate(cv)
        except Exception as exc:
            print(
                f"  ERROR: {type(exc).__name__}: {exc}"
            )
            return

        total = weighted_total(candidate_scores)

        scores[candidate_id] = {
            **candidate_scores,
            "weighted_total": total,
        }

        print(
            f"  academic={candidate_scores['academic']}, "
            f"research={candidate_scores['research']}, "
            f"experience={candidate_scores['experience']}, "
            f"total={total}"
        )

    winner_id = max(
        scores,
        key=lambda candidate_id: scores[candidate_id][
            "weighted_total"
        ],
    )

    winner_cv = extracted_cvs[winner_id]

    winner_name = (
        winner_cv["full_name"]
        if winner_cv["full_name"]
        else winner_id
    )

    print()
    print("### Part 2 — scores and the winner")
    print()

    score_rows = []

    for candidate_id in STORIES:
        result = scores[candidate_id]

        score_rows.append(
            [
                candidate_id,
                result["academic"],
                result["research"],
                result["experience"],
                result["weighted_total"],
            ]
        )

    print_table(
        [
            "Candidate",
            "academic (0–5)",
            "research (0–5)",
            "experience (0–5)",
            "weighted total (code)",
        ],
        score_rows,
    )

    print()
    print(
        f"Winner, computed by my code: "
        f"{winner_id} — {winner_name}"
    )

    ranking = sorted(
        scores.items(),
        key=lambda item: item[1]["weighted_total"],
        reverse=True,
    )

    first_id, first_score = ranking[0]
    second_id, second_score = ranking[1]

    gap = round(
        first_score["weighted_total"]
        - second_score["weighted_total"],
        2,
    )

    print()
    print(
        "Top two:"
    )
    print(
        f"1. {first_id}: "
        f"{first_score['weighted_total']}"
    )
    print(
        f"2. {second_id}: "
        f"{second_score['weighted_total']}"
    )
    print(
        f"Gap: {gap}"
    )

    print()
    print("Asking model separately for prose winner...")

    prose_winner = ask_prose_winner(
        extracted_cvs
    )

    print()
    print(
        "### Model's prose answer, asked separately"
    )
    print()
    print(prose_winner)


if __name__ == "__main__":
    main()