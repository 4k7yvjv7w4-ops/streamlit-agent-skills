---
name: streamlit-aggrid
description: Build interactive data grids in Streamlit with streamlit-aggrid (AG Grid). Use when the user works with AgGrid/st_aggrid — flat grids, selection driving other widgets, JsCode styling, editing, grouping, range selection — or asks what needs an AG Grid Enterprise license.
---

# Streamlit + AgGrid (streamlit-aggrid 1.2.x)

**Choosing a grid (shared matrix):** flat interactive grid or selection→Python
→ **aggrid** · pivot/tree wired to Python → **streamlit-pivot** · huge-data
client-side exploration → **perspective** · live range Σ/avg status bar →
**AG Grid enterprise only** (no free equivalent anywhere).

Runnable demo of every pattern below: `aggrid_lab.py` in this skill folder,
tabs 1–8 (`python -m streamlit run ~/.roo/skills/streamlit-aggrid/aggrid_lab.py`;
synthetic sample data bundled in `data/`). Assumes streamlit-aggrid **1.2.x**
(`pip show streamlit-aggrid`).

## Core API

```python
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode

gb = GridOptionsBuilder.from_dataframe(df)           # infer columnDefs from dtypes
gb.configure_default_column(sortable=True, filter=True, resizable=True,
                            floatingFilter=True)     # grid-wide defaults
gb.configure_column("col", header_name="Nice name", width=120, pinned="left",
                    valueFormatter="x.toFixed(1)")   # per-column overrides
gb.configure_grid_options(pagination=True, paginationPageSize=25)  # any gridOption

resp = AgGrid(df, gridOptions=gb.build(), theme="balham", height=520, key="k")
```

- `theme`: `"streamlit" | "alpine" | "balham" | "material"` (balham = densest).
- Always pass a stable `key` when the page has several grids or reruns often.
- `valueFormatter` as a plain string is a JS *expression* with `x` = cell value
  (`"(x / 1e6).toFixed(0)"`). No `JsCode` needed for expressions.
- Header click sorts (toggle asc/desc) out of the box — community feature.

## License map — ✅ community (free) vs 🔒 enterprise

| Feature | License | Free route |
|---|---|---|
| Sort · filter · floating filter · pagination · pinning | ✅ | — |
| All styling: JsCode cellStyle, class rules, row styles, custom_css | ✅ | — |
| Selection events into Python (master/detail, fan-out) | ✅ | — |
| Cell editing + dropdown editors | ✅ | — |
| CSV export | ✅ | — |
| Row grouping / aggregation / pivot mode | 🔒 | pandas groupby → flat grid; or streamlit-pivot / perspective |
| Drag-to-group panel | 🔒 | st.multiselect rebuilding gridOptions |
| Range selection + live Σ/avg status bar | 🔒 | st.dataframe + Python metrics (close, not identical) |
| Range copy to clipboard (TSV → Excel) | 🔒 | st.dataframe native drag-select + Ctrl/Cmd+C (free) |
| Set filter · context menu · Excel export · master-detail rows · tool panel | 🔒 | default filters free · two linked grids · st.download_button |

`enable_enterprise_modules=True` loads the enterprise build in **trial mode**
(console notice) — fine locally, license required to ship. With it `False`,
🔒 features simply don't activate; everything else keeps working.

## Gotchas (all hit and verified empirically)

1. **`from_dataframe()` injects `autoSizeStrategy: {type: "fitGridWidth"}`** —
   overrides explicit per-column `width=`, and collapses every column to
   ~36 px if it fires while the component iframe measures 0 px (first paint,
   hidden tab). Whenever you size columns by hand:
   ```python
   go = gb.build()
   go.pop("autoSizeStrategy", None)
   AgGrid(df, gridOptions=go, ...)
   ```
2. **JsCode is silently dropped** unless the AgGrid call has
   `allow_unsafe_jscode=True`.
