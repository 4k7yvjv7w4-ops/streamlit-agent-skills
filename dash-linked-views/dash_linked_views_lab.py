"""dash-linked-views lab — key input -> one cached fetch -> ZERO-latency linking in the browser.

Run:  python dash_linked_views_lab.py     Test: python test_dash_linked_views.py (headless browser)

  * key dropdown  -> SERVER callback: one cached lake pass -> dcc.Store bundle
  * regions grid click -> CLIENTSIDE callback (JS, ~10 lines): filters the
    detail grid + both charts from the Store. No server round-trip at all —
    the test counts _dash-update-component requests and sees none on click.
The bundle carries ready-made Plotly figures with ONE TRACE PER REGION so the
JS only toggles trace visibility — no figure building in JavaScript.
"""

import json
from pathlib import Path

import dash_ag_grid as dag
import duckdb
import numpy as np
import pandas as pd
import plotly.express as px
import pyarrow as pa
import pyarrow.dataset as pads
from dash import Dash, Input, Output, callback, clientside_callback, dcc, html
from flask_caching import Cache

ROOT = Path(__file__).resolve().parent / "sample_data"
SERVICES = ["auth", "search", "media", "billing"]
FETCHES = {"n": 0}


def make_lake() -> None:
    rng = np.random.default_rng(0)
    rows = [(d.date().isoformat(), s, r, ep, round(float(rng.uniform(40, 400)), 1),
             int(rng.integers(50, 5000)))
            for d in pd.date_range("2025-03-01", periods=15) for s in SERVICES
            for r in ["us-east-1", "eu-west-1", "ap-south-1"] for ep in ["/list", "/get", "/put"]]
    df = pd.DataFrame(rows, columns=["date", "service", "region", "endpoint", "latency_ms", "requests"])
    pads.write_dataset(pa.Table.from_pandas(df, preserve_index=False), ROOT / "events",
                       format="parquet", partitioning=["date"], partitioning_flavor="hive",
                       existing_data_behavior="delete_matching")


_CON = None


def db() -> duckdb.DuckDBPyConnection:
    global _CON
    if _CON is None:
        ROOT.mkdir(exist_ok=True); make_lake()
        _CON = duckdb.connect()
        _CON.execute(f"CREATE VIEW events AS SELECT * FROM read_parquet("
                     f"'{ROOT}/events/*/*.parquet', hive_partitioning=true)")
    return _CON


app = Dash(__name__)
cache = Cache(app.server, config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 600})


def fig_json(fig) -> dict:
    return json.loads(fig.to_json())                  # Store-safe (dates/numpy -> JSON)


@cache.memoize()
def fetch_bundle(service: str) -> dict:
    """ONE lake pass per key; everything the linked views need, Store-safe."""
    FETCHES["n"] += 1
    cur = db().cursor()
    base = "FROM events WHERE service = ?"
    regions = cur.execute(f"""SELECT region, round(avg(latency_ms),1) AS avg_ms, sum(requests) AS requests
                              {base} GROUP BY region ORDER BY avg_ms DESC""", [service]).df()
    detail = cur.execute(f"""SELECT region, endpoint, round(avg(latency_ms),1) AS avg_ms,
                                    sum(requests) AS requests {base} GROUP BY 1,2 ORDER BY 1,2""",
                         [service]).df()
    daily = cur.execute(f"""SELECT date, region, round(avg(latency_ms),1) AS avg_ms
                            {base} GROUP BY 1,2 ORDER BY 1""", [service]).df()
    return {
        "regions": regions.to_dict("records"),
        "detail": detail.to_dict("records"),
        # one trace per region (trace.name == region) -> JS toggles visibility
        "daily_fig": fig_json(px.line(daily, x="date", y="avg_ms", color="region",
                                      title=f"{service}: daily p95")),
        "bars_fig": fig_json(px.bar(detail, x="endpoint", y="requests", color="region",
                                    barmode="group", title="requests by endpoint")),
    }


grid = dict(defaultColDef={"sortable": True, "resizable": True}, columnSize="sizeToFit",
            dashGridOptions={"animateRows": False})

app.layout = html.Div(style={"maxWidth": "1100px", "margin": "auto"}, children=[
    html.H3("dash-linked-views — one fetch per key, zero-latency linking"),
    dcc.Dropdown(id="svc", options=SERVICES, value="auth", clearable=False, style={"width": 260}),
    html.Div(id="fetches"),
    dcc.Store(id="bundle"),
    html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 2fr", "gap": "12px"}, children=[
        html.Div([
            html.Small("click a region → everything else filters, in the browser"),
            dag.AgGrid(id="regions", columnDefs=[{"field": c} for c in ["region", "avg_ms", "requests"]],
                       getRowId="params.data.region", style={"height": 200},
                       **{**grid, "dashGridOptions": {"rowSelection": "single", "animateRows": False}}),
            html.Div(id="status", children="all regions"),
        ]),
        html.Div([dcc.Graph(id="daily", style={"height": 230}),
                  dcc.Graph(id="bars", style={"height": 200})]),
    ]),
    dag.AgGrid(id="detail", columnDefs=[{"field": c} for c in ["region", "endpoint", "avg_ms", "requests"]],
               getRowId="params.data.region + params.data.endpoint", style={"height": 260}, **grid),
])


@callback(Output("bundle", "data"), Output("fetches", "children"),
          Output("regions", "rowData"), Output("regions", "selectedRows"),
          Input("svc", "value"))
def load(svc):                                        # SERVER: once per key change
    b = fetch_bundle(svc)
    return b, f"lake fetches this process: {FETCHES['n']}", b["regions"], []


clientside_callback(                                  # BROWSER: every click, zero server trips
    """
    function(selected, bundle) {
        if (!bundle) { return [[], {}, {}, ""]; }
        const region = (selected && selected.length) ? selected[0].region : null;
        const rows = region ? bundle.detail.filter(r => r.region === region) : bundle.detail;
        const show = (fig) => {
            const f = JSON.parse(JSON.stringify(fig));            // never mutate the Store
            f.data.forEach(t => { t.visible = (!region || t.name === region) ? true : 'legendonly'; });
            return f;
        };
        return [rows, show(bundle.daily_fig), show(bundle.bars_fig),
                region ? ("filter: " + region) : "all regions"];
    }
    """,
    Output("detail", "rowData"), Output("daily", "figure"), Output("bars", "figure"),
    Output("status", "children"),
    Input("regions", "selectedRows"), Input("bundle", "data"),
)

if __name__ == "__main__":
    app.run(debug=True)
