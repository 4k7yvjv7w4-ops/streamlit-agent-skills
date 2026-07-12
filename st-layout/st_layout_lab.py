"""Streamlit layout lab — runnable ground truth for skills/st-layout.md.

Focus: page structure on 1.58 — the new sizing idiom, flex containers,
lazy tabs, dialogs, CSS targeting — and which pre-2025 "hard rules" are
now simply gone (a model trained on old docs will fight valid code).

Launch:  python -m streamlit run st_layout_lab.py
"""

from __future__ import annotations

import datetime as dt
import random
import time

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Streamlit layout lab", layout="wide")

st.session_state.setdefault("runs", 0)
st.session_state.runs += 1

with st.sidebar:
    st.title("Layout lab")
    st.metric("full-script runs", st.session_state.runs)
    st.caption("Skill: `st-layout/SKILL.md`")
    st.divider()
    st.markdown(
        "**Stale rules purged in 1.5x** (all verified gone):\n"
        "- ~~columns nest max 1 level~~\n"
        "- ~~no columns in sidebar~~\n"
        "- ~~no expander in expander~~\n"
        "- ~~set_page_config must be 1st~~ / ~~once~~\n\n"
        "**Still enforced:**\n"
        "- one `st.dialog` open per run\n"
        "- no form inside a form"
    )

TABS = st.tabs(
    [
        "1 📐 Sizing idiom",
        "2 🧱 Columns",
        "3 ↔️ Flex containers",
        "4 🗂️ Lazy tabs",
        "5 🫙 Expander & popover",
        "6 🪟 Dialogs",
        "7 🧭 Pages & chrome",
        "8 🔁 Reflow & placeholders",
        "9 🎨 CSS targeting",
        "10 ⚡ Fragments × layout",
    ]
)


def side_by_side(left="❌ old / broken", right="✅ 1.58 way"):
    c1, c2 = st.columns(2, gap="large")
    c1.subheader(left)
    c2.subheader(right)
    return c1, c2


# ================================================================ 1 sizing
with TABS[0]:
    st.markdown(
        """
**One sizing idiom everywhere:** `width=` / `height=` accept
`"stretch"` · `"content"` · pixel int, on nearly every element
(charts, dataframes, buttons, containers, images…).
`use_container_width=` is **deprecated** — it's `width="stretch"` now.
"""
    )
    c1, c2 = side_by_side("❌ deprecated", "✅ current")
    with c1:
        st.code(
            '''st.plotly_chart(fig, use_container_width=True)   # deprecation warning
st.dataframe(df, use_container_width=False)
st.button("go", use_container_width=True)''',
            language="python",
        )
    with c2:
        st.code(
            '''st.altair_chart(ch, width="stretch")   # fill the container
st.dataframe(df, width="content")       # shrink-wrap
st.button("go", width=200)              # exact px
st.container(height=300)                # px height -> scrolls (tab 3)''',
            language="python",
        )
        st.button("width='content'", width="content", key="sz_b1")
        st.button("width=260", width=260, key="sz_b2")
        st.button("width='stretch'", width="stretch", key="sz_b3")
    st.divider()
    st.markdown("**Vertical whitespace is a real element now:** `st.space(size=...)` "
                "(`xxsmall…xxlarge` / px / `'stretch'` inside fixed-height flex) — "
                "stop abusing `st.write('')`.")
    st.code('st.space("large")   # instead of st.write("") stacks', language="python")


