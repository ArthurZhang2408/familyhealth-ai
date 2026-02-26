"""Safety validation for diagnosis agent responses."""

from __future__ import annotations

import logging
import re

from app.services.diagnosis_prompts import EMERGENCY_RESPONSES, RED_FLAG_KEYWORDS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Red flag pre-check (Layer 2 — rule-based, runs BEFORE LLM)
# ---------------------------------------------------------------------------


def pre_check_red_flags(message: str, profile_age: float | None = None) -> list[str]:
    """Fast keyword-based red flag pre-check.

    Returns list of matched flag descriptions. Empty = no flags.
    This is a SUPPLEMENT to the LLM check, not a replacement.
    """
    flags: list[str] = []
    message_lower = message.lower()

    for category, keywords in RED_FLAG_KEYWORDS.items():
        for keyword in keywords:
            if keyword in message_lower:
                flags.append(f"{category}: '{keyword}'")
                break  # one match per category is enough

    # Pediatric age-based flags
    if profile_age is not None and profile_age < 0.25:  # under 3 months
        if any(w in message_lower for w in ["fever", "temperature", "hot"]):
            flags.append("pediatric: infant under 3 months with possible fever")

    return flags


def get_emergency_response(flags: list[str]) -> tuple[str, str]:
    """Get the emergency response template for the first matched flag category.

    Returns (message, severity).
    """
    if not flags:
        return "", "moderate"

    category = flags[0].split(":")[0].strip()
    template = EMERGENCY_RESPONSES.get(category, EMERGENCY_RESPONSES["cardiovascular"])
    return template["message"], template["severity"]


# ---------------------------------------------------------------------------
# Post-LLM response validation (runs AFTER LLM response)
# ---------------------------------------------------------------------------

PROHIBITED_PATTERNS: list[str] = [
    # Specific drug dosage recommendations
    r"\b(take|prescribe|recommend)\b.*\b\d+\s*(mg|ml|mcg|units)\b",
    # Cancer diagnosis claims
    r"\b(you have|diagnosed with|this is)\b.*(cancer|carcinoma|lymphoma|melanoma|leukemia)\b",
    # HIV/STI diagnosis
    r"\b(you have|diagnosed with|this is)\b.*(HIV|AIDS|herpes|chlamydia|gonorrhea|syphilis)\b",
    # "You don't need a doctor"
    r"\b(don't|do not|no)\s+(need to|have to)\s+(see|visit|consult)"
    r"\s+(a\s+)?(doctor|physician|medical)\b",
    # Prognosis / survival
    r"\b(survival rate|life expectancy|prognosis is|will likely die|terminal)\b",
]


def validate_response(text: str) -> list[str]:
    """Check the LLM response for prohibited content.

    Returns a list of violation descriptions. Empty list = clean.
    """
    violations: list[str] = []
    text_lower = text.lower()

    for pattern in PROHIBITED_PATTERNS:
        if re.search(pattern, text_lower):
            violations.append(f"Prohibited pattern matched: {pattern}")

    return violations


def sanitize_response(text: str, violations: list[str]) -> str:
    """If violations are detected, append a safety notice."""
    if not violations:
        return text

    logger.warning("Diagnosis response violated safety rules: %s", violations)

    return text + (
        "\n\n---\n"
        "**Important:** For the specific concerns raised above, please consult "
        "a healthcare professional directly. I can help you understand your symptoms "
        "and suggest next steps, but specific diagnosis and treatment decisions "
        "should be made with your doctor."
    )
