"""Offline Perspective lab — the CDN-free `streamlit-perspective` component.

Run:  python -m streamlit run perspective_offline_lab.py

Unlike the CDN embed (aggrid_lab.py tab 9), this pulls NOTHING from the network:
`streamlit-perspective` bundles the Perspective viewer + WASM and serves them
from the Streamlit app's own origin — the corporate / air-gapped route.

    pip install streamlit-perspective
    # then RESTART the server: the Components V2 manifest is scanned at server
    # start, so a fresh install isn't visible until you restart.

The import is guarded so this file still runs (showing an install hint) when the
package is absent or the server hasn't been restarted yet.
"""

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Offline Perspective", layout="wide")
st.title("Offline Perspective — no CDN")


@st.cache_data
def latency_long() -> pd.DataFrame:
    """Synthetic long telemetry: one row per (region, service, percentile)."""
    rng = np.random.default_rng(0)
    regions = ["us-east-1", "eu-west-1", "ap-south-1", "sa-east-1"]
    services = ["checkout", "search", "profile", "cart"]
    pctls = [50.0, 75.0, 90.0, 95.0, 99.0]
    rows = []
    for rgn in regions:
        for svc in services:
            base = rng.uniform(60, 240)
            for p in pctls:
                lat = base * (1 + (p - 50) / 60) + rng.normal(0, 6)
                rows.append((rgn, svc, p, round(max(10.0, lat), 1),
                             int(rng.integers(5_000, 900_000))))
    return pd.DataFrame(rows, columns=["region", "service", "pctl",
                                       "latency", "requests"])


df = latency_long()

st.caption(
    "Pivot region × service, split by percentile — all client-side, zero network "
    "fetch (WASM is bundled and served from the Streamlit origin). Perspective 3.x: "
    "the pivot uses a default aggregate; per-column agg/format lives in `columns_config` "
    "(NOT a top-level `aggregates` key, which 3.x dropped). Config round-trips to Python."
)

try:
    from streamlit_perspective import perspective_static

    result = perspective_static(
        df.to_dict("records"),
        config={
            "plugin": "Datagrid",
            "group_by": ["region", "service"],   # row pivot (nested)
            "split_by": ["pctl"],                 # COLUMN pivot (pctl is numeric -> headers sort 50..99)
            "columns": ["latency"],
            "sort": [["region", "asc"]],
            "settings": True,                     # open the config side panel
            # per-column STYLING is Perspective 3.x columns_config (verified keys):
            "columns_config": {"latency": {"number_bg_mode": "gradient",
                                           "bg_gradient": 400}},
            # "theme": "Pro Light",  # omit and the frontend injects "Pro Dark"
        },
        height=520,
        key="offline_pivot",
    )
    with st.expander("Config handed back to Python (the CDN embed can't do this)"):
        st.caption("Only the viewer config returns, and only on rerun — no click "
                   "events, no data round-trip. Re-pivot above, then rerun to see it change.")
        st.json((result or {}).get("config", {}), expanded=False)

except Exception as e:  # noqa: BLE001 — degrade gracefully for the smoke test
    st.info(
        f"`streamlit-perspective` unavailable ({type(e).__name__}). "
        "Install it and **restart** the server:\n\n"
        "```\npip install streamlit-perspective\n```\n\n"
        "Components V2 scans its manifest at server start, so a fresh install "
        "raises an `asset_dir` error until you restart — restart, don't debug it."
    )
    st.dataframe(df, width="stretch", height=360)

# --- live-data variant (needs an externally-run perspective-python server) ---
with st.expander("Live streaming — perspective_websocket (needs a running server)"):
    st.code(
        'from streamlit_perspective import perspective_websocket\n'
        '# pip install streamlit-perspective[examples]  ->  perspective-python + tornado\n'
        '# then run your own perspective-python websocket server, and point at it:\n'
        'perspective_websocket("ws://host:8080/websocket", "telemetry",\n'
        '                      config={"plugin": "Y Line", "columns": ["latency"]},\n'
        '                      height=520, key="live")\n'
        '# rows stream browser<->server directly, bypassing Streamlit.',
        language="python")
