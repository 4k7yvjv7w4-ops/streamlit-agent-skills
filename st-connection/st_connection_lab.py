"""st-connection lab — pooled connection + cached queries, no re-query per rerun.

Run:  python -m streamlit run st_connection_lab.py

Standalone: a custom BaseConnection over stdlib sqlite3 (no SQLAlchemy / no
external DB). Demonstrates: connection pooling, cached queries with ttl, the
re-query-every-rerun trap and its fix, and a manual refresh via .clear().
"""

import sqlite3
import time

import pandas as pd
import streamlit as st
from streamlit.connections import BaseConnection

st.set_page_config(page_title="st-connection lab", layout="wide")
st.title("st-connection — data access without re-querying every rerun")

st.session_state.setdefault("runs", 0)
st.session_state.runs += 1
st.sidebar.metric("full-script runs", st.session_state.runs)


# ---- custom connection over sqlite3 (stdlib) ----------------------------
class SQLiteConnection(BaseConnection[sqlite3.Connection]):
    """Wrap a driver once; `st.connection` pools it via cache_resource."""

    def _connect(self, **kw) -> sqlite3.Connection:
        path = self._secrets.get("path", ":memory:")
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.execute("CREATE TABLE IF NOT EXISTS latency(region TEXT, ms REAL)")
        if not conn.execute("SELECT count(*) FROM latency").fetchone()[0]:
            conn.executemany(
                "INSERT INTO latency VALUES (?,?)",
                [("us-east-1", 100.0), ("eu-west-1", 160.0), ("ap-south-1", 220.0),
                 ("us-east-1", 120.0), ("eu-west-1", 150.0), ("ap-south-1", 240.0)],
            )
            conn.commit()
        return conn

    def query(self, sql: str, ttl=None) -> pd.DataFrame:
        @st.cache_data(ttl=ttl, show_spinner=False)
        def _run(q: str) -> pd.DataFrame:
            # count real DB hits so the demo can prove caching
            st.session_state["db_hits"] = st.session_state.get("db_hits", 0) + 1
            return pd.read_sql(q, self._instance)
        return _run(sql)


conn = st.connection("lat_db", type=SQLiteConnection)   # pooled — one per app

st.session_state.setdefault("db_hits", 0)

tab1, tab2, tab3 = st.tabs(["1 · Cached query", "2 · The trap", "3 · Refresh"])

# --------------------------------------------------------- 1 · cached ----
with tab1:
    st.subheader("Pooled connection + cached query (ttl)")
    st.caption(
        "The connection is created ONCE (cache_resource, inside st.connection); "
        "`conn.query(sql, ttl=...)` caches the result. Flip the widget below and "
        "watch the DB-hit counter stay put while the run counter climbs — same "
        "SQL within the ttl never touches the DB."
    )
    region = st.selectbox("filter region", ["(all)", "us-east-1", "eu-west-1", "ap-south-1"])
    sql = "SELECT region, avg(ms) AS avg_ms, count(*) AS n FROM latency GROUP BY region"
    if region != "(all)":
        sql = f"SELECT region, avg(ms) AS avg_ms, count(*) AS n FROM latency WHERE region = '{region}' GROUP BY region"
    df = conn.query(sql, ttl="10m")
    st.dataframe(df, width="stretch", hide_index=True)
    c1, c2 = st.columns(2)
    c1.metric("real DB hits (cached queries don't add)", st.session_state.db_hits)
    c2.metric("full-script runs", st.session_state.runs)
    st.caption("Distinct SQL (new region) = one new DB hit; repeating it = cache.")

# ------------------------------------------------------------ 2 · trap ----
with tab2:
    st.subheader("Why a bare query re-hits the DB every rerun")
    st.code(
        '''# ❌ runs on EVERY widget touch — slow, hammers the DB
df = pd.read_sql(sql, conn)

# ✅ cached — DB hit only when args change or ttl expires
@st.cache_data(ttl="10m")
def load(_conn, sql): return pd.read_sql(sql, _conn)
df = load(conn, sql)        #  _conn is EXCLUDED from the cache key (underscore)''',
        language="python",
    )
    st.info(
        "The `_conn` underscore is the one everyone forgets: a connection isn't "
        "hashable, so without the `_` prefix you get `UnhashableParamError`. "
        "Prefix any unhashable arg (connection, client, model) to exclude it "
        "from the cache key."
    )

# --------------------------------------------------------- 3 · refresh ----
with tab3:
    st.subheader("Manual refresh — clear the cache, then rerun")
    st.caption(
        "`ttl` refreshes on a schedule; a button forces it now. Clearing the "
        "cached query function and rerunning re-hits the DB."
    )
    st.metric("real DB hits so far", st.session_state.db_hits)
    if st.button("↻ refresh data now"):
        conn.query.__wrapped__ if False else None      # (query builds its own cache)
        st.cache_data.clear()                          # clear all cached queries
        st.session_state.db_hits = 0
        st.rerun()                                     # guarded: button = one-shot
    st.code(
        '''# per-function:  load.clear()      # just this loader
# app-wide:      st.cache_data.clear()
# then st.rerun() behind a flip-first guard (see st-core)''',
        language="python",
    )
