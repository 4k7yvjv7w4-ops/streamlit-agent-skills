"""Self-test for mcp_duck_server — cross-source joins through a real MCP session.

Run:  python test_mcp_duck.py
"""
import asyncio
import json
import sqlite3

import pandas as pd

import mcp_duck_server as duck
from test_mcp_server import make_fixtures
from mcp.shared.memory import create_connected_server_and_client_session


def extra_fixtures() -> None:
    make_fixtures()                                       # parquet lake + app.db
    # a CSV sharing the join key with the parquet lake
    con = sqlite3.connect(duck.DATA_ROOT / "app.db")
    rows = con.execute("SELECT region, sla_ms FROM regions").fetchall()
    con.close()
    pd.DataFrame(rows, columns=["region", "sla_ms"]).to_csv(
        duck.DATA_ROOT / "regions.csv", index=False)


async def main() -> None:
    extra_fixtures()
    async with create_connected_server_and_client_session(duck.mcp._mcp_server) as c:
        tools = {t.name for t in (await c.list_tools()).tools}
        assert tools == {"describe_schema", "query_sql"}, tools

        r = await c.call_tool("describe_schema", {})
        schema = json.loads(r.content[0].text)
        assert set(schema["tables"]) == {"events", "regions"}
        assert "join" in schema["join_keys"]["events"].lower()
        print("PASS describe_schema: tables + documented join keys:",
              list(schema["tables"]))

        # ONE SQL join across parquet lake + CSV, aggregated server-side
        q = ("SELECT e.region, avg(e.latency_ms) AS avg_ms, any_value(r.sla_ms) AS sla_ms "
             "FROM events e JOIN regions r USING(region) "
             "WHERE e.date = DATE '2025-03-02' GROUP BY e.region ORDER BY avg_ms")
        r = await c.call_tool("query_sql", {"sql": q})
        rows = r.structuredContent["result"]
        assert len(rows) == 3 and {"region", "avg_ms", "sla_ms"} <= set(rows[0])
        print("PASS join: parquet ⋈ csv in one call ->", rows[0])

        r = await c.call_tool("query_sql", {"sql": "DROP VIEW events"})
        assert r.isError
        r = await c.call_tool("query_sql",
                              {"sql": "SELECT 1; DROP VIEW events"})
        assert r.isError and "chaining" in r.content[0].text
        print("PASS guards: non-SELECT and ';' chaining both refused")

        r = await c.call_tool("query_sql",
                              {"sql": "SELECT * FROM events", "limit": 2})
        assert len(r.structuredContent["result"]) == 2
        print("PASS cap: limit respected")

    print("\nALL OK")


if __name__ == "__main__":
    asyncio.run(main())
