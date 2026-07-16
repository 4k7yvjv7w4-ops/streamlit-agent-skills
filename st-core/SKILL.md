---
name: st-core
description: Streamlit execution model — reruns, session_state, callbacks, forms, caching, fragments. Use when writing or debugging ANY Streamlit app, especially infinite rerun loops, values that reset or vanish on refresh, buttons that "don't work", state errors, or live/auto-refreshing sections.
---

# Streamlit core (1.58.x) — execution model, state, refresh

**The one mental model:** on EVERY user interaction (any widget touched),
Streamlit re-executes the WHOLE script top-to-bottom. There are no event
handlers, no persistent locals, no main loop. A run is a pure function of
`st.session_state` + current widget values. Everything below follows from this.

Runnable proof of every claim: `st_core_lab.py` in this skill folder
(`python -m streamlit run ~/.roo/skills/st-core/st_core_lab.py`).
Verified on Streamlit **1.58**, API-checked on **1.55**: everything in
this skill exists on both (`st.fragment(run_every=)` needs ≥1.37).

## Hard rules (violations = the classic broken app)

1. **NEVER `while True:` at script level.** The script must finish each run.
   For a live section use `@st.fragment(run_every="2s")` (below). Loops are
   fine only INSIDE one run for a finite job (progress bar, `st.write_stream`).
2. **NEVER call `st.rerun()` unconditionally** (or under a condition that's
   still true next run) — Streamlit has NO loop protection; it spins forever.
   Every `st.rerun()` must sit behind a state guard you flip first:
   ```python
   if st.session_state.get("needs_refresh"):
       st.session_state.needs_refresh = False   # flip BEFORE rerun
       refresh_data()
       st.rerun()
   ```
3. **NEVER `time.sleep(n); st.rerun()` for auto-refresh.** The page never
   settles: widgets flicker, clicks get eaten mid-sleep. Use
   `@st.fragment(run_every=...)`, or `st.cache_data(ttl=...)` if "refresh"
   just means newer data. **There is NO native `st.autorefresh`** (verified —
   nothing in `dir(st)`). The `streamlit-autorefresh` PyPI package is
   third-party and reruns the WHOLE script every tick (resets every widget,
   steals focus); prefer the native scoped `@st.fragment(run_every=...)`.
4. **`st.experimental_rerun()` does not exist** (removed 1.27+). It is
   `st.rerun()`. Same for `st.experimental_memo/singleton` →
   `st.cache_data` / `st.cache_resource`; `st.experimental_fragment` →
   `st.fragment`; `@st.cache` is gone too.
5. **Most `st.rerun()` calls are unnecessary.** A widget interaction already
   triggers a rerun, and `on_click`/`on_change` callbacks run BEFORE that
   rerun, so their state writes are visible without asking for another one.
   Legit uses: close a `st.dialog`, apply a programmatic state change made
   BELOW where it's rendered (rule 2 pattern).

## `st.button` is momentary — the #1 vanishing-output bug

`st.button()` returns `True` for exactly ONE run (the click), then `False`
again. So `if st.button("run"): st.write(result)` shows the result until the
user touches anything else, then it VANISHES. And nested buttons can never
both be true: clicking the inner one makes the outer `False` again (verified).

```python
# WRONG                                # RIGHT — persist through state
if st.button("compute"):               if st.button("compute"):
    r = model()                            st.session_state.r = model()
    st.write(r)   # gone next run       if "r" in st.session_state:
                                            st.write(st.session_state.r)
```
Multi-step flows: one `step` key in session_state + `st.rerun()` per rule 2,
never button-inside-button.

## session_state rules

- Init once: `st.session_state.setdefault("k", default)` (or the
  `if "k" not in st.session_state:` form). Do it at the top, before widgets.
- **Writing `st.session_state.k` AFTER the widget with `key="k"` was created
  this run raises** `StreamlitAPIException: cannot be modified`. To set a
  widget programmatically, write the key BEFORE the widget line (usually: set
  a flag + `st.rerun()`, apply the write at the top of the next run) — or do
  it in a callback, which is always safe.
- **If `key` is already in session_state, `value=` is ignored** — state wins;
  the only trace is a warning in the SERVER log ("created with a default value
  but also had its value set via the Session State API"), nothing in the UI.
  Don't pass both and expect the default to apply.
- **A widget whose line doesn't execute on a run LOSES its state** (hidden
  tab-by-condition, collapsed branch — verified: slider at 8 came back at 0).
  To survive hiding, mirror to your own key:
  `st.slider(..., key="_w", on_change=lambda: st.session_state.update(w=st.session_state._w))`
  and feed it back via the write-before-widget pattern. (`st.tabs` is safe —
  all tabs' code runs every time, hidden or not; that's also why heavy tabs
  need caching.)
