"""Centralized branding constants.

Every user-facing string and app identifier lives here so a rebrand
only touches this file (+ environment/infra config for DB names, etc.).
"""

APP_NAME = "Salk"
APP_DESCRIPTION = "Salk — family health management platform API"
APP_VERSION = "0.1.0"

# ── Disclaimers ──────────────────────────────────────────────────────
# These are sent to the client and rendered in the UI.
# They intentionally do NOT reference the app name — they're generic
# medical disclaimers that work regardless of branding.

MEDICAL_DISCLAIMER = (
    "This is AI-generated health information, not a medical diagnosis. "
    "Always consult a qualified healthcare professional for medical advice, "
    "diagnosis, or treatment. If you are experiencing a medical emergency, "
    "call your local emergency number immediately."
)

REPORT_DISCLAIMER = (
    "This analysis is for informational purposes only. It is NOT a substitute "
    "for professional medical interpretation. Please consult your healthcare "
    "provider for medical decisions."
)

# ── Log identifiers ──────────────────────────────────────────────────
LOG_FILE = "salk.log"
LOG_STARTUP_MSG = f"{APP_NAME} backend starting up (env=%s)"
LOG_SHUTDOWN_MSG = f"{APP_NAME} backend shut down"
