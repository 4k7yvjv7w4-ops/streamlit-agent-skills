"""Page→page param passing lab — st.navigation + session_state + query_params.

Run:  python -m streamlit run st_nav_params_lab.py

Separate from st_layout_lab.py because st.navigation must OWN the entry file
(pages are the app; they can't nest inside another lab's tabs).

Demonstrates the two channels and their lifetimes:
  * st.session_state  — any Python object, same browser session, gone on refresh
  * st.query_params   — strings only, survives refresh, bookmarkable URL
and the two verified gotchas: default st.switch_page CLEARS query params
(carry them via query_params=), and query param values come back as str.
"""

import streamlit as st

SERVICES = ["checkout", "search", "profile", "cart", "media"]


def picker():
    st.title("1 · Picker")
    st.caption(
        "Choose a service, then jump. The button writes a rich dict into "
        "`st.session_state.handoff` AND puts the service into the URL via "
        "`st.switch_page(page, query_params=...)` — without that kwarg, "
        "switch_page CLEARS all query params (verified in source)."
    )
    svc = st.selectbox("service", SERVICES, key="svc_pick")
    days = st.slider("window (days)", 1, 30, 7, key="win_pick")

    if st.button("open details →", type="primary", key="go"):
        # 1) rich handoff — any object, same-session only
        st.session_state.handoff = {"service": svc, "window_days": days}
        # 2) durable handoff — string-only, survives refresh/bookmark
        st.switch_page(detail_page, query_params={"service": svc, "days": str(days)})

    st.info(
        "WRONG way: reading `st.session_state.svc_pick` on the Detail page. "
        "This page won't run there, so its widget keys are GONE (core rule) — "
        "always copy into your own keys before switching."
    )


def detail():
    st.title("2 · Detail")

    h = st.session_state.get("handoff")            # None on refresh/direct entry
    qp_svc = st.query_params.get("service")        # str or None
    qp_days = st.query_params.get("days")          # str! '7', not 7

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("session_state channel")
        if h:
            st.json(h)
            st.caption("Rich object arrived intact — but refresh this page "
                       "(F5) and it's gone: state doesn't survive a reload.")
        else:
            st.warning("No `handoff` in session_state — you refreshed or came "
                       "here directly. This is WHY query_params is the durable "
                       "source and state just a cache.")
    with c2:
        st.subheader("query_params channel")
        if qp_svc:
            days = int(qp_days) if qp_days and qp_days.isdigit() else 7
            st.metric(qp_svc, f"{days}-day window")
            st.caption(f"Values are STRINGS: got days={qp_days!r} "
                       f"({type(qp_days).__name__}) — parsed to int({days}). "
                       "This URL is bookmarkable; refresh keeps it working.")
        else:
            st.warning("No query params — arrive via the Picker button, or add "
                       "`?service=checkout&days=7` to the URL.")

    st.page_link(picker_page, label="← back to picker", icon="↩️")


picker_page = st.Page(picker, title="Picker", default=True)
detail_page = st.Page(detail, title="Detail", url_path="detail")

pg = st.navigation([picker_page, detail_page], position="sidebar")
pg.run()
