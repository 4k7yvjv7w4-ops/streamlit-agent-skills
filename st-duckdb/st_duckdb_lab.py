"""st-duckdb lab — SQL over a parquet lake inside Streamlit.

Run:  python -m streamlit run st_duckdb_lab.py

Builds a tiny local hive-partitioned lake (sample_data/, gitignored) standing
in for s3://… — the code is identical on S3 after INSTALL httpfs + a secret
(see SKILL.md). Tabs:
  1. cached connection + views + cache_data'd query (watch the scan counter)
  2. register(): join a WIDGET-driven in-memory frame with the lake
  3. results out: .df() vs .to_arrow_table() into st.dataframe
"""

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as pads
import streamlit as st

st.set_page_config(page_title="st-duckdb lab", layout="wide")
st.title("st-duckdb — SQL over the lake, inside the app")

ROOT = Path(__file__).resolve().parent / "sample_data"


def make_lake() -> None:
    rng = np.random.default_rng(0)
    days = ["2025-03-01", "2025-03-02", "2025-03-03"]
    rows = []
    for d in days:
        for r in ["us-east-1", "eu-west-1", "ap-south-1"]:
            for _ in range(400):
                rows.append((d, r, round(float(rng.uniform(40, 400)), 1)))
    df = pd.DataFrame(rows, columns=["date", "region", "latency_ms"])
    pads.write_dataset(pa.Table.from_pandas(df, preserve_index=False),
                       ROOT / "lake", format="parquet", partitioning=["date"],
                       partitioning_flavor="hive",
                       existing_data_behavior="delete_matching")
    pd.DataFrame({"region": ["us-east-1", "eu-west-1", "ap-south-1"],
                  "sla_ms": [150, 160, 250]}).to_csv(ROOT / "sla.csv", index=False)


@st.cache_resource                          # ONE connection per process
def db() -> duckdb.DuckDBPyConnection:
    ROOT.mkdir(exist_ok=True)
    make_lake()
    con = duckdb.connect()
    con.execute(f"CREATE VIEW events AS SELECT * FROM "
                f"read_parquet('{ROOT}/lake/*/*.parquet', hive_partitioning=true)")
    con.execute(f"CREATE VIEW sla AS SELECT * FROM read_csv_auto('{ROOT}/sla.csv')")
    return con


st.session_state.setdefault("scans", 0)


@st.cache_data(ttl="10m", show_spinner=False)
def q(sql: str) -> pd.DataFrame:            # sql string IS the cache key
    st.session_state.scans += 1             # count REAL lake scans
    return db().cursor().execute(sql).df()  # cursor per operation


tab1, tab2, tab3 = st.tabs(["1 · Query + cache", "2 · register(): memory ⋈ lake",
                            "3 · df vs arrow"])

with tab1:
    st.caption(
        "One cached connection with views; queries go through a cursor and the "
        "RESULT is cache_data'd — flip the selectbox: a new date = one real scan, "
        "repeats are cache hits. Swap the local root for s3://… and this code "
        "does not change."
    )
    day = st.selectbox("date", ["2025-03-01", "2025-03-02", "2025-03-03"], key="day")
    df = q(f"""SELECT e.region, avg(e.latency_ms) AS avg_ms,
                      any_value(s.sla_ms) AS sla_ms,
                      avg(e.latency_ms) > any_value(s.sla_ms) AS breach
               FROM events e JOIN sla s USING(region)
               WHERE e.date = DATE '{day}'
               GROUP BY e.region ORDER BY avg_ms DESC""")
    st.dataframe(df, hide_index=True, width="stretch")
    c1, c2 = st.columns(2)
    c1.metric("real lake scans", st.session_state.scans)
    c2.metric("rows returned (not scanned)", len(df))
    st.caption("Aggregate in SQL; the page only ever receives a few rows.")

with tab2:
    st.caption(
        "The Streamlit superpower: a WIDGET-driven frame joins the lake via "
        "register() — no temp files. Edit the override SLAs and watch breaches flip."
    )
    edited = st.data_editor(
        pd.DataFrame({"region": ["us-east-1", "eu-west-1", "ap-south-1"],
                      "new_sla": [120, 200, 200]}),
        hide_index=True, key="overrides")
    cur = db().cursor()
    cur.register("overrides", edited)       # in-memory frame -> table name
    j = cur.execute("""SELECT e.region, avg(e.latency_ms) AS avg_ms,
                              any_value(o.new_sla) AS new_sla,
                              avg(e.latency_ms) > any_value(o.new_sla) AS breach
                       FROM events e JOIN overrides o USING(region)
                       GROUP BY e.region ORDER BY avg_ms DESC""").df()
    st.dataframe(j, hide_index=True, width="stretch")

with tab3:
    st.caption(
        "Two ways out of DuckDB: .df() -> pandas, .to_arrow_table() -> pyarrow "
        "Table (st.dataframe takes it directly; fetch_arrow_table() is deprecated)."
    )
    cur = db().cursor()
    left, right = st.columns(2)
    with left:
        st.subheader(".df()")
        st.dataframe(cur.execute("SELECT * FROM events LIMIT 5").df(),
                     hide_index=True, width="stretch")
    with right:
        st.subheader(".to_arrow_table()")
        st.dataframe(cur.execute("SELECT * FROM events LIMIT 5").to_arrow_table(),
                     width="stretch")
    st.caption("Always LIMIT/aggregate in SQL before materializing — never "
               "`SELECT *` a lake into .df().")
