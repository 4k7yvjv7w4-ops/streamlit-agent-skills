---
name: dash-linked-views
description: Fast linked "dashboard" pages in Plotly Dash — a key input (code/id/name) drives several linked grids and charts, and clicking one view filters the others with ZERO server round-trips — one cached fetch per key into dcc.Store, ready-made per-category Plotly traces, and a 10-line clientside_callback (JavaScript template, copy don't author) that filters rows and toggles trace visibility. Use for "several tables and charts linked together reacting instantly", when clicks are slow because every callback hits the server, or as the Dash counterpart of st-linked-views.
---

# Linked views in Dash — one fetch per key, zero-latency linking (verified in a browser)

Proof: `dash_linked_views_lab.py` + `test_dash_linked_views.py` — headless
Chromium counts `_dash-update-component` requests: a region click re-filters
the detail grid and both charts with **zero** server requests; a key change
costs exactly one. Companions: [dash-data] (fetch/cache), [dash-grid],
[dash-layout]; Streamlit twin: [st-linked-views].

## The architecture — two kinds of fast, two kinds of callback

1. **Key changes** → a SERVER callback: one cached lake pass ([dash-data])
   returning a bundle for ALL views into `dcc.Store`. Unavoidable trip; make
   it one.
2. **Clicks between views** → a CLIENTSIDE callback: JavaScript running in
   the browser over the Store. No request, no Python, ~instant. This is the
   feature Streamlit fragments can't give you ([st-linked-views] round-trips).

## Make the JS trivial: prepare data for it in Python

The JS should only **filter rows** and **toggle visibility** — never build
figures. So the bundle carries figures with **one trace per category**
(`px.line(..., color="region")` → `trace.name == region`) and detail rows as
records:

```python
@cache.memoize()
def fetch_bundle(service: str) -> dict:                    # Store-safe JSON
    cur = db().cursor()
    regions = cur.execute("SELECT region, avg(latency_ms) avg_ms FROM events WHERE service=? GROUP BY 1", [service]).df()
    detail  = cur.execute("SELECT region, endpoint, sum(requests) requests FROM events WHERE service=? GROUP BY 1,2", [service]).df()
    daily   = cur.execute("SELECT date, region, avg(latency_ms) avg_ms FROM events WHERE service=? GROUP BY 1,2", [service]).df()
    return {"regions": regions.to_dict("records"), "detail": detail.to_dict("records"),
            "daily_fig": json.loads(px.line(daily, x="date", y="avg_ms", color="region").to_json()),
            "bars_fig":  json.loads(px.bar(detail, x="endpoint", y="requests", color="region", barmode="group").to_json())}

@callback(Output("bundle", "data"), Output("regions", "rowData"), Output("regions", "selectedRows"),
          Input("svc", "value"))
def load(svc):                                             # SERVER, once per key
    b = fetch_bundle(svc)
    return b, b["regions"], []                             # reset selection on key change
```

## The clientside template (copy verbatim; change only the field names)

```python
clientside_callback(
    """
    function(selected, bundle) {
        if (!bundle) { return [[], {}, {}, ""]; }
        const key = (selected && selected.length) ? selected[0].region : null;      // <- selector field
        const rows = key ? bundle.detail.filter(r => r.region === key) : bundle.detail;
        const show = (fig) => {
            const f = JSON.parse(JSON.stringify(fig));                             // never mutate the Store
            f.data.forEach(t => { t.visible = (!key || t.name === key) ? true : 'legendonly'; });
            return f;
        };
        return [rows, show(bundle.daily_fig), show(bundle.bars_fig), key ? "filter: " + key : "all"];
    }
    """,
    Output("detail", "rowData"), Output("daily", "figure"), Output("bars", "figure"), Output("status", "children"),
    Input("regions", "selectedRows"), Input("bundle", "data"),
)
```

Selector = a `dash-ag-grid` with `rowSelection: "single"` and a `getRowId`;
detail = another grid; charts = `dcc.Graph`s. Three things the JS relies on:
records have the selector field; traces are named by it; the Store is
treated as read-only (deep-copy before editing).

## Rules (verified)

- **Outputs are owned by one callback.** Everything the click updates belongs
  to the clientside callback ONLY; the server callback owns the Store, the
  selector's rows and its `selectedRows` reset. Mixing → "Duplicate callback
  outputs" in the browser ([dash-core]).
- **Bundle also as Input** to the clientside callback → a new key re-renders
  all views unfiltered without a second server trip.
- `visible: 'legendonly'` keeps hidden categories in the legend (click to
  bring back); `false` removes them entirely.
- Keep the bundle small (aggregate in SQL) — it rides in the page as JSON and
  the JS filters it per click.
- When linking logic needs Python (joins, pricing, anything non-trivial),
  fall back to a normal server callback with the same Inputs/Outputs — same
  wiring, one round-trip per click. Start clientside; move the few
  Python-heavy outputs server-side only if forced.
- Test in a browser: `dash.testing` needs chromedriver; the bundled test
  drives Playwright + Chromium directly and asserts the request count.
