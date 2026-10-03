"""dash-grid lab — dash-ag-grid essentials + DataTable for the simple cases.

Run:  python dash_grid_lab.py        Test: python test_dash_grid.py (headless browser)

  * columnDefs with JS-function props: valueFormatter (d3.format built in),
    cellStyle, and a CUSTOM function from assets/dashAgGridFunctions.js
  * single-row selection -> selectedRows -> Python callback
  * dash_table.DataTable for a plain, no-JS table
"""

import numpy as np
import pandas as pd
import dash_ag_grid as dag
from dash import Dash, Input, Output, callback, dash_table, dcc, html

rng = np.random.default_rng(0)
DF = pd.DataFrame({
    "service": ["auth", "search", "media", "billing"] * 3,
    "region": ["us-east-1"] * 4 + ["eu-west-1"] * 4 + ["ap-south-1"] * 4,
    "p95_ms": rng.uniform(60, 400, 12).round(1),
    "sla_ms": [150, 200, 300, 250] * 3,
    "requests": rng.integers(100, 9000, 12),
})

columnDefs = [
    {"field": "service", "checkboxSelection": False},
    {"field": "region"},
    {"field": "p95_ms", "headerName": "p95 (ms)",
     "valueFormatter": {"function": "d3.format(',.1f')(params.value)"},   # d3 is bundled
     "cellStyle": {"function":
                   "params.value > params.data.sla_ms ? {'color': '#b00020', 'fontWeight': 600} : null"}},
    {"field": "sla_ms", "headerName": "SLA"},
    {"field": "p95_ms", "headerName": "status", "colId": "status",
     "valueFormatter": {"function": "slaFlag(params)"}},                   # from assets/
    {"field": "requests", "valueFormatter": {"function": "d3.format(',')(params.value)"}},
]

app = Dash(__name__)
app.layout = html.Div(style={"maxWidth": "900px", "margin": "auto"}, children=[
    html.H3("dash-grid — AG Grid in Dash"),
    dag.AgGrid(
        id="grid",
        rowData=DF.to_dict("records"),
        columnDefs=columnDefs,
        defaultColDef={"sortable": True, "filter": True, "resizable": True},
        dashGridOptions={"rowSelection": "single", "animateRows": False},
        columnSize="sizeToFit",
        getRowId="params.data.service + params.data.region",     # stable ids -> selection survives updates
        style={"height": 360},
    ),
    html.Div(id="picked", children="click a row"),
    html.H4("DataTable (no JS, plain cases)"),
    dash_table.DataTable(id="plain", data=DF.head(4).to_dict("records"),
                         columns=[{"name": c, "id": c} for c in DF.columns],
                         sort_action="native", page_size=5),
])


@callback(Output("picked", "children"), Input("grid", "selectedRows"))
def picked(rows):
    if not rows:
        return "click a row"
    r = rows[0]
    return f"selected: {r['service']} @ {r['region']} — p95 {r['p95_ms']} vs SLA {r['sla_ms']}"


if __name__ == "__main__":
    app.run(debug=True)
