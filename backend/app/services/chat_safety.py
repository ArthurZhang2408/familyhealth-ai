"""Safety validation for chat responses."""

from __future__ import annotations

import logging
import re

from app.services.chat_prompts import CRISIS_KEYWORDS, CRISIS_RESPONSE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mental health crisis detection (runs BEFORE LLM)
# ---------------------------------------------------------------------------


def detect_mental_health_crisis(message: str) -> bool:
    """Check if the user's message indicates a mental health crisis.

    Uses phrase-based substring matching — fast and zero false-negatives for
    direct expressions, but may produce false positives for caregiver or
    research contexts (e.g. "researching self-harm prevention"). Acceptable
    for MVP: erring on the side of caution is the right trade-off here.

    Returns True if crisis language is detected.
    """
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in CRISIS_KEYWORDS)


def get_crisis_response() -> str:
    """Return the crisis response template with emergency resources."""
    return CRISIS_RESPONSE


# ---------------------------------------------------------------------------
# Post-LLM response validation (runs AFTER LLM response)
# ---------------------------------------------------------------------------

PROHIBITED_PATTERNS: list[str] = [
    # Specific drug dosage recommendations
    r"\b(take|prescribe|recommend)\b.*\b\d+\s*(mg|ml|mcg|units)\b",
    # "You don't need a doctor"
    (
        r"\b(don't|do not|no)\s+(need to|have to)\s+(see|visit|consult)"
        r"\s+(a\s+)?(doctor|physician|medical)\b"
    ),
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

    logger.warning("Chat response violated safety rules: %s", violations)

    return text + (
        "\n\n---\n"
        "**Important:** For the specific concerns raised above, please consult "
        "a healthcare professional directly. I can provide general health information, "
        "but specific treatment decisions should be made with your doctor."
    )
