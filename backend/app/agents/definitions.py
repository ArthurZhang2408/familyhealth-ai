"""Agent definitions — configuration objects for each agent type.

Each definition specifies: which LLM task to use, which tools are available,
and generation parameters. Services create AgentSessions and pass them
to AgentCore.run() with the appropriate definition.
"""

from __future__ import annotations

from app.agents.types import AgentDefinition
from app.services.llm import LLMTask

DIAGNOSIS_AGENT = AgentDefinition(
    name="diagnosis",
    description="Structured symptom assessment following OLDCARTS protocol",
    task=LLMTask.DIAGNOSIS,
    tool_names=["search_patient_memory"],
    temperature=0.3,
    max_tokens=2000,
    max_tool_rounds=3,
)

REPORT_AGENT = AgentDefinition(
    name="report_analysis",
    description="Medical report analysis with profile cross-referencing",
    task=LLMTask.REPORT_ANALYSIS,
    # No tools — Gemini JSON mode and function calling are mutually exclusive.
    # Context is pre-loaded by ContextBuilder (profile + memories).
    # Profile cross-referencing is handled via the Generated Knowledge prompt pattern.
    tool_names=[],
    temperature=0.1,
    max_tokens=8000,
    max_tool_rounds=0,
    response_format={"type": "json"},
)

CHAT_AGENT = AgentDefinition(
    name="chat",
    description="General health chat assistant",
    task=LLMTask.CHAT,
    tool_names=["search_patient_memory"],
    temperature=0.7,
    max_tokens=2000,
    max_tool_rounds=2,
)