- Two widgets with identical type+params raise `StreamlitDuplicateElementId`
  — pass distinct `key=`s. Widgets in loops: `key=f"row-{i}"`.

## Callbacks beat manual reruns

State mutated below its render point reads stale for one run (verified: the
`if st.button(...)` branch runs AFTER the counter above it was drawn).
Callbacks fix the ordering — they execute before the script re-runs:

```python
st.session_state.setdefault("count", 0)
def inc(): st.session_state.count += 1
st.button("+1", on_click=inc)                 # count is fresh this same run
st.metric("count", st.session_state.count)
```

`on_change` on inputs/selects works the same. Callbacks may write any state
key (even a widget's, since its line hasn't run yet). No `st.rerun()` needed.

- **`st.rerun()` inside a callback is a NO-OP** (verified): it shows a
  user-visible warning `Calling st.rerun() within a callback is a no-op.` and
  ABORTS the rest of the callback body — no extra rerun, no exception. The
  click already scheduled the rerun; in a callback just mutate `session_state`
  and return. Adding `st.rerun()` there "to apply the change" silently truncates
  your callback.

## Forms — stop the rerun-per-keystroke

Every widget interaction reruns the script; N inputs = N reruns while the
user fills them (each one re-hitting your data layer). Batch them:

```python
with st.form("params"):
    a = st.slider("a", 0, 10)
    b = st.selectbox("b", opts)
    go = st.form_submit_button("Apply")
if go: run_query(a, b)
```

Nothing reruns until submit (verified: run counter +1 total). Inside a form:
no `st.button`, no per-widget callbacks except on the submit button.

**"It reruns while I type" is almost never keystrokes.** Widgets commit on
different events (Streamlit frontend behavior): `text_input`/`text_area`/
`number_input` fire on **Enter or blur**, `slider`/`select_slider` on
**release** — NOT per keystroke, NOT mid-drag; `checkbox`/`radio`/`selectbox`/
`toggle` fire immediately. One committed change = one rerun, and the frontend
sends nothing when the value is unchanged. So constant reruns while typing mean
a *concurrent* whole-app auto-refresh (a timer / `st_autorefresh` / `sleep`+
`rerun`) stealing focus — scope that refresh into a `@st.fragment` that does
NOT contain the input, or wrap the inputs in `st.form`. Don't debounce
keystrokes; Streamlit doesn't need it.

## Caching — most "bad refresh" is really this

- `@st.cache_data` — DataFrames/serializable results. Returns a fresh COPY
  per call (mutations safe, verified `is` False). `ttl="15m"` for data that
  should refresh; `Foo.clear()` or `st.cache_data.clear()` on a ↻ button.
- `@st.cache_resource` — connections, models, threads. SAME object returned
  to all sessions (verified) — never mutate it per-user, add locks if needed.
- Args must be hashable and form the cache key; prefix unhashable ones with
  `_` to exclude them (`def load(_conn, day):`).
- Without caching, every widget tick re-runs every load in the script —
  the app "feels stuck" because each click costs seconds. Cache first,
  then debug reruns.

## Live refresh done right — `st.fragment`

```python
@st.fragment(run_every="2s")        # int seconds / timedelta / "2s" strings
def ticker():
    st.metric("last", get_price())  # only THIS function re-executes
ticker()
```

- The rest of the page does NOT rerun (verified: outer run counter frozen
  while the fragment ticks). Widgets inside the fragment rerun only the
  fragment; `st.rerun(scope="fragment")` restarts just it.
- Gotcha (verified): `scope="fragment"` RAISES if the fragment body is
  executing as part of a full-app run (first paint) — guard it, or flip
  state + let `run_every` pick it up.
- Fragments can read/write session_state freely; to push a change OUT to the
  full page, write state then `st.rerun()` (scope `"app"`, the default).