# ================================================================ 2 columns
with TABS[1]:
    st.markdown(
        "**`st.columns` in 1.58:** `gap=`, `vertical_alignment=`, `border=`, "
        "`width=` — and the old nesting bans are gone (verified: 2-level "
        "nesting, columns in sidebar — no exception; they just get narrow)."
    )
    st.code(
        '''cols = st.columns(3, gap="large", vertical_alignment="center", border=True)
cols = st.columns([2, 1])          # ratio spec
a.metric(...)                       # cols are DeltaGenerators: a.write, a.button…''',
        language="python",
    )
    st.markdown("##### metric-card row — the dashboard header pattern")
    vals = {"p95 (ms)": (152.3, -3.8), "error rate (%)": (0.42, +0.04), "throughput (k)": (24.1, +0.2)}
    hist = {k: list(np.cumsum(np.random.default_rng(i).normal(0, 1, 20)) + 50)
            for i, k in enumerate(vals)}
    for col, (name, (v, d)) in zip(st.columns(3, gap="medium"), vals.items()):
        col.metric(name, v, delta=d, border=True, chart_data=hist[name],
                   chart_type="area", height="stretch")
    st.caption(
        "`st.metric(border=True, chart_data=[...])` — the card border and the "
        "sparkline are built in now; no custom CSS, no mini-chart hacks. "
        "`height='stretch'` equalizes card heights across the row."
    )
    st.divider()
    c1, c2 = side_by_side("vertical_alignment='top' (default)", "…='bottom' — aligned controls")
    with c1:
        a, b = st.columns([3, 1])
        a.selectbox("region", ["us-east-1", "eu-west-1", "ap-south-1"], key="va1")
        b.button("↻", key="va_btn1")  # sits high, misaligned with the input
    with c2:
        a, b = st.columns([3, 1], vertical_alignment="bottom")
        a.selectbox("region", ["us-east-1", "eu-west-1", "ap-south-1"], key="va2")
        b.button("↻", key="va_btn2")  # bottoms align with the input box
    st.caption("The '↻ next to a selectbox floats too high' classic: "
               "`vertical_alignment='bottom'`, not padding hacks.")


# ======================================================= 3 flex containers
with TABS[2]:
    st.markdown(
        """
**`st.container` is a flexbox now** — `horizontal=True` lays children in a
wrapping row (`horizontal_alignment=`, `gap=`). This replaces the old
"6 columns just to make a toolbar" hack: columns are for page structure,
horizontal containers are for element rows.
"""
    )
    c1, c2 = side_by_side("❌ columns-as-toolbar", "✅ horizontal container")
    with c1:
        st.code(
            '''c = st.columns(6)              # rigid: 6 equal slots, no wrap,
c[0].button("1d"); c[1].button("1w")   # phone = 6 crushed slivers''',
            language="python",
        )
    with c2:
        with st.container(horizontal=True, gap="small"):
            for w in ["1d", "1w", "1m", "3m", "1y", "max"]:
                st.button(w, key=f"tb_{w}")
        st.code(
            '''with st.container(horizontal=True, gap="small"):
    for w in windows: st.button(w, key=w)   # natural widths, wraps on narrow''',
            language="python",
        )
    st.markdown("…or skip buttons entirely: `st.segmented_control` / `st.pills` "
                "ARE the toolbar for single/multi choice:")
    st.segmented_control("window", ["1d", "1w", "1m", "3m", "1y"], default="1m",
                         key="segwin", label_visibility="collapsed")
    st.divider()
    st.markdown("##### fixed-height scrolling container")
    c1, c2 = st.columns(2, gap="large")
    with c1:
        with st.container(height=200, border=True):
            for i in range(30):
                st.text(f"req {i:02d}  ·  auth-api p95  ·  {150 + i * 0.1:.1f}ms")
        st.caption("`st.container(height=200)` → scrolls. `autoscroll=True` pins "
                   "to the bottom (log/chat feeds).")
    with c2:
        st.code(
            '''with st.container(height=200, border=True):     # px height => scroll
    for line in tape: st.text(line)
# chat/log feed that follows the tail:
with st.container(height=300, autoscroll=True):
    for msg in messages: st.write(msg)''',
            language="python",
        )
    st.markdown("`st.container(border=True)` is the **card**; nesting containers "
                "is unrestricted (verified 3 deep).")


