---
name: dash-core
description: Building or debugging Plotly Dash apps — the callback-based alternative to Streamlit. Use for ANY Dash work — layout with dcc/html components, @callback Input/Output/State wiring, "Duplicate callback outputs" errors, app.run_server ObsoleteAttributeException, per-user state via dcc.Store (there is NO session_state), multi-page apps (dash.register_page/page_container), dcc.Interval polling, background callbacks, or testing callbacks without a browser.
---

# Dash — the inverse of Streamlit's model (verified on dash 4.4)

Streamlit re-runs the whole script on every interaction. Dash does the
opposite: the **layout is built once**, then each interaction fires a
**callback** — a plain function wired `Inputs → Outputs` — and ONLY the
declared outputs get patched in the browser. Nothing else re-executes.
Coming from Streamlit ([st-to-dash] maps every concept): stop thinking
"rerun", start thinking "which output does this interaction update".

```python
from dash import Dash, dcc, html, Input, Output, State, callback
import plotly.express as px

app = Dash(__name__)
app.layout = html.Div([
    dcc.Dropdown(id="svc", options=["auth", "search"], value="auth"),
    dcc.Graph(id="chart"),
])

@callback(Output("chart", "figure"), Input("svc", "value"))
def draw(svc):                      # runs on load AND whenever svc changes
    return px.line(df[df["service"] == svc], x="date", y="latency_ms")

if __name__ == "__main__":
    app.run(debug=True)             # NOT run_server — see Version traps
```

Runnable proof: `dash_core_lab.py` (+ `test_dash_core.py`, no browser needed).

## Callback rules (each verified)

- Every interactive component needs an **`id`**; callbacks address
  `(id, property)` pairs: `Output("chart", "figure")`, `Input("svc", "value")`.
- **`Input` triggers, `State` is read without triggering.** A "submit" flow is
  `Input("go", "n_clicks")` + `State(...)` for each field — the Dash form.
- **One Output belongs to one callback.** TRAP: a second callback on the same
  Output registers WITHOUT error in Python — the failure only appears in the
  browser as a "Duplicate callback outputs" overlay. Grep your Outputs; don't
  expect an exception. Escape hatch: `Output(..., allow_duplicate=True)`,
  which REQUIRES `prevent_initial_call=True` (raises `DuplicateCallback`
  otherwise).
- Callbacks run once at page load too — suppress with
  `prevent_initial_call=True`; return `dash.no_update` to skip updating some
  outputs.
- Several Inputs, which one fired? `from dash import ctx` → `ctx.triggered_id`.
- Dynamic component lists use pattern-matching ids:
  `Output({"type": "cell", "idx": MATCH}, "children")` (dict ids + MATCH/ALL).

## State — there is NO session_state

The server is **stateless**; state lives in the browser:

- Component props persist by themselves between callbacks (the dropdown holds
  its value — read it via `State`).
- Cross-callback per-user data → **`dcc.Store(id="memo")`**, read/write like
  any prop (`Output("memo", "data")` / `State("memo", "data")`, JSON-able).
- Widget values surviving refresh/navigation → `persistence=True,
  persistence_type="session"` on the component.
- **NEVER store per-user data in Python globals or module frames** — one
  process serves ALL users; globals are shared across everyone. Read-only
  reference data in globals is fine. Shared caches: `functools.lru_cache` /
  flask-caching on data functions (they're shared — like Streamlit's
  cache_data, not like session_state).

## Version traps (dash 4.x, verified)

- `app.run_server(...)` is GONE — raises `ObsoleteAttributeException` ("has
  been replaced by app.run"). Most old tutorials/LLM memory emit it. Use
  `app.run(host=..., port=..., debug=...)`.
- Imports are flat: `from dash import Dash, dcc, html, Input, Output, State,
  callback, ctx, no_update, MATCH, ALL, dash_table`. Never emit the ancient
  `import dash_core_components as dcc` / `dash_html_components`.
- `debug=True` gives the in-browser error overlay + hot reload — dev only.
  Production = gunicorn on `server = app.server` (Flask app).

## Multi-page (verified)

```python
app = Dash(__name__, use_pages=True)         # auto-loads pages/*.py
app.layout = html.Div([
    html.Div([dcc.Link(p["name"], href=p["relative_path"])
              for p in dash.page_registry.values()]),
    dash.page_container,
])
# pages/settings.py:
dash.register_page(__name__, path="/settings", name="Settings")
layout = html.Div([...])                     # module-level `layout` required
```

Page files can define their own `@callback`s; all register globally, so ids
must be unique ACROSS pages. Cross-page state → `dcc.Store` in the top-level
layout (it never unmounts).

## Slow work

A callback blocks its request, not the page — but blocks that user and a
worker. Polling UI: `dcc.Interval(id="tick", interval=2000)` as an Input
(the [st-jobs] fragment-poller equivalent). Truly long jobs: background
callbacks — `@callback(..., background=True, manager=DiskcacheManager(...))`
(`pip install diskcache`; import verified, execution path not lab-verified) —
or keep the job store from [st-jobs] and poll it via Interval.

## Testing without a browser (verified)

Callbacks are plain functions — call them directly:

```python
def test_draw():
    fig = draw("auth")
    assert fig.data and fig.data[0].y is not None
```

`ctx`/`no_update` paths need a request context — factor logic into helper
functions and test those. Full click-through testing needs `dash.testing`
(selenium + chromedriver) — heavier; direct calls catch most regressions.
