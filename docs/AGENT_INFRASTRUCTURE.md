# Agent Infrastructure

## Overview

Shared agent infrastructure that both diagnosis and report analysis (and
future features) use. Inspired by Oqoqo's pattern where `AgentCore` is the
reusable loop and agents are configurations.

## Architecture

```
app/agents/
├── types.py           # ToolDefinition, ToolCall, ToolResult, AgentEvent, AgentResult, AgentDefinition
├── registry.py        # ToolRegistry — register + execute tools
├── session.py         # AgentSession — per-interaction state
├── core.py            # AgentCore — the reusable agentic loop (supports thinking_delta events)
├── definitions.py     # DIAGNOSIS_AGENT, REPORT_AGENT, CHAT_AGENT
└── tools/
    ├── memory_search.py     # search_patient_memory (wraps MemoryService)
    ├── present_question.py  # present_question (terminal, structured Q&A)
    ├── profile_lookup.py    # get_profile_context (loads from DB)
    └── web_search.py        # web_search (DuckDuckGo + Tavily + PubMed)
```

## How It Works

1. Service creates an `AgentSession` (profile_id, system_prompt, messages)
2. Service calls `AgentCore.run(session, agent_definition)`
3. AgentCore loops: LLM call → tool calls detected → execute tools →
   inject results → next LLM call
4. Returns `AgentResult` with content, tool history, round count
5. Service does post-processing (safety, extraction, logging)

## Agent Definitions

| Agent | Task | Tools | Default Provider | Max Rounds | Thinking |
|-|-|-|-|-|-|
| DIAGNOSIS_AGENT | DIAGNOSIS | search_patient_memory, present_question, web_search | Cerebras (Gemini via env) | 6 | budget=-1 (auto) |
| REPORT_AGENT | REPORT_ANALYSIS | (none — JSON mode) | Gemini | 0 | disabled |
| CHAT_AGENT | CHAT | search_patient_memory, web_search | Cerebras | 3 | disabled |

## Tool Interface

Tools are async functions registered in `ToolRegistry` at startup:

```python
ToolDefinition(
    name="search_patient_memory",
    description="Search patient's health memory",
    parameters={...},  # JSON Schema
    handler=async_function,
)
```

AgentCore auto-injects `profile_id` from the session into every tool call.

## LLM Tool Calling

`LLMRequest` supports `tools` and `tool_choice` fields. `GeminiProvider`
maps these to Gemini's native function calling API. `LLMResponse` includes
`tool_calls` when the model requests tool execution.

## Thinking Support

When `AgentDefinition.thinking_budget` is set (e.g., `-1` for automatic) and the
provider is Gemini, the agent loop emits `THINKING_DELTA` events. These are:
- Streamed to the frontend as `thinking_delta` SSE events
- Accumulated in `PartsAccumulator.thinking_text`
- Persisted as `ThinkingPart` in `content_parts`
- NOT added to `text_buffer` or conversation history

`GeminiProvider` auto-boosts `max_output_tokens` to 8000 when thinking is active
(thinking tokens count against the output limit). Non-Gemini providers silently
ignore the `thinking_budget` field.

## Future Extensions

- Structured assessment rendering (`present_assessment` tool)
- Security hooks (PreToolUse validation)
