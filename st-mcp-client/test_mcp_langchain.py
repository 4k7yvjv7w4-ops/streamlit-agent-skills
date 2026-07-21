"""Self-test for the LangChain⇄MCP path — adapters + scripted model, no key.

Run:  python test_mcp_langchain.py
Needs: pip install langchain-mcp-adapters langchain-core  (the live path adds
langchain-openai). Drives the REAL reference server through langchain-mcp-
adapters and a scripted AIMessage sequence standing in for ChatOpenAI.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "st-mcp-server"))
import mcp_data_server as srv
from test_mcp_server import make_fixtures

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.shared.memory import create_connected_server_and_client_session


async def main() -> None:
    make_fixtures()
    async with create_connected_server_and_client_session(srv.mcp._mcp_server) as s:
        # 1) MCP tools -> LangChain BaseTools (name/description/args carried over)
        tools = await load_mcp_tools(s)
        by = {t.name: t for t in tools}
        assert set(by) == {"list_datasets", "query_parquet", "query_sql",
                           "read_csv", "call_api"}
        assert list(by["query_parquet"].args) == ["dataset", "date", "columns", "limit"]
        assert by["query_sql"].description.startswith("Run a READ-ONLY")
        print("PASS load_mcp_tools: 5 tools, args + descriptions carried over")

        # 2) direct execution the LangChain way
        out = await by["query_sql"].ainvoke(
            {"sql": "SELECT region, sla_ms FROM regions ORDER BY sla_ms LIMIT 1"})
        assert "us-east-1" in str(out)
        print("PASS ainvoke: tool executed against the MCP server")

        # 3) server-side isError -> returned as TEXT the model can read (no raise)
        bad = await by["query_sql"].ainvoke({"sql": "DELETE FROM regions"})
        assert "read-only" in str(bad)
        print("PASS errors: isError surfaces as tool-result text (handle_tool_errors)")

        # 4) the bounded loop, with scripted AIMessages standing in for the LLM.
        #    NOTE: LangChain tool_calls carry args as a PARSED DICT (not JSON str).
        script = iter([
            AIMessage(content="", tool_calls=[{
                "name": "query_sql", "id": "c1",
                "args": {"sql": "SELECT region FROM regions ORDER BY sla_ms LIMIT 1"}}]),
            AIMessage(content="Lowest-SLA region is us-east-1."),
        ])
        msgs: list = [HumanMessage("which region has the lowest sla?")]
        for _ in range(4):                                   # max_rounds bound
            ai = next(script)             # live: ai = await llm_with_tools.ainvoke(msgs)
            msgs.append(ai)
            if not ai.tool_calls:
                break
            for tc in ai.tool_calls:                         # several per turn possible
                r = await by[tc["name"]].ainvoke(tc["args"])
                msgs.append(ToolMessage(content=str(r)[:20_000],
                                        tool_call_id=tc["id"]))
        assert [m.__class__.__name__ for m in msgs] == \
            ["HumanMessage", "AIMessage", "ToolMessage", "AIMessage"]
        assert "us-east-1" in str(msgs[2].content) and "us-east-1" in msgs[-1].content
        print("PASS loop: Human -> AI(tool_calls) -> Tool -> AI final answer")

    print("\nALL OK")


if __name__ == "__main__":
    asyncio.run(main())
