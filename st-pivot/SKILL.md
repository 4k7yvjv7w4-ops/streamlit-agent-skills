---
name: st-pivot
description: Build BI pivot tables in Streamlit with streamlit-pivot (the official component). Use when the user works with st_pivot_table — pivots, hierarchy trees with collapse, conditional formatting, cell-click callbacks into Python, Excel export — or asks for a free alternative to AG Grid Enterprise grouping.
---

# streamlit-pivot (official Streamlit pivot component, 0.5.x)

**Choosing a grid (shared matrix):** flat interactive grid or selection→Python
→ **aggrid** · pivot/tree wired to Python → **st-pivot** · huge-data
client-side exploration → **perspective** · live range Σ/avg status bar →
**AG Grid enterprise only** (no free equivalent anywhere).

`pip install streamlit-pivot` — from the Streamlit team, Components V2,
Streamlit ≥ 1.51. Free, and unlike Perspective the config state and cell
clicks come back to Python. Runnable demos: `st_pivot_lab.py` in this folder
(click-any-level → second-frame chart), plus `aggrid_lab.py` in the
[st-aggrid] skill (`../st-aggrid/aggrid_lab.py`), tab 10 + the
🟩 expanders in tabs 1–8.

**Install gotcha:** the component manifest is scanned at SERVER START — a
running Streamlit server that predates the pip install raises
`Component … must be declared in pyproject.toml with asset_dir`. Restart the
server, don't debug the message.

## Core API

```python
from streamlit_pivot import st_pivot_table

result = st_pivot_table(
    df, key="pivot",                      # key is REQUIRED, unique per pivot
    rows=["region"], columns=["pctl"], values=["latency"],
    aggregation={"latency": "avg"},   # sum/avg/count/min/max/count_distinct/median/percentile_90/first/last
    number_format={"latency": ",.1f"},    # d3-style patterns ($,.0f · .1% · ,.2f)
    dimension_format={"pctl": ",.0f"},
    row_sort={"by": "value", "direction": "desc", "value_field": "latency"},
    show_totals=False, max_height=520,
    enable_drilldown=True,                # click a cell → source-records panel
)
result["config"]                          # current pivot config, back in Python
```

- Feed LONG data; `reset_index(drop=True)` first or the drill-down panel shows
  a `__index_level_0__` column.
- Sorting: initial via `row_sort`/`col_sort` (single dict or chained list;
  `"by": "key"` alphabetical or `"by": "value"` + `value_field`). Interactive
  sorting is in the **header ⋮ menu** — there is NO one-click-on-header sort
  (that stays an aggrid/st.dataframe advantage).

## Three display modes

1. **Matrix** — `rows=` + `columns=`: classic region × percentile pivot. **The
   `columns=` param IS the "split by a column"** — each distinct value of a
   `columns` field becomes its own column (Perspective calls it `split_by`, AG
   Grid calls it pivot mode and charges for it; here it's free and one kwarg:
   `columns=["region"]` splits region values across the top). Multiple splits
   nest: `columns=["region", "pctl"]`. Cells format cleanly via `number_format`
   (unlike AG Grid pivot, no result-column formatter gymnastics).
2. **Hierarchy tree** — `row_layout="hierarchy"` with 2+ row dims: the AG Grid
   grouping tree — indented column, +/− chevrons per group, level-wide
   collapse via the breadcrumb, subtotals auto-enabled. In table layout,
   `show_subtotals=True` + `subtotal_position="top"` gives collapsible group
   headers instead.
3. **Flat table** (dataframe-like, mixed strings + numbers) — all string
   columns as `rows`, all numeric as `values`, plus:
   `repeat_row_labels=True` (no label merging) and `null_handling="separate"`
   (default `"exclude"` silently DROPS rows with null string dims). Caveats:
   dims always render left of values (no interleaving); rows sharing all dim
   values aggregate into one; original row order not preserved. If you only
   need display, `st.dataframe` is simpler — use flat st-pivot for its
   formatting/export/click extras.

**No init-collapse parameter in 0.5.0** — collapsed state persists per `key`
and exports via toolbar Copy Config, but can't be preset from Python. Emulate
"load collapsed" by starting with fewer row dims.

