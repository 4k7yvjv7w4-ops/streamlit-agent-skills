"""dash-layout skeleton — page structure with dash-bootstrap-components, CDN-free.

Run:  python app.py        Test: python ../test_dash_layout.py

Bootstrap's CSS is VENDORED in assets/bootstrap.min.css (Dash auto-serves
assets/, Jupyter prefix included) — dbc.themes.* are CDN URLs that a corporate
proxy blocks, which shows up as "components render but look unstyled".
Refresh the file with ../fetch_bootstrap_css.py (PyPI wheel, no CDN).
"""

import dash_bootstrap_components as dbc
from dash import Dash, Input, Output, State, callback, dcc, html

app = Dash(__name__)                       # NO external_stylesheets: assets/ carries the theme

sidebar = dbc.Offcanvas(id="sidebar", title="Filters", is_open=False, children=[
    dbc.Label("region"), dcc.Dropdown(["us-east-1", "eu-west-1"], "us-east-1", id="region"),
])

navbar = dbc.Navbar(dbc.Container([
    dbc.NavbarBrand("latency console"),
    dbc.Button("filters", id="open-sidebar", color="secondary", size="sm"),
]), color="dark", dark=True)


def card(title, body_id):
    return dbc.Card([dbc.CardHeader(title), dbc.CardBody(id=body_id)], className="h-100")


app.layout = html.Div([
    navbar, sidebar,
    dbc.Container(fluid=True, className="py-3", children=[
        dbc.Row([                                   # 12-col responsive grid; stacks on mobile
            dbc.Col(card("summary", "summary"), md=4),
            dbc.Col(card("detail", "detail"), md=8),
        ], className="g-3"),
        dbc.Tabs(id="tabs", active_tab="t-chart", className="mt-3", children=[
            dbc.Tab(label="chart", tab_id="t-chart"),
            dbc.Tab(label="table", tab_id="t-table"),
        ]),
        html.Div(id="tab-body", className="mt-2"),
        dbc.Button("open dialog", id="open-modal", className="mt-3"),
        dbc.Modal(id="modal", is_open=False, children=[
            dbc.ModalHeader(dbc.ModalTitle("confirm")),
            dbc.ModalBody("dialogs are plain components toggled by is_open"),
            dbc.ModalFooter(dbc.Button("close", id="close-modal")),
        ]),
    ]),
])


@callback(Output("summary", "children"), Output("detail", "children"), Input("region", "value"))
def fill(region):
    return f"region = {region}", f"detail for {region}"


@callback(Output("tab-body", "children"), Input("tabs", "active_tab"))
def tab(active):                               # render the ACTIVE tab only
    return "a chart would go here" if active == "t-chart" else "a grid would go here"


@callback(Output("sidebar", "is_open"), Input("open-sidebar", "n_clicks"),
          State("sidebar", "is_open"), prevent_initial_call=True)
def toggle_sidebar(_, is_open):
    return not is_open


@callback(Output("modal", "is_open"),
          Input("open-modal", "n_clicks"), Input("close-modal", "n_clicks"),
          State("modal", "is_open"), prevent_initial_call=True)
def toggle_modal(_o, _c, is_open):
    return not is_open


if __name__ == "__main__":
    app.run(debug=True)