# ============================================================== 4 lazy tabs
with TABS[3]:
    st.markdown(
        """
**Default `st.tabs` runs ALL tab bodies every run** (core-skill fact — switching
tabs doesn't even rerun). New in 1.5x: give tabs `key=` + `on_change="rerun"`
and each tab exposes **`.open`** — gate heavy work on it so only the visible
tab computes. Verified: on first paint only tab A's body executed.
"""
    )
    c1, c2 = side_by_side("❌ 10 heavy tabs, all compute", "✅ lazy tabs via .open")
    with c1:
        st.code(
            '''t = st.tabs(["Overview", "Metrics", …])   # every load_*() runs on EVERY
with t[0]: draw_overview(load_overview())  # interaction anywhere in the app —
with t[1]: draw_metrics(load_metrics())    # 10 tabs = 10x the work per click''',
            language="python",
        )
    with c2:
        st.code(
            '''t = st.tabs(["Overview", "Metrics", …], key="tab", on_change="rerun")
with t[0]:
    if t[0].open:                  # ONLY the selected tab's body runs
        draw_overview(load_overview())   # (switching now costs one rerun)
# programmatic switch: st.session_state.tab = "Metrics"  (before st.tabs line)''',
            language="python",
        )
    st.markdown("live — watch which bodies executed this run:")
    lt = st.tabs(["🐢 heavy A", "🐢 heavy B", "🐢 heavy C"], key="lazytab", on_change="rerun")
    ran = []
    for i, name in enumerate(["A", "B", "C"]):
        with lt[i]:
            if lt[i].open:
                ran.append(name)
                time.sleep(0.3)  # pretend heavy
                st.success(f"body {name} computed at "
                           f"{dt.datetime.now().strftime('%H:%M:%S')} — the others did not run")
    st.caption(f"executed this run: **{', '.join(ran)}** · active tab in state: "
               f"`st.session_state.lazytab = {st.session_state.get('lazytab')!r}`")
    st.markdown(
        "Trade-off: with `on_change='rerun'` a tab switch is a full rerun "
        "(default tabs switch client-side, free). Use lazy tabs when the tab "
        "bodies are expensive; plain tabs + `st.cache_data` when they're not. "
        "Widgets inside a `.open`-gated branch lose state when hidden — "
        "mirror to your own keys (core skill, state rule c)."
    )


# ==================================================== 5 expander & popover
with TABS[4]:
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown(
            """
**`st.expander` is visual-only collapse** — the body EXECUTES even when
collapsed (verified: a state write inside a collapsed expander ran).
Collapsing ≠ lazy. Heavy content in an expander still costs every run —
gate on a checkbox/toggle if you need real laziness. Widgets inside keep
state across expand/collapse (the line always runs).
"""
        )
        with st.expander("collapsed — but my body ran", expanded=False):
            st.session_state.exp_ran_at = dt.datetime.now().strftime("%H:%M:%S")
            st.write("hello")
        st.caption(f"state written from inside while collapsed: "
                   f"`{st.session_state.exp_ran_at}` (updates every run)")
        st.code(
            '''with st.expander("diagnostics", icon="🔬"):        # runs regardless
    st.dataframe(cheap_summary)
if st.toggle("full diagnostics"):                   # REAL laziness = a gate
    st.dataframe(expensive_frame())''',
            language="python",
        )
    with c2:
        st.markdown(
            """
**`st.popover`** — a button that opens a floating panel; the filter-bar
workhorse. Body also runs every run (same rule). Panel closes on outside
click; widget values persist (they're normal widgets).
"""
        )
        with st.container(horizontal=True):
            with st.popover("⚙️ filters"):
                st.multiselect("region", ["us-east", "eu-west", "ap-south", "us-west"],
                               default=["us-east", "eu-west"], key="pop_region")
                st.slider("min samples", 0, 50, 10, key="pop_n")
            with st.popover("📅 window"):
                st.radio("range", ["30d", "60d", "180d"], key="pop_win", horizontal=True)
        st.caption(f"reads like any widget: region={st.session_state.pop_region}, "
                   f"n≥{st.session_state.pop_n}, window={st.session_state.pop_win}")
        st.markdown("Nesting: expander-in-expander, popover-in-popover, either in "
                    "columns — all legal now (verified, no exception).")


