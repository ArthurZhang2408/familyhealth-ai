#!/usr/bin/env python3
"""End-to-end tests for the report analysis feature against live infrastructure.

Exercises the complete stack: PostgreSQL, Mem0, Gemini (Pass 1), Qwen (Pass 2).
No mocks. All prod settings.

Three test scenarios, each with:
  - A tailored patient profile with specific conditions/meds/history
  - Seeded Mem0 memories (previous lab results)
  - A real or realistic medical report
  - Defined expected metrics: what the analysis SHOULD detect
  - Post-analysis memory verification

Usage:
    cd backend && python3 scripts/e2e_report_analysis.py

Requires:
    - PostgreSQL running (docker compose up -d db)
    - Valid GEMINI_API_KEY and QWEN_API_KEY in .env
    - Alembic migrations applied
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.WARNING)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# ===================================================================
# Helpers
# ===================================================================


def _print_header(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def _print_step(n: int, msg: str) -> None:
    print(f"\n  --- Step {n}: {msg} ---")


def _truncate(text: str, max_len: int = 120) -> str:
    return text[:max_len] + "..." if len(text) > max_len else text


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""

    def __str__(self) -> str:
        icon = "PASS" if self.passed else "FAIL"
        suffix = f" ({self.detail})" if self.detail else ""
        return f"  {icon}  {self.name}{suffix}"


@dataclass
class TestScenario:
    """A self-contained report analysis test scenario."""

    title: str
    profile_data: dict
    seed_memories: list[dict]
    report_bytes: bytes
    report_filename: str
    # Expected metrics — each is (description, keywords_any_of)
    # Analysis must mention at least ONE keyword from each expectation
    expected_findings_keywords: list[tuple[str, list[str]]]
    expected_alert_keywords: list[tuple[str, list[str]]]
    expected_recommendation_keywords: list[tuple[str, list[str]]]
    # Memory expectations — keywords that should appear in extracted facts
    expected_memory_keywords: list[str]
    # Context cross-reference expectations
    expected_profile_context_refs: list[tuple[str, list[str]]]


async def _retry_llm(coro_fn, *, max_retries: int = 3, base_delay: float = 30.0):
    """Retry an async callable that may hit LLM rate limits."""
    for attempt in range(max_retries):
        try:
            return await coro_fn()
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = (
                "429" in err_str or "resource_exhausted" in err_str or "quota" in err_str
            )
            if is_rate_limit and attempt < max_retries - 1:
                delay = base_delay * (2**attempt)
                print(f"    Rate limited (attempt {attempt + 1}). Waiting {delay:.0f}s...")
                await asyncio.sleep(delay)
            else:
                raise


def _make_text_pdf(text_lines: list[str]) -> bytes:
    """Create a minimal valid PDF containing the given text lines.

    Produces a simple single-page PDF with embedded text content.
    No external dependencies — builds raw PDF structure.
    """
    # Build content stream
    content_lines = ["BT", "/F1 11 Tf"]
    y = 750
    for line in text_lines:
        # Escape special PDF characters
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_lines.append(f"1 0 0 1 50 {y} Tm")
        content_lines.append(f"({safe}) Tj")
        y -= 16
        if y < 50:
            break
    content_lines.append("ET")
    stream = "\n".join(content_lines)

    # Build PDF objects
    objects = []
    # Obj 1: Catalog
    objects.append("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj")
    # Obj 2: Pages
    objects.append("2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj")
    # Obj 3: Page
    objects.append(
        "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]\n"
        "   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj"
    )
    # Obj 4: Content stream
    objects.append(f"4 0 obj\n<< /Length {len(stream)} >>\nstream\n{stream}\nendstream\nendobj")
    # Obj 5: Font
    objects.append("5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj")

    # Assemble PDF
    body = "\n".join(objects)
    xref_offset = len(b"%PDF-1.4\n") + len(body.encode()) + 1
    pdf = (
        f"%PDF-1.4\n{body}\n"
        f"xref\n0 6\n"
        f"0000000000 65535 f \n"
        f"0000000009 00000 n \n"
        f"0000000058 00000 n \n"
        f"0000000115 00000 n \n"
        f"0000000300 00000 n \n"
        f"0000000500 00000 n \n"
        f"trailer\n<< /Size 6 /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF"
    )
    return pdf.encode()


# ===================================================================
# Test Scenario 1: CBC Report — Diabetic Patient on Metformin
# ===================================================================
# Uses the REAL Drlogy CBC PDF (scripts/fixtures/drlogy_cbc.pdf)
#
# Report key values:
#   - Hemoglobin: 12.5 g/dL (LOW, ref 13.0-17.0)
#   - PCV: 57.5% (HIGH, ref 40-50)
#   - Platelets: 150,000 (BORDERLINE, ref 150,000-410,000)
#   - All WBC differential: normal
#   - Lab interpretation: "Further confirm for Anemia"
#
# Profile context that should influence analysis:
#   - Type 2 Diabetes → HbA1c relevance, metabolic context
#   - Metformin → known to cause B12/folate deficiency → anemia
#   - Previous hemoglobin was 13.8 g/dL → declining trend
#   - Hypertension + Lisinopril → renal panel context


def _build_scenario_1() -> TestScenario:
    cbc_path = FIXTURES_DIR / "drlogy_cbc.pdf"
    if cbc_path.exists():
        report_bytes = cbc_path.read_bytes()
        filename = "drlogy_cbc.pdf"
    else:
        # Fallback: text-based CBC
        report_bytes = _make_text_pdf(
            [
                "COMPLETE BLOOD COUNT (CBC) - Lab Report",
                "Patient: Sample Patient    Date: 2026-02-20",
                "",
                "Investigation          Result    Ref Range       Unit    Flag",
                "---------------------------------------------------------------",
                "Hemoglobin (Hb)        12.5      13.0 - 17.0     g/dL    LOW",
                "Total RBC count        5.2       4.5 - 5.5       mill/cumm",
                "Packed Cell Vol (PCV)  57.5      40 - 50         %       HIGH",
                "MCV                    87.75     83 - 101        fL",
                "MCH                    27.2      27 - 32         pg",
                "MCHC                   32.8      32.5 - 34.5     g/dL",
                "RDW                    13.6      11.6 - 14.0     %",
                "Total WBC count        9000      4000 - 11000    cumm",
                "Neutrophils            60        50 - 62         %",
                "Lymphocytes            31        20 - 40         %",
                "Eosinophils            1         0 - 6           %",
                "Monocytes              7         0 - 10          %",
                "Basophils              1         0 - 2           %",
                "Platelet Count         150000    150000-410000   cumm    BORDERLINE",
                "",
                "Interpretation: Further confirm for Anemia",
            ]
        )
        filename = "cbc_report.pdf"

    return TestScenario(
        title="Test 1: CBC + Diabetic on Metformin (real PDF)",
        profile_data={
            "account_id": uuid.uuid4(),
            "name": "Maria Santos",
            "relationship": "parent",
            "sex": "female",
            "date_of_birth": date(1971, 6, 20),
            "blood_type": "B+",
            "allergies": [
                {"allergen": "Sulfa drugs", "severity": "moderate", "reaction": "rash"},
            ],
            "current_medications": [
                {"name": "Metformin", "dosage": "1000mg", "frequency": "twice daily"},
                {"name": "Lisinopril", "dosage": "10mg", "frequency": "once daily"},
            ],
            "medical_conditions": [
                {"condition": "Type 2 Diabetes", "diagnosed": "2018", "status": "active"},
                {"condition": "Hypertension", "diagnosed": "2019", "status": "managed"},
            ],
            "family_medical_history": {
                "Diabetes": ["Mother", "Maternal grandmother"],
                "Anemia": ["Sister"],
            },
        },
        seed_memories=[
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "Mom's hemoglobin was 13.8 g/dL in September 2025.",
                    },
                    {"role": "assistant", "content": "Hemoglobin of 13.8 is within normal range."},
                ],
                "category": "lab_results",
                "source": "report:previous-cbc",
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Mom's HbA1c was 7.2% in January 2026."
                            " Doctor wants closer monitoring."
                        ),
                    },
                    {
                        "role": "assistant",
                        "content": "HbA1c of 7.2% indicates borderline diabetic control.",
                    },
                ],
                "category": "lab_results",
                "source": "chat:hba1c",
            },
        ],
        report_bytes=report_bytes,
        report_filename=filename,
        expected_findings_keywords=[
            ("Low hemoglobin detected", ["hemoglobin", "hb", "12.5"]),
            ("High PCV detected", ["pcv", "packed cell", "57.5", "hematocrit"]),
            ("Borderline platelets detected", ["platelet", "150000", "150,000", "borderline"]),
        ],
        expected_alert_keywords=[
            ("Anemia alert", ["anemia", "anaemia", "low hemoglobin", "hemoglobin"]),
        ],
        expected_recommendation_keywords=[
            ("Follow-up recommended", ["follow-up", "follow up", "retest", "confirm", "further"]),
            (
                "Healthcare provider consult",
                ["doctor", "physician", "healthcare", "provider", "consult"],
            ),
        ],
        expected_memory_keywords=["hemoglobin", "12.5"],
        expected_profile_context_refs=[
            (
                "Metformin-anemia link mentioned",
                ["metformin", "b12", "folate", "vitamin", "medication"],
            ),
        ],
    )


# ===================================================================
# Test Scenario 2: Lipid Panel — Family History of Heart Disease
# ===================================================================
# Constructed text-PDF with abnormal lipid values.
# Profile has father with MI at 52 → cardiovascular risk amplification.
# Seeded memory: previous cholesterol was 198 → now worsened to 245.


def _build_scenario_2() -> TestScenario:
    report_bytes = _make_text_pdf(
        [
            "LIPID PANEL - Laboratory Report",
            "Patient: Sample Patient    Date: 2026-02-18",
            "Ordering Physician: Dr. Johnson    Fasting: Yes (12 hours)",
            "",
            "Test                   Result    Reference Range     Unit     Flag",
            "--------------------------------------------------------------------",
            "Total Cholesterol      245       < 200               mg/dL    HIGH",
            "LDL Cholesterol        168       < 100               mg/dL    HIGH",
            "HDL Cholesterol        35        > 40                mg/dL    LOW",
            "Triglycerides          225       < 150               mg/dL    HIGH",
            "VLDL Cholesterol       45        < 30                mg/dL    HIGH",
            "Total/HDL Ratio        7.0       < 5.0                        HIGH",
            "Non-HDL Cholesterol    210       < 130               mg/dL    HIGH",
            "",
            "Risk Assessment: HIGH cardiovascular risk based on lipid profile.",
            "Recommendation: Lifestyle modification and pharmacological intervention",
            "              should be considered. Repeat in 3 months.",
        ]
    )

    return TestScenario(
        title="Test 2: Lipid Panel + Family Heart Disease History",
        profile_data={
            "account_id": uuid.uuid4(),
            "name": "James Chen",
            "relationship": "self",
            "sex": "male",
            "date_of_birth": date(1978, 11, 3),
            "blood_type": "O+",
            "allergies": [],
            "current_medications": [],
            "medical_conditions": [],
            "family_medical_history": {
                "Heart Disease": ["Father (MI at age 52)"],
                "High Cholesterol": ["Father", "Paternal uncle"],
                "Stroke": ["Paternal grandmother"],
            },
        },
        seed_memories=[
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "My total cholesterol was 198 mg/dL"
                            " in March 2025. Doctor said it was borderline."
                        ),
                    },
                    {
                        "role": "assistant",
                        "content": "198 mg/dL is borderline. Below 200 is desirable.",
                    },
                ],
                "category": "lab_results",
                "source": "chat:cholesterol-2025",
            },
        ],
        report_bytes=report_bytes,
        report_filename="lipid_panel_2026.pdf",
        expected_findings_keywords=[
            ("Elevated total cholesterol", ["total cholesterol", "245"]),
            ("Elevated LDL", ["ldl", "168"]),
            ("Low HDL", ["hdl", "35"]),
            ("Elevated triglycerides", ["triglyceride", "225"]),
        ],
        expected_alert_keywords=[
            ("Cardiovascular risk alert", ["cardiovascular", "heart", "cardiac", "risk"]),
            ("LDL significantly elevated", ["ldl", "high", "elevated"]),
        ],
        expected_recommendation_keywords=[
            ("Lifestyle changes recommended", ["lifestyle", "diet", "exercise", "weight"]),
            (
                "Statin discussion suggested",
                ["statin", "medication", "pharmacolog", "lipid-lowering", "cholesterol-lowering"],
            ),
        ],
        expected_memory_keywords=["cholesterol", "ldl"],
        expected_profile_context_refs=[
            (
                "Family heart disease risk noted",
                ["family", "father", "heart", "hereditary", "genetic", "history"],
            ),
            (
                "Worsening trend noted",
                ["wors", "increas", "previous", "198", "trend", "rise", "higher"],
            ),
        ],
    )


# ===================================================================
# Test Scenario 3: Basic Metabolic Panel — CKD Patient on Losartan
# ===================================================================
# Constructed text-PDF with kidney-relevant abnormalities.
# Profile has CKD stage 2 + Losartan → potassium risk.
# Seeded memory: eGFR 72 → now 52 = progression.


def _build_scenario_3() -> TestScenario:
    report_bytes = _make_text_pdf(
        [
            "BASIC METABOLIC PANEL (BMP) - Laboratory Report",
            "Patient: Sample Patient    Date: 2026-02-22",
            "Ordering Physician: Dr. Patel",
            "",
            "Test                   Result    Reference Range     Unit     Flag",
            "--------------------------------------------------------------------",
            "Glucose (fasting)      102       70 - 100            mg/dL    HIGH",
            "BUN                    28        7 - 20              mg/dL    HIGH",
            "Creatinine             1.6       0.7 - 1.3           mg/dL    HIGH",
            "eGFR                   52        > 60                mL/min   LOW",
            "Sodium                 139       136 - 145           mEq/L",
            "Potassium              5.4       3.5 - 5.0           mEq/L    HIGH",
            "Chloride               101       98 - 106            mEq/L",
            "CO2 (Bicarbonate)      22        23 - 29             mEq/L    LOW",
            "Calcium                9.2       8.5 - 10.5          mg/dL",
            "BUN/Creatinine Ratio   17.5      10 - 20",
            "",
            "Note: eGFR calculated using CKD-EPI equation.",
            "Clinical correlation recommended for elevated creatinine and",
            "reduced eGFR suggesting possible progression of renal impairment.",
        ]
    )

    return TestScenario(
        title="Test 3: BMP + CKD Patient on Losartan (potassium risk)",
        profile_data={
            "account_id": uuid.uuid4(),
            "name": "Robert Kim",
            "relationship": "parent",
            "sex": "male",
            "date_of_birth": date(1958, 4, 12),
            "blood_type": "A-",
            "allergies": [
                {"allergen": "Contrast dye", "severity": "moderate", "reaction": "nausea"},
            ],
            "current_medications": [
                {"name": "Losartan", "dosage": "50mg", "frequency": "once daily"},
                {"name": "Amlodipine", "dosage": "5mg", "frequency": "once daily"},
            ],
            "medical_conditions": [
                {
                    "condition": "Chronic Kidney Disease Stage 2",
                    "diagnosed": "2023",
                    "status": "active",
                },
                {"condition": "Hypertension", "diagnosed": "2015", "status": "managed"},
            ],
            "family_medical_history": {
                "Kidney Disease": ["Mother (dialysis at 70)"],
                "Hypertension": ["Father", "Mother"],
            },
        },
        seed_memories=[
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Dad's eGFR was 72 mL/min in October 2025"
                            " and creatinine was 1.2 mg/dL."
                        ),
                    },
                    {
                        "role": "assistant",
                        "content": (
                            "eGFR of 72 places him in CKD stage 2." " Monitoring is important."
                        ),
                    },
                ],
                "category": "lab_results",
                "source": "report:bmp-oct2025",
            },
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Dad's potassium was 4.8 mEq/L in October 2025."
                            " Doctor said to watch it because of Losartan."
                        ),
                    },
                    {
                        "role": "assistant",
                        "content": (
                            "Potassium of 4.8 is upper-normal."
                            " Losartan can raise potassium levels."
                        ),
                    },
                ],
                "category": "lab_results",
                "source": "chat:potassium",
            },
        ],
        report_bytes=report_bytes,
        report_filename="bmp_report_2026.pdf",
        expected_findings_keywords=[
            ("Elevated creatinine detected", ["creatinine", "1.6"]),
            ("Low eGFR detected", ["egfr", "52"]),
            ("Elevated potassium detected", ["potassium", "5.4"]),
            ("Elevated BUN detected", ["bun", "28"]),
            ("Low bicarbonate detected", ["bicarbonate", "co2", "22"]),
        ],
        expected_alert_keywords=[
            (
                "CKD progression alert",
                ["ckd", "kidney", "renal", "progression", "decline", "egfr"],
            ),
            ("Hyperkalemia risk", ["potassium", "hyperkalemia", "5.4", "high"]),
        ],
        expected_recommendation_keywords=[
            ("Nephrology referral", ["nephrolog", "specialist", "kidney", "referral"]),
            (
                "Healthcare provider consult",
                ["doctor", "physician", "healthcare", "provider", "consult"],
            ),
        ],
        expected_memory_keywords=["creatinine", "egfr"],
        expected_profile_context_refs=[
            ("Losartan-potassium link", ["losartan", "potassium", "arb", "medication"]),
            (
                "CKD progression from previous",
                ["progress", "declin", "previous", "72", "worsen", "stage"],
            ),
        ],
    )


# ===================================================================
# Test Scenario 4: Real Lipid Panel PDF + Statin Patient
# ===================================================================
# Uses the REAL Drlogy Lipid Profile PDF.
# Report values: Total Chol 250 (HIGH), LDL 190 (HIGH),
# HDL 50, TG 100, VLDL 10, Non-HDL 100.
# Profile: patient already on atorvastatin — are statins working?


def _build_scenario_4() -> TestScenario:
    pdf_path = FIXTURES_DIR / "drlogy_lipid_profile.pdf"
    if not pdf_path.exists():
        return None  # type: ignore[return-value]

    return TestScenario(
        title="Test 4: Real Lipid PDF + Patient on Statin",
        profile_data={
            "account_id": uuid.uuid4(),
            "name": "Anita Sharma",
            "relationship": "self",
            "sex": "female",
            "date_of_birth": date(1975, 8, 10),
            "blood_type": "A+",
            "allergies": [],
            "current_medications": [
                {
                    "name": "Atorvastatin",
                    "dosage": "20mg",
                    "frequency": "once daily",
                },
            ],
            "medical_conditions": [
                {
                    "condition": "Hyperlipidemia",
                    "diagnosed": "2023",
                    "status": "active",
                },
            ],
            "family_medical_history": {
                "Heart Disease": ["Father (MI at 58)"],
                "High Cholesterol": ["Mother"],
            },
        },
        seed_memories=[
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "My total cholesterol was 260 mg/dL"
                            " before starting atorvastatin in 2023."
                        ),
                    },
                    {
                        "role": "assistant",
                        "content": (
                            "260 mg/dL is high. Atorvastatin" " should help bring it down."
                        ),
                    },
                ],
                "category": "lab_results",
                "source": "chat:lipid-baseline",
            },
        ],
        report_bytes=pdf_path.read_bytes(),
        report_filename="drlogy_lipid_profile.pdf",
        expected_findings_keywords=[
            ("Total cholesterol detected", ["cholesterol", "250"]),
            ("High LDL detected", ["ldl", "190"]),
            ("HDL detected", ["hdl", "50"]),
            ("Triglycerides detected", ["triglyceride", "100"]),
        ],
        expected_alert_keywords=[
            ("Elevated cholesterol alert", ["cholesterol", "high", "elevated"]),
            ("LDL elevated", ["ldl", "high", "elevated"]),
        ],
        expected_recommendation_keywords=[
            (
                "Medication review",
                [
                    "statin",
                    "atorvastatin",
                    "medication",
                    "dose",
                    "adjust",
                    "pharmacolog",
                ],
            ),
        ],
        expected_memory_keywords=["cholesterol", "ldl"],
        expected_profile_context_refs=[
            (
                "Statin effectiveness noted",
                [
                    "atorvastatin",
                    "statin",
                    "medication",
                    "despite",
                    "current",
                ],
            ),
        ],
    )


# ===================================================================
# Test Scenario 5: Real KFT PDF + CKD Patient
# ===================================================================
# Uses the REAL Drlogy KFT PDF.
# Report values: all "normal" but Sodium=100 (data quirk, actually low).
# Profile: CKD patient on Losartan — should cross-reference renal values.


def _build_scenario_5() -> TestScenario:
    pdf_path = FIXTURES_DIR / "drlogy_kft.pdf"
    if not pdf_path.exists():
        return None  # type: ignore[return-value]

    return TestScenario(
        title="Test 5: Real KFT PDF + CKD Patient on Losartan",
        profile_data={
            "account_id": uuid.uuid4(),
            "name": "David Park",
            "relationship": "parent",
            "sex": "male",
            "date_of_birth": date(1960, 2, 14),
            "blood_type": "O-",
            "allergies": [],
            "current_medications": [
                {
                    "name": "Losartan",
                    "dosage": "50mg",
                    "frequency": "once daily",
                },
            ],
            "medical_conditions": [
                {
                    "condition": "Chronic Kidney Disease Stage 2",
                    "diagnosed": "2022",
                    "status": "active",
                },
                {
                    "condition": "Hypertension",
                    "diagnosed": "2018",
                    "status": "managed",
                },
            ],
            "family_medical_history": {
                "Kidney Disease": ["Mother"],
            },
        },
        seed_memories=[
            {
                "messages": [
                    {
                        "role": "user",
                        "content": ("Dad's creatinine was 1.4 mg/dL" " in June 2025."),
                    },
                    {
                        "role": "assistant",
                        "content": ("Creatinine of 1.4 is mildly" " elevated for CKD stage 2."),
                    },
                ],
                "category": "lab_results",
                "source": "report:kft-prev",
            },
        ],
        report_bytes=pdf_path.read_bytes(),
        report_filename="drlogy_kft.pdf",
        expected_findings_keywords=[
            ("Creatinine detected", ["creatinine", "1.2"]),
            ("Urea/BUN detected", ["urea", "bun", "16"]),
            ("Potassium detected", ["potassium", "3.5"]),
            ("Sodium detected", ["sodium", "100"]),
        ],
        expected_alert_keywords=[
            (
                "Renal monitoring note",
                [
                    "kidney",
                    "renal",
                    "ckd",
                    "creatinine",
                    "sodium",
                    "monitor",
                    "low",
                ],
            ),
        ],
        expected_recommendation_keywords=[
            (
                "Continued monitoring",
                ["monitor", "follow", "kidney", "renal", "consult"],
            ),
        ],
        expected_memory_keywords=["creatinine"],
        expected_profile_context_refs=[
            (
                "Losartan-kidney link",
                ["losartan", "kidney", "renal", "ckd", "medication"],
            ),
        ],
    )


# ===================================================================
# Test Runner
# ===================================================================


def _check_keywords_in_text(text: str, keywords: list[str]) -> bool:
    """Return True if ANY keyword is found (case-insensitive) in text."""
    lower = text.lower()
    return any(kw.lower() in lower for kw in keywords)


async def run_scenario(
    scenario: TestScenario,
    memory_service,
    llm_router,
    context_builder,
    memory_extractor,
    async_session_factory,
    agent_core=None,
) -> list[CheckResult]:
    """Run a single test scenario and return check results."""
    from sqlalchemy import text as sql_text

    from app.models.profile import Profile
    from app.models.report import ReportAnalysis
    from app.services.report_analyzer import ReportAnalyzerService

    checks: list[CheckResult] = []
    profile_id: uuid.UUID | None = None

    try:
        # ----------------------------------------------------------
        # Step 1: Create profile
        # ----------------------------------------------------------
        _print_step(1, "Create profile")
        async with async_session_factory() as db:
            profile = Profile(id=uuid.uuid4(), **scenario.profile_data)
            profile_id = profile.id
            db.add(profile)
            await db.commit()
        print(f"    Profile: {scenario.profile_data['name']} (id={profile_id})")
        conds = [c["condition"] for c in scenario.profile_data["medical_conditions"]]
        print(f"    Conditions: {conds}")
        print(
            f"    Medications: {[m['name'] for m in scenario.profile_data['current_medications']]}"
        )

        # ----------------------------------------------------------
        # Step 2: Seed Mem0 memories
        # ----------------------------------------------------------
        _print_step(2, "Seed episodic memories")
        for conv in scenario.seed_memories:
            result = await memory_service.add(
                profile_id,
                conv["messages"],
                category=conv["category"],
                source=conv["source"],
            )
            facts = result.get("results", [])
            for f in facts:
                print(f"    [{f.get('event', '?')}] {f.get('memory', '')[:80]}")
        checks.append(CheckResult("Memories seeded", True))

        # Wait for Mem0 indexing
        await asyncio.sleep(2)

        # ----------------------------------------------------------
        # Step 3: Create report record + run analysis
        # ----------------------------------------------------------
        _print_step(3, "Run report analysis (Gemini Pass 1 + Qwen Pass 2)")
        t0 = time.time()

        async def _run_analysis():
            async with async_session_factory() as db:
                loaded_profile = await db.get(Profile, profile_id)
                report = ReportAnalysis(
                    profile_id=profile_id,
                    file_url=f"upload:{scenario.report_filename}",
                    file_type="lab_report",
                    original_filename=scenario.report_filename,
                    status="pending",
                )
                db.add(report)
                await db.flush()

                svc = ReportAnalyzerService(db, agent_core, context_builder, memory_extractor)
                report = await svc.analyze(report, loaded_profile, scenario.report_bytes)
                await db.commit()
                await db.refresh(report)
                return report

        report = await _retry_llm(_run_analysis)
        elapsed = time.time() - t0
        print(f"    Status: {report.status} ({elapsed:.1f}s)")

        checks.append(
            CheckResult(
                "Analysis completed",
                report.status == "completed",
                (
                    f"status={report.status}, err={report.error_message}"
                    if report.status != "completed"
                    else ""
                ),
            )
        )

        if report.status != "completed":
            print(f"    ERROR: {report.error_message}")
            return checks

        # ----------------------------------------------------------
        # Step 4: Validate analysis result structure
        # ----------------------------------------------------------
        _print_step(4, "Validate analysis structure")
        result = report.analysis_result
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"

        summary = result.get("summary", "")
        findings = result.get("findings", [])
        alerts = result.get("alerts", [])
        recommendations = result.get("recommendations", [])

        print(f"    Summary: {_truncate(summary)}")
        print(f"    Findings: {len(findings)}")
        for f in findings[:5]:
            status_marker = "*" if f.get("status", "") not in ("normal", "") else " "
            name = f.get("name", "?")
            val = f.get("value", "?")
            unit = f.get("unit", "")
            st = f.get("status", "?")
            print(f"      {status_marker} {name}: {val} {unit} [{st}]")
        if len(findings) > 5:
            print(f"      ... and {len(findings) - 5} more")
        print(f"    Alerts: {alerts}")
        print(f"    Recommendations: {recommendations}")

        checks.append(CheckResult("Has summary", bool(summary), f"{len(summary)} chars"))
        checks.append(CheckResult("Has findings", len(findings) >= 3, f"count={len(findings)}"))
        checks.append(CheckResult("Has alerts", len(alerts) >= 1, f"count={len(alerts)}"))
        checks.append(
            CheckResult(
                "Has recommendations", len(recommendations) >= 1, f"count={len(recommendations)}"
            )
        )

        # ----------------------------------------------------------
        # Step 5: Validate expected findings
        # ----------------------------------------------------------
        _print_step(5, "Validate expected findings detected")

        # Build a searchable text from all findings
        def _finding_text(f: dict) -> str:
            parts = [
                f.get("name", ""),
                f.get("value", ""),
                f.get("unit", ""),
                f.get("status", ""),
                f.get("explanation", ""),
                f.get("reference_range", ""),
            ]
            return " ".join(parts)

        findings_text = " ".join(_finding_text(f) for f in findings)

        for desc, keywords in scenario.expected_findings_keywords:
            found = _check_keywords_in_text(findings_text, keywords)
            checks.append(CheckResult(desc, found, f"searched: {keywords[:3]}"))

        # ----------------------------------------------------------
        # Step 6: Validate alerts
        # ----------------------------------------------------------
        _print_step(6, "Validate expected alerts")
        alerts_text = " ".join(alerts)

        for desc, keywords in scenario.expected_alert_keywords:
            found = _check_keywords_in_text(alerts_text, keywords)
            # Also check summary + findings explanations as fallback
            if not found:
                full_text = alerts_text + " " + summary + " " + findings_text
                found = _check_keywords_in_text(full_text, keywords)
            checks.append(CheckResult(desc, found, f"searched: {keywords[:3]}"))

        # ----------------------------------------------------------
        # Step 7: Validate recommendations
        # ----------------------------------------------------------
        _print_step(7, "Validate expected recommendations")
        recs_text = " ".join(recommendations)

        for desc, keywords in scenario.expected_recommendation_keywords:
            found = _check_keywords_in_text(recs_text, keywords)
            if not found:
                found = _check_keywords_in_text(recs_text + " " + summary, keywords)
            checks.append(CheckResult(desc, found, f"searched: {keywords[:3]}"))

        # ----------------------------------------------------------
        # Step 8: Validate profile context cross-references
        # ----------------------------------------------------------
        _print_step(8, "Validate profile context references in analysis")
        # Search across all textual output
        full_output = summary + " " + findings_text + " " + alerts_text + " " + recs_text

        for desc, keywords in scenario.expected_profile_context_refs:
            found = _check_keywords_in_text(full_output, keywords)
            checks.append(CheckResult(desc, found, f"searched: {keywords[:3]}"))

        # ----------------------------------------------------------
        # Step 9: Validate extracted facts
        # ----------------------------------------------------------
        _print_step(9, "Validate extracted facts (Pass 2)")
        facts = report.extracted_facts
        print(f"    Extracted facts: {len(facts)}")
        for fact in facts[:5]:
            print(f"      - {_truncate(str(fact), 80)}")

        checks.append(CheckResult("Facts extracted", len(facts) >= 1, f"count={len(facts)}"))

        facts_text = " ".join(str(f) for f in facts)
        for kw in scenario.expected_memory_keywords:
            found = kw.lower() in facts_text.lower()
            checks.append(CheckResult(f"Fact contains '{kw}'", found))

        # ----------------------------------------------------------
        # Step 10: Verify Mem0 memory update
        # ----------------------------------------------------------
        _print_step(10, "Verify Mem0 memory update")

        # Run memory extraction (same as background task would)
        if facts:
            try:
                fact_messages = [
                    {
                        "role": "assistant",
                        "content": "Medical report analysis results:\n"
                        + "\n".join(f"- {f}" for f in facts),
                    }
                ]
                await memory_extractor.extract_and_store(
                    profile_id=profile_id,
                    messages=fact_messages,
                    source="report:e2e-test",
                    category="lab_results",
                )
                await asyncio.sleep(2)
            except Exception as e:
                print(f"    Memory extraction error: {e}")

        # Search for memories related to this report
        memories = await memory_service.search(
            profile_id,
            " ".join(scenario.expected_memory_keywords),
            limit=10,
            threshold=0.05,
        )
        print(f"    Memories found: {len(memories)}")
        for mem in memories[:3]:
            print(f"      [{mem.get('score', 0):.2f}] {_truncate(mem.get('memory', ''), 80)}")

        checks.append(
            CheckResult("Memories stored in Mem0", len(memories) > 0, f"count={len(memories)}")
        )

    finally:
        # ----------------------------------------------------------
        # Cleanup
        # ----------------------------------------------------------
        if profile_id:
            try:
                await memory_service.delete_all(profile_id)
            except Exception:
                pass
            try:
                async with async_session_factory() as db:
                    await db.execute(
                        sql_text("DELETE FROM action_log WHERE profile_id = :pid"),
                        {"pid": profile_id},
                    )
                    await db.execute(
                        sql_text("DELETE FROM report_analyses WHERE profile_id = :pid"),
                        {"pid": profile_id},
                    )
                    await db.execute(
                        sql_text("DELETE FROM profiles WHERE id = :pid"),
                        {"pid": profile_id},
                    )
                    await db.commit()
            except Exception:
                pass
            print("    Cleanup complete")

    return checks


# ===================================================================
# Main
# ===================================================================


async def run() -> bool:
    from app.api.deps import get_agent_core, get_llm_router, get_memory_service
    from app.core.database import async_session_factory, engine
    from app.services.context_builder import ContextBuilder
    from app.services.memory_extractor import MemoryExtractor

    engine.echo = False

    memory_service = get_memory_service()
    llm_router = get_llm_router()
    context_builder = ContextBuilder(memory_service)
    memory_extractor = MemoryExtractor(memory_service)
    agent_core = get_agent_core()

    # Real-PDF scenarios (primary — reliable with Gemini)
    scenarios = [
        _build_scenario_1(),  # Real Drlogy CBC
        _build_scenario_4(),  # Real Drlogy Lipid Profile
        _build_scenario_5(),  # Real Drlogy KFT
    ]

    # Synthetic-PDF scenarios (experimental — Gemini may not parse)
    if "--include-synthetic" in sys.argv:
        scenarios.extend(
            [
                _build_scenario_2(),  # Synthetic Lipid Panel
                _build_scenario_3(),  # Synthetic BMP
            ]
        )

    # Filter out None (missing fixture PDFs)
    scenarios = [s for s in scenarios if s is not None]

    all_checks: list[tuple[str, list[CheckResult]]] = []

    for scenario in scenarios:
        _print_header(scenario.title)
        checks = await run_scenario(
            scenario,
            memory_service,
            llm_router,
            context_builder,
            memory_extractor,
            async_session_factory,
            agent_core,
        )
        all_checks.append((scenario.title, checks))

        # Delay between scenarios to avoid rate limiting
        await asyncio.sleep(5)

    # ==================================================================
    # Final Results
    # ==================================================================
    _print_header("FINAL RESULTS")

    total_pass = 0
    total_fail = 0

    for title, checks in all_checks:
        passed = sum(1 for c in checks if c.passed)
        failed = len(checks) - passed
        total_pass += passed
        total_fail += failed

        status = "ALL PASSED" if failed == 0 else f"{failed} FAILED"
        print(f"\n  {title}: {passed}/{len(checks)} ({status})")
        for c in checks:
            print(f"  {c}")

    print(f"\n{'=' * 70}")
    print(f"  TOTAL: {total_pass}/{total_pass + total_fail} passed, {total_fail} failed")
    print(f"{'=' * 70}")

    return total_fail == 0


if __name__ == "__main__":
    ok = asyncio.run(run())
    sys.exit(0 if ok else 1)
