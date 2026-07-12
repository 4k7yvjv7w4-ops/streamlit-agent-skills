---
name: perspective-streamlit
description: Embed FINOS Perspective in Streamlit with the streamlit-perspective component (perspective_static / perspective_websocket) for client-side pivoting and exploration of large tables — CDN-free, self-hosted WASM, config round-trips to Python. Use for drag-drop pivots / column splits / chart plugins on big data, corporate/air-gapped setups, or linking Perspective to Streamlit.
---

# FINOS Perspective in Streamlit — `streamlit-perspective` (0.0.x, perspective-viewer 3.x)

**Choosing a grid (shared matrix):** flat interactive grid or selection→Python
→ **aggrid** · pivot/tree wired to Python → **streamlit-pivot** · huge-data
client-side exploration → **perspective** · live range Σ/avg status bar →
**AG Grid enterprise only** (no free equivalent anywhere).

`pip install streamlit-perspective` — a Streamlit **Components V2** (no-iframe)
wrapper around Perspective (Apache-2.0 engine; MIT wrapper). It **bundles the
viewer + WASM and serves them from the Streamlit origin — no CDN, works
air-gapped**, and (unlike the old CDN embed) the viewer config **round-trips to
Python**. Millions of rows, row AND column pivots, chart plugins.
Runnable proof: `perspective_offline_lab.py` in this skill folder.

## Install — and the one gotcha that WILL bite

```bash
pip install streamlit-perspective        # needs streamlit>=1.51, Python>=3.10
```

**RESTART the Streamlit server after installing.** The Components V2 manifest
(`asset_dir='frontend/build'`) is scanned at SERVER START; a bare import before
restart raises `StreamlitAPIException: ... must be declared in pyproject.toml
with asset_dir to use file-backed css`. Restart the server — don't debug the
message. (Same gotcha as [streamlit-pivot].) Pin the version: it's early
(0.0.x, single maintainer) — treat the API as unstable.

## Core recipe — `perspective_static`

```python
import streamlit as st
from streamlit_perspective import perspective_static

result = perspective_static(
    df.to_dict("records"),           # list[dict], one dict per row (positional, required)
    config={
        "plugin": "Datagrid",        # or "Y Line" / "Heatmap" / "Treemap" / "Candlestick" / …
        "group_by": ["region"],      # row pivot
        "split_by": ["pctl"],        # COLUMN pivot (aggrid community can't do this)
        "columns": ["latency"],
        "filter": [["region", "==", "us-east-1"]],
        "sort": [["latency", "desc"]],
        "settings": True,            # open the config side panel
        # "theme": "Pro Light",      # omit and the frontend injects "Pro Dark"
    },
    height=520,
    key="viewer",                    # STABLE key — required to read edits back (below)
)
```

`data` is records (`df.to_dict("records")`). `config` is passed **verbatim** to
Perspective's `viewer.restore()` — no key whitelisting, so any restore-valid key
works.

## The config dict (Perspective 3.x)

- Common keys: `plugin` · `group_by` · `split_by` · `columns` · `sort`
  (`[[col, dir]]`) · `filter` (`[[col, op, value]]`) · `expressions` · `theme` ·
  `settings` · `title` · `columns_config` · `plugin_config`.