3. **`aggFunc="avg"` returns `{count, value}` objects on group rows** (nested
   re-weighting) — a string formatter `"x.toFixed(3)"` throws there. Unwrap in
   a JsCode formatter (`if (typeof v === 'object') v = v.value;`). `sum`
   returns a plain number.
4. **Repeated `configure_column` calls on one field reset omitted kwargs** — a
   second call adding only `cellStyle` wipes `header_name`/`valueFormatter`
   from the first. Pass everything in one call.
5. **`selected_rows` is a DataFrame (or None) in 1.x** — pre-1.0 returned a
   list of dicts; check `isinstance` if supporting both.
6. Grids inside `st.tabs` mount at 0 width while hidden — see gotcha 1.
7. Edited numeric cells can come back as strings —
   `pd.to_numeric(..., errors="coerce")`.

## Column order — default order & interactive reorder

**Default (display) order = the DataFrame's column order.** `from_dataframe()`
builds `columnDefs` in that order and the grid renders them in that order.
Control it by ordering the frame:

```python
df = df[["region", "action", "latency", "requests"]]   # this IS the display order
gb = GridOptionsBuilder.from_dataframe(df)
```

- **`configure_column` does NOT reorder** — it edits an existing colDef in
  place, so call sequence has no effect on position. Arrange the DataFrame.
- **`pinned="left"`/`"right"`** pulls a column to the edge regardless of
  position; among several pinned columns, relative order is still DataFrame order.
- Hand-built `columnDefs` (list of dicts) → the list order is the display order.

**Interactive drag-reorder** is on by DEFAULT (headers are movable, no config).
Disable with `gb.configure_default_column(suppressMovable=True)` (or
`suppressMovableColumns=True` grid-wide). Two known issues if you keep it on:

1. **Rerun storm** — `columnMoved` fires on every micro-move during the drag,
   each a Streamlit rerun. Gate it to drag-end:
   ```python
   should_return = JsCode('''
   function should_return({streamlitRerunEventTriggerName, eventData}){
       if (streamlitRerunEventTriggerName == 'columnMoved') return eventData.finished;
       return true;
   }''')
   AgGrid(df, ..., should_return_js=should_return, allow_unsafe_jscode=True)
   ```
2. **Reorder lost on rerun** — the grid rebuilds from `columnDefs` (Python
   order) every rerun, so a user drag snaps back on the next unrelated rerun.
   Persist it yourself: `update_mode` must include `GridUpdateMode.COLUMN_MOVED`
   (NOT part of VALUE_CHANGED), read `resp.columns_state`, stash in
   `session_state`, re-apply via `initialState={"columnOrder": {"orderedColIds":
   [...]}}`. Requires a stable `key` (changing key or `reload_data=True` wipes
   state). Same remount class as the density toggle.

## Pattern — selection driving other widgets (master/detail, fan-out)

```python
gb.configure_selection(selection_mode="single", use_checkbox=False)
resp = AgGrid(df, gridOptions=gb.build(),
              update_mode=GridUpdateMode.SELECTION_CHANGED, key="master")
sel = resp.selected_rows          # DataFrame, or None when empty
if sel is not None and len(sel):
    name = sel.iloc[0]["id"]
    c1, c2 = st.columns(2)        # layout is free: side-by-side, stacked, anywhere
    with c1: AgGrid(curve_for(name),  ..., key=f"curve-{name}")
    with c2: st.line_chart(history_for(name))
```

Rules that make fan-out robust: detail widgets get a `key` that includes the
selection (remount fresh, not patch stale state); only the master grid sets
`update_mode=SELECTION_CHANGED` (details stay display-only).

## Pattern — row grouping / in-grid aggregation (🔒)

```python
gb.configure_column("region", rowGroup=True, hide=True, enableRowGroup=True)
gb.configure_column("latency", aggFunc="avg", valueFormatter=avg_fmt)   # JsCode, gotcha 3
gb.configure_column("requests", aggFunc="sum")
gb.configure_grid_options(
    groupDefaultExpanded=0,
    rowGroupPanelShow="always",              # drag-to-group strip (client-side)
    autoGroupColumnDef={"headerName": "Region", "minWidth": 160,
                        "cellRendererParams": {"suppressCount": True}},  # no "(45)"
    suppressAggFuncInHeader=True,
)
AgGrid(view, ..., enable_enterprise_modules=True, allow_unsafe_jscode=True)
```

