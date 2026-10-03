---
name: dash-grid
description: Tables in Plotly Dash — dash-ag-grid (AG Grid) for interactive grids and dash_table.DataTable for plain ones. Covers columnDefs with JS-function props ({"function" - valueFormatter/cellStyle/cellRenderer}), the assets/dashAgGridFunctions.js namespace for custom JS, row selection → selectedRows → callback, getRowId stability, community-vs-enterprise features, and porting st-aggrid/st-dataframe knowledge. Use for any grid/table in Dash or when a JS function prop "does nothing".
---

# Grids in Dash (verified on dash-ag-grid 35 / dash 4.4, in a real browser)

**Pick:** interactive grid (sort/filter/select/format/edit) → `dash-ag-grid`
· plain small table, no JS → `dash_table.DataTable`. Proof:
`dash_grid_lab.py` + `test_dash_grid.py` (headless Chromium: rows render,
formatters run, custom function runs, click reaches Python).
Everything you know from [st-aggrid] (JsCode styling, weighted averages,
license map) carries over — the SYNTAX for JS changes, the ideas don't.

## The grid

```python
import dash_ag_grid as dag

dag.AgGrid(
    id="grid",
    rowData=df.to_dict("records"),
    columnDefs=[
        {"field": "service"},
        {"field": "p95_ms", "headerName": "p95 (ms)",
         "valueFormatter": {"function": "d3.format(',.1f')(params.value)"},   # d3 bundled
         "cellStyle": {"function": "params.value > params.data.sla_ms ? {'color':'#b00020'} : null"}},
        {"field": "p95_ms", "colId": "status", "headerName": "status",
         "valueFormatter": {"function": "slaFlag(params)"}},                   # YOUR js, see below
    ],
    defaultColDef={"sortable": True, "filter": True, "resizable": True},
    dashGridOptions={"rowSelection": "single", "animateRows": False},
    getRowId="params.data.service + params.data.region",   # stable ids: selection survives rowData updates
    columnSize="sizeToFit", style={"height": 360},
)

@callback(Output("picked", "children"), Input("grid", "selectedRows"))
def picked(rows):                       # [] when nothing selected — guard it
    return rows[0]["service"] if rows else "click a row"
```

## JS-function props — the rules (verified)

- Any prop that AG Grid expects as a function is written as
  `{"function": "<js expression using params>"}`. The expression is the
  function BODY's return value — no `function(params){}` wrapper, no `return`.
- `d3` (format/scale) is available in those expressions; use it for numbers.
- **Custom functions live in `assets/dashAgGridFunctions.js`** and must be
  attached to `window.dashAgGridFunctions`:
  ```js
  var dagfuncs = (window.dashAgGridFunctions = window.dashAgGridFunctions || {});
  dagfuncs.slaFlag = function (params) { return params.value > params.data.sla_ms ? "BREACH" : "ok"; };
  ```
  then `{"function": "slaFlag(params)"}`. A function defined anywhere else is
  silently not found → the cell shows the raw value. Dash serves `assets/`
  automatically (prefix-aware under Jupyter — [dash-jupyter]).
- Same namespace trick for `cellRenderer` components: `window.dashAgGridComponentFunctions`.
- Two columns on the same `field` need distinct `colId`s or the second is
  dropped.

## Selection, editing, updates

- `selectedRows` is the Python-facing prop (list of row dicts). `cellClicked`
  gives `{rowIndex, colId, value}` for click-anywhere semantics.
- Editable: `"editable": True` in a columnDef → `cellValueChanged` carries
  `oldValue/value/data`. Validate server-side; the grid trusts the browser.
- Replace rows with a new `rowData` (whole list); with `getRowId` set the grid
  keeps scroll + selection. Append/update individual rows via `rowTransaction`.
- Big tables: paginate (`dashGridOptions={"pagination": True}`) or aggregate
  first ([dash-data]) — rowData rides in the page as JSON.

## Community vs enterprise (same map as st-aggrid)

Free: sort, filter, select, edit, formatters/styles, pagination, column
groups. **Enterprise** (`enableEnterpriseModules=True` + `licenseKey=`):
row grouping/aggregation (incl. custom aggFuncs like weighted averages),
pivot, range selection, Excel export, status bar. The enterprise bundle
ships in the wheel but renders a watermark without a key. Need grouping with
no license → aggregate in SQL and show a flat grid.

## DataTable (plain cases)

`dash_table.DataTable(data=records, columns=[{"name": c, "id": c} ...],
sort_action="native", page_size=20)` — no JS, no assets, decent for ≤ a few
thousand rows; conditional styling via `style_data_conditional` (declarative
filters, not JS).
