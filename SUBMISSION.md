# HW2 submission

Name: Serbina Sofiya
Student ID: S23070210
Group: CSS4007-ENG-10
Repository: https://github.com/vesta-12/hw2-vesta-12

## AI tool disclosure

I used it to help interpret the task requirements, draft and refine the system prompts for all three sublabs, review Python code, identify issues in validation and trap-detection logic, and help structure the written explanations in SUBMISSION.md. For Sublab Easy, ChatGPT helped draft the four role prompts (policy_officer, front_desk, auditor, and bilingual_clerk). For Sublab Medium, ChatGPT helped design the conversation compression workflow, the structured memory-state prompt, schema validation, token tracking. For Sublab Hard, ChatGPT helped draft the extraction and scoring prompts, including the rules for missing GPA values, GPA conversion, publication status, experience counting. I ran the programs myself, checked their actual outputs, fixed issues found during the runs, and used the results produced by my repository for the tables and analysis in this submission.

---
## Sublab Easy — one task, four roles

### Decisions per role

One row per enquiry. In each cell, the first value is the `decision` returned by the run. ✓ means it agrees with `expected`; ✗ means it differs from `expected`.

| Enquiry                    | policy_officer | front_desk    | auditor       | bilingual_clerk |
| -------------------------- | -------------- | ------------- | ------------- | --------------- |
| E-01                       | `granted` ✓    | `granted` ✓   | `more_info` ✗ | `granted` ✓     |
| E-02                       | `more_info` ✓  | `more_info` ✓ | `more_info` ✓ | `more_info` ✓   |
| E-03                       | `refused` ✓    | `more_info` ✗ | `refused` ✓   | `refused` ✓     |
| E-04                       | `refused` ✓    | `more_info` ✗ | `refused` ✓   | `refused` ✓     |
| E-05                       | `granted` ✓    | `granted` ✓   | `more_info` ✗ | `granted` ✓     |
| E-06                       | `granted` ✓    | `granted` ✓   | `more_info` ✗ | `granted` ✓     |
| E-07                       | `granted` ✓    | `granted` ✓   | `more_info` ✗ | `granted` ✓     |
| E-08                       | `not_found` ✓  | `not_found` ✓ | `not_found` ✓ | `not_found` ✓   |
| E-09                       | `refused` ✓    | `more_info` ✗ | `refused` ✓   | `refused` ✓     |
| E-10                       | `more_info` ✓  | `more_info` ✓ | `more_info` ✓ | `more_info` ✓   |
| **agrees with `expected`** | **10/10**      | **7/10**      | **6/10**      | **10/10**       |
| **parsed**                 | **10/10**      | **10/10**     | **10/10**     | **10/10**       |
| **schema-valid**           | **10/10**      | **10/10**     | **10/10**     | **10/10**       |

### Which field moved, on which enquiry, under which role

| Field               | Enquiries that moved                     | Role(s) that moved it                                             |
| ------------------- | ---------------------------------------- | ----------------------------------------------------------------- |
| `found`             | none                                     | none                                                              |
| `decision`          | E-03, E-04, E-09; E-01, E-05, E-06, E-07 | `front_desk`: E-03, E-04, E-09; `auditor`: E-01, E-05, E-06, E-07 |
| `amount`            | E-01, E-05, E-06, E-07                   | `auditor`                                                         |
| `missing_documents` | none                                     | none                                                              |

### Raw replies

Full reply for E-03 from `front_desk`, where the role changed the decision away from the policy officer's `refused`:

```json
{
  "applicant_id": "A-203",
  "found": true,
  "decision": "more_info",
  "amount": 0,
  "missing_documents": [],
  "reason": "The application cannot be granted today because the recorded GPA is 2.4, below the required minimum of 2.67."
}
```

Full reply for E-07 from `bilingual_clerk`:

```json
{
  "applicant_id": "A-201",
  "found": true,
  "decision": "granted",
  "amount": 250000,
  "missing_documents": [],
  "reason": "Сіз грант талаптарына сай келесіз: GPA көрсеткіші 2.67-ден жоғары, табыс санатыңыз 1 және қажетті құжаттардың екеуі де тіркелген. Грант мөлшері — 250 000 теңге."
}
```

### Written answers

**1. Which fields are role-sensitive and which are not?** Point at rows in your tables.

Decision and Amount were role-sensitive in my run. Found and Missing_documents were not, neither field changed on any enquiry under any role.