## Events back into Python (the killer feature)

```python
result = st_pivot_table(df, key="p", ..., on_cell_click=lambda: None)
pay = (st.session_state.get("p") or {}).get("cell_click") or {}
# payload: {"rowKey": [...], "colKey": [...], "value": 123.4,
#           "valueField": "latency", "filters": {"region": "eu-west-1", "pctl": 95}}
name = pay.get("filters", {}).get("region")
if name:
    ...metrics / detail tables / charts in any st.columns layout you like...
```

- Callbacks fire with NO arguments; read `st.session_state[key]`.
- Clicking a SUBTOTAL row omits the child dims from `filters` — branch on
  which keys are present to give subtotal clicks team-level behavior.
- Fan-out layout is entirely yours (side-by-side sub-table + chart, etc.);
  only the pivot's internal layout is fixed.
- `on_config_change` + `result["config"]` persist user customizations.

### Click ANY level (top → leaf) → chart from a SECOND frame

The depth of the `filters` dict IS the level you clicked, so one handler serves
every tier of a `row_layout="hierarchy"` tree. Classic use case: a wide
**detail** frame for one date drives the pivot; a skinny **history** frame
(the second df) drives the chart; they share only the key. (AG Grid can't do
this — its `getSelectedRows()` returns leaf rows only, so group clicks reach
Python as nothing; st-pivot's `on_cell_click` returns the key path at any level.
Both verified.)

```python
st_pivot_table(detail_df, key="piv", rows=["team", "service"],
    values=["latency", "requests"], row_layout="hierarchy", on_cell_click=lambda: None)
f = (st.session_state.get("piv") or {}).get("cell_click", {}).get("filters", {})

if f.get("service"):                       # LEAF — full path {team, service}
    s = hist[(hist.team == f["team"]) & (hist.service == f["service"])]
    st.line_chart(s.set_index("date")["latency"])
elif f.get("team"):                        # TOP LEVEL — parent key only {team}
    st.line_chart(hist[hist.team == f["team"]].groupby("date")["latency"].mean())
```

- **Scales to any depth**: `rows=["team","service","instance"]` yields `{team}`,
  `{team,service}`, `{team,service,instance}` at the three tiers — same branch.
- **One skinny history frame serves every level**: keep the finest grain and
  `groupby(date).mean()` (or sum) to answer a higher-level click; no per-level
  pre-aggregates needed. Wrap it in `@st.cache_data` — it loads once.

Runnable proof: `st_pivot_lab.py` in this skill folder.

## Weighted averages & ratios — `synthetic_measures` (NOT `aggregation`)

`aggregation` only offers sum/avg/…/percentile — **there is no weighted-avg
aggregator**, and picking `avg` averages the per-row latencies unweighted. A
weighted mean is a *ratio of two sums* (`Σ(value·weight) / Σweight`), so it's a
**synthetic measure**, computed AFTER aggregation. Crucially this is
**drill-down-correct at every level**: both sums roll up independently and the
ratio is recomputed per cell, so a region subtotal and its percentile children
are each a true weighted mean — never an average-of-averages.

```python
# 1) precompute the PRODUCT column in pandas — numerator/denominator must be
#    real df columns, and the component SUMS each within every cell/group.
df["lat_x_req"] = df["latency"] * df["requests"]

st_pivot_table(
    df, key="wavg", rows=["region", "pctl"], values=["latency", "requests"],
    aggregation={"latency": "avg", "requests": "sum"},
    row_layout="hierarchy",                      # the drill-down tree
    synthetic_measures=[{
        "id": "wavg_lat", "label": "Latency (req-weighted ms)",
        "operation": "sum_over_sum",             # Σnumerator / Σdenominator
        "numerator": "lat_x_req", "denominator": "requests",
        "format": ",.1f",                        # optional d3 pattern
    }],
)
```

- **`operation`** is one of `sum_over_sum` (ratios / weighted avg) ·
  `difference` (num − den) · `formula` (expression string, field names in
  `"quotes"`, whitelisted funcs only). `id` + `label` are required and must be
  unique.
