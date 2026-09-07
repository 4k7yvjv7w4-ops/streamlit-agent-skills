---
name: dash-jupyter
description: Running a Plotly Dash app from inside JupyterLab / JupyterHub behind a corporate proxy — fixes the blank page, 404s on _dash-component-suites, and dead callbacks by pairing jupyter-server-proxy with requests_pathname_prefix. Ships a verified skeleton (app.py + pages/) ready to copy, covers notebook-cell modes (jupyter_mode, infer_jupyter_proxy_config), the missing-trailing-slash silent failure, and port-in-use on cell re-run. Use whenever Dash must be developed or served from a Jupyter environment.
---

# Dash inside JupyterLab/JupyterHub (verified on dash 4.4)

Load [dash-core] for the framework itself; this skill is only about making it
reachable from a Jupyter environment.

## Why the page is blank

Your Dash server binds `localhost:PORT` **on the Jupyter machine** — your
browser talks only to the Jupyter/Hub web proxy and can never reach that port
directly. `jupyter-server-proxy` (a Jupyter extension) bridges it: it exposes
your port at `<jupyter-base>/proxy/PORT/` and **strips that prefix** before
forwarding. So there are two different URL worlds, and Dash must be told about
both:

- **Browser side** — every asset/callback URL Dash writes into the page must
  start with the proxy prefix → `requests_pathname_prefix`.
- **Server side** — requests arrive with the prefix already stripped, so the
  routes stay at root → `routes_pathname_prefix="/"`.

Without this, the HTML loads but every `_dash-component-suites` fetch 404s at
the hub root (blank page), and `_dash-update-component` POSTs die (frozen
callbacks). Prereq once per environment: `pip install jupyter-server-proxy`
into the environment the **Jupyter server** runs in, then restart Jupyter
(if `<base>/proxy/PORT/` itself 404s, the extension isn't installed/loaded).

## The skeleton (verified — copy `skeleton/` and go)

```python
import os
import dash
from dash import Dash, dcc, html

PORT = 8519
BASE = os.environ.get("JUPYTERHUB_SERVICE_PREFIX", "/")   # "/user/<you>/" on Hub, "/" on plain Lab
PREFIX = f"{BASE}proxy/{PORT}/"                           # trailing slash REQUIRED

app = Dash(__name__, use_pages=True,
           requests_pathname_prefix=PREFIX,               # what the browser sees
           routes_pathname_prefix="/")                    # what the server serves

app.layout = html.Div([
    html.Div([dcc.Link(p["name"], href=p["relative_path"])
              for p in dash.page_registry.values()]),
    dash.page_container,
])

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, debug=False)     # proxy is local — no 0.0.0.0 needed
```

Run it from a **JupyterLab terminal** (`python app.py`) — the right mode for a
real app: survives kernel restarts, logs visible. Then open
`https://<your-jupyter-host><PREFIX>` (e.g.
`https://hub.internal/user/you/proxy/8519/`).

Verified end-to-end: asset URLs come out prefixed, routes serve at the
stripped root, callbacks round-trip, and **dash pages need no extra work** —
`page_registry[...]["relative_path"]` already includes the prefix, so
`dcc.Link` navigation just works. Never hardcode `/user/<name>/` — read
`JUPYTERHUB_SERVICE_PREFIX` (unset on plain JupyterLab, hence the `"/"`
default).

## Notebook-cell mode (quick experiments only)

Dash absorbed jupyter-dash; `app.run()` detects notebooks:

```python
from dash import jupyter_dash
jupyter_dash.infer_jupyter_proxy_config()   # JupyterHub: call FIRST, in its own cell
app.run(jupyter_mode="external")            # prints the proxied link; "inline" = iframe in the cell
```

(API-checked on dash 4.4; the infer call needs a live Hub to fully exercise —
if it can't detect your setup, fall back to the explicit-prefix skeleton
above, which needs no detection.) Keep `debug=False` or at least never enable
the reloader in a notebook — the reloader re-executes the process and
notebooks can't. Re-running the cell → "Address already in use": the old
server thread still holds the port; bump `PORT` or restart the kernel. For
anything beyond a throwaway, use the terminal mode.

## Gotchas (verified unless marked)

- **Missing trailing slash fails SILENTLY**: `requests_pathname_prefix=
  "/proxy/8519"` is accepted, then emits mangled URLs like
  `/proxy/8519_dash-component-suites/...` → 404s, blank page, no Python error.
  A missing LEADING slash at least raises `InvalidConfig`. Always end with `/`.
- Blank page or 404s on `_dash-component-suites` → wrong/missing
  `requests_pathname_prefix`. Frozen callbacks with the page rendering → same
  root cause (the POST goes to the unprefixed path).
- `jupyter-server-proxy` also offers `/proxy/absolute/PORT/` which does NOT
  strip the prefix — if you use that variant, set `routes_pathname_prefix=
  PREFIX` too (both sides prefixed). Default `/proxy/PORT/` strips; keep
  routes at `"/"`. (Stripping behavior is the extension's documented default.)
- Deploying later outside Jupyter? The same app runs unchanged with
  `PREFIX="/"` — the env-var default degrades gracefully; behind a corporate
  reverse proxy path, reuse the exact same two-prefix mechanics.
