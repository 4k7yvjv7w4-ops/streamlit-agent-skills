"""Streamlit execution-model lab — runnable ground truth for skills/streamlit-core.md.

Every tab demonstrates one class of bug a code-writing model produces
(infinite rerun loops, vanishing outputs, state errors, bad refresh) with the
❌ broken pattern (bounded so it can't hang the app) next to the ✅ fix, live.

Launch:  python -m streamlit run st_core_lab.py
"""

from __future__ import annotations

import datetime as dt
import random
import time

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Streamlit core lab", layout="wide")

# ---------------------------------------------------------------- run counter
# The single most useful debugging device in any Streamlit app: proof that the
# WHOLE script re-executes on every interaction, and a way to see extra reruns.
st.session_state.setdefault("runs", 0)
st.session_state.runs += 1

with st.sidebar:
    st.title("Streamlit core lab")
    st.metric("full-script runs this session", st.session_state.runs)
    st.caption(
        "This counter lives at the top of the script. Watch it: EVERY widget "
        "you touch anywhere re-runs the whole file. That is the execution "
        "model — the rest of the lab is consequences."
    )
    st.divider()
    st.caption("Skill: `streamlit-core/SKILL.md`")

TABS = st.tabs(
    [
        "1 🧠 Execution model",
        "2 🔘 Button traps",
        "3 🔁 Rerun loops",
        "4 🗃️ session_state",
        "5 ⚡ Callbacks",
        "6 📋 Forms",
        "7 💾 Caching",
        "8 📡 Live refresh",
        "9 ⏳ In-run status",
    ]
)


def broken_fixed(broken_title: str = "❌ broken", fixed_title: str = "✅ fixed"):
    c1, c2 = st.columns(2, gap="large")
    c1.subheader(broken_title)
    c2.subheader(fixed_title)
    return c1, c2


# =============================================================== 1 execution
with TABS[0]:
    st.markdown(
        """
**On every interaction Streamlit re-executes the whole script top-to-bottom.**
No event handlers, no persistent locals, no main loop. A run is a pure
function of `st.session_state` + current widget values.
"""
    )
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.slider("touch me (does nothing else)", 0, 100, key="em_slider")
        st.checkbox("or me", key="em_check")
        st.write(
            f"script executed at **{dt.datetime.now().strftime('%H:%M:%S.%f')[:-3]}** — "
            f"run **#{st.session_state.runs}**"
        )
        st.caption(
            "Touch either widget: the timestamp changes and the sidebar run "
            "counter climbs. The slider is on tab 1, yet code on tabs 2–9 "
            "ran too — `st.tabs` executes ALL tabs every run."
        )
    with c2:
        st.code(
            '''# consequences you must design for:
# 1. locals do NOT survive:      x = compute()        # gone next run
# 2. only session_state survives: st.session_state.x = compute()
# 3. slow code runs EVERY interaction  -> st.cache_data (tab 7)
# 4. "wait here" is impossible          -> no while True, no sleep-loops (tab 3)
# 5. all st.tabs bodies run every time  -> cache heavy tabs''',
            language="python",
        )

