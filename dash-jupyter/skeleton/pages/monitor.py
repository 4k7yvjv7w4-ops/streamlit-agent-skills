import dash
from dash import html, dcc, callback, Input, Output
dash.register_page(__name__, path="/monitor", name="Monitor")
layout = html.Div([dcc.Input(id="thr", value="150"), html.Div(id="echo")])
@callback(Output("echo", "children"), Input("thr", "value"))
def echo(v): return f"threshold={v}"
