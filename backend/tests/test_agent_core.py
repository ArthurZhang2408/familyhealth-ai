"""Tests for the shared agent infrastructure.

Covers: types, registry, session, core loop, and LLM tool_calls integration.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

from app.agents.core import AgentCore, AgentDefinition
from app.agents.registry import ToolRegistry
from app.agents.session import AgentSession
from app.agents.types import (
    AgentEvent,
    AgentEventType,
    AgentResult,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from app.services.llm import LLMResponse, LLMTask, ToolCallResponse

# ===================================================================
# Helpers
# ===================================================================

PROFILE_ID = uuid.uuid4()


async def _echo_tool(query: str, profile_id: str, **kwargs) -> dict:
    """Test tool that echoes its arguments."""
    return {"echo": query, "profile_id": profile_id}


async def _error_tool(**kwargs) -> dict:
    raise RuntimeError("Tool exploded")


def _make_tool(name: str = "test_tool", handler=None) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description="A test tool",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        handler=handler or _echo_tool,
    )


def _make_agent_def(**overrides) -> AgentDefinition:
    defaults = {
        "name": "test_agent",
        "description": "Test agent",
        "task": LLMTask.CHAT,
        "tool_names": [],
        "temperature": 0.3,
        "max_tokens": 1000,
        "max_tool_rounds": 3,
    }
    defaults.update(overrides)
    return AgentDefinition(**defaults)


def _make_session(**overrides) -> AgentSession:
    defaults = {
        "profile_id": PROFILE_ID,
        "system_prompt": "You are a test agent.",
        "messages": [{"role": "user", "content": "Hello"}],
    }
    defaults.update(overrides)
    return AgentSession(**defaults)


def _make_llm_response(
    content: str = "Hello!",
    tool_calls: list[ToolCallResponse] | None = None,
) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="test-model",
        usage={"prompt_tokens": 10, "completion_tokens": 5},
        tool_calls=tool_calls,
        finish_reason="tool_calls" if tool_calls else "stop",
    )


# ===================================================================
# 1. Core Types
# ===================================================================


class TestCoreTypes:
    def test_tool_definition_to_declaration(self):
        tool = _make_tool()
        decl = tool.to_declaration()
        assert decl["name"] == "test_tool"
        assert "properties" in decl["parameters"]

    def test_tool_call_make_id(self):
        id1 = ToolCall.make_id()
        id2 = ToolCall.make_id()
        assert id1 != id2
        assert id1.startswith("tc_")

    def test_tool_result(self):
        result = ToolResult(call_id="tc_123", name="test", output={"data": 42})
        assert not result.is_error

    def test_agent_event(self):
        event = AgentEvent(type=AgentEventType.TEXT, data={"text": "hi"})
        assert event.type == "text"

    def test_agent_result(self):
        result = AgentResult(content="Done", model="m", usage={})
        assert result.rounds == 1
        assert not result.max_rounds_hit


# ===================================================================
# 2. Tool Registry
# ===================================================================


class TestToolRegistry:
    def test_register_and_get(self):
        registry = ToolRegistry()
        tool = _make_tool()
        registry.register(tool)
        assert registry.get("test_tool") is tool
        assert registry.get("nonexistent") is None

    def test_get_declarations(self):
        registry = ToolRegistry()
        registry.register(_make_tool("tool_a"))
        registry.register(_make_tool("tool_b"))
        decls = registry.get_declarations(["tool_a", "tool_b"])
        assert len(decls) == 2
        assert decls[0]["name"] == "tool_a"

    def test_get_declarations_empty(self):
        registry = ToolRegistry()
        assert registry.get_declarations([]) is None
        assert registry.get_declarations(["missing"]) is None

    async def test_execute_success(self):
        registry = ToolRegistry()
        registry.register(_make_tool())
        call = ToolCall(id="tc_1", name="test_tool", arguments={"query": "hi"})
        result = await registry.execute(call, injected_args={"profile_id": "pid"})
        assert not result.is_error
        assert result.output["echo"] == "hi"

    async def test_execute_unknown_tool(self):
        registry = ToolRegistry()
        call = ToolCall(id="tc_1", name="missing", arguments={})
        result = await registry.execute(call)
        assert result.is_error
        assert "Unknown tool" in result.output["error"]

    async def test_execute_handler_error(self):
        registry = ToolRegistry()
        registry.register(_make_tool("bad_tool", handler=_error_tool))
        call = ToolCall(id="tc_1", name="bad_tool", arguments={})
        result = await registry.execute(call)
        assert result.is_error
        assert "exploded" in result.output["error"]


# ===================================================================
# 3. Agent Session
# ===================================================================


class TestAgentSession:
    def test_creation(self):
        session = _make_session()
        assert session.profile_id == PROFILE_ID
        assert session.turn_count == 0
        assert len(session.messages) == 1

    def test_tool_tracking(self):
        session = _make_session()
        tc = ToolCall(id="tc_1", name="test", arguments={})
        tr = ToolResult(call_id="tc_1", name="test", output={})
        session.tool_calls_made.append(tc)
        session.tool_results.append(tr)
        assert len(session.tool_calls_made) == 1
        assert len(session.tool_results) == 1

    def test_metadata(self):
        session = _make_session(metadata={"key": "value"})
        assert session.metadata["key"] == "value"


# ===================================================================
# 4. Agent Core Loop
# ===================================================================


class TestAgentCore:
    def _make_core(self, responses: list[LLMResponse]) -> AgentCore:
        """Build an AgentCore with a mock LLMRouter returning given responses."""
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(side_effect=responses)
        registry = ToolRegistry()
        registry.register(_make_tool("search_patient_memory"))
        return AgentCore(llm_router=mock_router, tool_registry=registry)

    async def test_simple_no_tools(self):
        """Agent with no tools returns LLM response directly."""
        core = self._make_core([_make_llm_response("Hello!")])
        session = _make_session()
        agent_def = _make_agent_def(tool_names=[])

        result = await core.run(session, agent_def)

        assert result.content == "Hello!"
        assert result.rounds == 1
        assert not result.max_rounds_hit
        assert result.tool_calls_made == []

    async def test_single_tool_round(self):
        """Agent makes one tool call, then returns final text."""
        tool_call = ToolCallResponse(
            id="tc_1",
            name="search_patient_memory",
            arguments={"query": "previous labs"},
        )
        core = self._make_core(
            [
                _make_llm_response("", tool_calls=[tool_call]),
                _make_llm_response("Based on your history..."),
            ]
        )
        session = _make_session()
        agent_def = _make_agent_def(tool_names=["search_patient_memory"])

        result = await core.run(session, agent_def)

        assert result.content == "Based on your history..."
        assert result.rounds == 2
        assert len(result.tool_calls_made) == 1
        assert result.tool_calls_made[0].name == "search_patient_memory"
        assert len(result.tool_results) == 1
        assert not result.tool_results[0].is_error

    async def test_multi_tool_rounds(self):
        """Agent makes multiple tool rounds before returning text."""
        tc1 = ToolCallResponse(
            id="tc_1",
            name="search_patient_memory",
            arguments={"query": "medications"},
        )
        tc2 = ToolCallResponse(
            id="tc_2",
            name="search_patient_memory",
            arguments={"query": "lab results"},
        )
        core = self._make_core(
            [
                _make_llm_response("", tool_calls=[tc1]),
                _make_llm_response("", tool_calls=[tc2]),
                _make_llm_response("Analysis complete."),
            ]
        )
        session = _make_session()
        agent_def = _make_agent_def(tool_names=["search_patient_memory"])

        result = await core.run(session, agent_def)

        assert result.content == "Analysis complete."
        assert result.rounds == 3
        assert len(result.tool_calls_made) == 2

    async def test_max_rounds_hit(self):
        """Agent stops after max_tool_rounds even if LLM keeps calling tools."""
        tc = ToolCallResponse(
            id="tc_1",
            name="search_patient_memory",
            arguments={"query": "loop"},
        )
        # More tool calls than max_tool_rounds
        core = self._make_core(
            [
                _make_llm_response("", tool_calls=[tc]),
                _make_llm_response("", tool_calls=[tc]),
                _make_llm_response("", tool_calls=[tc]),
                _make_llm_response("", tool_calls=[tc]),
            ]
        )
        session = _make_session()
        agent_def = _make_agent_def(
            tool_names=["search_patient_memory"],
            max_tool_rounds=2,
        )

        result = await core.run(session, agent_def)

        assert result.max_rounds_hit
        assert result.rounds == 3  # max_tool_rounds + 1

    async def test_tool_error_continues(self):
        """Agent continues even when a tool call errors."""
        tc = ToolCallResponse(
            id="tc_1",
            name="nonexistent_tool",
            arguments={},
        )
        core = self._make_core(
            [
                _make_llm_response("", tool_calls=[tc]),
                _make_llm_response("Handled the error."),
            ]
        )
        session = _make_session()
        agent_def = _make_agent_def(tool_names=["nonexistent_tool"])

        result = await core.run(session, agent_def)

        assert result.content == "Handled the error."
        assert result.tool_results[0].is_error

    async def test_profile_id_injected(self):
        """AgentCore injects profile_id into tool arguments."""
        captured_args = {}

        async def capture_tool(**kwargs):
            captured_args.update(kwargs)
            return {"result": "ok"}

        registry = ToolRegistry()
        registry.register(_make_tool("capture_tool", handler=capture_tool))
        mock_router = AsyncMock()
        tc = ToolCallResponse(
            id="tc_1",
            name="capture_tool",
            arguments={"query": "test"},
        )
        mock_router.route = AsyncMock(
            side_effect=[
                _make_llm_response("", tool_calls=[tc]),
                _make_llm_response("Done"),
            ]
        )
        core = AgentCore(llm_router=mock_router, tool_registry=registry)

        session = _make_session()
        agent_def = _make_agent_def(tool_names=["capture_tool"])
        await core.run(session, agent_def)

        assert captured_args["profile_id"] == str(PROFILE_ID)

    async def test_session_messages_updated(self):
        """AgentCore appends assistant and tool messages to session."""
        tc = ToolCallResponse(
            id="tc_1",
            name="search_patient_memory",
            arguments={"query": "test"},
        )
        core = self._make_core(
            [
                _make_llm_response("", tool_calls=[tc]),
                _make_llm_response("Final answer"),
            ]
        )
        session = _make_session()
        agent_def = _make_agent_def(tool_names=["search_patient_memory"])

        await core.run(session, agent_def)

        # Original user msg + assistant msg + tool result msg
        assert len(session.messages) == 3
        assert session.messages[1]["role"] == "assistant"
        assert "Tool search_patient_memory" in session.messages[2]["content"]


# ===================================================================
# 5. Agent Definitions
# ===================================================================


class TestAgentDefinitions:
    def test_diagnosis_agent(self):
        from app.agents.definitions import DIAGNOSIS_AGENT

        assert DIAGNOSIS_AGENT.name == "diagnosis"
        assert DIAGNOSIS_AGENT.task == LLMTask.DIAGNOSIS
        assert "search_patient_memory" in DIAGNOSIS_AGENT.tool_names

    def test_report_agent(self):
        from app.agents.definitions import REPORT_AGENT

        assert REPORT_AGENT.name == "report_analysis"
        assert REPORT_AGENT.task == LLMTask.REPORT_ANALYSIS
        assert REPORT_AGENT.max_tokens == 8000

    def test_chat_agent(self):
        from app.agents.definitions import CHAT_AGENT

        assert CHAT_AGENT.name == "chat"
        assert CHAT_AGENT.temperature == 0.7