# ================================================================= 2 buttons
with TABS[1]:
    st.markdown(
        "**`st.button` returns `True` for exactly ONE run** — the click. "
        "Anything rendered under `if st.button(...):` vanishes on the next interaction."
    )
    c1, c2 = broken_fixed()
    with c1:
        if st.button("compute (broken)", key="b_broken"):
            st.success(f"result = {random.randint(1000, 9999)}  ← now touch the slider below")
        st.slider("any other interaction", 0, 10, key="b_distract1")
        st.caption("Click compute, then move the slider: the result is GONE — "
                   "the button read `False` on the slider's rerun.")
    with c2:
        if st.button("compute (fixed)", key="b_fixed"):
            st.session_state.b_result = random.randint(1000, 9999)
        if "b_result" in st.session_state:
            st.success(f"result = {st.session_state.b_result}  (survives anything)")
        st.slider("any other interaction", 0, 10, key="b_distract2")
        st.code(
            '''if st.button("compute"):
    st.session_state.r = model()      # persist the OUTCOME
if "r" in st.session_state:
    st.write(st.session_state.r)      # render FROM state''',
            language="python",
        )

    st.divider()
    st.markdown("**Nested buttons can never both be `True`** — clicking the inner one reruns the script, and the outer reads `False` again.")
    c1, c2 = broken_fixed()
    with c1:
        if st.button("step 1 (broken)", key="nb1"):
            st.info("now click step 2 — it will just make this whole block disappear")
            if st.button("step 2 (unreachable)", key="nb2"):
                st.balloons()  # never happens
    with c2:
        st.session_state.setdefault("wizard_step", 0)
        if st.session_state.wizard_step == 0:
            if st.button("step 1 (fixed)", key="nb3"):
                st.session_state.wizard_step = 1
                st.rerun()
        elif st.session_state.wizard_step == 1:
            st.info("step 1 done — state machine, not nesting")
            if st.button("step 2", key="nb4"):
                st.session_state.wizard_step = 0
                st.balloons()
        st.code(
            '''st.session_state.setdefault("step", 0)   # one state key drives the flow
if st.session_state.step == 0:
    if st.button("step 1"): st.session_state.step = 1; st.rerun()
elif st.session_state.step == 1:
    if st.button("step 2"): ...''',
            language="python",
        )

# ============================================================== 3 rerun loops
with TABS[2]:
    st.markdown(
        """
**Streamlit has NO loop protection** — an unconditional `st.rerun()` (or one
whose condition is still true next run) spins forever. Verified: 200 chained
reruns execute happily. Every `st.rerun()` must sit behind a state guard you
**flip before** calling it.
"""
    )
    c1, c2 = broken_fixed("❌ the infinite loops (code only — they would hang this app)",
                          "✅ guarded rerun, live (bounded cascade)")
    with c1:
        st.code(
            '''# LOOP 1 — unconditional
st.write(data)
st.rerun()                        # forever

# LOOP 2 — guard never flips
if st.session_state.dirty:
    refresh()
    st.rerun()                    # dirty still True next run -> forever

# LOOP 3 — the "auto refresh" that eats every click
while True:
    draw_dashboard()
    time.sleep(5)                 # script never finishes a run

# LOOP 4 — sleep+rerun: page never settles, widgets flicker
time.sleep(5)
st.rerun()                        # use @st.fragment(run_every=...) instead''',
            language="python",
        )
    with c2:
        st.session_state.setdefault("cascade_left", 0)
        st.session_state.setdefault("cascade_log", [])
        if st.button("trigger a 5-rerun cascade", key="cascade_btn"):
            st.session_state.cascade_left = 5
            st.session_state.cascade_log = []
        if st.session_state.cascade_left > 0:
            st.session_state.cascade_left -= 1          # flip BEFORE rerun
            st.session_state.cascade_log.append(
                f"run #{st.session_state.runs} — {st.session_state.cascade_left} reruns left"
            )
            time.sleep(0.35)                            # only so you can see it
            st.rerun()
        for line in st.session_state.cascade_log:
            st.text(line)
        if st.session_state.cascade_log and st.session_state.cascade_left == 0:
            st.success("terminated — because the guard (`cascade_left`) was decremented "
                       "BEFORE `st.rerun()`. Comment the decrement out and this tab "
                       "would loop forever.")
        st.code(
            '''if st.session_state.get("needs_refresh"):
    st.session_state.needs_refresh = False   # flip FIRST
    refresh_data()
    st.rerun()''',
            language="python",
        )