Dynamic grouping, two ways: `st.multiselect` → set `rowGroup=True,
rowGroupIndex=i` per chosen column and put the choice in the grid `key`
(server-side, app sees it, costs a rerun) · or the drag panel (instant,
client-side, Python never sees it, resets on rerun). Both coexist fine.

## Pattern — weighted-average aggregation (the JsCode that returns 0)

Weighting one column by another (latency weighted by request volume, price by
quantity) is the aggFunc that everyone gets wrong. **A custom aggFunc runs on
GROUP rows, and there `params.data` is `undefined` and `params.values` holds
only THIS column's values** — so any aggFunc that reaches for a sibling weight
column (`params.data.requests`, another field) reads `undefined`, and
`value * undefined` → `NaN`, guarded down to **0**. That is the zero. There is
no way to see a second column from inside the aggFunc.

Fix: **carry the weight INSIDE the value.** A `valueGetter` turns each leaf into
`{value, weight}`; the aggFunc sums `value*weight` and `weight`, divides, and
returns the *same shape* so it re-aggregates correctly up every level of the
tree — **which is exactly what makes it drill-down-safe**: a region→percentile
group re-weights its child percentile results, and each of those re-weights its
leaves, so every level you expand shows a true weighted mean, never an
average-of-averages:

```python
# leaf rows -> {value, weight}; group rows return null so the aggFunc runs
weighted_value = JsCode('''
function(p){ if(!p.data) return null;
  return {value: p.data.latency_ms, weight: p.data.requests}; }''')

# runs on group rows; children (leaf OR sub-group) both carry .value/.weight
weighted_avg = JsCode('''
function(p){ let vw=0, w=0;
  p.values.forEach(function(o){ if(o && o.weight){ vw += o.value*o.weight; w += o.weight; }});
  // w===0 (empty / all-zero-weight group) -> null, NOT 0: divide-by-zero would
  // give NaN, and a fake 0.0 misreads as "0ms latency". null renders blank and
  // its weight:0 makes a PARENT skip it (o.weight is falsy), so it stays out of
  // the higher-level mean too.
  return {value: w ? vw/w : null, weight: w,
          toString: function(){ return this.value == null ? '' : this.value.toFixed(1); }}; }''')

gb.configure_column("latency_ms", valueGetter=weighted_value, aggFunc=weighted_avg)
AgGrid(df, ..., enable_enterprise_modules=True, allow_unsafe_jscode=True)
```

**Zero total weight is handled by the `w ? … : null` guard** — no NaN, no
Infinity, no fabricated 0. Zero-weight *leaves* are already excluded (`if(o &&
o.weight)` treats weight 0 as falsy), so one zero-request row never poisons the
average and an all-zero group shows blank. (streamlit-pivot's `sum_over_sum`
does the same: `Σden === 0 → null`.)

Four things that keep it at 0 / blank — check in this order:
1. **`allow_unsafe_jscode=True` missing** → the JsCode is silently dropped
   (gotcha 2); the column reverts to a plain/blank value. Easiest miss.
2. **Weight not carried in the value** → aggFunc can't see it (the root cause above).
3. **No `toString` (or `valueFormatter`)** → the aggFunc returns an OBJECT; a
   string formatter like `"x.toFixed(1)"` *throws* on it (same trap as gotcha
   3 for built-in `avg`). The inline `toString` renders it; a JsCode formatter
   that unwraps `.value` also works.
4. **`enable_enterprise_modules` not set** → grouping/aggregation never activates.

Don't need interactive in-grid grouping? A pandas weighted mean into a flat
community grid is far less fragile — `np.average(g.latency_ms, weights=g.requests)`
per group — and is the default steer in the grid matrix. Reach for the JsCode
only when users drag grouping around client-side.
## Pattern — pivot mode: split a column into COLUMNS (🔒)

