"""dash-data lab — data access in Dash: singleton connection, shared cache, Store-safe results.

Run:  python dash_data_lab.py        Test: python test_dash_data.py

Streamlit habits translated:
  cache_resource  -> module-level singleton (one DuckDB connection per PROCESS)
  cache_data      -> flask_caching memoize (SHARED by all users; TTL; key = args)
  DataFrame out   -> JSON-able records for dcc.Store (never a DataFrame)
The lake is the same hive layout as [st-duckdb]; swap sample_data/ for your
S3 route (pyarrow dataset + wrapper) — that code is framework-agnostic.
"""

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as pads
from dash import Dash, Input, Output, callback, dash_table, dcc, html
from flask_caching import Cache

ROOT = Path(__file__).resolve().parent / "sample_data"
SERVICES = ["auth", "search", "media"]
FETCHES = {"n": 0}                                   # proof counter (process-wide)


def make_lake() -> None:
    rng = np.random.default_rng(0)
    rows = [(d.date().isoformat(), s, r, round(float(rng.uniform(40, 400)), 1),
             int(rng.integers(50, 5000)))
            for d in pd.date_range("2025-03-01", periods=10)
            for s in SERVICES for r in ["us-east-1", "eu-west-1", "ap-south-1"]]
    df = pd.DataFrame(rows, columns=["date", "service", "region", "latency_ms", "requests"])
    pads.write_dataset(pa.Table.from_pandas(df, preserve_index=False), ROOT / "events",
                       format="parquet", partitioning=["date"], partitioning_flavor="hive",
                       existing_data_behavior="delete_matching")


_CON: duckdb.DuckDBPyConnection | None = None


def db() -> duckdb.DuckDBPyConnection:
    """Module singleton == st.cache_resource. Shared, read-only: safe as a global."""
    global _CON
    if _CON is None:
        ROOT.mkdir(exist_ok=True)
        make_lake()
        _CON = duckdb.connect()
        _CON.execute(f"CREATE VIEW events AS SELECT * FROM read_parquet("
                     f"'{ROOT}/events/*/*.parquet', hive_partitioning=true)")
    return _CON


app = Dash(__name__)
cache = Cache(app.server, config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 600})


@cache.memoize()                                     # == st.cache_data(ttl=600) but SHARED
def fetch_regions(service: str) -> list[dict]:       # key = args -> primitives only
    FETCHES["n"] += 1
    cur = db().cursor()                              # cursor per call (thread-safe)
    df = cur.execute("""SELECT region, round(avg(latency_ms), 1) AS avg_ms,
                               sum(requests) AS requests
                        FROM events WHERE service = ? GROUP BY region
                        ORDER BY avg_ms DESC""", [service]).df()
    return df.to_dict("records")                     # JSON-able -> dcc.Store safe


app.layout = html.Div(style={"maxWidth": "720px", "margin": "auto"}, children=[
    html.H3("dash-data — singleton connection + shared cache"),
    dcc.Dropdown(id="svc", options=SERVICES, value="auth", clearable=False),
    dcc.Store(id="regions"),
    dash_table.DataTable(id="tbl", columns=[{"name": c, "id": c}
                                            for c in ["region", "avg_ms", "requests"]]),
    html.Div(id="fetches"),
])


@callback(Output("regions", "data"), Output("fetches", "children"), Input("svc", "value"))
def load(svc):
    rows = fetch_regions(svc)
    return rows, f"lake fetches this process: {FETCHES['n']} (shared across ALL users)"


@callback(Output("tbl", "data"), Input("regions", "data"))
def show(rows):
    return rows or []


if __name__ == "__main__":
    app.run(debug=True)
