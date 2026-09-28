from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from jsonschema import ValidationError, validate
from openai import OpenAI

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"

MODEL = "gpt-5.6-luna"

load_dotenv(ROOT_DIR / ".env")

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError(
        "OPENAI_API_KEY is not set. Put it in the .env file."
    )

client = OpenAI()

def load_json(filename: str) -> Any:
    path = DATA_DIR / filename

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


CHAT_SCRIPT = load_json("chat_script.json")
MEMORY_SCHEMA = load_json("memory_state.schema.json")
RECORDS = load_json("records.json")
POLICY = load_json("policy.json")

CHAT_SYSTEM = f"""
You are an assistant for a study grant office.

Have a natural conversation with the applicant and remember information
from the conversation context that is sent to you.

Use the authoritative office data below when answering questions about
the grant policy or official applicant records.

Important rules:
- The official records and policy are authoritative for grant decisions.
- A claim from the applicant does not modify an official record.
- Do not invent office procedures that are not present in the supplied policy.
- If the applicant asks about something that the available policy does not
  specify, clearly say that the available information does not answer it.
- Keep answers concise.
- If a MEMORY STATE is included in the context, treat it as a structured
  summary of the earlier conversation, not as a new user message.

AUTHORITATIVE RECORDS:
{json.dumps(RECORDS, ensure_ascii=False, indent=2)}

AUTHORITATIVE POLICY:
{json.dumps(POLICY, ensure_ascii=False, indent=2)}
""".strip()


COMPRESSION_SYSTEM = """
You compress a grant-office conversation into a structured memory state.

Return only the state required by the supplied JSON schema.

Rules for the state:
- applicant_id is the applicant ID established by the conversation,
  or null if none was established.
- topic is a short description of what the conversation is about.
- facts contain facts stated by the APPLICANT.
- Do not put model deductions into facts.
- decisions contain conclusions or decisions already established during
  the conversation.
- constraints contain conditions on how or when something can happen,
  such as a day, deadline, availability, or requirement stated by the
  applicant.
- open_questions contain questions that remain unresolved.
- If the assistant said that the available information does not specify
  an answer, that question is still open.
- language describes the language or languages used by the applicant.
- Do not invent information.
- Preserve details that may matter later even if they are not directly
  part of the grant decision.
- Arrays must be present even when empty.
""".strip()

def memory_message(state: dict[str, Any]) -> dict[str, str]:
    return {
        "role": "user",
        "content": (
            "MEMORY STATE FROM EARLIER CONVERSATION:\n"
            + json.dumps(
                state,
                ensure_ascii=False,
                indent=2,
            )
        ),
    }


def build_chat_input(
    history: list[dict[str, str]],
    state: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": CHAT_SYSTEM,
        }
    ]

    if state is not None:
        messages.append(memory_message(state))

    messages.extend(history)

    return messages

def chat_call(
    history: list[dict[str, str]],
    state: dict[str, Any] | None = None,
) -> tuple[str, int]:
    messages = build_chat_input(
        history=history,
        state=state,
    )

    response = client.responses.create(
        model=MODEL,
        input=messages,
        store=False,
    )

    answer = response.output_text.strip()
    input_tokens = response.usage.input_tokens

    return answer, input_tokens

def compress_context(
    history: list[dict[str, str]],
    current_state: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, int, str | None]:
    """
    Returns:
        new_state
        input_tokens
        error

    If parsing or validation fails, new_state is None and the caller
    must keep the original history.
    """

    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": COMPRESSION_SYSTEM,
        }
    ]

    # If the conversation was compressed before, preserve that state
    # when producing a new state.
    if current_state is not None:
        messages.append(memory_message(current_state))

    messages.extend(history)

    try:
        response = client.responses.create(
            model=MODEL,
            input=messages,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "memory_state",
                    "schema": MEMORY_SCHEMA,
                    "strict": True,
                }
            },
            store=False,
        )

        input_tokens = response.usage.input_tokens
        raw = response.output_text.strip()

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            return (
                None,
                input_tokens,
                f"JSON parse failed: {exc}",
            )

        try:
            validate(
                instance=parsed,
                schema=MEMORY_SCHEMA,
            )
        except ValidationError as exc:
            return (
                None,
                input_tokens,
                f"Schema validation failed: {exc.message}",
            )

        return parsed, input_tokens, None

    except Exception as exc:
        return (
            None,
            0,
            f"{type(exc).__name__}: {exc}",
        )

def probe_retrieved(
    probe: dict[str, Any],
    answer: str,
) -> bool:
    """
    Q-2 and Q-3 contain alternative spellings/formats.
    Q-5 represents one fact with two important words,
    so both 'letter' and 'employer' must be present.
    """

    text = answer.casefold()

    expected = [
        str(item).casefold()
        for item in probe["expect_contains"]
    ]

    if probe["id"] == "Q-5":
        return all(item in text for item in expected)

    return any(item in text for item in expected)