# ============================================================ 4 session_state
with TABS[3]:
    st.markdown("**Four state rules, each live:**")

    st.markdown("##### a) writing a widget's key AFTER its widget line raises")
    c1, c2 = broken_fixed()
    with c1:
        st.slider("slider with key='ss_a'", 0, 10, key="ss_a")
        if st.button("set it to 7 the WRONG way (write after widget)", key="ss_a_btn"):
            try:
                st.session_state.ss_a = 7
            except Exception as e:  # StreamlitAPIException
                st.error(f"`{type(e).__name__}`: {e}")
    with c2:
        # the write happens at the TOP of the run, before the widget line
        if st.session_state.pop("ss_b_set7", False):
            st.session_state.ss_b = 7
        st.slider("slider with key='ss_b'", 0, 10, key="ss_b")
        if st.button("set it to 7 the RIGHT way (flag → rerun → write-before-widget)", key="ss_b_btn"):
            st.session_state.ss_b_set7 = True
            st.rerun()
        st.code(
            '''if st.session_state.pop("set7", False):
    st.session_state.sl = 7          # BEFORE the widget line: legal
st.slider("s", 0, 10, key="sl")
if st.button("set to 7"):
    st.session_state.set7 = True; st.rerun()''',
            language="python",
        )

    st.divider()
    st.markdown("##### b) if the key is already in state, `value=` is ignored")
    st.session_state.setdefault("ss_c", 3)
    v = st.slider("declared with value=8 but key pre-set to 3 → shows 3", 0, 10, value=8, key="ss_c")
    st.caption(f"widget returned {v} — state won. The only trace is a warning in the "
               "SERVER log, nothing in the UI.")

    st.divider()
    st.markdown("##### c) a widget whose line doesn't execute LOSES its state")
    c1, c2 = broken_fixed()
    with c1:
        show1 = st.checkbox("show slider", value=True, key="ss_show1")
        if show1:
            st.slider("set me to 8, then hide/show me", 0, 10, key="ss_d")
        st.caption("Hide then re-show: back to 0. The run where the line didn't "
                   "execute dropped the widget's state.")
    with c2:
        st.session_state.setdefault("ss_e_keep", 5)
        if st.session_state.get("ss_show2", True):
            # write-before-widget feeds the kept value back in
            st.session_state.ss_e = st.session_state.ss_e_keep
        show2 = st.checkbox("show slider ", value=True, key="ss_show2")
        if show2:
            st.slider(
                "I survive hiding", 0, 10, key="ss_e",
                on_change=lambda: st.session_state.update(ss_e_keep=st.session_state.ss_e),
            )
        st.caption("`on_change` mirrors the value to a NON-widget key; on re-show "
                   "the widget key is re-seeded from it before the widget line.")

    st.divider()
    st.markdown("##### d) identical widgets need distinct `key=`s")
    st.code(
        '''st.button("go"); st.button("go")          # StreamlitDuplicateElementId
for i, row in enumerate(rows):
    st.button("del", key=f"del-{i}")          # keys in loops: derive from i/id
# NEVER key=f"x-{time.time()}" — a new key each run = widget resets each run''',
        language="python",
    )

