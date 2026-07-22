---
name: st-mcp-server
description: Build an MCP (Model Context Protocol) server in Python with FastMCP that exposes data sources — parquet lakes, SQL databases, CSV files, internal APIs — as tools an LLM can call. Use when creating/editing an MCP server, wrapping a data layer for an LLM, writing @mcp.tool functions, choosing stdio vs streamable-http transport, or testing a server without a client app. Ships a runnable reference server + in-memory test.
---

# mcp-server — expose your data layer as LLM-callable tools

Reference implementation: `mcp_data_server.py` (parquet / SQL / CSV / API
tools) + `test_mcp_server.py` (drives the real server through a real MCP
session **in memory** — run it, no client app needed). Verified on
**mcp 1.28** (`pip install mcp`). Pair with [st-mcp-client] to wire an LLM to it.

## FastMCP in 20 lines

```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("data-server")

@mcp.tool()
def query_sql(sql: str, limit: int = 100) -> list[dict]:
    """Run a READ-ONLY SQL query (SELECT/WITH only). At most `limit` rows."""
    ...

if __name__ == "__main__":
    mcp.run()                       # stdio; mcp.run(transport="streamable-http") for shared
```

- **Type hints ARE the schema** (verified): `sql: str, limit: int = 100` →
  JSON schema with `required: ["sql"]`; `list[str] | None = None` → optional
  array. No manual JSON schema.
