"""Self-test: fetch discipline via AppTest + the linking logic as pure Python.

Run:  python test_st_linked_views.py
"""
import logging

import pandas as pd
from streamlit.testing.v1 import AppTest

logging.getLogger("streamlit").setLevel(logging.ERROR)


def main() -> None:
    at = AppTest.from_file("st_linked_views_lab.py").run()
    assert not at.exception, at.exception
    f1 = at.session_state["fetches"]
    at.run()                                             # plain rerun -> cache hit
    assert at.session_state["fetches"] == f1, "a rerun re-fetched the lake"
    at.selectbox(key="service").select("media").run()    # new key -> ONE fetch
    assert not at.exception and at.session_state["fetches"] == f1 + 1
    at.selectbox(key="service").select("auth").run()     # back -> cached
    assert at.session_state["fetches"] == f1 + 1
    print(f"PASS fetch discipline: {f1} -> rerun {f1} -> new key {f1 + 1} -> back {f1 + 1}")

    kinds = [e.type for e in at.main]
    assert kinds.count("dataframe") == 2 and kinds.count("vega_lite_chart") == 2
    print("PASS page: selector grid + detail table + 2 charts, zero exceptions")

    import st_linked_views_lab as lab                    # pure function, no page needed
    b = {"regions": pd.DataFrame({"region": ["a", "b"], "avg_ms": [1, 2]}),
         "detail": pd.DataFrame({"region": ["a", "a", "b"], "endpoint": list("xyz")}),
         "daily": pd.DataFrame({"region": ["a", "b"], "avg_ms": [1, 2]})}
    v = lab.apply_selection(b, "a")
    assert set(v["detail"]["region"]) == {"a"} and set(v["daily"]["region"]) == {"a"}
    assert len(v["regions"]) == 2, "the selector table must NOT filter itself"
    assert lab.apply_selection(b, None) is b
    print("PASS apply_selection: filters siblings, keeps selector, None = all")
    print("\nALL OK")


if __name__ == "__main__":
    main()
