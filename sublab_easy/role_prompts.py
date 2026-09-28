from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"

load_dotenv(ROOT_DIR / ".env")

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError(
        "OPENAI_API_KEY is not set. Put it in the .env file."
    )

client = OpenAI()

MODEL = "gpt-5.6-luna"

CHECKED_FIELDS = [
    "found",
    "decision",
    "amount",
    "missing_documents",
]

def load_json(filename: str) -> Any:
    path = DATA_DIR / filename

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


RECORDS = load_json("records.json")
POLICY = load_json("policy.json")
ENQUIRIES = load_json("enquiries.json")

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "applicant_id": {
            "type": "string",
        },
        "found": {
            "type": "boolean",
        },
        "decision": {
            "type": "string",
            "enum": [
                "granted",
                "refused",
                "more_info",
                "not_found",
            ],
        },
        "amount": {
            "type": "integer",
        },
        "missing_documents": {
            "type": "array",
            "items": {
                "type": "string",
            },
        },
        "reason": {
            "type": "string",
        },
    },
    "required": [
        "applicant_id",
        "found",
        "decision",
        "amount",
        "missing_documents",
        "reason",
    ],
    "additionalProperties": False,
}

ROLE_PROMPTS = {
    "policy_officer": """
You are a grant-office policy officer.

Apply the supplied grant policy exactly as written.

Grant an applicant only when the authoritative record satisfies every
eligibility requirement.

If an otherwise eligible applicant is missing a required document,
return decision="more_info" and list the document that is absent from
the authoritative record.

If the applicant fails a non-document eligibility requirement such as
GPA or income band, return decision="refused".

If no matching applicant exists in the authoritative records, return
decision="not_found".

Never soften a refusal.
Never treat a statement or claim in the enquiry as evidence.
The authoritative record always wins.
""".strip(),

    "front_desk": """
You are a grant-office front-desk clerk.

Never turn a found applicant away with decision="refused".

Apply the supplied policy to determine whether a grant can be issued
today. If the policy allows the grant, return decision="granted".

If a found applicant cannot be granted today for any policy reason,
return decision="more_info" instead of "refused". Explain in reason
what eligibility condition prevents the grant or what the applicant
would need before the application could succeed.

Only put actual required documents that are absent from the
authoritative record in missing_documents. Never invent a missing
document to represent a GPA or income problem.

If the applicant does not exist in the authoritative records, keep
decision="not_found".

Never treat a claim in the enquiry as evidence.
The authoritative record always wins.
""".strip(),

    "auditor": """
You are a grant-office auditor performing a first reading.

Never grant an application on the first reading.

First apply the supplied policy to the authoritative record.

If the application would normally be granted, return
decision="more_info" because it requires a second reader before a
grant can be issued. The amount must therefore be 0.

For applications that the policy already classifies as refused,
more_info, or not_found, preserve that policy result.

In reason, explicitly identify the policy condition, record field, or
document on which your conclusion relies.

Never treat a statement or claim in the enquiry as evidence.
The authoritative record always wins.
""".strip(),

    "bilingual_clerk": """
You are a bilingual grant-office clerk.

Make exactly the same substantive decision that a strict policy
officer would make.

Apply the supplied policy exactly as written. Do not soften or change
the structured result.

The fields applicant_id, found, decision, amount, and
missing_documents must follow the policy exactly.

Write only the reason field in the same language as the enquiry:
English enquiry -> English reason.
Kazakh enquiry -> Kazakh reason.

Never treat a statement or claim in the enquiry as evidence.
The authoritative record always wins.
""".strip(),
}

