"""mcp_data_server — reference MCP server exposing parquet / SQL / CSV / API.

Run (stdio, for local clients like Roo/desktop hosts):
    python mcp_data_server.py
Run (streamable HTTP, for a shared/company-LLM deployment):
    python mcp_data_server.py --http          # serves on 127.0.0.1:8000/mcp

Self-test (no client needed, in-memory session):
    python test_mcp_server.py

Point it at your data by editing DATA_ROOT / DB_PATH / API_BASE below.
Every tool is READ-ONLY and row-capped: tool output goes into an LLM context,
so returning megabytes is a bug, not a feature.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds
from mcp.server.fastmcp import FastMCP

DATA_ROOT = Path(__file__).resolve().parent / "sample_data"   # parquet lake + csvs
DB_PATH = DATA_ROOT / "app.db"                                 # sqlite for the demo
API_BASE = "https://internal-api.example.invalid"              # your internal API
API_ALLOWED = {"health", "datasets"}                           # endpoint allowlist

HARD_CAP = 500                     # rows, whatever the caller asks for

mcp = FastMCP("data-server")


@mcp.tool()
def list_datasets() -> dict:
    """List available parquet datasets (with their partitions) and CSV files.
    Call this FIRST to discover what exists before querying."""
    lakes = {}
    for d in sorted(DATA_ROOT.glob("*")) if DATA_ROOT.exists() else []:
        if d.is_dir() and any(d.rglob("*.parquet")):
            parts = sorted({p.parent.name for p in d.rglob("*.parquet")})
            lakes[d.name] = parts[:50]
    csvs = [p.name for p in DATA_ROOT.glob("*.csv")] if DATA_ROOT.exists() else []
    return {"parquet_datasets": lakes, "csv_files": csvs}


@mcp.tool()
def query_parquet(dataset: str, date: str, columns: list[str] | None = None,
                  limit: int = 100) -> list[dict]:
    """Read ONE date partition of a hive-partitioned parquet dataset, with
    column projection. `dataset` is a name from list_datasets; `date` like
    '2025-03-01'. Returns at most `limit` rows (hard cap 500). Ask for only
    the columns you need — the read is pushed down, not filtered after."""
    root = DATA_ROOT / dataset
    if not root.is_dir():
        raise ValueError(f"unknown dataset {dataset!r} — call list_datasets first")
    d = ds.dataset(root, format="parquet", partitioning="hive")
    t = d.to_table(filter=ds.field("date") == date, columns=columns)
    return t.to_pylist()[: min(max(limit, 1), HARD_CAP)]


@mcp.tool()
def query_sql(sql: str, limit: int = 100) -> list[dict]:
    """Run a READ-ONLY SQL query (must start with SELECT or WITH) against the
    app database. Returns at most `limit` rows (hard cap 500). Prefer
    aggregated queries over row dumps."""
    if not sql.lstrip().lower().startswith(("select", "with")):
        raise ValueError("read-only server: only SELECT/WITH statements allowed")
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        cur = con.execute(sql)                       # sqlite: single statement only
        return [dict(r) for r in cur.fetchmany(min(max(limit, 1), HARD_CAP))]
    finally:
        con.close()


@mcp.tool()
def read_csv(filename: str, columns: list[str] | None = None,
             limit: int = 100) -> list[dict]:
    """Read a CSV from the data folder (name from list_datasets). Returns at
    most `limit` rows (hard cap 500)."""
    p = (DATA_ROOT / Path(filename).name)            # no path traversal
    if p.suffix != ".csv" or not p.exists():
        raise ValueError(f"unknown csv {filename!r} — call list_datasets first")
    df = pd.read_csv(p, usecols=columns, nrows=min(max(limit, 1), HARD_CAP))
    return df.to_dict("records")


@mcp.tool()
def call_api(endpoint: str, params: dict | None = None) -> dict:
    """GET an allowlisted internal-API endpoint (one of: health, datasets).
    Returns the JSON body. Anything not on the allowlist is refused."""
    if endpoint not in API_ALLOWED:
        raise ValueError(f"endpoint {endpoint!r} not allowlisted: {sorted(API_ALLOWED)}")
    import httpx                                     # lazy: only if actually used
    r = httpx.get(f"{API_BASE}/{endpoint}", params=params or {}, timeout=10)
    r.raise_for_status()
    return r.json()


if __name__ == "__main__":
    if "--http" in sys.argv:
        mcp.run(transport="streamable-http")          # shared deployment
    else:
        mcp.run()                                     # stdio (local host launches it)