- **This is Perspective 3.x — there is NO top-level `aggregates` key.** It's
  absent from the bundle. A column gets a default aggregate under a pivot;
  per-column aggregation/formatting lives in **`columns_config`**, not a
  top-level `aggregates` dict. (Don't carry `aggregates` over from v2 examples.)
- **`split_by` on a string column sorts headers lexically** ("p100" < "p20").
  Use a numeric column (percentile as float) so headers sort 50, 75, …, 99.
- Themes: `Pro Light` · `Pro Dark` (default) · `Monokai` · `Solarized` ·
  `Solarized Dark` · `Vaporwave`. Plugins bundled: `Datagrid`, `Y Line`,
  `Y Bar`, `X Bar`, `Y Scatter`, `Y Area`, `Heatmap`, `Treemap`, `Sunburst`,
  `Candlestick`, `OHLC`.

## Config round-trip to Python — what actually comes back

The return value is `{"config": <viewer config>}` and it is the **only** thing
that reaches Python:

```python
result = perspective_static(df.to_dict("records"), config={...}, key="viewer")
st.json(result["config"])            # the user's live pivot/filter/sort/theme, on RERUN
```

- Before any interaction, `result["config"]` equals the config you passed (or `{}`).
- When the user re-pivots/filters/sorts/re-themes, the new config comes back on
  the **next rerun** — read `result["config"]` with a stable `key`.
- **Scope, precisely:** config only, on rerun only. There is **no
  `on_config_change` callback** (the wrappers hardwire a no-op), **no
  click/select events** reach Python, and **no data round-trip** (cell edits
  change only the browser's copy). Need click→Python? Use [streamlit-pivot] or
  [streamlit-aggrid].

## Per-column styling — `columns_config` (Perspective 3.x)

```python
config={"plugin": "Datagrid", "columns": ["latency"],
        "columns_config": {"latency": {
            "number_bg_mode": "gradient",          # "color" | "gradient" | "pulse" | "disabled"
            "bg_gradient": 400,                      # scale anchor
            "pos_bg_color": "#d62728", "neg_bg_color": "#2ca02c"}}}
```

Use `columns_config` only — the old CDN embed's "restore twice" and "send both
v2 `plugin_config.columns` and v3 shapes" hacks are NOT needed here (the
component owns the restore path and this bundle is strictly 3.x).

## Huge / live data — `perspective_websocket`

```python
from streamlit_perspective import perspective_websocket
perspective_websocket("ws://host:8080/websocket", "telemetry",
                      config={"plugin": "Y Line", "columns": ["latency"]},
                      height=520, key="live")
```

Points the in-browser viewer at a **running `perspective-python` server**; rows
stream browser↔server directly, **bypassing Streamlit** (Python only supplies
the URL + table name). The component does NOT run the server — stand it up
yourself (`pip install streamlit-perspective[examples]` → `perspective-python`,
`tornado`). Auth, `ws://` reachability from the client, and CORS are on you.

## Gotchas (verified against the bundle)

1. **Restart after install** — the asset_dir manifest scan (above). #1 time-sink.
2. **`theme` defaults to `Pro Dark`** — omitting `theme` does NOT render
   themeless; set it explicitly for `Pro Light`.
3. **No top-level `aggregates`** (Perspective 3.x) — use `columns_config`.
4. **`split_by` string headers sort lexically** — pivot on numeric columns.
5. **Only config returns, only on rerun** — no callbacks, no click events, edits
   are browser-only.
6. **Heavy first load** — one ~4.9 MB ES module with WASM inlined as base64
   (+ ~0.6 MB CSS). The trade for zero CDN and air-gap support.
7. Viewer may measure **0 px in a hidden `st.tabs` panel** until shown
   (Perspective behavior; verify in a browser before relying on it in tabs).

## The old CDN embed (legacy)

A raw `components.html` embed loading Perspective 3.x from `cdn.jsdelivr.net`
still ships in `aggrid_lab.py` (tab 9 + the 🟣 expanders) as a zero-dependency,
**one-way** linked-viewers demo — it renders BLANK if a proxy blocks the CDN.
`streamlit-perspective` above replaces it for real use (self-hosted, config
round-trips). Reach for the CDN embed only for a throwaway demo with no install.

## vs AG Grid patterns — what maps

| AG Grid pattern | Perspective equivalent | Fidelity |
|---|---|---|
| Sort/filter/format | config `sort`/`filter` + `columns_config` | High; no pinning/pagination |
| Value heatmap | `columns_config` number bg color/gradient | Built-in modes only, no arbitrary JS |
| Grouping/pivot | `group_by`/`split_by` | **Better than enterprise** (column pivots), free |
| Selection → Python | config round-trip on rerun (NOT clicks) | Config only; clicks stay in the browser |
| Editable | Datagrid edit toggle | Browser-only, no data round trip |
| Range Σ/avg + copy | pivot-for-sums + toolbar export | Different model, no ad-hoc ranges |