The `front_desk` role changed `decision` on E-03, E-04, and E-09 from `refused` to `more_info`, because it was instructed never to turn a found applicant away with a refusal. The `auditor` also changed `decision` on E-01, E-05, E-06, and E-07 from `granted` to `more_info`, because it was instructed never to grant on a first reading. On the same four rows, `amount` changed from the policy grant amount to `0`.

The `bilingual_clerk` did not change any of the four structured fields. Its effect was only on `reason`: for E-07, the enquiry was in Kazakh and the reason was produced in Kazakh while the structured result stayed the same as the policy officer's.

**2. Which enquiries are most sensitive to the role, and why those?** Say what E-03, E-04, E-07 and E-10 are each testing.

E-03 and E-04 are sensitive because they are clear policy failures. E-03 tests a GPA below the minimum, while E-04 tests an income band that is not allowed. The `policy_officer` returns `refused`, but the `front_desk` changes both to `more_info`, showing that the role can change how an otherwise negative policy result is presented as an operational decision.

E-07 tests both role behaviour and language. The applicant qualifies under the policy. The `auditor` changes the decision from `granted` to `more_info` because a second reading is required, while the `bilingual_clerk` keeps the same structured result but writes `reason` in Kazakh.

E-10 tests whether a claim made by the user can override the authoritative record. The user says that the ID card was uploaded, but the record still does not contain it. Every role kept `decision="more_info"` and `missing_documents=["id_card"]`. This shows that the evidence source remained stable even when the enquiry contradicted it.

E-09 was also role-sensitive for the same policy reason as E-03: it refers to the same applicant with the below-minimum GPA, but identifies her by name rather than applicant ID.

**3. Where does discretion belong — the role paragraph, or code that reads `decision` afterwards?** Say what a downstream program can and cannot tell about which role produced a record.

Discretion about workflow or presentation can live in the role paragraph. For example, `front_desk` intentionally converts refusals into `more_info`, and `auditor` intentionally delays grants until a second reading.

However, a downstream program should not infer the role from `decision`. The same value can be produced for different reasons. For example, `more_info` may mean that a document is genuinely missing, that the front desk softened a refusal, or that the auditor requires another reader.

Therefore, if the downstream program needs to know which role produced a result, the role should be stored explicitly as metadata rather than inferred from the JSON decision. Critical policy constraints should also be checked in deterministic code instead of relying only on role wording.

**4. Is a role a boundary?** Say in Week 2 terms what the role paragraph is made of, and what you would put in code — not in the prompt — if a wrong `decision` were expensive.

A role is not a security or correctness boundary. In Week 2 terms, the role paragraph is still made of tokens placed in the model's context. The model receives those tokens together with the rest of the conversation and generates a continuation conditioned on them. A system role can strongly influence behaviour, but it does not provide a deterministic guarantee.

For example, "never grant on a first reading" and "write the reason in the enquiry language" are model instructions, not security controls.

If an incorrect `decision` were expensive, I would enforce the important invariants in code. The program could deterministically check the applicant against `records.json` and `policy.json`, validate the returned JSON against the schema, verify that a granted amount matches the applicant's income band, check that all required documents exist, and reject or flag a model response that contradicts the authoritative policy. The prompt would guide the model, while code would enforce rules that must not fail.


---

## Sublab Medium — memory you choose

### Tokens per call

| Call                  | A — never compressed | B — compressed at the `compress` turn |
| --------------------- | -------------------- | ------------------------------------- |
| 1                     | 943                  | 943                                   |
| 2                     | 987                  | 1000                                  |
| 3                     | 1076                 | 1066                                  |
| 4                     | 1152                 | 1158                                  |
| 5                     | 1199                 | 1212                                  |
| 6                     | 1283                 | 1287                                  |
| 7                     | 1380                 | 1359                                  |
| 8                     | 1462                 | 1437                                  |
| 9                     | 1553                 | 1530                                  |
| 10                    | —                    | 1112                                  |
| 11                    | 1651                 | 1297                                  |
| 12                    | 1735                 | 1397                                  |
| **peak**              | **1735**             | **1530**                              |
| **total for the run** | **14421**            | **14798**                             |

Call 10 in run B is the compression call. In run A, `<compress>` is a local command and is skipped, so no model call occurs at that point.

### Probes after the conversation

