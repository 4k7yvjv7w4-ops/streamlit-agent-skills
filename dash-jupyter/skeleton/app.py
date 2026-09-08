"""Dash-under-Jupyter skeleton — run from a JupyterLab TERMINAL: python app.py

Then open  https://<your-jupyter-host><PREFIX>  (printed at startup).
Works unchanged on JupyterHub (/user/<you>/proxy/PORT/), plain JupyterLab
(/proxy/PORT/), and outside Jupyter entirely (PREFIX degrades to "/").
Requires jupyter-server-proxy installed in the Jupyter server's environment.
"""

import os

import dash
from dash import Dash, dcc, html

PORT = 8519
BASE = os.environ.get("JUPYTERHUB_SERVICE_PREFIX", "/")
# PREFIX must be EXACTLY what precedes the app's routes in your browser's
# address bar (trailing slash required). If pages render their links but no
# content, the computed value is wrong — the server log's
# UnsupportedRelativePath error prints the browser's real path ("You
# supplied: ..."); set DASH_PREFIX to its prefix part and restart.
PREFIX = os.environ.get("DASH_PREFIX") or f"{BASE}proxy/{PORT}/"

app = Dash(__name__, use_pages=True,
           requests_pathname_prefix=PREFIX,   # browser-side URLs
           routes_pathname_prefix="/")        # server-side (proxy strips the prefix)

app.layout = html.Div(style={"maxWidth": "760px", "margin": "auto"}, children=[
    html.Div([dcc.Link(p["name"], href=p["relative_path"], style={"marginRight": "1em"})
              for p in dash.page_registry.values()]),
    html.Hr(),
    dash.page_container,
])

if __name__ == "__main__":
    print(f"open <your-jupyter-host>{PREFIX}")
    app.run(host="127.0.0.1", port=PORT, debug=False)
