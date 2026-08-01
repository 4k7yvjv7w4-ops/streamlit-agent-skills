"""dash-core lab — the callback model, state, and polling in one page.

Run:  python dash_core_lab.py     (then open http://127.0.0.1:8050)
Test: python test_dash_core.py    (no browser needed)

Sections:
  1. Input -> Output: dropdown redraws the chart (only the chart updates)
  2. form flow: Inputs held as State, one button triggers; dcc.Store keeps
     a per-user run log (there is NO session_state)
  3. dcc.Interval: a 2s tick patching one Div — the polling primitive
"""

from dash import (Dash, dcc, html, Input, Output, State, callback, ctx,
                  no_update)
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
app.layout = html.Div(style={"maxWidth": "760px", "margin": "auto"}, children=[
    html.H3("dash-core lab"),

    html.H4("1 · Input → Output"),
    dcc.Dropdown(id="svc", options=sorted(DF["service"].unique()), value="auth"),
    dcc.Graph(id="chart"),

    html.H4("2 · State + Store (the form flow)"),
    dcc.Input(id="threshold", type="number", value=150),
    html.Button("evaluate", id="go", n_clicks=0),
    html.Div(id="verdict"),
    dcc.Store(id="runs", data=[]),          # per-user log; NOT a global
    html.Div(id="runlog"),

    html.H4("3 · Interval (polling primitive)"),
    dcc.Interval(id="tick", interval=2000),
    html.Div(id="clock"),
])


@callback(Output("chart", "figure"), Input("svc", "value"))
def draw(svc):
    d = DF[DF["service"] == svc]
    return px.line(d, x="date", y="latency_ms", title=f"{svc} latency")


@callback(Output("verdict", "children"), Output("runs", "data"),
          Input("go", "n_clicks"),
          State("threshold", "value"), State("svc", "value"),
          State("runs", "data"),
          prevent_initial_call=True)
def evaluate(n, threshold, svc, runs):
    if threshold is None:
        return "enter a threshold", no_update
    avg = DF.loc[DF["service"] == svc, "latency_ms"].mean()
    verdict = f"{svc}: avg {avg:.0f} ms — {'BREACH' if avg > threshold else 'ok'} vs {threshold}"
    return verdict, runs + [verdict]


@callback(Output("runlog", "children"), Input("runs", "data"))
def show_log(runs):
    return html.Ul([html.Li(r) for r in runs[-5:]])


@callback(Output("clock", "children"), Input("tick", "n_intervals"))
def clock(n):
    return f"tick #{n or 0} (every 2s, only this Div updates)"


if __name__ == "__main__":
    app.run(debug=True)