| Probe                 | Tests     | A retrieved? | A answer                                                                                                                                                             | B retrieved? | B answer                                                                                                                                                                            |
| --------------------- | --------- | ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Q-1 identity          | turn 1    | yes          | You are **Daniyar Qoshan**, applicant **A-202**.                                                                                                                     | yes          | You are **Daniyar Qoshan**, applicant **A-202**.                                                                                                                                    |
| Q-2 missing document  | turn 5    | yes          | Your **ID card** is still missing from the official record. Your transcript is on file.                                                                              | yes          | Your **ID card** is still missing from the official record.                                                                                                                         |
| Q-3 band and amount   | turns 3–4 | yes          | Your official income band is **2**. Under the policy, that corresponds to a grant of **150,000 KZT**, provided your ID card is added to the record.                  | yes          | Your official income band is **2**, which corresponds to a grant amount of **150,000 KZT**, provided your missing **ID card** is added and the other requirements remain satisfied. |
| Q-4 the constraint    | turn 6    | no           | The available policy does not specify office opening hours or which days documents can be submitted. I therefore can’t confirm which day you can come to the office. | yes          | You said you can come to the office on **Thursdays** because of your lab commitments. The available policy does not specify whether the ID card can be submitted on that day.       |
| Q-5 the open question | turn 7    | yes          | You asked whether a **scanned letter from your employer** would count, or whether it had to be the **original**.                                                     | yes          | You asked whether a **scanned employer letter would be accepted or whether the original would be required**.                                                                        |
| **retrieved**         |           | **4/5**      |                                                                                                                                                                      | **5/5**      |                                                                                                                                                                                     |

### The state my compression produced

```json
{
  "applicant_id": "A-202",
  "topic": "Study grant eligibility and submission of missing documents",
  "facts": [
    "Applicant's name is Daniyar Qoshan.",
    "Applicant sent a transcript last week.",
    "Applicant's family's certificate identifies income band 2.",
    "The scanner at the applicant's home is broken.",
    "Applicant can only come to the office on Thursdays because of lab commitments all other days.",
    "Applicant says their sister Aruzhan applied last year and is also on file."
  ],
  "decisions": [
    "The ID card is still missing from the official record.",
    "The applicant does not currently qualify while the required ID card is missing.",
    "If the ID card is added and the requirements are met, the grant amount would be 150,000 KZT.",
    "The available policy does not establish that a sibling's application affects the applicant's eligibility."
  ],
  "constraints": [
    "Applicant can only attend the office on Thursdays.",
    "Applicant has lab commitments throughout the rest of the week.",
    "The applicant currently cannot upload the ID card using the home scanner because it is broken."
  ],
  "open_questions": [
    "Are there alternative ways to submit the ID card when the scanner is unavailable?",
    "Can the applicant submit the ID card at the office on a Thursday?",
    "Does a scanned employer letter count, or is the original required?",
    "Would the grant decision be made on the same day the ID card is submitted?",
    "Does Aruzhan's application affect the applicant's eligibility?"
  ],
  "language": "Kazakh and English"
}
```

### Written answers

**1. What did compression buy?** Peak tokens both ways, probes retrieved both ways, and — if a probe was lost — which one and which turn it came from.

Compression reduced the peak input size from **1735 tokens to 1530 tokens**. After the compression point, the difference became clear: the last two calls used 1651 and 1735 tokens without compression, compared with 1297 and 1397 tokens with compressed memory.

However, compression did not reduce the total token cost of this short run. The uncompressed run used **14421 tokens**, while the compressed run used **14798 tokens**, because producing the structured state itself required an additional 1112-token model call. In a longer conversation, that one-time cost could be recovered over more later calls.

The uncompressed run retrieved **4/5 probes**, while the compressed run retrieved **5/5**. The lost probe in run A was **Q-4**, which tested the Thursday constraint stated in **turn 6**. Interestingly, the information existed in the full conversation, but the model did not retrieve it correctly. The compressed state stored Thursday explicitly under `constraints`, which made it easier to retrieve later.

**2. Why must the state be structured rather than a paragraph?** You could have asked for "a summary". Say what changes when the summary is an object with named fields.

A structured state makes memory explicit and machine-checkable. Instead of asking the model for a fluent paragraph and hoping that important details remain, the schema forces information into named categories such as `facts`, `constraints`, `decisions`, and `open_questions`.

This matters because details such as the Thursday availability and the unanswered employer-letter question are easy to omit from a normal summary because they are not the main grant decision. With named fields, the model is explicitly asked to preserve those types of information.

