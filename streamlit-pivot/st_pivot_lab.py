"""streamlit-pivot lab — click any level (top → leaf) → chart from a SECOND frame.

Run:  python -m streamlit run streamlit-pivot/st_pivot_lab.py
(needs `pip install streamlit-pivot`; restart the server after installing —
the component manifest is scanned at server start.)

Use case: a WIDE detail frame for one date drives a hierarchy pivot; clicking
any node (a top-level team, or a leaf service) charts THAT level's history from
a separate skinny frame. The depth of the click payload's `filters` dict IS the
level, so one handler serves every tier — and AG Grid can't do this at all
(its getSelectedRows returns leaf rows only; group clicks reach Python as None).
"""

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="st-pivot lab", layout="wide")
st.title("Click any level → chart from a second frame")

TEAMS = {"Platform": ["auth-api", "gateway"], "Data": ["ingest", "query-svc"],
         "Web": ["storefront"]}


@st.cache_data
def detail_for_today() -> pd.DataFrame:
    """WIDE frame: lots of columns for ONE date, nested team → service."""
    rng = np.random.default_rng(0)
    return pd.DataFrame([
        {"team": t, "service": s,
         "latency": round(rng.uniform(80, 300), 1),
         "requests": int(rng.uniform(1e6, 5e7)),
         "error_rate": round(rng.uniform(0, 3), 2)}
        for t, svcs in TEAMS.items() for s in svcs
    ])


@st.cache_data
def history() -> pd.DataFrame:
    """SKINNY second frame: per-service latency series over time (finest grain)."""
    rng = np.random.default_rng(1)
    dates = pd.date_range("2026-01-01", periods=120, freq="D")
    return pd.concat([
        pd.DataFrame({"date": dates, "team": t, "service": s,
                      "latency": 150 + np.cumsum(rng.normal(0, 1.5, 120))})
        for t, svcs in TEAMS.items() for s in svcs
    ], ignore_index=True)


st.caption(
    "Click a **team** row (top level) → team-aggregate history · click a "
    "**service** row (leaf) → that service's history. The `filters` payload's "
    "depth tells you which level was clicked."
)

try:
    from streamlit_pivot import st_pivot_table

    st_pivot_table(
        detail_for_today(),
        key="piv",
        rows=["team", "service"],
        values=["latency", "requests", "error_rate"],
        aggregation={"latency": "avg", "requests": "sum", "error_rate": "avg"},
        number_format={"latency": ",.1f", "requests": ",.0f", "error_rate": ",.2f"},
        row_layout="hierarchy",
        show_totals=False,
        max_height=340,
        enable_drilldown=False,
        on_cell_click=lambda: None,   # fire a rerun; read payload from session_state
    )

    f = (st.session_state.get("piv") or {}).get("cell_click", {}).get("filters", {})
    st.write("**click payload `filters`:**", f)

    h = history()
    if f.get("service"):                       # LEAF — full path present
        sub = h[(h.team == f["team"]) & (h.service == f["service"])]
        st.markdown(f"#### {f['team']} / {f['service']} — service history")
        st.line_chart(sub.set_index("date")["latency"])
    elif f.get("team"):                        # TOP LEVEL — only the parent key
        sub = h[h.team == f["team"]].groupby("date")["latency"].mean()
        st.markdown(f"#### {f['team']} — team-aggregate history (mean of services)")
        st.line_chart(sub)
    else:
        st.info("Click a team or service row above.")
except Exception as e:  # component needs Streamlit ≥ 1.51 + a server restart after install
    st.error(f"streamlit-pivot unavailable: {e}")
    st.caption("`pip install streamlit-pivot`, then RESTART the Streamlit server.")
