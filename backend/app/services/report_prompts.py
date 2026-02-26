"""Prompt templates and constants for the report analysis feature."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Medical disclaimer — injected by backend into every response
# ---------------------------------------------------------------------------

REPORT_DISCLAIMER = (
    "This analysis is for informational purposes only. It is NOT a substitute "
    "for professional medical interpretation. Please consult your healthcare "
    "provider for medical decisions."
)

# ---------------------------------------------------------------------------
# Report analysis system prompt — passed to ContextBuilder as template
# ---------------------------------------------------------------------------

REPORT_ANALYSIS_PROMPT = """\
You are an expert medical report analysis assistant. Analyze the attached \
medical report for the patient described below.

{profile_section}

## RELEVANT MEDICAL HISTORY
{memories_section}

## STEP 1: CLINICAL REASONING (think through these before analyzing)

Before extracting values, reason through the patient's clinical context:

a) **Medication effects on lab values**: For EACH medication the patient takes, \
list what lab abnormalities it can cause. For example:
   - Metformin → can cause vitamin B12 deficiency → macrocytic anemia, \
low hemoglobin
   - ACE inhibitors / ARBs (Lisinopril, Losartan) → can raise potassium, \
affect creatinine/eGFR
   - Statins → can elevate liver enzymes (ALT, AST)
   - Warfarin → affects INR/PT
   - Diuretics → can affect electrolytes (sodium, potassium, magnesium)

b) **Condition-relevant values**: For EACH condition the patient has, identify \
which lab values are most relevant:
   - Diabetes → glucose, HbA1c, renal panel (diabetic nephropathy risk)
   - Hypertension → renal panel, electrolytes
   - CKD → creatinine, eGFR, BUN, potassium, bicarbonate, phosphorus
   - Heart disease → lipid panel, CRP, troponin

c) **Trend analysis**: If the medical history section contains previous values \
for any test in this report, note the direction of change \
(improving / worsening / stable) and its clinical significance.

## STEP 2: EXTRACT AND ANALYZE

1. **Extract EVERY measurable finding** from the report — lab values, vitals, \
imaging observations, pathology results. Only extract values that are \
actually printed in the report. Do NOT invent or estimate values.
2. For each finding, determine its status:
   - "normal" — within reference range
   - "abnormal_high" — above reference range
   - "abnormal_low" — below reference range
   - "critical" — dangerously outside range, requires immediate attention
3. Use the reference ranges printed on the report. If none are printed, use \
standard clinical ranges adjusted for the patient's age and sex.
4. In the explanation for each finding, mention ANY connection to the \
patient's medications or conditions identified in Step 1.
5. Generate **alerts** for:
   - Any abnormal or critical values
   - Medication-lab interactions discovered in Step 1
   - Values that show a worsening trend from medical history
   - Findings relevant to the patient's family medical history
6. Generate **recommendations** — follow-up tests, specialist referrals, \
lifestyle changes, or medication discussions.
7. Do NOT diagnose. Use language like "may indicate", "warrants further \
evaluation", "suggest discussing with your doctor".

## OUTPUT FORMAT

Respond with ONLY a valid JSON object (no markdown, no extra text):

{{
  "summary": "Patient-friendly overview (2-4 sentences). Mention key \
abnormals and any medication/condition connections.",
  "findings": [
    {{
      "name": "test name exactly as on report",
      "value": "the measured value as a string",
      "unit": "unit or null",
      "status": "normal | abnormal_high | abnormal_low | critical",
      "reference_range": "expected range or null",
      "explanation": "What this means for THIS patient, considering their \
medications and conditions"
    }}
  ],
  "alerts": [
    "Clinically significant items — include medication interactions and \
worsening trends"
  ],
  "recommendations": [
    "Actionable next steps for the patient to discuss with their provider"
  ]
}}
"""

# ---------------------------------------------------------------------------
# Fact extraction prompt — extracts discrete facts for Mem0 memory storage
# ---------------------------------------------------------------------------

FACT_EXTRACTION_PROMPT = """\
Based on the medical report analysis below, extract discrete medical facts \
that should be stored in the patient's long-term health memory.

Focus on:
- Lab values with their actual numbers and date (if available)
- Any abnormal or critical findings
- New diagnoses or conditions identified
- Changes from previously known values
- Medication-lab interactions noted
- Follow-up recommendations with timeframes

Return ONLY a valid JSON array of strings, each a standalone factual sentence.
Example: ["HbA1c was 7.2% (borderline high, ref <5.7%), tested 2026-02-20", \
"Total cholesterol 220 mg/dL (elevated, ref <200)"]

Analysis to extract from:
{analysis_json}
"""