The object can also be validated before replacing the original history. My program checks that every required field exists and has the correct type. If parsing or validation fails, the original conversation is kept. A normal paragraph provides much less structure for both validation and later programmatic use.

**3. What is missing from your state that you would add?** Name what you would add and what you would drop to pay for it.

I would add explicit **provenance/source information** to distinguish facts stated by the applicant from facts confirmed by the official record.

For example, the applicant said that their family's certificate shows income band 2, while the official record independently confirms income band 2. Those statements have different reliability, but the current state does not have a dedicated field that clearly records the source of each item.

To pay for that additional information, I would drop lower-value conversational details such as the broken home scanner or the information about the sister's previous application once they are no longer relevant to the current workflow. I would prioritize source information because it helps prevent applicant claims from being confused with authoritative record data.

**4. When is compression the wrong choice?** Name a conversation where it would lose something that cannot be recovered, and say whether your program would notice.

Compression is the wrong choice when the exact wording of the conversation matters, for example a legal dispute, a formal complaint, or a conversation where a precise promise or consent statement may later need to be audited.

A structured summary may preserve the meaning but lose exact wording, sequence, tone, or small qualifications. Once the original history is discarded, those details cannot be reconstructed reliably from the compressed state.

My program would **not necessarily notice this kind of loss**. It detects malformed JSON and schema violations, but a summary can be perfectly valid according to the schema while still omitting an important detail. Schema validation guarantees the shape of memory, not that the summary is semantically complete.

---

## Sublab Hard — stories in, CVs out, the best candidate by code

### Part 1 — extraction

| Story | Parsed? | Valid? | Fields that came back `null` | Traps hit |
|---|---|---|---|---|
| story-01 | yes | yes | none | none |
| story-02 | yes | yes | `graduation_year`, `gpa_original_value`, `gpa_original_scale`, `gpa_4_scale` | no GPA stated |
| story-03 | yes | yes | none | GPA on another scale, paper not published |
| story-04 | yes | yes | none | paper not published |
| story-05 | yes | yes | none | paper not published |
| story-06 | yes | yes | `graduation_year`, `gpa_original_value`, `gpa_original_scale`, `gpa_4_scale` | contradiction |

Paste the extraction for **story-06**, the one that contradicts itself:

```json
{
  "candidate_id": "story-06",
  "full_name": "Nurzhan Abilov",
  "degree": "BSc in Statistics",
  "graduation_year": null,
  "gpa_original_value": null,
  "gpa_original_scale": null,
  "gpa_4_scale": null,
  "languages": [
    "Kazakh",
    "Russian",
    "English"
  ],
  "published_peer_reviewed_outputs": 1,
  "research_outputs": [
    {
      "title_or_description": "Paper on survey weighting",
      "status": "Published in a peer-reviewed proceedings",
      "counts_as_published": true,
      "evidence_quote": "one paper published, in a peer-reviewed proceedings, on survey weighting"
    },
    {
      "title_or_description": "Poster at a local event",
      "status": "Poster presented; not counted as published",
      "counts_as_published": false,
      "evidence_quote": "One poster at a local event, which I do not think counts."
    }
  ],
  "total_countable_experience_months": 40,
  "experience_items": [
    {
      "description": "Insurance analytics team",
      "months": 40,
      "evidence_quote": "I have been at an insurance analytics team since February 2023, which is about forty months."
    }
  ],
  "ambiguities": [
    "Graduation year is contradictory: the story says, \"I graduated in 2024,\" but also says, \"I am currently a final-year student graduating in 2026.\"",
    "GPA is contradictory: the story says, \"My GPA was 3.2,\" but also says, \"I think it was 3.5.\""
  ],
  "evidence": {
    "full_name": "# Nurzhan Abilov",
    "degree": "I graduated in 2024 with a BSc in Statistics.",
    "graduation_year": "I graduated in 2024 ... I am currently a final-year student graduating in 2026",
    "gpa": "My GPA was 3.2. Actually I should double-check that, I think it was 3.5",
    "languages": "Languages: Kazakh, Russian, English.",
    "published_peer_reviewed_outputs": "one paper published, in a peer-reviewed proceedings, on survey weighting",
    "total_countable_experience_months": "I have been at an insurance analytics team since February 2023, which is about forty months."
  }
}
```

### Part 2 — scores and the winner

