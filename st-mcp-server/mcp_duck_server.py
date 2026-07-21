"""mcp_duck_server — MCP server with JOINS across parquet + CSV via DuckDB.

Use this variant when your sources share keys (multiple parquet datasets and
CSVs with common id columns): the model writes ONE SQL statement and the join
happens server-side — never make the LLM merge rows from separate tools in
its own context.

Run:        python mcp_duck_server.py            (stdio; --http for shared)
Self-test:  python test_mcp_duck.py

Edit SOURCES to point at your files. DuckDB queries them IN PLACE (no ETL,
no copy) with predicate/projection/partition pushdown into parquet.
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
from mcp.server.fastmcp import FastMCP

DATA_ROOT = Path(__file__).resolve().parent / "sample_data"
HARD_CAP = 500

# name -> (reader SQL, documented join key(s)) — the docs are FOR THE MODEL
SOURCES: dict[str, tuple[str, str]] = {
    "events":   (f"read_parquet('{DATA_ROOT}/latency/*/*.parquet', hive_partitioning=true)",
                 "region (join to regions.region); partitioned by date"),
    "regions":  (f"read_csv_auto('{DATA_ROOT}/regions.csv')",
                 "region (join to events.region)"),
}

mcp = FastMCP("duck-server")


def _con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()                       # per-call: no shared cursor state
    for name, (reader, _doc) in SOURCES.items():
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM {reader}")
    return con


@mcp.tool()
def describe_schema() -> dict:
    """Tables, their columns/types, and the JOIN KEYS between them. Call this
    FIRST and use the documented keys — do not guess join columns."""
    con = _con()
    try:
        cols: dict[str, list] = {}
        for tbl, col, typ in con.execute(
                "SELECT table_name, column_name, data_type "
                "FROM information_schema.columns ORDER BY table_name").fetchall():
            cols.setdefault(tbl, []).append(f"{col} {typ}")
        return {"tables": cols,
                "join_keys": {n: doc for n, (_r, doc) in SOURCES.items()}}
    finally:
        con.close()


@mcp.tool()
def query_sql(sql: str, limit: int = 100) -> list[dict]:
    """Run ONE read-only SQL statement (SELECT/WITH) over ALL sources — joins
    across parquet and CSV are allowed and encouraged (see describe_schema for
    keys). Prefer aggregated results; at most `limit` rows (hard cap 500)."""
    s = sql.strip()
    if not s.lower().startswith(("select", "with")) or ";" in s.rstrip(";"):
        raise ValueError("read-only server: ONE SELECT/WITH statement, no ';' chaining")
    con = _con()
    try:
        cur = con.execute(s.rstrip(";"))
        names = [d[0] for d in cur.description]
        rows = cur.fetchmany(min(max(limit, 1), HARD_CAP))
        return [dict(zip(names, r, strict=True)) for r in rows]
    finally:
        con.close()


if __name__ == "__main__":
    mcp.run(transport="streamable-http" if "--http" in sys.argv else "stdio")
