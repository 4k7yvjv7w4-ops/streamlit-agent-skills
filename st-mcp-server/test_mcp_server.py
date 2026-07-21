"""Self-test for mcp_data_server — in-memory MCP session, no client app needed.

Run:  python test_mcp_server.py
Builds throwaway sample data, then drives the REAL server through a real MCP
client session (list_tools + call_tool), asserting schemas, caps, and guards.
"""
import asyncio
import json
import sqlite3

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds

import mcp_data_server as srv
from mcp.shared.memory import create_connected_server_and_client_session


def make_fixtures() -> None:
    root = srv.DATA_ROOT
    root.mkdir(exist_ok=True)
    df = pd.DataFrame({
        "date": ["2025-03-01"] * 3 + ["2025-03-02"] * 3,
        "region": ["us-east-1", "eu-west-1", "ap-south-1"] * 2,
        "latency_ms": [110.0, 140.0, 220.0, 115.0, 138.0, 210.0],
    })
    ds.write_dataset(pa.Table.from_pandas(df, preserve_index=False), root / "latency",
                     format="parquet", partitioning=["date"], partitioning_flavor="hive",
                     existing_data_behavior="delete_matching")
    df.head(4).to_csv(root / "sample.csv", index=False)
    con = sqlite3.connect(srv.DB_PATH)
    con.execute("CREATE TABLE IF NOT EXISTS regions(region TEXT, sla_ms REAL)")
    con.execute("DELETE FROM regions")
    con.executemany("INSERT INTO regions VALUES (?,?)",
                    [("us-east-1", 150), ("eu-west-1", 160), ("ap-south-1", 250)])
    con.commit(); con.close()


async def main() -> None:
    make_fixtures()
    async with create_connected_server_and_client_session(srv.mcp._mcp_server) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
        assert set(tools) == {"list_datasets", "query_parquet", "query_sql",
                              "read_csv", "call_api"}, sorted(tools)
        # type hints became the JSON schema; required = args without defaults
        qp = tools["query_parquet"].inputSchema
        assert qp["required"] == ["dataset", "date"], qp
        print("PASS schemas: 5 tools, required args derived from type hints")

        r = await c.call_tool("list_datasets", {})
        listing = json.loads(r.content[0].text)
        assert "latency" in listing["parquet_datasets"], listing
        print("PASS list_datasets:", listing)

        r = await c.call_tool("query_parquet", {"dataset": "latency",
                                                "date": "2025-03-02",
                                                "columns": ["region", "latency_ms"]})
        rows = r.structuredContent["result"]
        assert len(rows) == 3 and set(rows[0]) == {"region", "latency_ms"}, rows
        print("PASS query_parquet: partition + projection pushdown,", len(rows), "rows")

        r = await c.call_tool("query_sql",
                              {"sql": "SELECT region, sla_ms FROM regions ORDER BY sla_ms",
                               "limit": 2})
        assert len(r.structuredContent["result"]) == 2
        print("PASS query_sql: rows capped by limit")

        r = await c.call_tool("query_sql", {"sql": "DELETE FROM regions"})
        assert r.isError and "read-only" in r.content[0].text
        print("PASS write blocked -> isError with message (not a crash)")

        r = await c.call_tool("read_csv", {"filename": "../../etc/passwd.csv"})
        assert r.isError
        r = await c.call_tool("read_csv", {"filename": "sample.csv", "limit": 2})
        assert len(r.structuredContent["result"]) == 2
        print("PASS read_csv: traversal refused, cap respected")

        r = await c.call_tool("call_api", {"endpoint": "not-allowed"})
        assert r.isError and "allowlisted" in r.content[0].text
        print("PASS call_api: non-allowlisted endpoint refused")

    print("\nALL OK")


if __name__ == "__main__":
    asyncio.run(main())
