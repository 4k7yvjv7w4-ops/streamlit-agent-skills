"""st-jobs lab — background work without freezing the app.

Run:  python -m streamlit run st_jobs_lab.py

Tab 1: the core pattern — submit slow jobs to a cache_resource'd
       ThreadPoolExecutor, watch a self-terminating fragment blotter
       (run_every only while something is running), results promote to the
       full page via st.rerun().
Tab 2: proof of the SILENT-failure rule — what actually happens when a worker
       thread touches st.session_state / st.write / st.rerun (verified 1.58:
       no exception; mock state, dropped output, no-op).

Bounded for AppTest: fake jobs sleep ~1s; nothing loops unbounded.
"""

import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

st.set_page_config(page_title="st-jobs lab", layout="wide")
st.title("st-jobs — submit slow work, keep the app interactive")


@st.cache_resource                      # ONE pool per process, not per rerun
def executor() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=4)


st.session_state.setdefault("jobs", {})

tab1, tab2 = st.tabs(["1 · Submit & blotter", "2 · Why workers must not touch st.*"])


# ------------------------------------------------- 1 · the core pattern ----
with tab1:
    st.caption(
        "Submit a fake slow job (~1s). The worker runs OFF the script thread and "
        "mutates a plain dict; the blotter fragment polls every second ONLY while "
        "something is running (`run_every` is conditional), then `st.rerun()` "
        "promotes completion to a full run, which re-evaluates `run_every` to None "
        "— polling stops by itself."
    )

    def worker(job: dict, seconds: float) -> None:
        # off the script thread — NO st.* in here, plain Python only
        try:
            time.sleep(seconds)
            job["result"] = f"p95={100 + int(seconds * 40)}ms"
            job["status"] = "done"
        except Exception as e:           # an uncaught exception would be SILENT
            job["status"], job["error"] = "error", repr(e)

    if st.button("submit a 1s report job", key="submit"):
        job = {"status": "running", "t0": time.time(), "result": None}
        st.session_state.jobs[uuid.uuid4().hex[:6]] = job
        executor().submit(worker, job, 1.0)

    running = any(j["status"] == "running" for j in st.session_state.jobs.values())

    @st.fragment(run_every="1s" if running else None)   # self-terminating poll
    def blotter() -> None:
        if not st.session_state.jobs:
            st.info("no jobs yet — submit one above")
        for jid, j in st.session_state.jobs.items():
            if j["status"] == "running":
                st.write(f"⏳ {jid} · running {time.time() - j['t0']:.0f}s")
            elif j["status"] == "done":
                st.write(f"✅ {jid} · done → {j['result']}")
            else:
                st.error(f"❌ {jid} · {j.get('error')}")
        still = any(j["status"] == "running" for j in st.session_state.jobs.values())
        if running and not still:
            st.rerun()      # full rerun -> run_every re-evaluates to None

    blotter()
    st.caption(
        f"page-level view (full runs only): "
        f"{sum(j['status'] == 'done' for j in st.session_state.jobs.values())} done / "
        f"{len(st.session_state.jobs)} jobs — navigate away and back, jobs keep going."
    )


# -------------------------------------- 2 · silent-failure demonstration ----
with tab2:
    st.caption(
        "The classic bug is calling st.* from the worker. On 1.58 it does NOT "
        "raise — it fails SILENTLY: `st.session_state` writes go to a process-"
        "global MOCK (your session never sees them), `st.write` output is "
        "dropped, `st.rerun()` is a no-op. Click and see."
    )
    st.session_state.setdefault("probe_results", {})

    def probe_state(box: dict) -> None:
        try:
            st.session_state["ghost"] = "written-from-thread"
            box["r"] = "no exception — went to the MOCK state"
        except Exception as e:
            box["r"] = f"raised {type(e).__name__}"

    def probe_write(box: dict) -> None:
        try:
            st.write("hello from a worker thread")
            box["r"] = "no exception — output silently dropped"
        except Exception as e:
            box["r"] = f"raised {type(e).__name__}"

    def probe_rerun(box: dict) -> None:
        try:
            st.rerun()
            box["r"] = "no exception — silent no-op"
        except Exception as e:
            box["r"] = f"raised {type(e).__name__}"

    if st.button("run the three probes in worker threads", key="probes"):
        for name, fn in [("session_state", probe_state),
                         ("st.write", probe_write), ("st.rerun", probe_rerun)]:
            st.session_state.probe_results[name] = {"r": "pending…"}
            executor().submit(fn, st.session_state.probe_results[name])

    if st.session_state.probe_results:
        for name, box in st.session_state.probe_results.items():
            st.write(f"`{name}` from a worker → {box['r']}")
        st.write("did the thread's write reach the REAL session_state? →",
                 "ghost" in st.session_state)
        st.caption(
            "`ghost` stays False: the worker's session_state write vanished into "
            "the mock. This is why the rule is 'communicate through a plain dict' "
            "— the failure mode is silence, not an error you'd notice."
        )
