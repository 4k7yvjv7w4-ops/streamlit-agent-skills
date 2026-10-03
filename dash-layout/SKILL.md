---
name: dash-layout
description: Page structure in Plotly Dash with dash-bootstrap-components — responsive Row/Col grid, Cards, Tabs, Modal dialogs, Offcanvas sidebar, Navbar — CDN-free for corporate/air-gapped setups (dbc.themes.* are CDN URLs; vendor the CSS into assets/, obtained from a PyPI wheel). Use for laying out a Dash page, when components render but look unstyled, or when porting st-layout (columns/tabs/dialogs/sidebar) to Dash.
---

# Layout in Dash — dash-bootstrap-components, CDN-free (verified dbc 2.0 / dash 4.4)

Proof: `skeleton/app.py` + `test_dash_layout.py` (headless Chromium confirms
the vendored CSS is applied and modal/offcanvas/tabs callbacks work). Copy
`skeleton/` to start a page. Multi-page routing is in [dash-core] /
[dash-jupyter]; this skill is what goes INSIDE a page.

## The corporate trap first: themes are CDN links

`dbc.themes.BOOTSTRAP` is `https://cdn.jsdelivr.net/npm/bootstrap@…/bootstrap.min.css`.
Behind a proxy that blocks it, **components render but look unstyled**
(plain buttons, no grid, modal shows as static text). Fix — vendor the CSS:

- `skeleton/assets/bootstrap.min.css` ships in this skill (Bootstrap 5.3, MIT).
- To refresh WITHOUT a CDN: `python fetch_bootstrap_css.py` — it pulls the
  `Bootstrap-Flask` wheel from PyPI (your internal index works) and extracts
  `static/bootstrap5/css/bootstrap.min.css`. Verified: the index then links
  `assets/bootstrap.min.css` and nothing external.
- Construct the app with **no** `external_stylesheets`; Dash auto-serves
  `assets/` (prefix-aware under Jupyter — [dash-jupyter]).
- Bootstrap's JS is NOT needed — dbc re-implements behaviors in React.

## st-layout → dbc map

| Streamlit | dbc | Note |
|---|---|---|
| `st.columns([1, 2])` | `dbc.Row([dbc.Col(..., md=4), dbc.Col(..., md=8)])` | 12-unit grid; `md=` = width at ≥768px, stacks below |
| `st.container(border=True)` | `dbc.Card([dbc.CardHeader(), dbc.CardBody()])` | `className="h-100"` to equalize heights in a Row |
| `st.tabs` | `dbc.Tabs(id=, active_tab=)` + callback on `active_tab` | render ONLY the active tab's content (cheap pages) |
| `@st.dialog` | `dbc.Modal(id=, is_open=)` toggled by a callback | content is static layout; fill it via callbacks |
| `st.sidebar` | `dbc.Offcanvas(id=, is_open=)` (slide-in) or a fixed `dbc.Col(width=2)` | Offcanvas for filters; fixed Col for permanent nav |
| page header | `dbc.Navbar` / `dbc.NavbarSimple` | put `dcc.Link`s for pages here |
| `st.metric` | `dbc.Card` + `html.H4` (value) + `dbc.Badge` (delta) | no built-in metric widget |
| `st.expander` | `dbc.Accordion` / `dbc.Collapse` | |
| `st.empty()` placeholder | `html.Div(id=)` as an Output | every dynamic region needs an id |

## Toggle pattern (modal / sidebar / collapse) — verified

```python
@callback(Output("modal", "is_open"),
          Input("open-modal", "n_clicks"), Input("close-modal", "n_clicks"),
          State("modal", "is_open"), prevent_initial_call=True)
def toggle(_open, _close, is_open):
    return not is_open
```

Two buttons → one callback flipping the State; no `ctx` needed when both
simply toggle. Use `ctx.triggered_id` only when open/close must differ.

## Gotchas (verified unless marked)

- Unstyled page = missing/blocked CSS, not a code bug. Check the index HTML
  for the stylesheet href; `curl <prefix>assets/bootstrap.min.css` should
  return CSS.
- Overlays block clicks: an open Modal/Offcanvas intercepts the page —
  close one before expecting clicks elsewhere (bit the test; bites users).
- Spacing is Bootstrap utility classes (`className="mt-3 g-3 py-2"`), not
  inline style dicts — learn ~10 of them; they cover 90% of layout.
- `dbc.Tabs` children are placeholders — don't nest heavy components inside
  `dbc.Tab`; render into a sibling `html.Div` from the `active_tab` callback.
- dash-mantine-components is the alternative library; same CDN caveat
  (`dmc.styles.*` are CDN links) — vendor the same way (not lab-verified).
