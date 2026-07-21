"""mcp_llm_bridge — connect ANY OpenAI-compatible LLM to an MCP server.

Most company LLM platforms (vLLM, gateways, Azure-style endpoints) speak the
OpenAI chat-completions API with function calling — but have NO native MCP
support. This bridge is the missing piece:

    MCP session --list_tools--> [convert] --tools=--> your LLM
    your LLM --tool_calls--> [loop] --call_tool--> MCP session --> back to LLM

Provider-agnostic: you supply `call_llm(messages, tools) -> assistant message
dict` (adapter for any OpenAI-compatible client below). Self-test with a MOCK
LLM + in-memory MCP server:  python test_mcp_bridge.py   (no key, no network).
"""
from __future__ import annotations

import json
from typing import Any, Callable


# ------------------------------------------------- schema conversion ----
def mcp_tools_to_openai(tools) -> list[dict]:
    """MCP list_tools() result -> OpenAI `tools=` payload (function calling)."""
    return [{
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description or "",
            "parameters": t.inputSchema or {"type": "object", "properties": {}},
        },
    } for t in tools]


# ------------------------------------------------------- agent loop ----
async def run_agent(messages: list[dict], call_llm: Callable, session,
                    max_rounds: int = 6) -> tuple[str, list[dict]]:
    """Drive LLM <-> MCP tool calls until the model answers in text.

    messages: OpenAI-style chat history (mutated in place: tool calls/results
              are appended, so the transcript is auditable).
    call_llm(messages, tools) -> the assistant message as a dict:
              {"content": str|None, "tool_calls": [{"id","function":{"name",
              "arguments"(JSON str)}}]|None}
    session:  an initialized mcp ClientSession.
    Returns (final_text, messages). Bounded by max_rounds — never loops forever.
    """
    tools = mcp_tools_to_openai((await session.list_tools()).tools)

    for _ in range(max_rounds):
        msg = call_llm(messages, tools)
        messages.append({"role": "assistant",
                         "content": msg.get("content"),
                         **({"tool_calls": msg["tool_calls"]}
                            if msg.get("tool_calls") else {})})
        calls = msg.get("tool_calls") or []
        if not calls:                                    # plain answer -> done
            return msg.get("content") or "", messages

        for tc in calls:                                 # may be several per turn
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            try:
                r = await session.call_tool(name, args)
                if r.isError:
                    body = f"TOOL ERROR: {r.content[0].text if r.content else 'unknown'}"
                elif r.structuredContent is not None:
                    body = json.dumps(r.structuredContent)
                else:
                    body = "\n".join(c.text for c in r.content
                                     if getattr(c, "text", None))
            except Exception as e:                       # transport-level failure
                body = f"TOOL ERROR: {type(e).__name__}: {e}"
            messages.append({"role": "tool", "tool_call_id": tc["id"],
                             "content": body[:20_000]})   # cap what re-enters context

    return ("[stopped: max_rounds tool iterations reached without a final answer]",
            messages)


# ------------------------------------- reference adapter (copy & edit) ----
_ADAPTER = '''
def openai_compatible(base_url, model, api_key="x", temperature=0):
    """Company LLM / vLLM / any OpenAI-compatible endpoint."""
    from openai import OpenAI
    client = OpenAI(base_url=base_url, api_key=api_key)
    def call_llm(messages, tools):
        r = client.chat.completions.create(model=model, messages=messages,
                                           tools=tools, temperature=temperature)
        m = r.choices[0].message
        return {"content": m.content,
                "tool_calls": [tc.model_dump() for tc in (m.tool_calls or [])] or None}
    return call_llm
'''


# ------------------------------------------------ stdio session helper ----
async def stdio_session(server_cmd: list[str]):
    """Async context manager yielding an initialized session to a stdio server.

        async with stdio_session(["python", "mcp_data_server.py"]) as s:
            text, transcript = await run_agent(msgs, call_llm, s)
    """
    from contextlib import asynccontextmanager
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    @asynccontextmanager
    async def _cm():
        params = StdioServerParameters(command=server_cmd[0], args=server_cmd[1:])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()
                yield s
    return _cm()