# ================================================================ 6 dialogs
with TABS[5]:
    st.markdown(
        """
**`@st.dialog("title")`** turns a function into a modal. Rules (verified):
call the decorated function to OPEN it; **only one dialog may open per
run** (second call raises `StreamlitAPIException`); the body reruns like a
fragment while open; **`st.rerun()` inside is the close button**. Dismissal
(X / esc / outside click) just stops rendering it — widget keys inside
keep their LAST values in session_state, so hand results over explicitly.
"""
    )
    c1, c2 = st.columns(2, gap="large")
    with c1:

        @st.dialog("Alert rule", width="medium", on_dismiss="rerun")
        def alert_rule():
            st.selectbox("service", ["auth-api", "checkout", "search-api"], key="al_svc")
            st.number_input("threshold (ms)", 1, 500, 250, key="al_thresh")
            a, b = st.columns(2)
            if a.button("submit", type="primary", width="stretch"):
                st.session_state.alert = (st.session_state.al_svc,
                                          st.session_state.al_thresh)
                st.rerun()  # closes the dialog
            if b.button("cancel", width="stretch"):
                st.session_state.pop("alert", None)
                st.rerun()

        if st.button("open alert dialog", key="dlg_open"):
            alert_rule()
        if "alert" in st.session_state:
            st.success(f"alert: {st.session_state.alert[0]} > "
                       f"{st.session_state.alert[1]} ms")
        else:
            st.caption("nothing submitted — dismissing with ✕ hands over nothing, "
                       "because only the submit branch copies values out.")
    with c2:
        st.code(
            '''@st.dialog("Alert rule", width="medium")     # small | medium | large
def alert_rule():
    st.selectbox("service", [...], key="al_svc")
    if st.button("submit"):
        st.session_state.alert = st.session_state.al_svc    # hand over
        st.rerun()                                          # CLOSE

if st.button("open"):
    alert_rule()                   # opening = calling it
if "alert" in st.session_state:    # consume OUTSIDE the dialog
    ...

# - one open dialog per run; a second call raises
# - dismissible=False removes the ✕; on_dismiss="rerun"/callback hooks esc/✕
# - don't: st.dialog inside a fragment, dialogs opening dialogs''',
            language="python",
        )


# ========================================================= 7 pages & chrome
with TABS[6]:
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown(
            """
**`st.set_page_config`** — callable anywhere and multiple times now
(verified: after `st.write`, and twice — no exception; later calls win).
Still put it first by convention: everything before it renders on default
settings for a frame. `layout="wide"` is the dashboard default.
"""
        )
        st.code(
            '''st.set_page_config(
    page_title="Latency monitor", page_icon="📈",
    layout="wide",                       # centered = blog width
    initial_sidebar_state="collapsed",   # phones: don't cover the page
)''',
            language="python",
        )
        st.markdown(
            "**A tab-monolith has a natural upgrade:** `st.navigation` — each "
            "section becomes a function, ONLY the selected page's code runs "
            "(unlike default tabs), URL routes per page, `position='top'` "
            "gives a navbar instead of sidebar entries."
        )
    with c2:
        st.code(
            '''# multipage without a pages/ dir — single entry file:
def overview():  ...   # each page = a function (or "pages/overview.py" path)
def metrics():   ...

pg = st.navigation(
    {"Dashboards": [st.Page(overview, title="Overview", icon="📊", default=True),
                    st.Page(metrics, title="Metrics", url_path="metrics")],
     "Alerts":  [st.Page(alerts_fn, title="Alerts")]},
    position="top",        # or "sidebar" (default) / "hidden" (roll your own)
)
pg.run()                   # ONLY the selected page executes

# st.switch_page(page_or_path)  = programmatic jump
# st.page_link(page, label=..)  = styled in-app link''',
            language="python",
        )
    st.caption("Session state is shared across pages; widgets on a page you "
               "navigate away from lose their values unless mirrored "
               "(same rule as any non-executed widget line).")


# ================================================== 8 reflow & placeholders
with TABS[7]:
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown(
            """
**`st.empty()`** = a single-slot placeholder: each write REPLACES the
content (verified: two writes → only the last renders). `.container()` on
it groups several elements in the slot; `.empty()` clears it. This is how
you draw "into" an earlier spot on the page from later code.
"""
        )
        st.code(
            '''slot = st.empty()                 # reserve the spot up top
... later in the script ...
slot.metric("total", total)        # fills/overwrites the reserved spot
with slot.container():             # multiple elements in one slot
    st.write(a); st.write(b)
slot.empty()                       # clear''',
            language="python",
        )
        st.markdown(
            "**Widget identity is the `key`, not the position** (verified: a "
            "keyed slider moved between columns kept its value). Reflowing a "
            "page — moving a widget between containers/columns — is safe. "
            "Only a run where its line doesn't execute at all resets it."
        )
    with c2:
        st.markdown("live: move the slider between columns — value survives")
        st.session_state.setdefault("mv_right", False)
        a, b = st.columns(2, border=True)
        target = b if st.session_state.mv_right else a
        with target:
            st.slider("keyed slider (key='mv')", 0, 10, key="mv")
        st.checkbox("render it in the right column instead", key="mv_right")
        st.divider()
        st.markdown("**Still enforced** (verified raises):")
        st.code(
            '''with st.form("a"):
    with st.form("b"): ...
# StreamlitAPIException: Forms cannot be nested in other forms.''',
            language="python",
        )