def run_probes(
    history: list[dict[str, str]],
    state: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    results = []

    # Every probe is tested independently against the same final
    # conversation state. One probe must not teach the model the
    # answer to a later probe.
    for probe in CHAT_SCRIPT["probes"]:
        probe_history = list(history)

        probe_history.append(
            {
                "role": "user",
                "content": probe["question"],
            }
        )

        answer, tokens = chat_call(
            history=probe_history,
            state=state,
        )

        retrieved = probe_retrieved(
            probe,
            answer,
        )

        results.append(
            {
                "id": probe["id"],
                "tests": probe["tests"],
                "question": probe["question"],
                "answer": answer,
                "retrieved": retrieved,
                "tokens": tokens,
            }
        )

    return results

def run_script(
    use_compression: bool,
) -> dict[str, Any]:
    history: list[dict[str, str]] = []
    state: dict[str, Any] | None = None

    token_events: list[dict[str, Any]] = []

    print()
    print(
        "RUN B — COMPRESSED"
        if use_compression
        else "RUN A — NEVER COMPRESSED"
    )
    print("=" * 70)

    user_turn_number = 0

    for script_index, text in enumerate(
        CHAT_SCRIPT["conversation"],
        start=1,
    ):

        if text == "<compress>":
            if not use_compression:
                print(
                    f"[event {script_index}] "
                    "<compress> skipped in uncompressed run"
                )

                token_events.append(
                    {
                        "event": script_index,
                        "kind": "compress skipped",
                        "tokens": None,
                    }
                )

                continue

            print(
                f"[event {script_index}] "
                "compressing conversation..."
            )

            new_state, tokens, error = compress_context(
                history=history,
                current_state=state,
            )

            token_events.append(
                {
                    "event": script_index,
                    "kind": "compression",
                    "tokens": tokens,
                }
            )

            if error is not None:
                print(
                    "COMPRESSION FAILED."
                )
                print(
                    "Keeping full conversation history."
                )
                print(
                    f"Reason: {error}"
                )

                # IMPORTANT:
                # do not replace state and do not clear history
                continue

            state = new_state

            # Compression succeeded, so old turns can now be
            # discarded.
            history = []

            print("Compression successful.")
            print("State:")
            print(
                json.dumps(
                    state,
                    ensure_ascii=False,
                    indent=2,
                )
            )

            continue

        user_turn_number += 1

        history.append(
            {
                "role": "user",
                "content": text,
            }
        )

        answer, tokens = chat_call(
            history=history,
            state=state,
        )

        history.append(
            {
                "role": "assistant",
                "content": answer,
            }
        )

        token_events.append(
            {
                "event": script_index,
                "kind": f"chat turn {user_turn_number}",
                "tokens": tokens,
            }
        )

        print()
        print(
            f"Turn {user_turn_number}"
        )
        print(
            f"Applicant: {text}"
        )
        print(
            f"Assistant: {answer}"
        )
        print(
            f"Input tokens: {tokens}"
        )

    probes = run_probes(
        history=history,
        state=state,
    )

    print()
    print("PROBES")
    print("-" * 70)

    for result in probes:
        status = (
            "RETRIEVED"
            if result["retrieved"]
            else "LOST"
        )

        print()
        print(
            f'{result["id"]}: {status}'
        )
        print(
            f'Q: {result["question"]}'
        )
        print(
            f'A: {result["answer"]}'
        )

    return {
        "tokens": token_events,
        "state": state,
        "probes": probes,
        "history": history,
    }

def markdown_cell(value: Any) -> str:
    if value is None:
        return "—"

    if isinstance(value, bool):
        return "yes" if value else "no"

    text = str(value)

    return (
        text.replace("|", "\\|")
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
        + " | ".join(
            ["---"] * len(headers)
        )
        + " |"
    )

    for row in rows:
        print(
            "| "
            + " | ".join(
                markdown_cell(value)
                for value in row
            )
            + " |"
        )


def numeric_tokens(
    run: dict[str, Any],
) -> list[int]:
    return [
        event["tokens"]
        for event in run["tokens"]
        if isinstance(event["tokens"], int)
    ]


def print_comparison(
    run_a: dict[str, Any],
    run_b: dict[str, Any],
) -> None:
    print()
    print("=" * 70)
    print("TOKEN TABLE")
    print("=" * 70)
    print()

    # There are 12 entries in chat_script["conversation"].
    # One is <compress>. In A it is skipped; in B it is a
    # real compression model call.
    rows = []

    max_events = max(
        len(run_a["tokens"]),
        len(run_b["tokens"]),
    )

    for index in range(max_events):
        a = (
            run_a["tokens"][index]["tokens"]
            if index < len(run_a["tokens"])
            else None
        )

        b = (
            run_b["tokens"][index]["tokens"]
            if index < len(run_b["tokens"])
            else None
        )

        rows.append(
            [
                index + 1,
                a,
                b,
            ]
        )

    a_values = numeric_tokens(run_a)
    b_values = numeric_tokens(run_b)

    rows.append(
        [
            "**peak**",
            max(a_values),
            max(b_values),
        ]
    )

    rows.append(
        [
            "**total for the run**",
            sum(a_values),
            sum(b_values),
        ]
    )

    print_table(
        [
            "Call / event",
            "A — never compressed",
            "B — compressed at `<compress>`",
        ],
        rows,
    )

    print()
    print(
        "NOTE: the script contains 12 entries, but one is the "
        "`<compress>` command. Therefore A skips that event, "
        "while B makes a compression model call there."
    )

    print()
    print("=" * 70)
    print("PROBE TABLE")
    print("=" * 70)
    print()

    probes_a = {
        probe["id"]: probe
        for probe in run_a["probes"]
    }

    probes_b = {
        probe["id"]: probe
        for probe in run_b["probes"]
    }

    probe_rows = []

    for probe in CHAT_SCRIPT["probes"]:
        probe_id = probe["id"]

        result_a = probes_a[probe_id]
        result_b = probes_b[probe_id]

        probe_rows.append(
            [
                probe_id,
                probe["tests"],
                result_a["retrieved"],
                result_a["answer"],
                result_b["retrieved"],
                result_b["answer"],
            ]
        )

    print_table(
        [
            "Probe",
            "Tests",
            "A retrieved?",
            "A answer",
            "B retrieved?",
            "B answer",
        ],
        probe_rows,
    )

    retrieved_a = sum(
        probe["retrieved"]
        for probe in run_a["probes"]
    )

    retrieved_b = sum(
        probe["retrieved"]
        for probe in run_b["probes"]
    )

    print()
    print(
        f"Retrieved A: {retrieved_a}/5"
    )
    print(
        f"Retrieved B: {retrieved_b}/5"
    )

    print()
    print("=" * 70)
    print("COMPRESSED STATE")
    print("=" * 70)
    print()

    if run_b["state"] is None:
        print(
            "No valid compressed state was produced."
        )
    else:
        print("```json")
        print(
            json.dumps(
                run_b["state"],
                ensure_ascii=False,
                indent=2,
            )
        )
        print("```")

def interactive_chat() -> None:
    history: list[dict[str, str]] = []
    state: dict[str, Any] | None = None

    last_tokens: int | None = None

    print()
    print("Interactive grant-office chat")
    print("=" * 70)
    print("Commands:")
    print("  compress  - compress conversation memory")
    print("  tokens    - show input tokens from the last model call")
    print("  state     - show current compressed state")
    print("  context   - show what local memory is currently kept")
    print("  exit      - leave the chat")
    print()

    while True:
        try:
            text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            print("Goodbye.")
            return

        if not text:
            continue

        command = text.casefold()

        if command in {
            "exit",
            "quit",
        }:
            print("Goodbye.")
            return

        if command == "tokens":
            if last_tokens is None:
                print(
                    "No model call has been made yet."
                )
            else:
                print(
                    f"Last call input tokens: {last_tokens}"
                )

            continue

        if command == "state":
            if state is None:
                print(
                    "No compressed state is active."
                )
            else:
                print(
                    json.dumps(
                        state,
                        ensure_ascii=False,
                        indent=2,
                    )
                )

            continue

        if command == "context":
            print(
                f"Uncompressed messages kept: {len(history)}"
            )
            print(
                f"Compressed state active: {state is not None}"
            )

            if state is not None:
                print(
                    json.dumps(
                        state,
                        ensure_ascii=False,
                        indent=2,
                    )
                )

            continue

        if command == "compress":
            if not history:
                print(
                    "There is no new conversation to compress."
                )
                continue

            new_state, tokens, error = compress_context(
                history=history,
                current_state=state,
            )

            last_tokens = tokens

            if error is not None:
                print(
                    "Compression failed."
                )
                print(
                    "The existing conversation was kept."
                )
                print(
                    f"Reason: {error}"
                )
                continue

            state = new_state
            history = []

            print("Compression successful.")
            print("Old turns were discarded.")
            print("Current state:")
            print(
                json.dumps(
                    state,
                    ensure_ascii=False,
                    indent=2,
                )
            )

            continue

        history.append(
            {
                "role": "user",
                "content": text,
            }
        )

        try:
            answer, tokens = chat_call(
                history=history,
                state=state,
            )
        except Exception as exc:
            # Do not leave an unanswered user message in the
            # stored history after an API failure.
            history.pop()

            print(
                f"API error: {type(exc).__name__}: {exc}"
            )
            continue

        last_tokens = tokens

        history.append(
            {
                "role": "assistant",
                "content": answer,
            }
        )

        print(
            f"Assistant: {answer}"
        )

def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Start an interactive chat session.",
    )

    args = parser.parse_args()

    if args.interactive:
        interactive_chat()
        return

    print(
        "chat_script.json contains "
        f'{len(CHAT_SCRIPT["conversation"])} script entries.'
    )

    print(
        "One entry is the local <compress> command, "
        "so it is not an applicant message."
    )

    run_a = run_script(
        use_compression=False,
    )

    run_b = run_script(
        use_compression=True,
    )

    print_comparison(
        run_a,
        run_b,
    )


if __name__ == "__main__":
    main()