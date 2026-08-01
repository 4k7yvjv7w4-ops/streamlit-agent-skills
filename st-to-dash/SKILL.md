---
name: st-to-dash
description: Porting or migrating a Streamlit app to Plotly Dash — or deciding whether to. Maps every Streamlit concept to its Dash equivalent — session_state to dcc.Store, widgets to dcc components + callbacks, st.cache_data to shared caches, fragments/run_every to targeted callbacks/dcc.Interval, st.navigation to dash pages, forms to State+button, AppTest to direct callback calls — with a verified side-by-side example pair and a porting recipe.
---

# Streamlit → Dash migration (verified: streamlit 1.58 / dash 4.4)

Load [dash-core] alongside this. The bundled pair `example_streamlit.py` /
`example_dash.py` is the SAME app in both frameworks — read them side by side;
both are test-verified.

## Decide first — should you switch?

Dash buys you: **no full rerun** (each interaction patches only its declared
outputs), a **stateless multi-user server** (gunicorn workers scale), and
fine-grained control of what updates when. It costs you: every widget needs
an `id` + explicit callback wiring (Streamlit's "just read the variable" is
gone), charts must be **Plotly** (Altair specs don't port — every chart is
rewritten), and there's no free rich-widget layer (st.dataframe/column_config
→ DataTable or dash-ag-grid, configured by hand). Rule of thumb: internal
tool, small user count, fast iteration → stay on Streamlit; many concurrent
users or rerun cost dominating → Dash is worth the wiring.

## The mental inversion

A Streamlit script IS the page: it re-runs top-to-bottom per interaction and
variables are the state. A Dash app is a **static layout + a callback graph**:
functions declared to fire when specific `(id, property)` inputs change,
patching specific outputs. Porting = turning "code that reads widgets inline"
into "callbacks that receive those widgets' values as arguments".

## Concept map

| Streamlit | Dash | Notes |
|---|---|---|
| whole-script rerun | callback per interaction | nothing else re-executes |
| `st.session_state` | `dcc.Store(id=...)` | JSON-able, per-browser; read `State("s","data")`, write `Output("s","data")` |
| `st.selectbox / st.slider / st.text_input` | `dcc.Dropdown / dcc.Slider / dcc.Input` | value arrives as a callback argument, not a return value |
| `st.button` | `html.Button` + `Input("b","n_clicks")` | guard first fire with `prevent_initial_call=True` |
| `st.form` + submit | fields as `State`, button as the only `Input` | exactly Streamlit's batch semantics |
| widget `key=` + keep() | `id=` + `persistence=True` | survives refresh/page switch (`persistence_type="session"`) |
| `st.altair_chart` / `st.plotly_chart` | `dcc.Graph(figure=px...)` | Altair must be REWRITTEN in Plotly; interactive legend is built-in |
| chart `on_select` → Python | `Input("g","clickData")` / `"selectedData"` | point dicts, not named fields — map curveNumber yourself |
| `st.dataframe` / `st.data_editor` | `dash_table.DataTable` (editable=True) / dash-ag-grid | column_config niceties are manual |
| `st.cache_data` | `functools.lru_cache` / flask-caching | SHARED across users — was true of cache_data too |
| `st.cache_resource` | module-level singleton | globals are fine for shared read-only resources, NEVER per-user state |
| `@st.fragment` | nothing to port | callbacks are already fragment-granular |
| fragment `run_every` | `dcc.Interval` as an Input | stop/re-time by patching `Output("tick","interval")` / `disabled` |
| `st.navigation` / switch_page | `use_pages=True` + `dash.register_page` + `dcc.Link` | ids unique ACROSS pages; cross-page state in a top-level Store |
| `st.query_params` | `dcc.Location` + callback on `"search"` | parse/build the query string yourself |
| `st.secrets` | env vars / your config lib | Flask has no secrets.toml |
| `st.rerun` | not needed | update the outputs instead |
| background jobs ([st-jobs]) | same job store, polled by Interval; or `background=True` callbacks | the SQLite store ports unchanged |
| `AppTest` | direct-call callbacks (plain functions) | see [dash-core] Testing |

## Porting recipe (do it in this order)

1. **Inventory the seams**: every widget, every `session_state` key, every
   cached function, every page. Each widget gets an `id`; each "block that
   reacts" becomes one callback.
2. **Build the dead layout first** — all components with ids, no callbacks.
   Run it; you get the visual shell.
3. **Wire callbacks one at a time**, innermost data-flow first. Everywhere the
   Streamlit code read a widget variable inline, that widget becomes an
   `Input`/`State` of the callback that used it.
4. **Port state**: each `session_state` key → a field in a `dcc.Store` dict
   (one Store per concern, not one per key). Initialization code (the
   `setdefault` block) → the Store's `data=` default.
5. **Rewrite charts in Plotly** (px first, graph_objects when px can't).
6. **Move caching**: cache_data'd loaders → `lru_cache`d module functions —
   verify nothing per-user leaked into them (in Dash that's cross-user
   contamination, not a stale widget).
7. **Test**: port AppTest asserts to direct callback calls — same
   drive-by-key spirit, no browser.

## Gotchas that bite ex-Streamlit authors (verified)

- Writing per-user data to a global "because it worked in Streamlit" — a Dash
  process serves ALL users; that's cross-user leakage. Store or props, always.
- Two callbacks writing one Output: registers silently in Python, breaks only
  in the browser ("Duplicate callback outputs"). Streamlit had no such
  constraint — grep your Outputs after porting.
- `app.run_server` from old examples raises `ObsoleteAttributeException` on
  dash 4.x — it's `app.run`.
- Callbacks fire once at page load (Streamlit scripts "fire" too, but empty-
  state guards ported 1:1 will run before any click) — `prevent_initial_call=
  True` on action callbacks, `no_update` for partial output skips.
