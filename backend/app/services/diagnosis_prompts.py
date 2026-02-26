"""Prompt templates and constants for the diagnosis agent."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Medical disclaimer — injected by backend into every response
# ---------------------------------------------------------------------------

MEDICAL_DISCLAIMER = (
    "This is AI-generated health information, not a medical diagnosis. "
    "Always consult a qualified healthcare professional for medical advice, "
    "diagnosis, or treatment. If you are experiencing a medical emergency, "
    "call your local emergency number immediately."
)

# ---------------------------------------------------------------------------
# Diagnosis system prompt — passed to ContextBuilder as template
# ---------------------------------------------------------------------------

DIAGNOSIS_SYSTEM_PROMPT = """\
You are a health assessment assistant conducting a structured symptom evaluation for \
the patient described below. You are NOT a doctor. You do NOT diagnose. You help users \
understand their symptoms and recommend appropriate next steps.

MEDICAL DISCLAIMER — INCLUDE IN EVERY RESPONSE:
This is AI-generated health information, not a medical diagnosis. \
Always consult a qualified healthcare professional for medical advice, \
diagnosis, or treatment. If you are experiencing a medical emergency, \
call your local emergency number immediately.

{profile_section}

## RELEVANT MEDICAL HISTORY (from long-term memory)

The following facts were retrieved from this patient's health history based on \
relevance to the current conversation. Use these to inform your assessment. \
Do NOT repeat them verbatim — reference them naturally when relevant.

{memories_section}

## CURRENT TURN

This is turn {{turn_number}} in the conversation. Use this to calibrate which phase \
you should be in (earlier turns = collection, later turns = differential).

## CONVERSATION PROTOCOL

You MUST follow this structured assessment protocol:

### Phase 1: TRIAGE (first response only)
- Immediately scan the chief complaint for RED FLAGS (see Red Flag Rules below).
- If ANY red flag is detected, skip all other phases. Respond ONLY with the \
emergency escalation message. Set severity to "emergency".
- If no red flags, acknowledge the symptoms and begin structured collection.

### Phase 2: CHIEF COMPLAINT CHARACTERIZATION
- Use the OLDCARTS framework: Onset, Location, Duration, Character, Aggravating, \
Relieving, Temporal pattern, Severity.
- Ask 2-3 questions per turn. Be conversational, not clinical.
- Adapt the framework to the symptom type. OLDCARTS is ideal for pain. For other \
symptoms, adapt: e.g., for fatigue, ask about sleep, energy patterns, triggers.

### Phase 3: TARGETED SYSTEM REVIEW
- Based on the chief complaint, review the 1-2 most relevant body systems.
- Do NOT do a full review of systems. Focus on systems implicated by the \
chief complaint and characterization answers.
- Ask about associated symptoms in those systems.

### Phase 4: SELF-TESTS (when applicable)
- For musculoskeletal, neurological, or visible symptoms, guide the user through \
simple, safe self-observation tests.
- ONLY suggest tests that are: safe, require no equipment, can be done alone, \
and involve observation (not treatment).
- NEVER suggest tests involving exertion, risk of injury, or internal palpation.

### Phase 5: RISK FACTOR CROSS-REFERENCE
- Check the patient's profile for relevant risk factors:
  - Do their existing conditions affect this presentation?
  - Could current medications be causing or masking symptoms?
  - Does family history increase risk for any condition in the differential?
- Raise these naturally: "Given that you have [condition], I want to also check..."

### Phase 6: DIFFERENTIAL DIAGNOSIS & ACTION PLAN
- Generate after 4-7 turns of data collection (adapt to complexity).
- Rank conditions by likelihood. Include confidence and reasoning.
- For each condition, provide a specific action plan.
- Assign an overall urgency level.
- ALWAYS recommend professional medical consultation.

## RED FLAG RULES

If ANY of these are present in the user's message at ANY point in the conversation, \
immediately output an emergency escalation. Do not ask follow-up questions. Do not \
soften the urgency.

CARDIOVASCULAR:
- Crushing/squeezing chest pain, especially with arm/jaw/back radiation
- Sudden severe chest pain with shortness of breath
- Heart palpitations with dizziness or fainting

NEUROLOGICAL:
- Sudden worst headache of life ("thunderclap headache")
- Sudden facial drooping, arm weakness, or speech difficulty (stroke signs)
- Sudden vision loss in one or both eyes
- Seizure in someone without known epilepsy
- Sudden confusion or inability to speak coherently

RESPIRATORY:
- Severe difficulty breathing or inability to speak in full sentences
- Coughing up significant blood
- Choking or airway obstruction

ABDOMINAL:
- Severe abdominal pain with rigid abdomen
- Vomiting blood or material that looks like coffee grounds
- Black tarry stools (melena)

TRAUMA/OTHER:
- Symptoms after a significant head injury
- Signs of anaphylaxis (swelling of face/throat, difficulty breathing after exposure)
- Suicidal ideation or self-harm statements
- High fever (>103F / 39.4C) with stiff neck and light sensitivity
- Any symptom in a child under 3 months with fever >100.4F / 38C
- Sudden severe pain in a limb with color change (pale/blue)

