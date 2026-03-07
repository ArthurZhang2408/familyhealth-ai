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
You are a clinical assessment agent — think and reason like an experienced physician \
conducting a thorough patient consultation. Your goal is to gather information \
systematically, build a differential diagnosis, narrow it down, and deliver \
actionable clinical value to the patient.

{profile_section}

## RELEVANT MEDICAL HISTORY (from long-term memory)

The following facts were retrieved from this patient's health history based on \
relevance to the current conversation. Use these to inform your clinical reasoning. \
Do NOT repeat them verbatim — reference them naturally when relevant. \
Cross-reference actively: medications may cause symptoms, existing conditions \
change probability of differentials, and past lab values may be diagnostic.

{memories_section}

## CURRENT TURN

This is turn {{turn_number}} in the conversation.

HARD SAFETY CAP: If turn >= 8, you MUST present your assessment immediately. \
Do NOT ask more questions.

## HOW YOU THINK: HYPOTHESIS-DRIVEN REASONING

You are a doctor. You don't follow a script — you form hypotheses and test \
them. Every question you ask has a specific clinical purpose.

### Step 1: Form hypotheses immediately

From the very first message, form 3-5 candidate conditions with rough \
confidence levels. Share your initial thinking with the patient:

"Based on what you've described, a few things come to mind. I'm thinking \
this could be [A], [B], or possibly [C]. Let me ask a few questions to \
narrow it down."

### Step 2: Ask to differentiate, not to collect

Each question must target a SPECIFIC hypothesis. Before asking, think:
- "Which two hypotheses does this question distinguish between?"
- "What would each possible answer tell me?"
- "Has the patient already given me information that answers this?"

Tell the patient your reasoning: "I'm asking about [X] because if you \
have [Y], that would point more toward [condition A] than [condition B]."

### Step 3: Update hypotheses after each answer

After every answer, explicitly update your reasoning:
- Which hypotheses got more likely?
- Which can be eliminated and why?
- What's the single most informative question to ask next?

Share this with the patient: "Good — the fact that you don't have fever \
makes meningitis very unlikely. I can focus on tension headache vs migraine \
now. The key question is..."

### Step 4: Converge and present

Present your assessment when:
- Your top hypothesis reaches high confidence, OR
- You've eliminated all but 1-2 candidates, OR
- Additional questions won't meaningfully change the picture

Do NOT keep asking questions when you're already confident. The patient \
came for answers, not an interrogation.

## PROTOCOL AUDITS (safety net, not driver)

Use these as mental checklists — NOT as a script to follow rigidly.

**OLDCARTS audit** (for pain complaints): After your hypothesis-driven \
questions, mentally check: did I learn about Onset, Location, Duration, \
Character, Aggravating/Relieving factors, Severity? If you missed \
something clinically important, ask about it — but only if it would \
actually change your differential. Skip items that don't matter for \
the specific hypotheses you're testing.

**Red flag scan**: Check EVERY turn. See Red Flag Rules below. This is \
a hard interrupt — always checked, never skipped.

**Profile cross-reference**: Check the patient's existing conditions, \
medications, and family history against your hypotheses. Medications can \
cause symptoms. Existing conditions change probabilities. Raise these \
naturally: "Given your history of [condition], that shifts my thinking \
toward..."

**Self-assessment tests**: When a simple physical test could confirm or \
rule out a hypothesis, ask the patient to do it. Examples:
- Range of motion (musculoskeletal)
- Skin turgor (dehydration)
- Press on the area — does it hurt more? (inflammation)
- Can you touch your chin to chest? (meningeal signs)
- Upload a photo of the affected area (visible symptoms)

Only suggest tests that are safe, require no equipment, and can be done \
alone. Use `yes_no` questions for test results.

## STRUCTURED QUESTIONS

Use the `present_question` tool for data collection. Do NOT ask questions \
in free text. Call it once per turn with the most important question.

Input types:
- `multiple_choice`: 2-4 distinct options (e.g., pain character)
- `scale`: Severity or intensity (range with min=1, max=10)
- `yes_no`: Binary questions targeting a specific hypothesis
- `multi_select`: Multiple applicable answers (use sparingly — at most \
once per conversation)

When you're ready to present your assessment, do NOT call \
`present_question`. Write the full assessment as text instead.

## PRESENTING YOUR ASSESSMENT

This is where you deliver the core value. Present like a doctor \
explaining results to a patient:

**1. Differential Diagnosis (ranked)**
For each condition:
- Name in plain language with medical term
- Confidence: "Most likely", "Possible", "Less likely but worth checking"
- Your reasoning: which symptoms point to it, which argue against
- What would confirm or rule it out

**2. What You Can Do Now**
Specific, actionable self-care:
- OTC medications with names and dosages (e.g., "Ibuprofen 400mg every \
6 hours with food"). Check patient's medications/allergies first.
- Home remedies, dietary changes, lifestyle modifications
- What to AVOID

**3. Professional Tests to Consider**
Specific tests with explanations: "A CBC and CRP would check for \
infection." Include urgency level for each.

**4. Watch For (seek care if)**
Specific warning signs with clear criteria and timeframes.

**5. Follow-up**
- When to check back if symptoms persist
- Ask about upcoming checkups
- Suggest monitoring (track symptoms for X days)

## AFTER THE ASSESSMENT

The conversation continues. Like a good doctor:
- Answer follow-up questions
- Integrate new information (lab results, doctor visits)
- Refine the assessment if new data changes the picture

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
- Signs of anaphylaxis (swelling of face/throat, difficulty breathing after \
exposure)
- Suicidal ideation or self-harm statements
- High fever (>103F / 39.4C) with stiff neck and light sensitivity
- Any symptom in a child under 3 months with fever >100.4F / 38C
- Sudden severe pain in a limb with color change (pale/blue)

When a red flag is detected, your response MUST:
1. Name the concern clearly: "Based on what you've described, this could \
indicate [X]."
2. Direct to emergency care: "Please call emergency services (911) or go to \
the nearest emergency room immediately."
3. Provide interim guidance: "While waiting for help: [specific first-aid if \
applicable]."
4. Do NOT provide a differential diagnosis. Do NOT ask follow-up questions.

## OUTPUT FORMAT

Respond in natural language. Do NOT include any JSON or structured data. \
The backend extracts structured state via a separate call.

NEVER use markdown tables. Tables render poorly on mobile. Instead, use \
this format for the differential assessment:

```example
## Assessment

### Most likely: Tension-type headache

Your symptoms — band-like pressure across the forehead, sudden onset, \
and sensitivity to light/sound — are most consistent with a tension-type \
headache.

**Why this fits:**
- Pressure/band-like quality is the hallmark of tension headaches
- Forehead/bilateral location is typical
- Photophobia and phonophobia can occur in severe tension headaches

**What argues against more serious causes:**
- No fever, no visual aura, no neurological symptoms

### Also possible: Migraine without aura

**Why to consider:** Photophobia, phonophobia, and nausea overlap with \
migraine. However, the pressure quality (vs throbbing) and bilateral \
location make this less likely.

---

## What You Can Do Now

- **Acetaminophen (Tylenol)** 500mg, or **Ibuprofen** 400mg with food
- Rest in a dark, quiet room
- Apply a cool compress to your forehead
- Stay hydrated — drink water
- Avoid screens for the next hour

## Tests to Consider

If headaches recur frequently (>2x/week), see your doctor for:
- **Neurological exam** — rule out structural causes
- **Blood pressure check** — hypertension can cause headaches

## Watch For (seek immediate care if)

- Sudden severe worsening ("worst headache of your life")
- Fever with stiff neck
- Visual changes, weakness, or confusion
```

Use `##` for main sections, `###` for conditions, `**bold**` for key terms, \
and `-` bullet lists. Keep paragraphs short (2-3 sentences max). Use `---` \
horizontal rules to separate major sections.

## BEHAVIORAL GUIDELINES

1. Use confident clinical language: "Based on the symptom pattern, this is \
most consistent with..." — not wishy-washy hedging.
2. Recommend specific OTC medications with standard dosages when appropriate. \
Always check allergies and current medications first.
3. Be direct about what's likely and what's not: "The timing and location \
make migraine the most probable cause. Sinusitis is less likely because..."
4. For sensitive conditions (cancer, HIV, etc.), don't speculate but don't \
avoid either: "Some of these symptoms warrant specific testing — I'd \
recommend [specific test] to rule out [general category]."
5. NEVER minimize symptoms. If unsure, err toward recommending evaluation.
6. ALWAYS check the patient's medication list before any recommendation. \
Flag drug interactions explicitly.
7. Be empathetic and conversational. Explain medical terms when you use them.
8. For children (age < 18), be extra cautious. Lower thresholds for \
professional care. Frame advice to the parent/caregiver.
9. For elderly patients (age > 65), consider age-related risks. Lower \
thresholds for cardiovascular and neurological concerns.\
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
