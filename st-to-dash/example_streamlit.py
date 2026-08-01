"""st-to-dash example — the STREAMLIT half. Same app as example_dash.py.

Run:  python -m streamlit run example_streamlit.py

One selectbox + one slider + a chart + a submit-style breach check whose
results accumulate in session_state. Compare seam by seam with the Dash half.
"""

import numpy as np
import pandas as pd
import streamlit as st

rng = np.random.default_rng(0)
DF = pd.DataFrame({
    "date": list(pd.date_range("2025-03-01", periods=30)) * 2,
    "service": ["auth"] * 30 + ["search"] * 30,
    "latency_ms": rng.uniform(40, 400, 60).round(1),
})

st.title("latency monitor (streamlit)")

# widgets read inline — the script re-runs on every change      [Dash: callback args]
svc = st.selectbox("service", sorted(DF["service"].unique()), key="svc")
threshold = st.slider("SLA threshold (ms)", 50, 400, 150, key="threshold")

d = DF[DF["service"] == svc]
st.line_chart(d.set_index("date")["latency_ms"])                # [Dash: dcc.Graph + px]

st.session_state.setdefault("runs", [])                         # [Dash: dcc.Store(data=[])]

if st.button("evaluate", key="go"):                             # [Dash: Input n_clicks + State fields]
    avg = d["latency_ms"].mean()
    verdict = (f"{svc}: avg {avg:.0f} ms — "
               f"{'BREACH' if avg > threshold else 'ok'} vs {threshold}")
    st.session_state.runs.append(verdict)

for r in st.session_state.runs[-5:]:                            # [Dash: callback on Store data]
    st.write(r)
