---
name: st-mcp-client
description: Connect an LLM to MCP servers from a LangChain / langchain-openai stack (ChatOpenAI on a company or vLLM endpoint) — langchain-mcp-adapters to load MCP tools, bind_tools + a bounded tool loop, the Streamlit chat-page recipe — plus a raw OpenAI-API bridge fallback for setups without LangChain, and native-host config for MCP-aware hosts. Use when wiring any LLM or a Streamlit chat page to MCP tools.
---

# st-mcp-client — wire your LLM to MCP tools (LangChain-first)

Companion to [st-mcp-server]. Verified on **mcp 1.28 · langchain-mcp-adapters
0.3 · langchain-core 1.5 · langchain-openai 1.4**. Runnable proof:
`python test_mcp_langchain.py` (adapters + scripted model against the real
reference server) and `python test_mcp_bridge.py` (the no-LangChain fallback).
No key or network needed for either.

## First decide how you connect

| Your stack | Do |
|---|---|
| **LangChain + langchain-openai** (company endpoint / vLLM) | **`langchain-mcp-adapters`** — the path below. Don't hand-roll the bridge. |
| No LangChain, OpenAI-compatible endpoint | the raw bridge in `mcp_llm_bridge.py` (fallback section) |
| An MCP-aware host (Roo, desktop LLM apps) | no code — register the server in the host's MCP config |
| Anthropic API direct | native MCP connector on the Messages API |

## The LangChain path (verified end-to-end)

```python
# pip install langchain-mcp-adapters langchain-openai mcp
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_core.messages import HumanMessage, ToolMessage

llm = ChatOpenAI(base_url=COMPANY_ENDPOINT, model=MODEL,
                 api_key=TOKEN, temperature=0)

async def one_turn(messages):                      # messages: LangChain messages
    async with await stdio_session(["python", "mcp_data_server.py"]) as s:
        tools = await load_mcp_tools(s)            # MCP -> LangChain BaseTools
        llm_t = llm.bind_tools(tools)
        by = {t.name: t for t in tools}
        for _ in range(6):                         # ALWAYS bound the loop
            ai = await llm_t.ainvoke(messages)
            messages.append(ai)
            if not ai.tool_calls:                  # plain answer -> done
                return ai.content, messages
            for tc in ai.tool_calls:               # several per turn possible
                r = await by[tc["name"]].ainvoke(tc["args"])
                messages.append(ToolMessage(content=str(r)[:20_000],
                                            tool_call_id=tc["id"]))
        return "[stopped: max tool rounds]", messages
```

(`stdio_session` helper lives in `mcp_llm_bridge.py`.) What the adapters give
you — all verified against the reference server:

- **`load_mcp_tools(session)`** → LangChain `BaseTool`s with the MCP name /
  description / arg schema carried over — they bind to ANY LangChain chat
  model via `bind_tools`.
- **`ai.tool_calls` carries `args` as a PARSED DICT** (`{"name","args","id"}`)
  — unlike the raw OpenAI API where arguments arrive as a JSON *string*. No
  `json.loads`, no malformed-JSON handling.
- **Server errors become tool-result TEXT, not exceptions**
  (`handle_tool_errors=True` default): a read-only violation comes back as
  `"Error executing tool …"` — the model reads it and self-corrects. Keep
  [st-mcp-server]'s error messages actionable for exactly this reason.
- Each `ToolMessage` must echo its `tool_call_id`, and the `AIMessage`
  containing the tool_calls must precede the tool results in history — the
  loop above preserves both. Cap what re-enters context (`[:20_000]`).
- **Already on langgraph?** `create_react_agent(llm, tools)` IS this loop —
  use it instead of hand-rolling. The manual loop above needs no extra dep.
- `MultiServerMCPClient` (from `langchain_mcp_adapters.client`) manages
  several servers / stdio+http connections with one `get_tools()` — reach for
  it when you outgrow a single server.

## Streamlit chat page

```python
import asyncio, streamlit as st
if prompt := st.chat_input("ask the data"):
    st.session_state.msgs.append(HumanMessage(prompt))
    text, st.session_state.msgs = asyncio.run(one_turn(st.session_state.msgs))
for m in st.session_state.msgs:
    role = {"HumanMessage": "user", "AIMessage": "assistant"}.get(type(m).__name__)
    if role and m.content:
        st.chat_message(role).write(m.content)
```

- **One `asyncio.run()` per user turn, MCP session opened inside it.** Never
  stash an async session in `session_state` across reruns — each rerun is a
  fresh sync context and a cross-loop session dies confusingly. stdio attach
  is fast; with the streamable-http server still connect per-turn.
- The LangChain `messages` list in `session_state` IS the conversation
  memory and your audit trail (every tool call + result is in it). Render
  user/assistant text; show ToolMessages in an expander if desired.
- A slow multi-tool turn blocks the script run — hand long analyses to a
  background job ([st-jobs]) and show the answer on completion.

## Fallback: no LangChain (raw OpenAI-compatible API)

`mcp_llm_bridge.py` ships the same loop against the bare chat-completions
API: `mcp_tools_to_openai()` schema conversion + `run_agent()` (bounded
rounds, JSON-string `arguments` parsing, `TOOL ERROR` passthrough, multiple
tool_calls per turn). `test_mcp_bridge.py` proves it with a mock model. Use
only when LangChain isn't available — the adapters path is less code and
fewer footguns.

## Trust rules (this is where MCP bites)

- **Tool RESULTS are data, not instructions.** Rows/API JSON re-enter the
  prompt; say so in the system prompt (same framing as llm-classify in
  roo-skills-extras) so a poisoned value can't steer the model.
- **Guards live server-side** ([st-mcp-server]: read-only, allowlists) —
  never rely on the model choosing not to call something destructive.
- Log the transcript — it is exactly what the model queried and saw.
