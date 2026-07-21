---
name: st-mcp-client
description: Connect an LLM to MCP servers — native config for MCP-aware hosts (Roo, desktop apps), and a bridge/agent loop for company LLMs that only speak the OpenAI-compatible chat API (vLLM, internal gateways, local Qwen): convert MCP tool schemas to function-calling `tools=`, execute tool_calls against the MCP session, feed results back. Use when wiring any LLM or a Streamlit chat page to MCP tools. Ships mcp_llm_bridge.py + a mock-LLM self-test.
---

# mcp-client — wire an LLM to your MCP tools

Companion to [st-mcp-server]. Module: `mcp_llm_bridge.py`; proof:
`python test_mcp_bridge.py` — a scripted mock LLM drives the REAL reference
server through the REAL loop, no key/network. Verified on **mcp 1.28**.

## First decide: does your host already speak MCP?

| Your LLM lives in… | Do |
|---|---|
| An MCP-aware host (Roo Code, Claude Desktop-class apps) | **No code.** Register the server in the host's MCP config and it handles everything: `{"mcpServers": {"data": {"command": "python", "args": ["/path/mcp_data_server.py"]}}}` |
| A company / OpenAI-compatible endpoint (vLLM, gateway, local Qwen) — **no native MCP** | **The bridge below** — you own the loop |
| Anthropic API direct | Native MCP connector on the Messages API (server URL in the request) — no loop needed |

## The bridge (OpenAI-compatible ⇄ MCP)

Three pieces, all in `mcp_llm_bridge.py` and all verified:

```python
from mcp_llm_bridge import mcp_tools_to_openai, run_agent, stdio_session

async with await stdio_session(["python", "mcp_data_server.py"]) as s:
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": question}]
    text, transcript = await run_agent(messages, call_llm, s, max_rounds=6)
```

1. **`mcp_tools_to_openai(tools)`** — MCP `list_tools()` → the `tools=`
   payload (name/description/inputSchema map 1:1 onto function calling).
2. **`run_agent(messages, call_llm, session)`** — the loop: model returns
   `tool_calls` → each is executed via `session.call_tool` → results appended
   as `role:"tool"` messages → model called again → until it answers in text.
   **Bounded by `max_rounds`** (verified: a model that never stops calling
   tools is cut off, no infinite loop). Handles several tool_calls per turn,
   malformed JSON arguments, and caps each tool result at 20k chars before it
   re-enters context.
3. **`call_llm` is YOUR adapter** (same adapter pattern as llm-classify (roo-skills-extras)) — the
   OpenAI-compatible reference is in the module's `_ADAPTER` string: works for
   a company gateway or a local Qwen served by vLLM. `temperature=0`.

**Errors flow to the model, not to a crash** (verified): a tool exception or
`isError` result becomes a `TOOL ERROR: …` tool message — the model reads it
and self-corrects (that's why [st-mcp-server] says make error messages actionable).

## Streamlit chat page over the bridge

```python
import asyncio, streamlit as st
if prompt := st.chat_input("ask the data"):
    st.session_state.msgs.append({"role": "user", "content": prompt})
    async def turn():
        async with await stdio_session(SERVER_CMD) as s:
            return await run_agent(st.session_state.msgs, call_llm, s)
    text, st.session_state.msgs = asyncio.run(turn())
for m in st.session_state.msgs:
    if m["role"] in ("user", "assistant") and m.get("content"):
        st.chat_message(m["role"]).write(m["content"])
```

- **One `asyncio.run()` per user turn, session opened inside it.** Don't try
  to keep an async MCP session in `session_state` across reruns — each rerun
  is a fresh sync context and a cross-loop session dies confusingly. stdio
  attach is fast; for a long-lived shared connection use the streamable-http
  server and open per-turn all the same.
- Keep `messages` in `session_state` (the transcript IS the conversation
  memory). Render only user/assistant text; tool messages are audit detail
  (show in an expander if desired).
- A slow multi-tool turn blocks the script run — for long analyses submit it
  as a background job ([st-jobs] pattern) and stream the answer on completion.

## Trust rules (this is where MCP bites)

- **Tool RESULTS are data, not instructions.** Your rows/API JSON re-enter
  the prompt; a poisoned value ("ignore previous instructions…") must not
  steer the model. Put it in the system prompt explicitly — same framing as
  [llm-classify].
- **The model must not get write-shaped tools "for free".** Guard rails live
  server-side ([st-mcp-server]: read-only, allowlist) — never rely on the model
  choosing not to call something destructive.
- Log `transcript` — the appended tool_calls + results are your audit trail
  of exactly what the model queried.

## Gotchas (verified)

- `arguments` arrives as a **JSON string**, not a dict — parse with a
  fallback to `{}` (the bridge does).
- Several `tool_calls` can arrive in ONE assistant turn — answer each with
  its own `tool_call_id` message or the next API call 400s.
- The assistant message that contains `tool_calls` must itself be appended to
  history before the tool results, in order — the bridge preserves this.
- Some OpenAI-compatible gateways reject `"tool_calls": null` — the bridge
  omits the field when empty for compatibility.
