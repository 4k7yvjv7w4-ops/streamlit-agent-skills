"""Self-test for mcp_llm_bridge — MOCK LLM + in-memory MCP server.

Run:  python test_mcp_bridge.py     (no API key, no network)

Verifies: MCP->OpenAI schema conversion, the tool-call loop (LLM asks for a
tool, gets the result back, answers), error passthrough as TOOL ERROR, and
the max_rounds bound on a model that never stops calling tools.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "st-mcp-server"))
import mcp_data_server as srv                      # reuse the reference server
from test_mcp_server import make_fixtures
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_llm_bridge import mcp_tools_to_openai, run_agent


def scripted_llm(script):
    """A fake OpenAI-compatible model that plays back scripted turns."""
    it = iter(script)
    def call_llm(messages, tools):
        assert any(t["function"]["name"] == "query_sql" for t in tools)
        return next(it)
    return call_llm


async def main():
    make_fixtures()
    async with create_connected_server_and_client_session(srv.mcp._mcp_server) as s:
        # 1) conversion: MCP schemas -> OpenAI tools payload
        tools = mcp_tools_to_openai((await s.list_tools()).tools)
        by_name = {t["function"]["name"]: t for t in tools}
        assert by_name["query_parquet"]["function"]["parameters"]["required"] == \
            ["dataset", "date"]
        assert by_name["query_sql"]["function"]["description"].startswith("Run a READ-ONLY")
        print("PASS conversion: 5 tools, schema + description carried over")

        # 2) full loop: model calls a tool, reads result, answers
        script = [
            {"content": None, "tool_calls": [{"id": "c1", "function": {
                "name": "query_sql",
                "arguments": json.dumps({"sql": "SELECT region, sla_ms FROM regions "
                                                "ORDER BY sla_ms LIMIT 1"})}}]},
            {"content": "Lowest SLA region is us-east-1 (150ms).", "tool_calls": None},
        ]
        msgs = [{"role": "user", "content": "which region has the lowest SLA?"}]
        text, transcript = await run_agent(msgs, scripted_llm(script), s)
        assert "us-east-1" in text
        toolmsg = next(m for m in transcript if m["role"] == "tool")
        assert "us-east-1" in toolmsg["content"] and toolmsg["tool_call_id"] == "c1"
        print("PASS loop: tool result fed back, final answer returned")
        print("     transcript roles:", [m["role"] for m in transcript])

        # 3) tool error surfaces as TOOL ERROR (model can react), not a crash
        script = [
            {"content": None, "tool_calls": [{"id": "c2", "function": {
                "name": "query_sql", "arguments": json.dumps({"sql": "DELETE FROM regions"})}}]},
            {"content": "That query is not allowed; the server is read-only.",
             "tool_calls": None},
        ]
        text, transcript = await run_agent(
            [{"role": "user", "content": "clear the table"}], scripted_llm(script), s)
        assert any(m["role"] == "tool" and m["content"].startswith("TOOL ERROR")
                   for m in transcript)
        print("PASS error path: isError -> 'TOOL ERROR: ...' message to the model")

        # 4) a model that never answers is bounded by max_rounds
        loop_forever = lambda messages, tools: {"content": None, "tool_calls": [
            {"id": "x", "function": {"name": "list_datasets", "arguments": "{}"}}]}
        text, _ = await run_agent([{"role": "user", "content": "hi"}],
                                  loop_forever, s, max_rounds=3)
        assert text.startswith("[stopped: max_rounds")
        print("PASS bound: runaway tool-calling stops at max_rounds")

    print("\nALL OK")


if __name__ == "__main__":
    asyncio.run(main())
