---
name: dash-data
description: Data access in Plotly Dash — translating Streamlit's cache_resource/cache_data habits to a module-singleton connection, a SHARED flask-caching memoize keyed by primitives, cursor-per-callback DuckDB over parquet/S3 lakes, and Store-safe (JSON-able) results. Use when loading data in a Dash app, when "every callback re-queries", when a dcc.Store refuses a DataFrame, or when porting st-duckdb/st-connection code to Dash.
---

# Data access in Dash (verified on dash 4.4 and 3.2 / duckdb 1.5)

Proof: `dash_data_lab.py` + `test_dash_data.py` (fetch counter, 8-thread
cursor hammer, JSON round-trip). The LAKE side is framework-agnostic — hive
layout, pushdown, the pyarrow/S3-wrapper route — read it in [st-duckdb] /
[st-parquet]; only the caching and the hand-off to components change here.

## The translation table

| Streamlit | Dash | Why |
|---|---|---|
| `@st.cache_resource` connection | module-level singleton (`_CON`, lazy `db()`) | one process serves everyone; a read-only engine is a safe global |
| `@st.cache_data(ttl=…)` | `@cache.memoize()` from flask-caching | SHARED by all users (cache_data was too); keyed by call args |
| return a DataFrame | return `df.to_dict("records")` | callbacks hand results to `dcc.Store` / grids — JSON only |
| cached function reads `session_state` | never — args only | there is no per-user state on the server |

```python
_CON = None
def db() -> duckdb.DuckDBPyConnection:          # == cache_resource
    global _CON
    if _CON is None:
        _CON = duckdb.connect()
        _CON.execute("CREATE VIEW events AS SELECT * FROM read_parquet('…/*/*.parquet', hive_partitioning=true)")
    return _CON

app = Dash(__name__)
cache = Cache(app.server, config={"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 600})

@cache.memoize()                                 # == cache_data(ttl=600), SHARED
def fetch_regions(service: str) -> list[dict]:   # primitives in, JSON out
    cur = db().cursor()                          # cursor per call — thread-safe (verified)
    return cur.execute("SELECT region, avg(latency_ms) avg_ms FROM events "
                       "WHERE service = ? GROUP BY 1", [service]).df().to_dict("records")

@callback(Output("store", "data"), Input("svc", "value"))
def load(svc): return fetch_regions(svc)
```

## Rules (verified)

- **Cursor per callback, never a shared cursor.** Callbacks run in server
  threads; the singleton connection + `.cursor()` per call survived an
  8-thread hammer. Views/registered datasets made on the parent are visible
  to cursors (register() of in-memory frames is NOT — see [st-duckdb]).
- **memoize = shared.** Same key → same result for ALL users; keys must be
  primitives (str/int/tuple). Never memoize on a per-user id unless you WANT
  per-user entries (and then expect memory to grow with users). TTL via
  `CACHE_DEFAULT_TIMEOUT` or `@cache.memoize(timeout=60)`.
- **Store-safe results**: `dcc.Store` takes JSON — records lists, dicts,
  `json.loads(fig.to_json())` for figures. A DataFrame in `Store.data` fails
  at serialization time, not in Python. Dates: keep ISO strings.
- **Bind parameters** (`?` + list) — never f-string user input into SQL; the
  key input IS user input.
- **Multi-worker deploy** (gunicorn `-w 4`): `SimpleCache` is per process →
  each worker fetches once; fine for small bundles. Shared cache across
  workers = `FileSystemCache` / Redis (documented, not lab-verified).
- Testing: call memoized functions inside `with app.server.app_context():`
  (flask-caching needs it outside a request).
