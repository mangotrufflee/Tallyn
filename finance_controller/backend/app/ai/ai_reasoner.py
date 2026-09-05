import json
import time
from openai import OpenAI

def build_ai_prompt(bank_row, candidates):

    prompt = f"""
You are a cautious AI finance reconciliation assistant.

Your job is to verify whether the BANK TRANSACTION matches
one of the PROVIDED ERP CANDIDATES.

You MUST only select an invoice from the candidates provided.
You MUST NOT invent an invoice.

Financial accuracy is more important than forcing a match.

==================================================
BANK TRANSACTION
==================================================

Transaction ID:
{bank_row["transaction_id"]}

Date:
{bank_row["date"]}

Amount:
₹{bank_row["amount"]:,.2f}

Counterparty:
{bank_row["counterparty"]}


==================================================
ERP CANDIDATES
==================================================

"""

    for i, candidate in enumerate(candidates, start=1):

        prompt += f"""
CANDIDATE {i}

Invoice ID:
{candidate["invoice_id"]}

Date:
{candidate["date"]}

Amount:
₹{candidate["amount"]:,.2f}

Vendor:
{candidate["vendor"]}

Reference:
{candidate["reference"]}

Amount similarity:
{candidate["amount_score"]}

Vendor similarity:
{candidate["vendor_score"]}

Date similarity:
{candidate["date_score"]}

Reference similarity:
{candidate["reference_score"]}

Overall matching score:
{candidate["final_score"]}

"""

    prompt += """
==================================================
HOW TO REASON
==================================================

Use the following evidence hierarchy:

1. DIRECT REFERENCE MATCH IS THE STRONGEST EVIDENCE.

If the ERP candidate's Reference exactly matches the
Bank Transaction ID, this is strong evidence that the
candidate belongs to the bank transaction.

2. EXACT DATE MATCH IS STRONG EVIDENCE.

3. EXACT AMOUNT MATCH IS STRONG EVIDENCE.

4. VENDOR SIMILARITY IS SUPPORTING EVIDENCE.

Vendor names may legitimately differ between systems.
For example:

NETFLIX
Netflix Entertainment Services

can refer to the same organization.

55. MATERIAL AMOUNT DIFFERENCES PREVENT AUTOMATIC MATCHING.

Amount consistency is mandatory for an automatic MATCH.

If the bank amount and ERP amount differ materially,
the candidate must NOT be classified as MATCH.

Even if the reference, vendor and date match,
a material amount discrepancy means the transaction
requires REVIEW.

For example:

Bank amount: ₹9,500
ERP amount: ₹14,500

This is a ₹5,000 discrepancy.

The correct decision is:

REVIEW

The matching invoice may still be selected as the
suspected invoice, but it must NOT be marked MATCH.

6. DO NOT BE OVERLY CAUTIOUS WHEN MULTIPLE STRONG SIGNALS AGREE.

If one candidate has:

- exact reference match
- exact date match
- exact amount match
- strong vendor similarity

then that candidate should normally be classified as MATCH.

7. REVIEW should be used when evidence is conflicting
or when two or more candidates remain genuinely plausible.

8. EXCEPTION should be used when no candidate has
sufficient evidence.

9. Never select a candidate that was not provided.

10. Do not reject a candidate merely because the ERP vendor
name is longer or formatted differently from the bank name.

==================================================
IMPORTANT
==================================================

The numerical matching scores were calculated by a
deterministic reconciliation system.

Use those scores as evidence.

A candidate with:

Reference similarity = 100
Date similarity = 100
Amount similarity = 100
Vendor similarity = 100
Overall score = 100

has extremely strong evidence and should normally be MATCH.

==================================================
OUTPUT FORMAT
==================================================

Return ONLY valid JSON.

Use exactly this structure:

{{
    "decision": "MATCH",
    "selected_invoice": "INV0001",
    "confidence": 95,
    "reason": "The transaction matches the ERP candidate on reference, amount, date and vendor.",
    "risk": "LOW"
}}

The "decision" must be exactly one of:

MATCH
REVIEW
EXCEPTION

If there is no suitable invoice:

"selected_invoice": null

Confidence must be a number between 0 and 100.

Risk must be exactly one of:

LOW
MEDIUM
HIGH
"""

    return prompt


def validate_ai_response(raw_response):

    try:
        cleaned_response = raw_response.strip()

        # Remove Markdown code fences if the model adds them
        if cleaned_response.startswith("```"):
            lines = cleaned_response.splitlines()

            # Remove first line: ```json
            if lines[0].startswith("```"):
                lines = lines[1:]

            # Remove last line: ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            cleaned_response = "\n".join(lines).strip()

        result = json.loads(cleaned_response)

        required_fields = [
            "decision",
            "selected_invoice",
            "confidence",
            "reason",
            "risk"
        ]

        for field in required_fields:
            if field not in result:
                return {
                    "valid": False,
                    "error": f"Missing field: {field}",
                    "result": None
                }

        if result["decision"] not in [
            "MATCH",
            "REVIEW",
            "EXCEPTION"
        ]:
            return {
                "valid": False,
                "error": "Invalid decision",
                "result": None
            }

        if not isinstance(result["confidence"], (int, float)):
            return {
                "valid": False,
                "error": "Confidence must be numeric",
                "result": None
            }

        if not 0 <= result["confidence"] <= 100:
            return {
                "valid": False,
                "error": "Confidence must be between 0 and 100",
                "result": None
            }

        if result["risk"] not in [
            "LOW",
            "MEDIUM",
            "HIGH"
        ]:
            return {
                "valid": False,
                "error": "Invalid risk level",
                "result": None
            }

        return {
            "valid": True,
            "error": None,
            "result": result
        }

    except json.JSONDecodeError:
        return {
            "valid": False,
            "error": "AI returned invalid JSON",
            "result": None
        }

def ask_ai(prompt):
    """
    Send the reconciliation prompt to Qwen running locally
    through Ollama.
    """

    print("10. Connecting to local Qwen...")

    client = OpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama"
    )

    print("11. Sending request to Qwen...")

    inference_start = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model="qwen2.5:3b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a cautious finance "
                        "reconciliation assistant."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0
        )
    finally:
        print(
            f"[TIMING] AI inference: "
            f"{time.perf_counter() - inference_start:.2f}s"
        )

    print("12. Response received")

    return response.choices[0].message.content