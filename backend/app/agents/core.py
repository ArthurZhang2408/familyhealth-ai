"""AgentCore — the shared, reusable agentic loop.

Adapted from the Oqoqo pattern where AgentCore is the engine and agents
are configurations. The core handles:
  LLM call → tool call detection → tool execution → result injection → repeat

Services (DiagnosisService, ReportAnalyzerService) configure an agent
definition and session, then call ``AgentCore.run()`` instead of manually
orchestrating LLM calls.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from app.agents.registry import ToolRegistry
from app.agents.session import AgentSession
from app.agents.types import AgentDefinition, AgentEvent, AgentEventType, AgentResult, ToolCall
from app.services.llm import LLMMessage, LLMRequest, LLMResponse, LLMRouter

logger = logging.getLogger(__name__)


class AgentCore:
    """Reusable agentic loop: LLM → tool calls → execution → repeat.

    The core is LLM-agnostic — it delegates to ``LLMRouter`` for actual
    generation. Tools are resolved from the shared ``ToolRegistry``.

    Services use ``run()`` for agentic interactions (with tool calling)
    and ``call()`` for simple non-agentic LLM calls (extraction, summarization).
    """

    def __init__(
        self,
        llm_router: LLMRouter,
        tool_registry: ToolRegistry,
    ) -> None:
        self._llm = llm_router
        self._tools = tool_registry

    async def call(self, request: LLMRequest) -> LLMResponse:
        """Single LLM call — no agent loop, no tools.

        Use for non-agentic tasks: structured extraction, summarization,
        fact extraction. Delegates directly to LLMRouter.
        """
        return await self._llm.route(request)

    async def run(
        self,
        session: AgentSession,
        agent_def: AgentDefinition,
    ) -> AgentResult:
        """Execute the agentic loop.

        Calls the LLM with the agent's tool set. If the LLM returns tool
        calls, executes them, injects results, and calls the LLM again.
        Repeats until the LLM returns a text response or
        ``max_tool_rounds`` is reached.
        """
        tool_declarations = self._tools.get_declarations(agent_def.tool_names)

        last_content = ""
        last_model = ""
        last_usage: dict[str, int] = {}

        for round_num in range(agent_def.max_tool_rounds + 1):
            request = self._build_request(session, agent_def, tool_declarations)
            try:
                response = await self._llm.route(request)
            except Exception:
                logger.exception(
                    "Agent '%s' LLM call failed on round %d",
                    agent_def.name,
                    round_num + 1,
                )
                raise

            session.turn_count += 1
            last_content = response.content
            last_model = response.model
            last_usage = response.usage

            # No tool calls → we're done
            if not response.tool_calls:
                return AgentResult(
                    content=response.content,
                    model=response.model,
                    usage=response.usage,
                    tool_calls_made=list(session.tool_calls_made),
                    tool_results=list(session.tool_results),
                    rounds=round_num + 1,
                )

            # Append assistant message with tool call intent
            session.messages.append({"role": "assistant", "content": response.content or ""})

            # Execute each tool call
            injected = {"profile_id": str(session.profile_id)}
            hit_terminal = False
            for tc_response in response.tool_calls:
                tc = ToolCall(
                    id=tc_response.id,
                    name=tc_response.name,
                    arguments=tc_response.arguments,
                )
                session.tool_calls_made.append(tc)
                result = await self._tools.execute(tc, injected_args=injected)
                session.tool_results.append(result)

                logger.info(
                    "Agent '%s' tool '%s': %s",
                    agent_def.name,
                    tc.name,
                    "error" if result.is_error else "ok",
                )

                # Terminal tools stop the loop (e.g., present_question)
                tool_def = self._tools.get(tc.name)
                if tool_def and tool_def.terminal:
                    hit_terminal = True
                    break

                # Inject tool result as message for next LLM round
                result_text = json.dumps(result.output, default=str)
                session.messages.append(
                    {"role": "user", "content": f"[Tool {tc.name}] {result_text}"}
                )

            if hit_terminal:
                return AgentResult(
                    content=response.content,
                    model=response.model,
                    usage=response.usage,
                    tool_calls_made=list(session.tool_calls_made),
                    tool_results=list(session.tool_results),
                    rounds=round_num + 1,
                )

        # Max rounds exceeded
        logger.warning(
            "Agent '%s' hit max_tool_rounds (%d)",
            agent_def.name,
            agent_def.max_tool_rounds,
        )
        return AgentResult(
            content=last_content,
            model=last_model,
            usage=last_usage,
            tool_calls_made=list(session.tool_calls_made),
            tool_results=list(session.tool_results),
            rounds=agent_def.max_tool_rounds + 1,
            max_rounds_hit=True,
        )

    async def run_stream(
        self,
        session: AgentSession,
        agent_def: AgentDefinition,
    ) -> AsyncIterator[AgentEvent]:
        """Streaming version of run(). Yields AgentEvents as they occur.

        Every round uses route_stream() for true token-by-token output.
        If the model returns tool calls in the stream, they are detected,
        executed, and the next round streams again.
        """
        tool_declarations = self._tools.get_declarations(agent_def.tool_names)
        last_text = ""

        for round_num in range(agent_def.max_tool_rounds + 1):
            request = self._build_request(session, agent_def, tool_declarations)

            text_buffer = ""
            tool_calls: list[ToolCall] = []

            try:
                async for chunk in self._llm.route_stream(request):
                    if chunk.type == "text_delta":
                        text_buffer += chunk.content
                        yield AgentEvent(
                            type=AgentEventType.TEXT_DELTA,
                            data={"content": chunk.content},
                        )
                    elif chunk.type == "tool_call":
                        for tc_resp in chunk.tool_calls:
                            tool_calls.append(
                                ToolCall(
                                    id=tc_resp.id,
                                    name=tc_resp.name,
                                    arguments=tc_resp.arguments,
                                )
                            )
            except Exception:
                logger.exception(
                    "Agent '%s' LLM call failed on round %d",
                    agent_def.name,
                    round_num + 1,
                )
                raise

            session.turn_count += 1
            last_text = text_buffer

            if not tool_calls:
                # Final response — text already streamed token-by-token
                yield AgentEvent(
                    type=AgentEventType.DONE,
                    data={"content": text_buffer},
                )
                return

            # Tool calls detected — execute them and continue
            session.messages.append({"role": "assistant", "content": text_buffer})

            injected = {"profile_id": str(session.profile_id)}
            hit_terminal = False
            for tc in tool_calls:
                session.tool_calls_made.append(tc)

                yield AgentEvent(
                    type=AgentEventType.TOOL_CALL,
                    data={"tool": tc.name, "arguments": tc.arguments},
                )

                result = await self._tools.execute(tc, injected_args=injected)
                session.tool_results.append(result)

                result_summary = (
                    f"Error: {result.output.get('error', 'unknown')}"
                    if result.is_error
                    else f"{result.output.get('count', len(result.output))} results"
                )
                yield AgentEvent(
                    type=AgentEventType.TOOL_RESULT,
                    data={"tool": tc.name, "summary": result_summary},
                )

                # Check if this tool is terminal (stops the agent loop)
                tool_def = self._tools.get(tc.name)
                if tool_def and tool_def.terminal:
                    hit_terminal = True
                    break

                result_text = json.dumps(result.output, default=str)
                session.messages.append(
                    {"role": "user", "content": f"[Tool {tc.name}] {result_text}"}
                )

            if hit_terminal:
                yield AgentEvent(
                    type=AgentEventType.DONE,
                    data={"content": text_buffer},
                )
                return

        # Max rounds exceeded — last streamed text is the final response
        logger.warning(
            "Agent '%s' hit max_tool_rounds (%d)",
            agent_def.name,
            agent_def.max_tool_rounds,
        )
        yield AgentEvent(
            type=AgentEventType.DONE,
            data={"content": last_text},
        )

    @staticmethod
    def _build_request(
        session: AgentSession,
        agent_def: AgentDefinition,
        tool_declarations: list[dict] | None,
    ) -> LLMRequest:
        """Build an LLMRequest from session state and agent config."""
        messages = []
        for m in session.messages:
            msg_kwargs = {"role": m["role"], "content": m.get("content", "")}
            if "image_parts" in m and m["image_parts"]:
                msg_kwargs["image_parts"] = m["image_parts"]
            messages.append(LLMMessage(**msg_kwargs))

        return LLMRequest(
            task=agent_def.task,
            system_prompt=session.system_prompt,
            messages=messages,
            temperature=agent_def.temperature,
            max_tokens=agent_def.max_tokens,
            response_format=agent_def.response_format,
            tools=tool_declarations,
        )