- **The docstring IS the tool description — and descriptions are prompts.**
  The model chooses tools by reading them. Say what it does, what args mean,
  what comes back, and steering ("call list_datasets FIRST", "prefer
  aggregated queries"). A vague docstring = wrong tool calls.
- **Raise for bad input** — an exception becomes `isError: true` + your
  message to the model (verified, not a crash). Make messages actionable:
  `"unknown dataset 'x' — call list_datasets first"`.
- Return plain Python (dict/list) — the SDK serializes and also provides
  `structuredContent` to capable clients.

## Design rules for LLM-facing data tools

1. **Few coarse tools, not many micro-tools.** A 27B model picks between 5
   well-described tools far better than 25. One `query_parquet`, not
   per-dataset tools.
2. **Cap EVERYTHING.** Tool output lands in the model's context: `limit`
   param + hard cap (500 rows in the reference), column projection, one
   partition per call. Returning megabytes is a bug.
3. **Discovery tool first**: `list_datasets()` so the model can find names
   instead of hallucinating them — and say "call this FIRST" in the other
   docstrings.
4. **Read-only by construction**: SELECT/WITH prefix guard on SQL, filename
   sanitization (`Path(name).name` kills traversal), endpoint **allowlist**
   for the internal API (all verified in the test).
5. **Pushdown, not post-filter**: the parquet tool takes `date` + `columns`
   and pushes both into the read — the [st-parquet] rules apply verbatim
   inside tools.

## Sources that share keys — federate with DuckDB, don't join in the model

When several parquet datasets and CSVs share id columns, do NOT expose them as
separate fetch tools and let the model merge rows in its context — that's
token-expensive, capped, and a mid-size model mis-joins silently. Register the
files as VIEWS in DuckDB (queries them IN PLACE — parquet pushdown included)
and expose exactly TWO tools (`mcp_duck_server.py`, proven by
`test_mcp_duck.py`):

```python
con = duckdb.connect()
con.execute("CREATE VIEW events  AS SELECT * FROM read_parquet('lake/*/*.parquet', hive_partitioning=true)")
con.execute("CREATE VIEW regions AS SELECT * FROM read_csv_auto('regions.csv')")
# tool 1: describe_schema() -> tables, columns/types AND DOCUMENTED JOIN KEYS
# tool 2: query_sql(sql)    -> one SELECT/WITH over ALL sources; joins welcome
```

- **`describe_schema` matters more than the query tool**: list every table's
  columns *and write the join keys down for the model* ("events.region joins
  regions.region") — a 27B cannot guess keys; documented keys make its SQL
  correct on the first try.
- One SQL join across parquet ⋈ CSV, aggregated server-side, returns a few
  rows instead of two row-dumps (verified). Partition filters still push down
  into the parquet scan (verified via EXPLAIN).
- Guards tighten: SELECT/WITH prefix **plus reject `;` chaining** (DuckDB will
  happily run multiple statements), caps via `fetchmany`, fresh connection per
  call (views recreated — no shared cursor state).
- **Mismatched key names/formats — normalize IN the view, never per query.**
  Real lakes disagree: one file has `account` = `12345`, another has
  `"account id"` (a space!) = `acct:12345`, one's an int, one's a string. Fix
  it ONCE at view definition so the model always sees one clean key
  (verified — the reference server's `owners` source does exactly this):

  ```sql
  CREATE VIEW a AS SELECT CAST(account AS VARCHAR) AS account_id, ...;
  CREATE VIEW b AS SELECT regexp_replace("account id", '^acct:', '') AS account_id,
                          "account id" AS account_ref_raw,   -- keep raw for audit
                          ... ;
  ```

  Three verified rules: use **`regexp_replace('^prefix:')`, NEVER `ltrim`** —
  ltrim strips a character SET, not a prefix (`ltrim('acct:a123','acct:')` →
  `'123'`, it ate the 'a'); **CAST both sides explicitly** (DuckDB happens to
  implicitly cast int⋈varchar, other engines error — don't rely on it); and
  after wiring, run a one-time coverage check
  (`SELECT count(*) FROM a LEFT JOIN b USING(k) WHERE b.k IS NULL`) so silent
  key mismatches surface as a number, not as wrong answers.
- **Is view-normalization slower? Measured (3M-row fact, local parquet):**
  join through a normalized fact key ~4x slower (63→257 ms) and a selective
  `WHERE key=…` ~15x slower (10→159 ms — the computed column loses parquet
  zone-map pruning); a small messy CSV dimension costs only ~+80 ms/query.
  So the rule: **small reference tables → normalize in views forever; large
  FACT tables (or big CSVs) → re-save a clean copy.** Keep the original files
  immutable and write a normalized parquet "silver" dataset with the
  idempotent per-partition job from [st-parquet] (clean canonical keys, CSVs
  converted to parquet); point the views at silver. On S3 the gap widens —
  CSV re-parse and lost pruning both multiply by network I/O.
- The per-source tools above remain right when sources are independent; switch
  to the DuckDB variant the moment answers span sources.

## Transports — which one you want

| Transport | Run | For |
|---|---|---|
| **stdio** (default) | client LAUNCHES `python mcp_data_server.py` | local hosts: Roo, desktop LLM apps, the [st-mcp-client] bridge |
| **streamable-http** | you run it as a service (`--http`, default `127.0.0.1:8000/mcp`) | shared server for the company-LLM platform / several users |

stdio = zero deployment, dies with the client, credentials are yours.
streamable-http = one server many clients — put auth in front (reverse proxy
+ token header) before exposing beyond localhost; the reference binds
127.0.0.1 for a reason.

## Test WITHOUT any client app (the trick worth the skill)

```python
from mcp.shared.memory import create_connected_server_and_client_session
async with create_connected_server_and_client_session(mcp._mcp_server) as c:
    tools = (await c.list_tools()).tools          # schemas as a client sees them
    r = await c.call_tool("query_sql", {"sql": "SELECT 1"})
    r.isError, r.structuredContent                # assert on these
```

`test_mcp_server.py` is exactly this — schemas, caps, read-only guard,
traversal guard, allowlist, all asserted. Run it after every edit.

## Gotchas (verified)

- A tool exception is **not** a server crash — it returns `isError: true`
  with the message. So validate loudly; the model reads the error and retries
  correctly.
- `fetchmany(limit)` caps SQL rows server-side — never `fetchall()` then
  slice; the cap must bound the DB read, not the return.
- sqlite's `execute()` runs a **single statement** — that plus the
  SELECT/WITH prefix blocks `; DROP` piggybacking. On other engines use a
  read-only connection/role, not just the prefix check.
- Keep the server import-light at module level (lazy-import `httpx` etc.):
  stdio clients launch the process per session — slow imports = slow attach.
- Wrapping a slow internal API? The MCP call blocks the model's turn — cap
  timeouts (10 s in the reference) and return partials rather than hanging.
