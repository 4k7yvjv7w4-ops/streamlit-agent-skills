---
name: st-jobs
description: Run long-lived work (slow queries, batch calcs, report generation, API calls) in a Streamlit app without freezing the UI, so the user can keep navigating while jobs complete. Use whenever a Streamlit app blocks or freezes during a slow operation, the user wants to "launch and keep working", asks about threading / ThreadPoolExecutor / background tasks / async in Streamlit, sees "missing ScriptRunContext" warnings, wants a job blotter or status poller, or asks how to make results survive a page refresh. Use it even if they don't say "background job" — any Streamlit + slow-task question qualifies.
---

# st-jobs — background work without freezing the app

Make a Streamlit app submit slow work, stay fully interactive, and show results
when they arrive. Runnable proof: `st_jobs_lab.py` in this skill folder.
Verified on Streamlit **1.58**; the fragment poller needs **≥1.37** (fine on
1.55; `parallel=` is NOT on 1.55 — see below).

## Why Streamlit blocks (read this first)

Each browser session gets **one script thread**, and every interaction —
including page navigation — is a full top-to-bottom rerun on that thread
([st-core]). While a slow call sits on it, no new run can start for that
session: the app freezes for that user (others are unaffected). A fragment
does NOT help by itself — it runs on the same thread ([st-core]).

The solution always has exactly two independent parts:

1. **Offload** the work to somewhere that is not the script thread.
2. **Poll** its status cheaply, without rerunning the whole page.

Never solve only one half. Offloading without polling gives no feedback;
polling on the script thread (`while` + `sleep`) is just blocking with extra
steps.

## Choose the offload target

| Situation | Use |
|---|---|
| IO-bound or releases the GIL (REST call, numpy, C++ bindings) | `ThreadPoolExecutor` — the default choice |
| Pure-Python CPU-bound | `ProcessPoolExecutor` (payload/result must pickle; each worker duplicates memory) |
| Jobs must survive an app restart or be shared across users | External queue or a job endpoint on the service that owns the compute — see "Graduating" |

Streamlit's official position: threading in app code is not officially
supported; this is the community-standard shape of their documented starting
point.

## Core pattern (verified in the lab)

```python
import streamlit as st
from concurrent.futures import ThreadPoolExecutor
import uuid, time

@st.cache_resource            # ONE pool per process, NOT per rerun
def executor():
    return ThreadPoolExecutor(max_workers=8)

st.session_state.setdefault("jobs", {})

def worker(job, payload):
    # Runs off the script thread. NEVER touch st.* / st.session_state here.
    try:
        job["result"] = do_slow_thing(payload)
        job["status"] = "done"
    except Exception as e:
        job["status"], job["error"] = "error", repr(e)

if st.button("Submit"):
    job = {"status": "running", "t0": time.time(), "result": None}
    st.session_state.jobs[uuid.uuid4().hex[:6]] = job
    executor().submit(worker, job, payload)

running = any(j["status"] == "running" for j in st.session_state.jobs.values())

@st.fragment(run_every="2s" if running else None)   # self-terminating poll
def blotter():
    for jid, j in st.session_state.jobs.items():
        if j["status"] == "running":
            st.write(f"{jid} · running {time.time()-j['t0']:.0f}s")
        elif j["status"] == "done":
            st.write(f"{jid} · done", j["result"])
        else:
            st.error(f"{jid} · {j['error']}")
    still = any(j["status"] == "running" for j in st.session_state.jobs.values())
    if running and not still:
        st.rerun()            # full rerun -> run_every re-evaluates to None

blotter()
```

Why each piece exists:

- **`@st.cache_resource` on the executor** — without it every rerun builds a
  new pool and orphans the old threads ([st-connection] semantics: one shared
  object).
- **Worker mutates a plain dict** — the dict happens to live in session_state,
  but the worker holds only a Python reference. That keeps the worker free of
  Streamlit APIs (verified: the mutation is visible on the next rerun).
- **`run_every` computed from state** — polling starts when a job runs, stops
  when none do. `run_every` is re-read only on a FULL run ([st-core]).
- **`st.rerun()` inside the fragment** — promotes completion to a full rerun so
  `run_every` re-evaluates to `None` and the rest of the page sees results.

## Rules that prevent the classic bugs (verified on 1.58)

- **Never call `st.*` (including `st.session_state`) from a worker thread —
  it fails SILENTLY, not loudly.** Verified: `st.session_state` writes from a
  context-less thread land in a process-global MOCK state (invisible to your
  real session — the write just vanishes); `st.write` output is dropped;
  `st.rerun()` is a no-op. You get at most a "missing ScriptRunContext" log
  line, no exception. Communicate through plain Python objects (the job dict)
  only.
- **Do not "fix" the warning with `add_script_run_ctx`.** The docs warn a
  custom thread must not outlive the script run that owns the context — a
  background job is *designed* to outlive it, so that pattern is disqualified.
  Keep workers pure instead.
- **`@st.fragment(parallel=True)` is not the answer** (and doesn't exist on
  1.55). It only parallelises slow fragments *within* one rerun; the rerun
  still must finish before the user can navigate. It solves "three slow charts
  serialize", not "let me walk away".
- **No `while True: … st.rerun()` / busy-waits** on the script thread
  ([st-core] hard rules). The fragment IS the poller.
- **One writer per job dict.** Each worker writes only its own job. Two threads
  mutating one key/list needs a `threading.Lock` — better, don't share.
- **Know the lifetime.** `session_state` survives page switches but NOT a
  browser refresh, redeploy, or crash — and threads die with the process. Say
  this to the user; it decides whether to graduate (below).

## Structure it as a seam

Even in the simplest version, shape the code as:

```python
submit(payload) -> job_id
status(job_id)  -> Job          # {"status", "result", "error", timestamps}
list_jobs(...)  -> list[Job]
```

with the UI calling only these three. Everything behind the seam is swappable —
in-memory today, SQLite or a real queue tomorrow — without touching the
Streamlit code. This is the highest-leverage decision in the whole pattern.

## Making jobs survive refresh: SQLite store

Move to a SQLite-backed store (same seam, threads unchanged, `session_state`
keeps only ids) when **any** of these is true: a job routinely takes more than
~2 minutes · more than one person uses the app · the app gets redeployed
during the working day · an audit trail of requests is wanted.

Read `references/sqlite_job_store.md` for the drop-in implementation, including
the dedup-by-payload-hash trick and the stuck-`running`-row caveat.

## Graduating to a real queue

When jobs must survive the app process itself, move execution out: RQ/Celery
with Redis, or — usually better — an async job endpoint on the service that
already owns the compute (`POST /jobs` → id, `GET /jobs/{id}`). The app then
stores only ids and polls HTTP; the fragment pattern above is unchanged. If the
slow call is already an RPC to another service, the fix is to stop calling it
synchronously, not to add new infrastructure.

## Checklist before handing over code

- [ ] Executor under `@st.cache_resource`
- [ ] Worker contains zero `st.` references (failures are SILENT, not errors)
- [ ] `run_every` is conditional and there's an `st.rerun()` path that stops it
- [ ] Errors caught in the worker and landed in the job record (an uncaught
      worker exception is invisible)
- [ ] Elapsed time shown for running jobs (users distrust spinners with no clock)
- [ ] Lifetime limitation stated, with the SQLite/queue upgrade path named