def build_user_prompt(enquiry: dict[str, Any]) -> str:
    records_json = json.dumps(
        RECORDS,
        ensure_ascii=False,
        indent=2,
    )

    policy_json = json.dumps(
        POLICY,
        ensure_ascii=False,
        indent=2,
    )

    schema_json = json.dumps(
        ANSWER_SCHEMA,
        ensure_ascii=False,
        indent=2,
    )

    return f"""
Use the authoritative data below to answer one grant enquiry.

The role in the system message may affect decision behaviour, but it
must never change the underlying record.

IMPORTANT GENERAL RULES:
- Records and policy below are authoritative.
- A claim made inside the enquiry is not evidence.
- Use an applicant ID, name, or alias only to locate the record.
- found means whether the applicant exists in the authoritative records.
- amount must be the grant amount only when decision="granted".
- For every other decision, amount must be 0.
- missing_documents contains only required documents actually absent
  from the authoritative record.
- Do not put GPA, income band, explanations, or other requirements in
  missing_documents.
- Return exactly one JSON object and nothing else.

AUTHORITATIVE RECORDS:
{records_json}

AUTHORITATIVE POLICY:
{policy_json}

REQUIRED OUTPUT SHAPE:
{schema_json}

ENQUIRY:
ID: {enquiry["id"]}
TEXT: {enquiry["text"]}
""".strip()