- **Stop or re-time a `run_every` fragment from the OUTER script — a widget
  INSIDE it can't.** `run_every` is re-read only on a FULL app run, so an
  interval slider or Stop button *inside* the fragment (which only reruns the
  fragment) never re-arms the timer (verified). Gate the fragment CALL from
  outside:
  ```python
  secs = st.slider("interval", 1, 10, 2)          # OUTSIDE the fragment
  run  = st.session_state.get("run", True)
  tick = st.fragment(run_every=secs if run else None)(_body)
  tick()
  if st.button("stop"): st.session_state.run = False; st.rerun()
  ```
  On the full rerun, `run_every=None` (or not calling it) emits no auto-refresh
  message and the timer stops.
- **A fragment's return value only reaches the caller on a FULL run** (verified).
  On a `run_every` tick or an inside-fragment widget change the outer script is
  NOT re-executed, so `data = ticker()` keeps the STALE value and downstream
  charts never update. Push live data out via `st.session_state` written INSIDE
  the fragment (`st.session_state.data = fetch()`), read it outside — or draw
  the chart within the fragment itself. Don't treat a fragment as a plain
  function you can assign from across ticks.
- **A fragment runs on the app's single thread — it is NOT a background thread.**
  `time.sleep` inside it freezes the WHOLE page for that duration; let
  `run_every` be the cadence, never sleep. Nested fragments are allowed
  (verified) but each is an independent rerun scope — a child tick does not
  rerun its parent, so keep `run_every` on the fragment that owns the data;
  don't nest timers for the same data. For REAL background work (submit a slow
  job, keep navigating, results arrive) → [st-jobs].
- Don't create the same-keyed widget both inside and outside a fragment.
- **Fragment ticks but the value never changes? Your live read is cached.**
  A `@st.cache_data` loader with NO `ttl` runs its body ONCE (verified) and
  returns that frozen value on every tick — `run_every` re-executes the
  function but the cache short-circuits it. This is the #1 "my fragment won't
  refresh" cause. Fix: don't cache the live read, OR give it `ttl` ≤ the
  refresh cadence (`@st.cache_data(ttl="2s")`), OR vary an argument each tick.

## Fragment as a scoped work box — fetch now, use later (no full rerun)

A fragment WITHOUT `run_every` is an in-page box whose widgets rerun ONLY the
box — the pattern for "look up reference data here, consume it in a later
action" without re-running the whole page per lookup:

```python
@st.fragment
def fetch_box():                              # clicks in here rerun ONLY the box
    with st.form("lookup"):                   # form inside fragment: legal (verified)
        code = st.selectbox("entity", codes, key="box_code")
        go = st.form_submit_button("fetch details")
    if go:
        st.session_state.details = get_details(code)   # hand off via STATE
        st.success(f"fetched {code}")
fetch_box()

if st.button("run request"):                  # OUTSIDE → its click IS a full rerun,
    d = st.session_state.get("details")       # which reads the stashed details
    if d is None: st.warning("fetch first")
    else:        run_request(d)
```

- The consumer needs **no `st.rerun()`**: its own click is a full run that reads
  fresh state (verified). Only if the OUTER page must display the fetched data
  IMMEDIATELY (before any next click) do you `st.rerun()` inside the fragment
  after writing state — costs one full run.
- Hand off via `session_state`, never the fragment's return value (stale across
  box-only reruns — bullet above). `@st.cache_data` the lookup so re-fetching
  the same entity is free.

## Status while working (inside ONE run — allowed loops)

```python
ph = st.empty()                       # placeholder, overwrite in place
for i, step in enumerate(steps):
    ph.text(f"{i+1}/{len(steps)} {step.name}")
    step.run()
ph.empty()
```
Also `st.progress`, `st.status("...", expanded=True)`, `st.spinner`,
`st.toast`. These animate WITHIN a run — no rerun involved, no loop risk.

## Debug checklist for "stuck in a loop / keeps refreshing"

1. Grep for `st.rerun` — is every one behind a flip-first state guard (rule 2)?
2. Grep for `while True` / `time.sleep` at script level → fragment (rule 1/3).
3. A widget writing a state key that another line writes back → ping-pong
   rerun; keep one writer per key.
4. `key=` collisions or f-string keys that change every run (e.g. containing
   `time.time()`) — a new key each run = widget resets each run.
5. Uncached slow loads make normal reruns LOOK like loops — add
   `st.cache_data` and a run-counter (`st.session_state.runs += 1`) to see
   what's actually happening.
6. Live section refreshes on its timer but shows STALE values → a
   `@st.cache_data` function with no `ttl` feeds it; the fragment re-runs but
   the cache returns the old value. Add `ttl` or don't cache the live read.
