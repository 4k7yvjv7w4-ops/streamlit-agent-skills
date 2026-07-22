---
name: st-duckdb
description: DuckDB as the in-app query engine for a Streamlit + S3/parquet setup — SQL (joins, aggregations) directly over parquet/CSV lakes without loading whole DataFrames: cached connection + cursor-per-operation, views over sources, httpfs/S3 credentials (plus a no-httpfs fsspec/s3fs fallback when the extension can't be installed), register() to join in-memory frames with the lake, arrow/df result handoff, cache_data on queries. Use when a Streamlit page needs SQL over files, cross-file joins, or pandas groupby/merge chains are slow/memory-hungry.
---

# st-duckdb — SQL over your lake, inside the app

Query parquet/CSV **in place** (pushdown included) and return only the small
result — instead of `read_parquet` → giant DataFrame → pandas merges. Runnable
proof: `st_duckdb_lab.py`. Verified on **duckdb 1.x / Streamlit 1.58**.
Companions: [st-parquet] (lake layout/pushdown rules), [st-connection]
(caching rules), [st-mcp-server] (the same engine behind MCP tools).

## The Streamlit wiring (verified)

```python
import duckdb, streamlit as st

@st.cache_resource                       # ONE connection per process
def db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()               # in-memory catalog; data stays in files
    con.execute("CREATE VIEW events AS SELECT * FROM "
                "read_parquet('data/lake/*/*.parquet', hive_partitioning=true)")
    con.execute("CREATE VIEW sla AS SELECT * FROM read_csv_auto('data/sla.csv')")
    return con

@st.cache_data(ttl="10m", show_spinner=False)
def q(sql: str) -> "pd.DataFrame":       # results cached; reruns don't re-scan
    return db().cursor().execute(sql).df()
```

- **`cache_resource` the connection, take a `.cursor()` per operation.**
  Verified: a cursor shares the parent's views/catalog, and concurrent script
  threads querying via their own cursors run clean. (A shared raw connection
  also survived a 8-thread hammer — DuckDB synchronizes internally — but
  cursors give independent result streams; never share one mid-fetch.)
- **`cache_data` the query results** — same rules as [st-connection]: ttl on
  live data, no ttl for immutable past dates, `_con`-style exclusion not
  needed here because `q()` takes only the SQL string (hashable, IS the key).
- Views make the seam: pages speak table names; when files move (or you
  promote a clean "silver" copy — [st-mcp-server]'s measured advice), only
  the `CREATE VIEW` strings change.

## S3 — same code, `s3://` paths

```python
con.execute("INSTALL httpfs; LOAD httpfs;")          # one-time download
con.execute("CREATE SECRET (TYPE s3, PROVIDER credential_chain)")  # env/profile/IAM role
con.execute("CREATE VIEW events AS SELECT * FROM "
            "read_parquet('s3://bkt/lake/*/*.parquet', hive_partitioning=true)")
```

- `credential_chain` uses the standard AWS chain (env → profile → IAM role) —
  no keys in code ([st-parquet] rules). Internal/MinIO endpoints:
  `CREATE SECRET (TYPE s3, ENDPOINT 'minio.internal:9000', URL_STYLE 'path', …)`.
- **Corporate/air-gapped:** `INSTALL httpfs` downloads the extension from
  duckdb.org once (this environment's proxy blocks it — S3 specifics are
  API-documented, not lab-verified). Behind a strict proxy, vendor the
  `httpfs.duckdb_extension` file and `INSTALL 'path/to/httpfs.duckdb_extension'`
  / `SET extension_directory` — then everything is offline.
- Pushdown carries over S3: partition + projection + zone-maps mean you pay
  for slices, not the lake ([st-parquet]). Filter in SQL, never in pandas after.

## No httpfs? Two verified fallbacks (pure pip wheels, nothing to INSTALL)

`pip install fsspec s3fs` — ordinary packages, they come through any
proxy/internal index even where the extension download is blocked.

```python
import fsspec
fs = fsspec.filesystem("s3")        # same AWS credential chain as boto3
con.register_filesystem(fs)         # do this BEFORE the CREATE VIEW lines
con.execute("CREATE VIEW events AS SELECT * FROM "
            "read_parquet('s3://bkt/lake/*/*.parquet', hive_partitioning=true)")
```

- **Verified** (against an fsspec filesystem standing in for s3fs): hive-partition
  pruning still shows up as file filters in `EXPLAIN`, and **cursors inherit the
  registered filesystem** — the cache_resource + cursor wiring above is unchanged.
- Alternative, if you already build pyarrow datasets ([st-parquet]):
  `con.register("events", pads.dataset("bkt/lake", filesystem=fs, partitioning="hive"))`
  — verified: the plan is an `ARROW_SCAN` with projections AND filters pushed down.
- Ranking: httpfs (native reader) is the fastest for big scans → vendored-extension
  install when you can ship a file → fsspec/s3fs as the works-anywhere route.

## Join the lake with in-memory frames — `register()` (verified)

The Streamlit-specific superpower: a widget-driven DataFrame can JOIN the lake
without writing it anywhere:

```python
overrides = editor_df                       # e.g. from st.data_editor
cur = db().cursor()
cur.register("overrides", overrides)        # pandas/arrow frame -> a table name
df = cur.execute("""SELECT e.region, avg(e.latency_ms) avg_ms, any_value(o.new_sla) sla
                    FROM events e JOIN overrides o USING(region)
                    GROUP BY e.region""").df()
```

## Results out (verified)

- `.df()` → pandas (the default for `st.dataframe`/charts).
- `.to_arrow_table()` → pyarrow Table — `st.dataframe` takes it directly;
  (`fetch_arrow_table()` is deprecated — don't emit it).
- ALWAYS aggregate or `LIMIT` in SQL before materializing — `.df()` on an
  unbounded `SELECT *` hauls the lake into memory, the exact thing this skill
  exists to avoid.

## Gotchas (verified unless marked)

- Views live in the connection's in-memory catalog — created once inside the
  `cache_resource` factory, they exist for the process's lifetime. Changing
  view definitions needs `db.clear()` + rerun (remakes the connection).
- Mismatched key names/formats across files → normalize IN the views, and
  re-save big fact tables clean — the measured 4–15x penalty and the
  `regexp_replace`-not-`ltrim` trap are in [st-mcp-server].
- `read_csv_auto` re-parses the CSV per query — fine for small reference
  files, promote big CSVs to parquet ([st-parquet]).
- A DuckDB query blocks the script thread like any other work — long scans on
  a slow lake belong in a background job ([st-jobs]).
- Don't `register()` under a name that shadows a view — last definition wins
  silently; keep in-memory names distinct (`overrides`, not `events`).
