"""st-testing lab — a small app that IS the subject under test.

Run the app:   python -m streamlit run st_testing_lab.py
Run the tests: python -m pytest st-testing/            (see test_st_testing.py)

Deliberately exercises the patterns the tests assert: a keyed counter with a
callback, a form (batched rerun), a state handoff, an intentional warning, and
a secrets read — each small and headless-testable.
"""

import streamlit as st

st.set_page_config(page_title="st-testing lab", layout="centered")
st.title("st-testing — the app under test")

st.session_state.setdefault("count", 0)


# --- 1. keyed counter via callback (tests: click by key, fresh state) -----
st.header("Counter")
st.button("+1", key="inc", on_click=lambda: st.session_state.update(count=st.session_state.count + 1))
st.metric("count", st.session_state.count)
st.write(f"count = {st.session_state.count}")


# --- 2. form: batched rerun (tests: set_value then submit) ----------------
st.header("Form")
with st.form("params"):
    region = st.selectbox("region", ["us-east-1", "eu-west-1", "ap-south-1"], key="region")
    threshold = st.slider("threshold (ms)", 0, 500, 200, key="threshold")
    go = st.form_submit_button("apply")
if go:
    st.session_state.applied = {"region": region, "threshold": threshold}
    st.success(f"applied {region} @ {threshold}ms")

if "applied" in st.session_state:
    st.write("last applied:", st.session_state.applied)


# --- 3. intentional warning (tests: warning != exception) -----------------
st.header("Warning is not an exception")
if st.checkbox("show a warning", key="warn_toggle"):
    st.warning("this is expected — tests assert on it, they don't fail on it")


# --- 4. secrets read (tests: at.secrets injection before run) -------------
st.header("Secrets")
try:
    token = st.secrets["api_token"]          # raises if NO secrets.toml exists at all
except Exception:                            # (StreamlitSecretNotFoundError / KeyError)
    token = "MISSING"
st.write(f"api_token = {token}")
