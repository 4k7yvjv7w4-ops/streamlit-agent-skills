---
name: st-testing
description: Headlessly test Streamlit apps with streamlit.testing.v1.AppTest — run a page with no browser, drive its widgets, and assert no exceptions. Use to write a smoke test for a page, verify a change actually works, gate CI, or reproduce a rerun/state bug deterministically. Covers driving widgets by key, injecting secrets/query_params, and AppTest's real limits.
---

# st-testing — verify a Streamlit page without a browser

`AppTest` runs your script headlessly, exposes every element, lets you set
widget values and click buttons, and reruns — all in-process. It's the fastest
way to answer "does this page actually work?" and the CI gate this whole bundle
uses. Runnable proof: `st_testing_lab.py` (the app under test) +
`test_st_testing.py` (the tests) — `python -m pytest st-testing/`. Verified on
Streamlit **1.58**.

## The 30-second smoke test (do this for every page)

```python
from streamlit.testing.v1 import AppTest

def test_page_runs():
    at = AppTest.from_file("pages/pricing.py").run()
    assert not at.exception          # at.exception is a LIST — empty = clean
```

That alone catches import errors, bad state access, `StreamlitAPIException`s,
and typos — the bulk of "it broke" — before you ever open a browser.

## Construct → run → inspect → drive

```python
at = AppTest.from_file("app.py", default_timeout=30)   # or from_string(src) / from_function(fn)
at.secrets["api_token"] = "x"                          # inject BEFORE run
at.query_params["service"] = "checkout"
at = at.run()                                          # runs; returns the SAME at (chainable)

# INSPECT (each is a list, in document order)
at.exception            # [] when clean — your main assertion
at.warning              # st.warning + Streamlit's own warnings (NOT failures)
at.title / at.markdown / at.metric / at.dataframe / at.json / at.error
at.session_state["k"]   # dict-like: use ["k"] and `"k" in at.session_state`, NOT .get()
at.sidebar.button       # scope to a container: at.sidebar.<elem>, at.tabs[i].<elem>

# DRIVE (mutate, then .run() to apply)
at.button[0].click().run()
at.selectbox[0].select("eu-west-1").run()
at.text_input[0].set_value("hi").run()
at.slider[0].set_value(14).run()
at.checkbox[0].set_value(True).run()
```

## Select widgets by KEY, not index (robust)

Index order shifts as the page grows; the `key=` is stable:

```python
btn = next(b for b in at.button if b.key == "go")
btn.click().run()
svc = next(s for s in at.selectbox if s.key == "svc_pick").select("search")
```

Give widgets you test a `key=`. `at.session_state[key]` reads a widget's value too.

## Golden rules

- **`assert not at.exception`** is the workhorse. `at.exception` is a list of
  caught app exceptions; empty = the run was clean.
- **A warning is NOT an exception.** `st.warning(...)`, and Streamlit's own
  "created with a default value but also had its value set…" notice, land in
  `at.warning`, not `at.exception` — don't fail the suite on an *expected*
  warning. Assert on `at.warning` text when the warning IS the behavior under
  test (e.g. `st.rerun()`-in-callback: `assert any("no-op" in w.value for w in at.warning)`).
- **Reruns are explicit.** Nothing re-runs until you call `.run()`; a
  `set_value` without a following `.run()` isn't applied.
- **Inject secrets/query_params BEFORE the first `.run()`** so the script sees
  them ([st-connection] creds inject exactly this way).

## Limits — what AppTest canNOT do (verified)

- **No real frontend components.** A custom Components-V2 component
  (streamlit-aggrid, streamlit-pivot, streamlit-perspective) raises at import
  under AppTest (no browser/asset host). GUARD the import in the app
  (`try: from st_aggrid import …` → fallback) so the page still passes the smoke
  test, or test the data path separately.
- **No keystrokes / drags.** `set_value()` commits atomically; you can't test
  per-keystroke behavior, and re-setting the same value still forces a `.run()`
  (AppTest bypasses the frontend's unchanged-value suppression).
- **No fragment partial reruns.** AppTest FULL-reruns on every interaction, so a
  `@st.fragment`'s scope-only rerun isn't modeled — fragment-local behavior
  (timer ticks, box-only reruns) can't be observed here; assert on the
  session_state it writes instead ([streamlit-core]).
- **An unconditional `st.rerun()` → `RuntimeError` timeout** (bounded hang at
  `default_timeout`), not a clean stop — that's the loop surfacing.
- **`st.switch_page` can need a second `.run()`** to settle in AppTest; re-query
  widgets after navigating.

## Patterns

- **CI gate:** one `test_*_runs()` per page asserting `not at.exception` — cheap,
  catches most regressions. This bundle runs exactly this on every lab.
- **State handoff:** drive page A, assert `at.session_state["handoff"]`, then
  assert page B consumes it (multipage: [st-layout]).
- **Repro a bug:** `from_string` an 8-line minimal app, drive it, assert the
  broken state — a deterministic repro beats clicking in a browser.
