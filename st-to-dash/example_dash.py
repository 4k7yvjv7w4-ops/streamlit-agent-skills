"""st-to-dash example — the DASH half. Same app as example_streamlit.py.

Run:  python example_dash.py      (http://127.0.0.1:8050)

Every seam is annotated with the Streamlit construct it replaces.
"""

from dash import Dash, dcc, html, Input, Output, State, callback
import numpy as np
import pandas as pd
import plotly.express as px

rng = np.random.default_rng(0)
DF = pd.DataFrame({
    "date": list(pd.date_range("2025-03-01", periods=30)) * 2,
    "service": ["auth"] * 30 + ["search"] * 30,
    "latency_ms": rng.uniform(40, 400, 60).round(1),
})

app = Dash(__name__)
app.layout = html.Div(style={"maxWidth": "720px", "margin": "auto"}, children=[
    html.H3("latency monitor (dash)"),
    # st.selectbox(key="svc")  ->  component with id, value read via callbacks
    dcc.Dropdown(id="svc", options=sorted(DF["service"].unique()), value="auth"),
    # st.slider(key="threshold")
    dcc.Slider(id="threshold", min=50, max=400, value=150,
               tooltip={"placement": "bottom"}),
    # st.line_chart(...)  ->  dcc.Graph patched by a callback
    dcc.Graph(id="chart"),
    # st.button(key="go")
    html.Button("evaluate", id="go", n_clicks=0),
    # st.session_state.runs  ->  per-user browser-side Store
    dcc.Store(id="runs", data=[]),
    html.Div(id="runlog"),
])


# "d = DF[DF.service == svc]; st.line_chart(d)" — the inline read becomes
# a callback with svc as an argument; ONLY the chart updates on change.
@callback(Output("chart", "figure"), Input("svc", "value"))
def draw(svc):
    d = DF[DF["service"] == svc]
    return px.line(d, x="date", y="latency_ms", title=f"{svc} latency")


# "if st.button(...):" block — button is the Input, the widgets the block
# read become State (form semantics), session_state.runs becomes the Store.
@callback(Output("runs", "data"),
          Input("go", "n_clicks"),
          State("svc", "value"), State("threshold", "value"),
          State("runs", "data"),
          prevent_initial_call=True)
def evaluate(n, svc, threshold, runs):
    avg = DF.loc[DF["service"] == svc, "latency_ms"].mean()
    verdict = (f"{svc}: avg {avg:.0f} ms — "
               f"{'BREACH' if avg > threshold else 'ok'} vs {threshold}")
    return runs + [verdict]


# "for r in st.session_state.runs[-5:]: st.write(r)" — a render callback
# that fires whenever the Store changes.
@callback(Output("runlog", "children"), Input("runs", "data"))
def show_log(runs):
    return html.Ul([html.Li(r) for r in runs[-5:]])


if __name__ == "__main__":
    app.run(debug=True)
