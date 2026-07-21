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
