# Agent Infrastructure

## Overview

Shared agent infrastructure that both diagnosis and report analysis (and
future features) use. Inspired by Oqoqo's pattern where `AgentCore` is the
reusable loop and agents are configurations.

## Architecture

```
app/agents/
├── types.py           # ToolDefinition, ToolCall, ToolResult, AgentEvent, AgentResult
├── registry.py        # ToolRegistry — register + execute tools
├── session.py         # AgentSession — per-interaction state
├── core.py            # AgentCore — the reusable agentic loop
├── definitions.py     # DIAGNOSIS_AGENT, REPORT_AGENT, CHAT_AGENT
└── tools/
    ├── memory_search.py   # search_patient_memory (wraps MemoryService)
    └── profile_lookup.py  # get_profile_context (loads from DB)
```

## How It Works

1. Service creates an `AgentSession` (profile_id, system_prompt, messages)
2. Service calls `AgentCore.run(session, agent_definition)`
3. AgentCore loops: LLM call → tool calls detected → execute tools →
   inject results → next LLM call
4. Returns `AgentResult` with content, tool history, round count
5. Service does post-processing (safety, extraction, logging)

## Agent Definitions

| Agent | Task | Tools | Model | Max Rounds |
|-|-|-|-|-|
| DIAGNOSIS_AGENT | DIAGNOSIS | search_patient_memory | gemini-2.5-flash | 3 |
| REPORT_AGENT | REPORT_ANALYSIS | search_patient_memory | gemini-2.5-flash | 3 |
| CHAT_AGENT | CHAT | search_patient_memory | qwen3.5:397b | 2 |

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

## Future Extensions

- Google Search grounding tool (guidelines lookup)
- Drug-interaction knowledge base tool
- Streaming support (yield AgentEvents for SSE)
- Security hooks (PreToolUse validation)