AG Grid's equivalent of Perspective `split_by` / a spreadsheet column pivot.
Row grouping turns a column's values into *rows*; **pivot mode** turns them
into *columns*. `pivotMode=True` + `pivot=True` on a dimension column:

```python
gb.configure_column("pctl",   rowGroup=True, hide=True)  # the ROW dimension
gb.configure_column("region", pivot=True)                # VALUES → columns (the split)
gb.configure_column("lat_ms", aggFunc="avg")             # aggregated into each cell
gb.configure_grid_options(pivotMode=True)
AgGrid(view, ..., enable_enterprise_modules=True)         # 🔒 enterprise
```

Result: one column group per distinct `region` value, rows grouped by `pctl`,
each cell the avg. **Gotcha (verified):** auto-generated pivot columns inherit
**no** `valueFormatter` — not the measure's, not `defaultColDef`'s — and
rounding the input can't fix it because the grid re-aggregates. Format them via
the `processPivotResultColDef` grid callback:

```python
fmt = JsCode('''function(colDef){
    colDef.valueFormatter = function(p){ return p.value == null ? '' : Number(p.value).toFixed(1); };
    return colDef;
}''')
gb.configure_grid_options(pivotMode=True, processPivotResultColDef=fmt)
```

Community **cannot** pivot columns at all — free routes: streamlit-pivot
`columns=["region"]` or Perspective `split_by`.

## Pattern — editable cells

```python
gb.configure_column("target", editable=True)
gb.configure_column("action", editable=True, cellEditor="agSelectCellEditor",
                    cellEditorParams={"values": ["page", "watch", "mute"]})
resp = AgGrid(st.session_state.df, gridOptions=gb.build(),
              update_mode=GridUpdateMode.VALUE_CHANGED, key="edit")
st.session_state.df = pd.DataFrame(resp.data)   # persist or edits vanish on rerun
```

## Formatting — the full matrix

| Target | Mechanism | Notes |
|---|---|---|
| Numbers | `valueFormatter` string expr | `"x.toFixed(2) + '%'"`; null-guard: `"x == null ? '' : …"` |
| One column, static | `cellStyle={...}` dict | paints EMPTY cells too (unlike value rules elsewhere) |
| Per cell, by value | `cellStyle=JsCode(fn)` | return a style object |
| Condition → CSS class | `cellClassRules={"cls": "x > 400"}` | style the class via `custom_css` |
| Whole row, by data | `getRowStyle=JsCode(fn)` | `params.data` is the row |
| Row condition → class | `rowClassRules={"cls": "data.region == 'ap-south-1'"}` | via `custom_css` |
| Global CSS | `AgGrid(custom_css={".ag-cell": {...}})` | selector → property dict |

Precedence: JsCode `cellStyle` > class rules > row style.

## Compact / dense grids

```python
gb.configure_grid_options(rowHeight=24, headerHeight=26)
AgGrid(df, ..., custom_css={".ag-cell": {"font-size": "11px"},
                            ".ag-header-cell-text": {"font-size": "11px"}})
```

24 px rows + 11 px font ≈ terminal density (stock ~40 px/13 px). If density is
a toggle, put the flag in the grid `key` — row height is fixed at mount.

## Excel-like range selection + Σ/avg + copy (🔒, no free equivalent)

```python
gb.configure_grid_options(
    cellSelection=True,        # drag ranges like Excel (was enableRangeSelection)
    statusBar={"statusPanels": [
        {"statusPanel": "agTotalRowCountComponent", "align": "left"},
        {"statusPanel": "agAggregationComponent", "align": "right"}]},
)
AgGrid(df, ..., enable_enterprise_modules=True)
```

Drag (or click + shift-click) a range → status bar shows live Average / Count /
Min / Max / Sum. Ctrl/Cmd+C copies the range as TSV (raw values, not formatted);
Ctrl+A selects all.