- **Don't multiply in a formula and hope** — `formula: '"latency" * "requests"'`
  is evaluated on already-aggregated cell values, giving `avg(latency)·sum(req)`,
  not the weighted mean. Precompute the product per source row so the SUM is
  `Σ(value·weight)`; that's what `sum_over_sum` needs.
- **Source columns can't double as row/column dims** — a field used as
  numerator/denominator AND in `rows`/`columns` raises `dim_value_overlap`
  (duplicate columns after the internal `reset_index`).
- **Zero denominator is safe** — the component returns `null` (blank cell) when
  `Σdenominator == 0`, never NaN/Infinity (verified in its source:
  `Σden === 0 ? null : num/den`). A group with no weight shows blank, which is
  correct; it also means a genuinely-zero weight can't fabricate a `0`.
- No pandas pre-agg needed beyond the product column; the component does the
  Σ/Σ and the division client-side. Verify against
  `np.average(g.latency, weights=g.requests)` per group (undefined when the
  weights sum to 0 — matches the blank cell).

## Conditional formatting — 3 rule types

```python
conditional_formatting=[
    # gradient; mid_value=0 → diverging scale (delta green/white/red)
    {"type": "color_scale", "apply_to": ["delta"], "min_color": "#2ca02c",
     "mid_color": "#ffffff", "max_color": "#d62728", "mid_value": 0},
    {"type": "data_bars", "apply_to": ["requests"], "color": "#1976d2"},
    # threshold: gt/gte/lt/lte/eq/between; background/color/bold per condition
    {"type": "threshold", "apply_to": ["err_rate"], "conditions": [
        {"operator": "gt",  "value": 1, "color": "#d62728"},
    ]},
]
```

Gotchas (verified):
- **Two threshold rules on the same field don't stack — last wins.** Combine
  styles as ORDERED conditions of one rule (first match applies).
- **Per-column rules need the column as its own value field** (wide data). With
  `split_by`, rules hit the measure across every split column.
- **Empty cells are never styled by value rules** (NaN fails all conditions;
  color scales skip blanks). For a static column fill that includes empties,
  use `data_cell_by_measure` (style layer, below) — or
  `null_handling={"field": "zero"}` if null genuinely means 0 (misleading for
  missing quotes).
- "Bold the top N by rank" isn't a rule type — thresholds are value-based;
  compute the rank in pandas and threshold on it.

## Styling — presets, regions, cascade

```python
style=["compact", {                      # list composes preset + overrides
    "stripe_color": None,                # striping blends OVER region colors — disable
    "row_header": {"background_color": "#e3f2fd"},   # row-label column (all levels)
    "subtotal":   {"background_color": "#e3f2fd"},   # parent rows in hierarchy mode
    "data_cell_by_measure": {            # static per-measure fill — paints EMPTY cells too
        "err_rate": {"background_color": "#fff9c4"}},
}]
```

- Presets: `default · striped · minimal · compact · comfortable · contrast`
  (theme-aware; `compact` = density control).
- Regions: `column_header, row_header, data_cell, row_total, column_total,
  subtotal` + table-wide `density/font_size/borders/stripe_color`.
- **Cascade (top wins):** conditional formatting → `data_cell_by_measure` →
  region overrides → table-wide → Streamlit theme. This one line answers most
  "why isn't my color showing" questions.
- Prefer `var(--st-...)` tokens over raw hex for dark-mode compatibility.

## Toolbar / viewer control

- `show_sections=False` — field chips collapse to a one-line summary.
- `locked=True` — viewer mode: config read-only, export/collapse/drill-down
  still work (right choice for monitors).
- `interactive=False` — toolbar gone, header menus disabled.

## Also has

Excel/CSV/TSV/**clipboard export** toolbar (`export_filename=`) · top-N and
value filters · `show_values_as` (% of total, running totals, ranks) ·
synthetic measures (weighted avg / ratios / formulas — see section above) ·
date hierarchies · `filters` /
`source_filters` (user-facing vs server-only) · `column_config` (links,
images, checkboxes on row dims). Not supported: cell editing (use
`st.data_editor`), ad-hoc range Σ/avg (AG Grid enterprise only).