# ================================================================ 5 callbacks
with TABS[4]:
    st.markdown(
        "**State mutated below its render point is stale for one run.** "
        "`on_click`/`on_change` callbacks run BEFORE the script re-executes, so "
        "their writes are visible immediately — and they never need `st.rerun()`."
    )
    c1, c2 = broken_fixed("❌ lags one run", "✅ callback — always fresh")
    with c1:
        st.session_state.setdefault("cb_broken", 0)
        st.metric("counter (drawn BEFORE the button)", st.session_state.cb_broken)
        if st.button("+1", key="cb_bb"):
            st.session_state.cb_broken += 1   # metric above already drawn → stale
        st.caption("Click: the metric shows the OLD value; it catches up on the "
                   "next interaction. (Adding st.rerun() here 'fixes' it at the "
                   "cost of a double run.)")
    with c2:
        st.session_state.setdefault("cb_fixed", 0)
        st.metric("counter", st.session_state.cb_fixed)
        st.button("+1", key="cb_fb",
                  on_click=lambda: st.session_state.update(
                      cb_fixed=st.session_state.cb_fixed + 1))
        st.code(
            '''def inc(): st.session_state.count += 1
st.button("+1", on_click=inc)        # runs BEFORE the rerun
st.metric("count", st.session_state.count)   # fresh, same run''',
            language="python",
        )

    with st.expander("❌ `st.rerun()` inside a callback is a no-op (don't add it)"):
        st.caption(
            "Qwen reflex: add `st.rerun()` in a callback 'to apply the change'. It "
            "does the opposite — it aborts the rest of the callback body and reruns "
            "nothing (the click already scheduled the rerun). Click and watch: the "
            "line after `st.rerun()` never runs, and Streamlit shows a warning."
        )
        st.session_state.setdefault("cb_reached_end", None)

        def _cb_with_rerun():
            st.session_state.cb_reached_end = False   # set BEFORE the rerun call
            st.rerun()                                # <-- no-op + warning, aborts here
            st.session_state.cb_reached_end = True    # NEVER runs

        st.button("run a callback that calls st.rerun()", key="cb_rerun_demo",
                  on_click=_cb_with_rerun)
        if st.session_state.cb_reached_end is False:
            st.write("`cb_reached_end` = **False** → the line after `st.rerun()` "
                     "was skipped. Streamlit logged: "
                     "*Calling st.rerun() within a callback is a no-op.*")

# ==================================================================== 6 forms
with TABS[5]:
    st.markdown(
        "**Every widget interaction is a full rerun** — N inputs = N reruns "
        "(each re-hitting your data layer) while the user is still typing. "
        "`st.form` batches them into one."
    )
    c1, c2 = broken_fixed("❌ bare inputs — rerun per widget", "✅ form — one rerun on submit")
    with c1:
        st.slider("a", 0, 10, key="f_a")
        st.selectbox("severity", ["low", "med", "high"], key="f_b")
        st.text_input("label", key="f_c")
        st.caption(f"sidebar run counter says it all — this text re-rendered on "
                   f"run #{st.session_state.runs}, once per touch.")
    with c2:
        with st.form("f_form"):
            a = st.slider("a", 0, 10)
            b = st.selectbox("severity", ["low", "med", "high"])
            c = st.text_input("label")
            go = st.form_submit_button("Apply")
        if go:
            st.success(f"ONE rerun with a={a}, severity={b}, label={c!r}")
        st.caption("Drag the slider, change the selectbox: run counter frozen "
                   "until Apply. Inside a form: no st.button, callbacks only on "
                   "the submit button.")

    with st.expander("When each widget commits — why it 'reruns while I type'"):
        st.caption(
            "Constant reruns while typing are almost never keystrokes — they're a "
            "concurrent auto-refresh stealing focus. Widgets commit on different events:"
        )
        st.markdown(
            "| Widget | Commits a change on |\n|---|---|\n"
            "| `text_input` · `text_area` · `number_input` | **Enter or blur** (focus loss) |\n"
            "| `slider` · `select_slider` | **release** (not mid-drag) |\n"
            "| `checkbox` · `radio` · `selectbox` · `toggle` | **immediately** |\n"
        )
        st.caption(
            "One committed change = one rerun; an unchanged value sends nothing. If a "
            "live section keeps refreshing your input away, scope the refresh into a "
            "`@st.fragment` that does NOT contain the input (or wrap inputs in `st.form`)."
        )