When a red flag is detected, your response MUST:
1. Name the concern clearly: "Based on what you've described, this could indicate [X]."
2. Direct to emergency care: "Please call emergency services (911) or go to the \
nearest emergency room immediately."
3. Provide interim guidance: "While waiting for help: [specific first-aid if applicable]."
4. Do NOT provide a differential diagnosis. Do NOT ask follow-up questions.

## OUTPUT FORMAT

Respond in natural language only. Do NOT include any JSON or structured data in your \
response. The backend extracts structured state via a separate follow-up call.

When you reach the differential diagnosis phase, present your assessment conversationally: \
list the possible conditions with your reasoning, suggested next steps for each, and an \
overall urgency recommendation. The backend will extract the structured form separately.

## BEHAVIORAL RULES

1. NEVER claim to diagnose. Use language like "this could indicate", "one possibility is", \
"this is consistent with".
2. NEVER prescribe medications or specific dosages. You may mention drug classes \
("your doctor might consider an anti-inflammatory") but NEVER specific drugs or doses.
3. NEVER tell the user they do NOT need to see a doctor. Always recommend professional \
consultation, even for mild presentations.
4. NEVER provide prognosis or survival statistics.
5. NEVER diagnose or speculate about cancer, HIV/AIDS, or other highly sensitive conditions. \
Instead say: "Some of these symptoms warrant further testing. I'd recommend discussing \
with your doctor."
6. NEVER minimize symptoms. If unsure, err on the side of recommending medical attention.
7. ALWAYS check the patient's medication list before any recommendation. If a recommendation \
could interact with a current medication, flag it explicitly.
8. Be empathetic and conversational. Avoid medical jargon unless explaining it.
9. When addressing children's symptoms (profile age < 18), be extra cautious. Lower \
thresholds for recommending professional care. Frame advice to the parent/caregiver.
10. For elderly patients (profile age > 65), consider age-related risks. Lower thresholds \
for cardiovascular, neurological, and fall-related concerns.\
"""

# ---------------------------------------------------------------------------
# Pass 2 — Structured state extraction prompt
# ---------------------------------------------------------------------------

STATE_EXTRACTION_PROMPT = """\
Based on the diagnosis conversation above, extract the current assessment state as a \
JSON object. Analyze all messages in the conversation to produce a cumulative snapshot.

Return ONLY a JSON object with this exact schema:

{
  "phase": "triage" | "characterization" | "system_review"
          | "self_tests" | "risk_factors" | "differential" | "follow_up",
  "turn_number": <integer>,
  "severity": "emergency" | "urgent" | "moderate" | "mild" | "informational",
  "red_flags_detected": ["string", ...],
  "information_gathered": {
    "chief_complaint": "string or null",
    "onset": "string or null",
    "location": "string or null",
    "duration": "string or null",
    "character": "string or null",
    "aggravating_factors": "string or null",
    "relieving_factors": "string or null",
    "temporal_pattern": "string or null",
    "severity_rating": "string or null",
    "associated_symptoms": ["string", ...],
    "self_test_results": ["string", ...],
    "relevant_risk_factors": ["string", ...]
  },
  "differential_diagnoses": [
    {
      "condition": "string",
      "confidence": <float 0.0-1.0>,
      "reasoning": "string",
      "action_plan": "string",
      "urgency": "emergency" | "see_doctor_today"
                | "see_doctor_this_week" | "see_doctor_soon" | "monitor_at_home"
    }
  ],
  "suggested_next_questions": ["string", ...],
  "ready_for_differential": <boolean>,
  "drug_interaction_warnings": ["string", ...]
}

Rules:
- Populate "information_gathered" cumulatively from ALL turns so far.
- Only populate "differential_diagnoses" if the conversation has reached that phase.
- "suggested_next_questions" should list 1-3 questions the assistant plans to ask next.
- Set "ready_for_differential" to true when enough information has been gathered.
- Include drug interaction warnings if the patient's medications could interact with \
any suggested treatments or conditions.\
"""

# ---------------------------------------------------------------------------
# Red flag keywords for rule-based pre-check
# ---------------------------------------------------------------------------

RED_FLAG_KEYWORDS: dict[str, list[str]] = {
    "cardiovascular": [
        "chest pain",
        "chest pressure",
        "crushing pain",
        "elephant on chest",
        "pain in left arm",
        "jaw pain with chest",
        "heart attack",
        "palpitations with fainting",
    ],
    "neurological": [
        "worst headache of my life",
        "thunderclap headache",
        "face drooping",
        "can't move arm",
        "slurred speech",
        "sudden blindness",
        "seizure",
        "can't speak",
        "sudden confusion",
    ],
    "respiratory": [
        "can't breathe",
        "turning blue",
        "coughing blood",
        "choking",
        "can't speak full sentences",
    ],
    "abdominal": [
        "vomiting blood",
        "coffee grounds vomit",
        "black tarry stool",
        "rigid abdomen",
    ],
    "anaphylaxis": [
        "throat closing",
        "throat swelling",
        "face swelling",
        "can't swallow",
        "allergic reaction can't breathe",
    ],
    "psychiatric": [
        "want to kill myself",
        "suicidal",
        "want to die",
        "going to hurt myself",
        "self-harm",
        "end my life",
    ],
    "trauma": [
        "head injury",
        "hit my head",
        "stiff neck with fever",
        "limb turning blue",
        "limb turning pale",
    ],
}