# ============================================================ 9 CSS targets
with TABS[8]:
    st.markdown(
        """
**Every `key=` becomes a stable CSS class: `st-key-<key>`** — on widgets AND
`st.container(key=...)`. This is the sanctioned escape hatch; stop scraping
auto-generated `st-emotion-*` classes (they change every release).
"""
    )
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.html(
            """<style>
            .st-key-hot_zone { background: rgba(255, 75, 75, .08);
                               border-left: 4px solid #ff4b4b;
                               padding: .6rem .8rem; border-radius: .5rem; }
            .st-key-hot_zone p { margin-bottom: .2rem; }
            </style>"""
        )
        with st.container(key="hot_zone"):
            st.write("**risk temperature 78 — hot**")
            st.write("styled via `.st-key-hot_zone`, survives Streamlit upgrades")
        st.code(
            '''st.html("<style> .st-key-hot_zone { … } </style>")
with st.container(key="hot_zone"):        # key -> class st-key-hot_zone
    st.write("…")''',
            language="python",
        )
    with c2:
        st.markdown(
            """
- `st.html(body)` — sanitized by default; **JS runs only with**
  `unsafe_allow_javascript=True` (1.5x). `st.markdown(css, unsafe_allow_html=True)`
  is the legacy spelling for style injection.
- Colored text without CSS: `st.markdown(":red[wide] / :green[tight]")`,
  `st.badge("HOT", color="red")`.
- App-wide look: `.streamlit/config.toml` `[theme]`
  (`primaryColor`, `base="dark"`, fonts) — prefer it over CSS for colors.
- Before ANY custom CSS, check the built-in: `border=`, `type="primary"`,
  `icon=`, `st.metric(border=True)` … 1.5x absorbed most old hacks.
"""
        )
        st.badge("built-in badge", color="violet")


# ===================================================== 10 fragments × layout
with TABS[9]:
    st.markdown(
        """
**A fragment must draw inside itself.** Writing to a container that exists
OUTSIDE the fragment doesn't raise — but on every fragment rerun the outside
elements pile up / get cleared out from under you on the next full run.
Rule: a fragment OWNS its pixels; to change the rest of the page, write
session_state + `st.rerun()` (core skill, tab 8).
"""
    )
    c1, c2 = side_by_side("❌ fragment writes to outer container", "✅ state out, redraw on full run")
    with c1:
        outer_slot = st.container(border=True)
        outer_slot.caption("outer container (created before the fragment)")

        @st.fragment
        def bad_frag():
            if st.button("tick (fragment rerun)", key="bf_btn"):
                pass
            outer_slot.write(f"wrote to OUTER at {dt.datetime.now().strftime('%H:%M:%S')}")

        bad_frag()
        st.caption("Click tick a few times: the outer box grows a new line per "
                   "fragment rerun (they stack), then a full-script run wipes "
                   "them. Unstable by design — don't.")
    with c2:
        st.code(
            '''@st.fragment(run_every="2s")
def ticker():
    px = get_price()
    st.metric("last", px)                  # draws INSIDE itself: fine
    if px > st.session_state.alert_lvl:    # needs to change the page?
        st.session_state.alert = px        # write state…
        st.rerun()                         # …full-app rerun redraws it all''',
            language="python",
        )
        st.markdown(
            "- widgets inside a fragment rerun only the fragment — a filter "
            "toolbar in a fragment can't refresh the chart outside it "
            "(state + `st.rerun()` can)\n"
            "- `st.dialog` may not be called from inside a fragment\n"
            "- fragments in columns/tabs/expanders: fine — the boundary is "
            "the FUNCTION, not the container"
        )
