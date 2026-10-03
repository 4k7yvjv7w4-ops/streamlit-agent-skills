"""st-linked-views lab — one cached fetch per key, fragment-scoped linking.

Run:  python -m streamlit run st_linked_views_lab.py

The pattern for "type a code, see several linked tables + charts, click one
to filter the others — fast":
  * KEY INPUT (outside the fragment)  -> ONE cached DuckDB fetch per key
  * FRAGMENT holds every linked view  -> a click reruns only the fragment,
    never re-queries (the bundle is passed in, not re-fetched)
  * selection -> Python filter -> sibling table + charts
Synthetic lake: service-latency telemetry, hive-partitioned by date and
SORTED BY the key (service) inside each partition so `WHERE service = X`
is a zone-map hit. Swap sample_data/ for s3://… — the code does not change.
"""

from pathlib import Path

import altair as alt
import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as pads
import streamlit as st

st.set_page_config(page_title="linked views", layout="wide")
ROOT = Path(__file__).resolve().parent / "sample_data"
SERVICES = ["auth", "search", "media", "billing", "export"]


def make_lake() -> None:
    rng = np.random.default_rng(0)
    rows = []
    for d in pd.date_range("2025-03-01", periods=20):
        for svc in SERVICES:                       # sorted by key within partition
            for region in ["us-east-1", "eu-west-1", "ap-south-1"]:
                for ep in ["/list", "/get", "/put"]:
                    rows.append((d.date().isoformat(), svc, region, ep,
                                 round(float(rng.uniform(40, 400)), 1),
                                 int(rng.integers(50, 5000))))
    df = pd.DataFrame(rows, columns=["date", "service", "region", "endpoint",
                                     "latency_ms", "requests"])
    pads.write_dataset(pa.Table.from_pandas(df, preserve_index=False),
                       ROOT / "events", format="parquet", partitioning=["date"],
                       partitioning_flavor="hive",
                       existing_data_behavior="delete_matching")


@st.cache_resource
def db() -> duckdb.DuckDBPyConnection:
    ROOT.mkdir(exist_ok=True)
    make_lake()
    con = duckdb.connect()
    con.execute(f"CREATE VIEW events AS SELECT * FROM read_parquet("
                f"'{ROOT}/events/*/*.parquet', hive_partitioning=true)")
    return con


st.session_state.setdefault("fetches", 0)


@st.cache_data(ttl="10m", show_spinner=False)
def fetch_bundle(service: str) -> dict[str, pd.DataFrame]:
    """ONE lake pass per key: every linked view's data, as small frames."""
    st.session_state.fetches += 1                      # proof counter
    cur = db().cursor()
    base = f"FROM events WHERE service = '{service}'"
    return {
        "regions": cur.execute(f"""SELECT region, avg(latency_ms) AS avg_ms,
                                          sum(requests) AS requests {base}
                                   GROUP BY region ORDER BY avg_ms DESC""").df(),
        "detail": cur.execute(f"""SELECT region, endpoint, avg(latency_ms) AS avg_ms,
                                         sum(requests) AS requests {base}
                                  GROUP BY region, endpoint""").df(),
        "daily": cur.execute(f"""SELECT date, region, avg(latency_ms) AS avg_ms
                                 {base} GROUP BY date, region ORDER BY date""").df(),
    }


def apply_selection(bundle: dict, region: str | None) -> dict[str, pd.DataFrame]:
    """Pure Python filter: selected region -> sibling views. None = all."""
    if region is None:
        return bundle
    return {k: (v[v["region"] == region] if "region" in v and k != "regions" else v)
            for k, v in bundle.items()}


@st.fragment
def linked_views(bundle: dict) -> None:
    """Everything that reacts to CLICKS lives here; clicks rerun ONLY this."""
    left, right = st.columns([1, 2])
    with left:
        st.caption("click a region → filters the rest (fragment rerun, no query)")
        ev = st.dataframe(bundle["regions"], hide_index=True, width="stretch",
                          on_select="rerun", selection_mode="single-row",
                          key="regions_grid")
        rows = ev["selection"]["rows"]                 # [] when nothing selected
        region = bundle["regions"].iloc[rows[0]]["region"] if rows else None
        st.metric("selected", region or "all regions")
    views = apply_selection(bundle, region)
    with right:
        st.altair_chart(
            alt.Chart(views["daily"]).mark_line().encode(
                x="date:T", y=alt.Y("avg_ms:Q", scale=alt.Scale(zero=False)),
                color="region:N").properties(height=220),
            width="stretch")
        st.altair_chart(
            alt.Chart(views["detail"]).mark_bar().encode(
                x="endpoint:N", y="requests:Q", color="region:N",
                tooltip=["region", "endpoint", "requests"]).properties(height=160),
            width="stretch")
    st.dataframe(views["detail"], hide_index=True, width="stretch")


# ---------------- page ----------------
st.title("Linked views — one fetch per key, instant-feel linking")
service = st.selectbox("service code (the key input)", SERVICES, key="service")
bundle = fetch_bundle(service)                        # outside the fragment
st.caption(f"lake fetches this session: {st.session_state.fetches} "
           "(changes only when the key changes — clicks below never re-query)")
linked_views(bundle)

with st.expander("free-form explore (Perspective, optional)"):
    try:
        from streamlit_perspective import perspective_static
        perspective_static(bundle["detail"], key="explore", height=360)
    except ImportError:
        st.caption("pip install streamlit-perspective for a drag-drop pivot of the "
                   "same bundle — a supporting panel, not the linking fabric "
                   "(its clicks never reach Python; see [st-perspective]).")
