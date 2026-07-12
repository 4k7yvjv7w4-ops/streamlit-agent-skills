"""Demonstration AppTest suite for st_testing_lab.py — every core pattern.

Run:  python -m pytest st-testing/          (or: python st-testing/test_st_testing.py)
No browser, no server — headless and deterministic.
"""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).with_name("st_testing_lab.py"))


def _fresh():
    return AppTest.from_file(APP, default_timeout=30)


def test_page_runs_clean():
    """The 30-second smoke test — catches import/state/API errors."""
    at = _fresh().run()
    assert not at.exception                      # at.exception is a LIST


def test_click_by_key_updates_state():
    at = _fresh().run()
    inc = next(b for b in at.button if b.key == "inc")   # by KEY, not index
    inc.click().run()
    inc.click().run()
    assert at.session_state["count"] == 2        # callback ran before each rerun
    assert not at.exception


def test_form_batches_then_hands_off():
    at = _fresh().run()
    # set widgets, then submit — nothing applies until the submit button's run
    next(s for s in at.selectbox if s.key == "region").select("eu-west-1")
    next(s for s in at.slider if s.key == "threshold").set_value(120)
    at = at.run()
    assert "applied" not in at.session_state     # form not submitted yet
    next(b for b in at.button if "params" in str(b.key)).click().run()
    assert at.session_state["applied"] == {"region": "eu-west-1", "threshold": 120}


def test_warning_is_not_an_exception():
    at = _fresh().run()
    next(c for c in at.checkbox if c.key == "warn_toggle").set_value(True).run()
    assert not at.exception                                  # a warning never fails this
    assert any("expected" in w.value for w in at.warning)    # assert ON the warning


def test_secrets_injected_before_run():
    at = _fresh()
    at.secrets["api_token"] = "sekret"           # BEFORE .run()
    at.run()
    assert any("api_token = sekret" in str(m.value) for m in at.markdown)
    assert not at.exception


if __name__ == "__main__":                       # runnable without pytest
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")
