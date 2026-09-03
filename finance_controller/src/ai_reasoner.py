import json
from openai import OpenAI

def build_ai_prompt(bank_row, candidates):
    """
    Build the prompt that will be sent to the AI.

    The AI receives:
    1. The bank transaction
    2. A small set of possible ERP matches
    3. Matching scores calculated by our deterministic matcher

    The AI's job is to reason about the evidence.
    """

    candidate_text = ""

    for i, candidate in enumerate(candidates, start=1):

        candidate_text += f"""
CANDIDATE {i}

Invoice ID:
{candidate["invoice_id"]}

Date:
{candidate["date"]}

Amount:
₹{candidate["amount"]:,.2f}

Vendor:
{candidate["vendor"]}

Amount similarity:
{candidate["amount_score"]}

Vendor similarity:
{candidate["vendor_score"]}

Date similarity:
{candidate["date_score"]}

Overall matching score:
{candidate["final_score"]}

"""


    prompt = f"""
You are an AI finance reconciliation assistant.

Your task is to evaluate whether a bank transaction
can safely be reconciled with one of the provided
ERP transaction candidates.

You are assisting a finance operations team.
Financial accuracy is more important than forcing
a match.

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

{candidate_text}


==================================================
DECISION RULES
==================================================

1. Do not automatically select the candidate with
   the highest numerical score.

2. Compare the transaction amount carefully.

3. Consider differences in transaction dates.

4. Vendor-name variations are acceptable when they
   clearly refer to the same organization.

5. A large amount discrepancy should normally prevent
   automatic reconciliation.

6. If multiple candidates are similarly plausible,
   recommend REVIEW.

7. If there is insufficient evidence to identify a
   reliable match, recommend EXCEPTION.

8. Never invent missing information.

9. Prefer REVIEW or EXCEPTION over an unsafe
   financial decision.

10. Give a short explanation for your decision.


==================================================
OUTPUT FORMAT
==================================================

Return ONLY valid JSON.

Use exactly this structure:

{{
    "decision": "MATCH",
    "selected_invoice": "INV0001",
    "confidence": 95,
    "reason": "The amount, vendor and date strongly support the match.",
    "risk": "LOW"
}}

The "decision" must be exactly one of:

MATCH
REVIEW
EXCEPTION

If there is no suitable invoice, use:

"selected_invoice": null

Confidence must be a number between 0 and 100.

Risk must be exactly one of:

LOW
MEDIUM
HIGH
"""

    return prompt


def validate_ai_response(response):
    """
    Validate the JSON returned by the AI.

    This protects the finance pipeline from malformed
    or unexpected AI responses.
    """

    try:
        result = json.loads(response)

    except json.JSONDecodeError:
        return {
            "valid": False,
            "error": "AI returned invalid JSON",
            "result": None,
        }

    required_fields = [
        "decision",
        "selected_invoice",
        "confidence",
        "reason",
        "risk",
    ]

    for field in required_fields:

        if field not in result:

            return {
                "valid": False,
                "error": (
                    f"Missing required field: {field}"
                ),
                "result": None,
            }

    valid_decisions = [
        "MATCH",
        "REVIEW",
        "EXCEPTION",
    ]

    if result["decision"] not in valid_decisions:

        return {
            "valid": False,
            "error": "Invalid decision returned by AI",
            "result": None,
        }

    valid_risks = [
        "LOW",
        "MEDIUM",
        "HIGH",
    ]

    if result["risk"] not in valid_risks:

        return {
            "valid": False,
            "error": "Invalid risk returned by AI",
            "result": None,
        }

    try:

        confidence = float(
            result["confidence"]
        )

    except (TypeError, ValueError):

        return {
            "valid": False,
            "error": "Confidence must be numeric",
            "result": None,
        }

    if not 0 <= confidence <= 100:

        return {
            "valid": False,
            "error": (
                "Confidence must be between 0 and 100"
            ),
            "result": None,
        }

    return {
        "valid": True,
        "error": None,
        "result": result,
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

    print("12. Response received")

    return response.choices[0].message.content