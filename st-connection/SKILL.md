---
name: st-connection
description: Load external data into Streamlit correctly — st.connection (SQL / custom BaseConnection), cached query functions with ttl, secrets.toml, and the caching rules that stop every rerun re-hitting your database. Use when an app reads from a DB / warehouse / API, when data should refresh on a schedule, or when the app "feels stuck" because it re-queries on every widget touch.
---

# st-connection — data access without re-querying every rerun

The whole script reruns on every widget touch ([streamlit-core]), so a bare
`pd.read_sql(...)` at script level re-hits the DB on EVERY interaction — the #1
"my app is slow / feels stuck" cause. Fix: a pooled connection +
**cached query functions**. Runnable proof: `st_connection_lab.py` in this
folder (`python -m streamlit run st-connection/st_connection_lab.py`) — a
custom sqlite connection, zero external deps. Verified on Streamlit **1.58**.

## Built-in SQL connection (the common case)

```python
conn = st.connection("warehouse", type="sql")        # needs SQLAlchemy installed
df = conn.query("select region, avg(latency_ms) FROM m GROUP BY region", ttl="10m")
```

- **The connection object is pooled** — `st.connection` caches it via
  `st.cache_resource` internally, so you get ONE shared connection across reruns
  and sessions, not a new one per run.
- **`conn.query(sql, ttl=…)` caches the RESULT** — same SQL within the ttl
  returns the cached DataFrame; no round-trip. `ttl` takes `"10m"` / seconds /
  `timedelta`; omit for cache-forever, `ttl=0` to disable. Also `params=` for
  bound params, `index_col=`, `chunksize=`.
- Config lives in **`.streamlit/secrets.toml`** under `[connections.warehouse]`
  (`url = "..."` or `dialect`/`host`/`username`/`password`/`database`). Never
  hardcode credentials; `st.secrets["..."]` reads them.

```toml
# .streamlit/secrets.toml
[connections.warehouse]
url = "postgresql://user:pass@host:5432/db"
```

## No SQLAlchemy? Hand-rolled loader — same caching rules

For a REST API, an internal pricing lib, a driver SQLAlchemy doesn't cover:

```python
@st.cache_resource                         # ONE client, shared, never re-created
def get_client():
    return PricingApi(st.secrets["api"]["token"])

@st.cache_data(ttl="5m", show_spinner="loading…")   # results cached per args
def load_series(_client, region: str, day: str):    # _client EXCLUDED from key
    return _client.fetch(region, day)                # returns a fresh COPY per call

df = load_series(get_client(), "us-east-1", "2025-03-04")
```

- **`@st.cache_resource`** for the connection/client/model — the SAME object for
  everyone; never mutate it per-user (add a lock if you must).
- **`@st.cache_data`** for the query RESULTS — hashable args form the cache key;
  a fresh copy is returned each call (mutations safe).
- **`_`-prefix any unhashable arg** (a connection, a client) to EXCLUDE it from
  the cache key — otherwise `UnhashableParamError`. This is the one everyone hits.

## Custom BaseConnection (wrap any driver once, reuse everywhere)

Subclass `BaseConnection`, implement `_connect`; `self._instance` is the pooled
driver handle, `self._secrets` is your `[connections.<name>]` section:

```python
from streamlit.connections import BaseConnection
import sqlite3, pandas as pd

class SQLiteConnection(BaseConnection[sqlite3.Connection]):
    def _connect(self, **kw):
        return sqlite3.connect(self._secrets.get("path", ":memory:"),
                               check_same_thread=False)
    def query(self, sql, ttl=None):
        @st.cache_data(ttl=ttl)
        def _run(q): return pd.read_sql(q, self._instance)
        return _run(sql)

conn = st.connection("lat_db", type=SQLiteConnection)   # pooled like the built-ins
```

## Refresh & invalidation

- **`ttl` is the scheduler** — `ttl="30s"` re-fetches at most twice a minute;
  the widget-driven reruns in between serve cached data (see [streamlit-core]).
- **Manual refresh button:** `load_curve.clear()` (one function) or
  `st.cache_data.clear()` (all) then `st.rerun()` — behind a flip-first guard.
- **Live section reading a NO-ttl cache never updates** — the classic
  fragment-refresh trap ([streamlit-core]); give the loader a `ttl` ≤ the
  refresh cadence.
- Connections auto-recover from a dropped link on next `query`; force it with
  `conn.reset()`.

## Gotchas (verified)

- **A bare query at script level re-runs on every widget touch** — always wrap
  loads in `@st.cache_data`. Add a `st.session_state.runs += 1` counter to see it.
- **`UnhashableParamError`** → an unhashable arg (connection/client/DataFrame)
  is in the cache key; `_`-prefix it.
- **Secrets are per-scope**: `.streamlit/secrets.toml` in the app dir (local) or
  the platform's secrets store (deployed). Missing key → `KeyError` at
  `st.secrets[...]`; `st.secrets.get(...)` to default.
- **`cache_resource` is shared across ALL sessions** — fine for a read pool,
  dangerous for per-user/stateful handles; scope those in `session_state`.
- **Don't put secrets in the cache key**: `load(_client, day)` not
  `load(token, day)` — a rotating token would fragment the cache and leak into it.
- Testable headlessly: inject creds with `AppTest.secrets["k"]=...` before
  `.run()` ([st-testing]); the lab passes AppTest clean.
