# SQLite-backed job store

Drop-in replacement for the in-memory job dict. Threads and the fragment poller are unchanged; only the seam's implementation moves. Jobs now survive browser refresh and are visible to every session of the app.

## Schema and store

```python
# job_store.py
import sqlite3, json, uuid, time, hashlib
from contextlib import contextmanager

DB = "jobs.db"

def _init():
    with sqlite3.connect(DB) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            payload_hash TEXT,
            payload TEXT,
            status TEXT,             -- running | done | error
            result TEXT,
            error TEXT,
            submitted_at REAL,
            finished_at REAL,
            heartbeat REAL,
            user TEXT
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS ix_hash ON jobs(payload_hash)")
_init()

@contextmanager
def _conn():
    c = sqlite3.connect(DB, timeout=10)
    c.execute("PRAGMA journal_mode=WAL")   # readers don't block the writer
    try:
        yield c
        c.commit()
    finally:
        c.close()

def payload_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()

def submit(payload: dict, user: str = "") -> str:
    h = payload_hash(payload)
    with _conn() as c:
        # dedup: same request already done or in flight -> reuse it
        row = c.execute(
            "SELECT id FROM jobs WHERE payload_hash=? AND status IN ('running','done') "
            "ORDER BY submitted_at DESC LIMIT 1", (h,)).fetchone()
        if row:
            return row[0]
        jid = uuid.uuid4().hex[:8]
        c.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (jid, h, json.dumps(payload, default=str), "running",
                   None, None, time.time(), None, time.time(), user))
        return jid

def finish(jid: str, result=None, error=None):
    with _conn() as c:
        c.execute("UPDATE jobs SET status=?, result=?, error=?, finished_at=? WHERE id=?",
                  ("error" if error else "done",
                   json.dumps(result, default=str) if result is not None else None,
                   error, time.time(), jid))

def beat(jid: str):
    with _conn() as c:
        c.execute("UPDATE jobs SET heartbeat=? WHERE id=?", (time.time(), jid))

def get(jid: str) -> dict | None:
    with _conn() as c:
        c.row_factory = sqlite3.Row
        row = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        return dict(row) if row else None

def list_jobs(user: str | None = None, limit: int = 50) -> list[dict]:
    with _conn() as c:
        c.row_factory = sqlite3.Row
        q = "SELECT * FROM jobs" + (" WHERE user=?" if user else "") + \
            " ORDER BY submitted_at DESC LIMIT ?"
        args = (user, limit) if user else (limit,)
        return [dict(r) for r in c.execute(q, args)]

STALE_S = 300
def effective_status(job: dict) -> str:
    """A 'running' row whose worker died stays running forever.
    Treat a silent heartbeat as failure."""
    if job["status"] == "running" and time.time() - (job["heartbeat"] or 0) > STALE_S:
        return "stale"
    return job["status"]
```

## Wiring into the app

```python
import job_store as js

def worker(jid, payload):
    try:
        result = do_slow_thing(payload)      # long call; add js.beat(jid)
        js.finish(jid, result=result)        # inside it if you can hook progress
    except Exception as e:
        js.finish(jid, error=repr(e))

if st.button("Submit"):
    jid = js.submit(payload, user=username)
    st.session_state.setdefault("my_jobs", []).append(jid)
    if js.get(jid)["status"] == "running" and js.get(jid)["result"] is None:
        executor().submit(worker, jid, payload)   # only if we created it

running = any(js.effective_status(js.get(j)) == "running"
              for j in st.session_state.get("my_jobs", []))

@st.fragment(run_every="2s" if running else None)
def blotter():
    for jid in st.session_state.get("my_jobs", []):
        job = js.get(jid)
        s = js.effective_status(job)
        ...render...
    ...st.rerun() on transition, as in SKILL.md...
```

## Caveats to state explicitly

- **Stuck rows**: if the process dies mid-job, the DB row stays `running`. That's what `heartbeat` + `effective_status` handle — surface `stale` as a failure the user can resubmit.
- **The thread still dies with the process.** SQLite makes the *record* durable, not the *execution*. If execution itself must survive restarts, this is the trigger to graduate to a queue or job endpoint (see SKILL.md).
- **WAL mode** is what makes concurrent read-while-write acceptable here; don't drop the pragma.
- **Dedup semantics**: hashing the payload means an identical request computed twice is free. If the user wants a forced recompute (e.g. newer input data), include a marker like the input snapshot id/date in the payload so the hash changes.