| Candidate | academic (0–5) | research (0–5) | experience (0–5) | weighted total (code) |
|---|---:|---:|---:|---:|
| story-01 | 5 | 5 | 2 | 4.40 |
| story-02 | 0 | 0 | 5 | 1.00 |
| story-03 | 4 | 2.5 | 3 | 3.35 |
| story-04 | 4 | 3 | 5 | 3.90 |
| story-05 | 5 | 2 | 2 | 3.50 |
| story-06 | 2 | 2.5 | 5 | 2.75 |

**Winner, computed by my code:** `story-01 — Aziza Bekova`, weighted total **4.40**.

**The model's prose answer, asked separately ("who should win?"):**

> I would award the scholarship to **Aziza Bekova**. She has a strong academic record, with a **3.8 GPA on a 4.0 scale**, and is the only candidate with **two published peer-reviewed outputs**, both of which clearly meet the rubric’s publication standard. Although her directly relevant experience is limited to eight months, her academic and research profile is the strongest overall.
>
> Tamerlan Saparov has substantially more experience—24 months—but a lower GPA and only one published peer-reviewed paper. The other candidates either have fewer publications, weaker or missing academic information, or less relevant experience.

### Part 3 — written answers

**1. Which rule did you have to add, and what broke without it? Name the story that forced it.**

I had to add an explicit rule for converting GPA values from another scale to the required 4.0 scale:

`gpa_4_scale = original_gpa / original_scale × 4.0`

`story-03` forced this rule because the candidate reports a GPA of 4.6 on a 5.0 scale. The assignment says that another scale must be converted, but it does not specify the conversion formula. Without an explicit rule, the model could choose its own conversion method, making the extraction inconsistent between runs. With the rule, the same input always produces the same conversion.

**2. Where did the model guess, and where did your code have to decide? One example of each, from your run.**

The model had to use judgement when selecting intermediate scores because the rubric mainly defines what a score of 0 and a score of 5 mean, but it does not define every value between them. For example, `story-03` received a research score of **2.5**. The rubric does not explicitly state that one published paper should equal 2.5, so that intermediate value is model judgement.

My code made the final quantitative decision. The model returned only the three structured criterion scores: `academic`, `research`, and `experience`. Python then applied the weights `0.5`, `0.3`, and `0.2`, rounded the result to two decimal places, compared the totals, and selected the candidate with the highest weighted score.

**3. Did your prose ranking and your computed ranking agree? Say which one you trust and why — and if they agreed, what you would need to see before trusting the prose one alone.**

Yes. Both the computed ranking and the separate prose answer selected **Aziza Bekova (`story-01`)**.

I trust the computed ranking more because the process is explicit and reproducible. The model provides structured numeric fields, while the weighted total and winner are calculated deterministically in code.

Before trusting the prose answer alone, I would need to see the criterion scores used for every candidate, the evidence behind those scores, and confirmation that the same rubric weights were applied consistently. A convincing natural-language explanation does not prove that the ranking calculation was performed correctly.

**4. The rubric has no anchor for a contradicted field. The stories say 3.2 and then 3.5; the rubric defines a 0 and a 5 and nothing in between for this case. Say what you did and what the rule should be.**

For `story-06`, I did not choose between GPA 3.2 and 3.5 and did not average them. The GPA fields were set to `null`, and the two conflicting statements were recorded in `ambiguities`. The same approach was used for the contradictory graduation year.

During scoring, the model was instructed not to reconstruct or guess the missing value and instead to use the remaining unambiguous evidence. In this run, the model assigned an academic score of **2**.

I think the rubric should define a deterministic rule for contradicted fields. A contradicted quantitative field should be treated as unavailable until it can be verified, while other non-contradicted evidence may still contribute to the criterion. This would reduce variation caused by the model deciding for itself how much a contradiction should reduce the score.

**5. How close were your top two candidates? If they were within 0.05, say what you would tell the committee and what you would change in the extraction to make that call defensible.**

The two highest scores were:

- `story-01`: **4.40**
- `story-04`: **3.90**

The difference was **0.50**, so they were not within 0.05.

Therefore, the near-tie condition did not apply in this run. I would still show the committee the individual criterion scores and their supporting evidence rather than relying only on the final total.

If the difference had been within 0.05, I would tell the committee that the ranking was too sensitive to model judgement to treat the numerical difference as decisive. I would make the extraction more defensible by attaching stronger evidence provenance to every scored field and manually verifying the specific facts that distinguish the two candidates.