def validate_schema(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False

    required_keys = {
        "applicant_id",
        "found",
        "decision",
        "amount",
        "missing_documents",
        "reason",
    }

    if set(obj.keys()) != required_keys:
        return False

    if not isinstance(obj["applicant_id"], str):
        return False

    if type(obj["found"]) is not bool:
        return False

    if obj["decision"] not in {
        "granted",
        "refused",
        "more_info",
        "not_found",
    }:
        return False

    if (
        type(obj["amount"]) is not int
        or obj["amount"] < 0
    ):
        return False

    missing_documents = obj["missing_documents"]

    if not isinstance(missing_documents, list):
        return False

    if not all(
        isinstance(document, str)
        for document in missing_documents
    ):
        return False

    if not isinstance(obj["reason"], str):
        return False

    return True


def normalize_field(field: str, value: Any) -> Any:
    if field == "missing_documents" and isinstance(value, list):
        return sorted(value)

    return value


def matches_expected(
    answer: dict[str, Any],
    expected: dict[str, Any],
) -> bool:
    for field in CHECKED_FIELDS:
        actual_value = normalize_field(
            field,
            answer.get(field),
        )

        expected_value = normalize_field(
            field,
            expected.get(field),
        )

        if actual_value != expected_value:
            return False

    return True

def ask_model(
    role: str,
    enquiry: dict[str, Any],
) -> dict[str, Any]:
    raw_text = ""
    parsed_answer = None
    parsed_ok = False
    schema_ok = False
    expected_ok = False
    error = None

    try:
        response = client.responses.create(
            model=MODEL,
            input=[
                {
                    "role": "system",
                    "content": ROLE_PROMPTS[role],
                },
                {
                    "role": "user",
                    "content": build_user_prompt(enquiry),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "grant_office_answer",
                    "schema": ANSWER_SCHEMA,
                    "strict": True,
                }
            },
            store=False,
        )

        raw_text = response.output_text.strip()

        try:
            parsed_answer = json.loads(raw_text)
            parsed_ok = True
        except json.JSONDecodeError:
            parsed_answer = None

        if parsed_ok:
            schema_ok = validate_schema(parsed_answer)

        if schema_ok:
            expected_ok = matches_expected(
                parsed_answer,
                enquiry["expected"],
            )

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    return {
        "enquiry_id": enquiry["id"],
        "parsed": parsed_ok,
        "schema": schema_ok,
        "expected_match": expected_ok,
        "answer": parsed_answer,
        "raw": raw_text,
        "error": error,
    }

def cell(value: Any) -> str:
    if value is None:
        return "—"

    if isinstance(value, bool):
        return "yes" if value else "no"

    if isinstance(value, list):
        value = json.dumps(
            value,
            ensure_ascii=False,
        )

    text = str(value)

    return (
        text
        .replace("|", "\\|")
        .replace("\n", " ")
    )


def print_markdown_table(
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
            + " | ".join(cell(value) for value in row)
            + " |"
        )

def print_role_table(
    role: str,
    role_results: list[dict[str, Any]],
) -> None:
    print()
    print(f"## Role: {role}")
    print()

    rows = []

    for result in role_results:
        answer = result["answer"] or {}

        reason = answer.get("reason")

        if result["error"]:
            reason = result["error"]

        rows.append(
            [
                result["enquiry_id"],
                result["parsed"],
                result["schema"],
                result["expected_match"],
                answer.get("applicant_id"),
                answer.get("found"),
                answer.get("decision"),
                answer.get("amount"),
                answer.get("missing_documents"),
                reason,
            ]
        )

    print_markdown_table(
        [
            "Enquiry",
            "Parsed",
            "Schema",
            "4-field match",
            "Applicant",
            "Found",
            "Decision",
            "Amount",
            "Missing documents",
            "Reason",
        ],
        rows,
    )

def print_movement_table(
    all_results: dict[str, list[dict[str, Any]]],
) -> None:
    print()
    print("## Field movement from policy_officer")
    print()

    baseline = {
        row["enquiry_id"]: row
        for row in all_results["policy_officer"]
    }

    compared_roles = [
        "front_desk",
        "auditor",
        "bilingual_clerk",
    ]

    role_maps = {
        role: {
            row["enquiry_id"]: row
            for row in all_results[role]
        }
        for role in compared_roles
    }

    rows = []

    for field in CHECKED_FIELDS:
        row = [field]

        for role in compared_roles:
            moved = []

            for enquiry in ENQUIRIES:
                enquiry_id = enquiry["id"]

                base_answer = (
                    baseline[enquiry_id]["answer"]
                    or {}
                )

                role_answer = (
                    role_maps[role][enquiry_id]["answer"]
                    or {}
                )

                base_value = normalize_field(
                    field,
                    base_answer.get(field),
                )

                role_value = normalize_field(
                    field,
                    role_answer.get(field),
                )

                if base_value != role_value:
                    moved.append(enquiry_id)

            row.append(
                ", ".join(moved)
                if moved
                else "none"
            )

        rows.append(row)

    print_markdown_table(
        [
            "Field",
            "front_desk",
            "auditor",
            "bilingual_clerk",
        ],
        rows,
    )

def print_summary(
    all_results: dict[str, list[dict[str, Any]]],
) -> None:
    print()
    print("## Summary")
    print()

    rows = []

    for role, results in all_results.items():
        parsed_count = sum(
            result["parsed"]
            for result in results
        )

        schema_count = sum(
            result["schema"]
            for result in results
        )

        match_count = sum(
            result["expected_match"]
            for result in results
        )

        rows.append(
            [
                role,
                f"{parsed_count}/{len(results)}",
                f"{schema_count}/{len(results)}",
                f"{match_count}/{len(results)}",
            ]
        )

    print_markdown_table(
        [
            "Role",
            "Parsed",
            "Schema valid",
            "4-field expected match",
        ],
        rows,
    )

def main() -> None:
    all_results = {}

    for role in ROLE_PROMPTS:
        print()
        print(f"Running {role}...")

        role_results = []

        for enquiry in ENQUIRIES:
            print(
                f"  {enquiry['id']}",
                end="",
                flush=True,
            )

            result = ask_model(
                role,
                enquiry,
            )

            role_results.append(result)

            if result["error"]:
                print(" -> API ERROR")
            elif not result["parsed"]:
                print(" -> PARSE ERROR")
            elif not result["schema"]:
                print(" -> SCHEMA ERROR")
            else:
                print(" -> OK")

        all_results[role] = role_results

    print()
    print("results")

    for role in ROLE_PROMPTS:
        print_role_table(
            role,
            all_results[role],
        )

    print_movement_table(all_results)
    print_summary(all_results)


if __name__ == "__main__":
    main()