# ================================================================== 7 caching
with TABS[6]:
    st.markdown(
        "**Uncached slow code runs on EVERY interaction** — the app feels "
        "'stuck in a loop' when it's really re-loading everything per click."
    )

    def slow_load(day: str) -> pd.DataFrame:
        time.sleep(1.5)  # pretend: S3 download + parse
        rng = random.Random(day)
        return pd.DataFrame(
            {"pctl": [50, 75, 90, 95, 99],
             "latency_ms": [round(120 + 60 * rng.random(), 1) for _ in range(5)]}
        )

    cached_load = st.cache_data(ttl="15m", show_spinner="loading (cached)…")(slow_load)

    c1, c2 = broken_fixed("❌ uncached — 1.5 s on every touch", "✅ st.cache_data(ttl='15m')")
    with c1:
        if st.checkbox("enable the uncached load (makes THIS tab slow)", key="cache_pain"):
            with st.spinner("loading (uncached)…"):
                df = slow_load("2026-07-03")
            st.dataframe(df, hide_index=True)
            st.slider("now touch me and feel the 1.5 s again", 0, 10, key="cache_touch")
    with c2:
        df = cached_load("2026-07-03")
        st.dataframe(df, hide_index=True)
        st.slider("touch me — instant, the cache ate the load", 0, 10, key="cache_touch2")
        if st.button("↻ force refresh (cached_load.clear())", key="cache_clear"):
            cached_load.clear()
            st.rerun()

    st.divider()
    st.code(
        '''@st.cache_data(ttl="15m")      # data: returns a fresh COPY per call
def load(day): ...

@st.cache_resource              # connections/models: ONE shared object,
def get_conn(): ...             # all sessions — never mutate per-user

def load(_conn, day): ...       # _prefix = excluded from the cache key
# @st.cache / st.experimental_memo / st.experimental_singleton are REMOVED''',
        language="python",
    )