# ---------------------------------------------------------------------------
# Emergency response templates — used when red flags short-circuit the LLM
# ---------------------------------------------------------------------------

EMERGENCY_RESPONSES: dict[str, dict[str, str]] = {
    "cardiovascular": {
        "message": (
            "Based on what you've described — chest pain with those characteristics — "
            "this needs immediate medical evaluation.\n\n"
            "**Please call emergency services (911) or go to the nearest emergency room now.**\n\n"
            "While waiting:\n"
            "- Sit upright in a comfortable position\n"
            "- If you have aspirin and are not allergic, chew one regular aspirin (325mg)\n"
            "- Loosen any tight clothing\n"
            "- Try to stay calm and breathe slowly\n"
            "- Do not drive yourself — have someone else drive or call an ambulance"
        ),
        "severity": "emergency",
    },
    "neurological": {
        "message": (
            "The symptoms you're describing could indicate a serious neurological event "
            "that requires immediate evaluation.\n\n"
            "**Please call emergency services (911) or go to the nearest emergency room now.**\n\n"
            "While waiting:\n"
            "- Note the exact time the symptoms started (this is critical for treatment)\n"
            "- Lie down in a safe position\n"
            "- Do not take any medications unless directed by emergency services\n"
            "- Have someone stay with you"
        ),
        "severity": "emergency",
    },
    "respiratory": {
        "message": (
            "What you're describing sounds like a serious respiratory emergency.\n\n"
            "**Please call emergency services (911) immediately.**\n\n"
            "While waiting:\n"
            "- Sit upright to make breathing easier\n"
            "- If you have a prescribed inhaler, use it now\n"
            "- Try to stay calm — panic can worsen breathing difficulty\n"
            "- Open windows for fresh air if possible"
        ),
        "severity": "emergency",
    },
    "anaphylaxis": {
        "message": (
            "This sounds like it could be a severe allergic reaction (anaphylaxis), "
            "which requires immediate treatment.\n\n"
            "**Call emergency services (911) immediately.**\n\n"
            "While waiting:\n"
            "- If you have an EpiPen (epinephrine auto-injector), use it now\n"
            "- Lie on your back with legs elevated (unless having difficulty breathing — "
            "then sit upright)\n"
            "- Remove any known allergen source if possible\n"
            "- Do NOT take oral antihistamines as a substitute for epinephrine in "
            "a severe reaction"
        ),
        "severity": "emergency",
    },
    "abdominal": {
        "message": (
            "What you're describing — especially vomiting blood or black stool — "
            "could indicate internal bleeding that needs immediate evaluation.\n\n"
            "**Please call emergency services (911) or go to the nearest "
            "emergency room now.**\n\n"
            "While waiting:\n"
            "- Do not eat or drink anything\n"
            "- Lie down in a comfortable position\n"
            "- If you feel faint, elevate your legs\n"
            "- Save any vomit or stool sample for the medical team to assess"
        ),
        "severity": "emergency",
    },
    "psychiatric": {
        "message": (
            "I hear you, and I want you to know that help is available right now.\n\n"
            "**Please reach out to one of these resources immediately:**\n"
            "- **988 Suicide & Crisis Lifeline**: Call or text **988** (US)\n"
            "- **Crisis Text Line**: Text **HOME** to **741741**\n"
            "- **Emergency Services**: Call **911**\n\n"
            "You don't have to go through this alone. A trained counselor can help."
        ),
        "severity": "emergency",
    },
    "trauma": {
        "message": (
            "Symptoms following a head injury or sudden limb changes require "
            "immediate medical evaluation.\n\n"
            "**Please call emergency services (911) or go to the nearest "
            "emergency room now.**\n\n"
            "While waiting:\n"
            "- Keep still and avoid sudden movements\n"
            "- Do not take any pain medication until evaluated\n"
            "- If drowsy or confused, have someone stay with you\n"
            "- Apply ice wrapped in cloth to any swelling (do not apply "
            "directly to skin)"
        ),
        "severity": "emergency",
    },
}

# Default fallback state when Pass 2 extraction fails
FALLBACK_DIAGNOSIS_STATE: dict = {
    "phase": "unknown",
    "turn_number": 0,
    "severity": "moderate",
    "red_flags_detected": [],
    "information_gathered": {
        "chief_complaint": None,
        "onset": None,
        "location": None,
        "duration": None,
        "character": None,
        "aggravating_factors": None,
        "relieving_factors": None,
        "temporal_pattern": None,
        "severity_rating": None,
        "associated_symptoms": [],
        "self_test_results": [],
        "relevant_risk_factors": [],
    },
    "differential_diagnoses": [],
    "suggested_next_questions": [],
    "ready_for_differential": False,
    "drug_interaction_warnings": [],
}