# ============================================================= 8 live refresh
with TABS[7]:
    st.markdown(
        "**The right auto-refresh:** `@st.fragment(run_every=...)` re-executes "
        "ONE function on a timer — the rest of the page (and its widgets) is "
        "untouched. No `while True`, no `sleep+rerun`."
    )
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.subheader("✅ live ticker fragment")
        # on/off + interval live OUTSIDE the fragment — run_every is re-read only
        # on a FULL run, so an interval widget INSIDE the fragment couldn't re-time it
        live = st.toggle("run the ticker", value=False, key="frag_live")
        secs = st.slider("interval (s) — OUTSIDE the fragment", 1, 5, 1, key="tick_secs")
        st.metric("full-script runs (frozen while ticking)", st.session_state.runs)

        st.session_state.setdefault("px", 100.0)

        def _ticker_body():
            st.session_state.px += random.gauss(0, 0.3)   # push OUT via session_state
            st.metric(
                "synthetic gauge (random walk)",
                f"{st.session_state.px:.2f}",
                delta=f"{random.gauss(0, 0.3):+.2f}",
            )
            st.caption(f"fragment ran at {dt.datetime.now().strftime('%H:%M:%S')}")
            return st.session_state.px                    # return only reaches caller on a FULL run

        # run_every=secs when on, None when off -> the timer stops (no auto-refresh msg)
        ticker = st.fragment(run_every=secs)(_ticker_body) if live else _ticker_body
        captured = ticker()
        st.caption(
            f"Turn it on: the value ticks every **{secs}s** while the full-script run "
            "counter above stays FROZEN. Move the slider or toggle off — both work "
            "because they're OUTSIDE the fragment (a widget inside it can't re-time or "
            f"stop the timer). The outer `return` is {captured:.2f} now but goes STALE "
            "on ticks — read `st.session_state.px`, not the return, across ticks."
        )
    with c2:
        st.subheader("rules")
        st.code(
            '''@st.fragment(run_every="2s")     # int secs / timedelta / "2s"
def ticker():
    st.metric("last", get_price())
ticker()

# - widgets INSIDE rerun only the fragment
# - st.rerun(scope="fragment") restarts just it, BUT raises if the
#   body is executing as part of a full-app run (first paint) — guard it
# - to push a change to the whole page: write state, st.rerun()  (scope app)
# - same-keyed widget inside AND outside a fragment: don't''',
            language="python",
        )
        st.markdown(
            "**If 'refresh' just means newer data**, you don't need any of "
            "this: `st.cache_data(ttl='5m')` + normal interactions is enough."
        )

    with st.expander("⚠️ The #1 'my fragment won't refresh' trap — a cached live read"):
        st.caption(
            "A fragment re-runs on its timer, but if it reads a `@st.cache_data` "
            "function with NO `ttl`, the cache returns the SAME value forever — the "
            "body runs once. Both buttons below call a function returning `now()`; "
            "click each a few times. The no-ttl one is FROZEN; the ttl one updates."
        )

        @st.cache_data
        def _clock_no_ttl():          # no ttl -> body runs once, value frozen
            return dt.datetime.now().strftime("%H:%M:%S.%f")[:-3]

        @st.cache_data(ttl="1s")
        def _clock_ttl():             # ttl -> body re-runs after it expires
            return dt.datetime.now().strftime("%H:%M:%S.%f")[:-3]

        d1, d2 = st.columns(2)
        with d1:
            st.button("read cached (no ttl)", key="clk_a")
            st.metric("❌ frozen", _clock_no_ttl())
        with d2:
            st.button("read cached (ttl='1s')", key="clk_b")
            st.metric("✅ updates", _clock_ttl())
        st.caption(
            "Fix: drop the cache on the live read, give it `ttl` ≤ the refresh "
            "cadence, or vary an argument each tick. Clear the frozen one with "
            "`_clock_no_ttl.clear()`."
        )

    with st.expander("✅ Fragment as a scoped work box — fetch now, use later"):
        st.caption(
            "A fragment WITHOUT `run_every`: clicks inside rerun ONLY the box. "
            "Fetch reference data here (watch the full-run counter above stay "
            "frozen), stash it in session_state, and a LATER button outside — "
            "whose own click is a full rerun — consumes it. No st.rerun() anywhere."
        )

        @st.cache_data
        def _svc_meta(name: str) -> dict:      # the 'expensive' lookup, cached
            return {"service": name, "owner_team": f"team-{name[:3]}",
                    "sla_ms": 250 if name == "checkout" else 400}

        @st.fragment
        def _fetch_box():
            with st.form("meta_lookup"):       # form INSIDE a fragment: legal
                name = st.selectbox("service", ["checkout", "search", "media"],
                                    key="box_svc")
                go = st.form_submit_button("fetch metadata")
            if go:
                st.session_state.svc_meta = _svc_meta(name)
                st.success(f"fetched {name} — full-run counter did NOT move")

        _fetch_box()

        if st.button("run health report (outside the box)", key="box_report"):
            meta = st.session_state.get("svc_meta")
            if meta is None:
                st.warning("fetch metadata first — nothing stashed yet")
            else:
                st.write(f"report: **{meta['service']}** · owner {meta['owner_team']} "
                         f"· SLA {meta['sla_ms']}ms — read from session_state on "
                         "THIS click's full rerun.")

# ============================================================ 9 in-run status
with TABS[8]:
    st.markdown(
        "**Loops are fine INSIDE one run** for a finite job — overwrite a "
        "placeholder in place. The trap is only loops ACROSS runs (tab 3)."
    )
    c1, c2 = st.columns(2, gap="large")
    with c1:
        if st.button("run a 6-step fake backfill", key="status_go"):
            ph = st.empty()
            bar = st.progress(0)
            steps = ["fetch metrics", "fetch logs", "fetch traces", "classify",
                     "aggregate", "write parquet"]
            for i, s in enumerate(steps):
                ph.text(f"{i + 1}/{len(steps)}  {s}")
                time.sleep(0.4)
                bar.progress((i + 1) / len(steps))
            ph.success("done — one single script run, zero reruns")
    with c2:
        st.code(
            '''ph = st.empty()                 # placeholder, overwrite in place
bar = st.progress(0)
for i, step in enumerate(steps):
    ph.text(f"{i+1}/{len(steps)} {step}")
    step.run()
    bar.progress((i+1)/len(steps))

# also: st.status("...", expanded=True), st.spinner, st.toast,
#       st.write_stream(gen) for token streams''',
            language="python",
        )
