---
name: st-layout
description: Streamlit page layout — columns, containers, tabs, expanders, popovers, dialogs, sidebar, multipage navigation, sizing, CSS targeting. Use when structuring a Streamlit page, building toolbars/cards/modals/metric rows, making tabs lazy, styling elements, or when layout code raises StreamlitAPIException.
---

# Streamlit layout (1.58.x) — structure, containers, chrome

Runnable proof of every claim: `st_layout_lab.py` in this skill folder
(`python -m streamlit run ~/.roo/skills/st-layout/st_layout_lab.py`).
Execution/state rules live in [st-core]; this skill is where things go
on the page.

**Version guard:** verified on Streamlit **1.58**, API-checked on **1.55**.
Everything here exists on 1.55 too (STALE RULES included) with ONE
exception: `st.container(autoscroll=)` is 1.56+ — skip it below that.

## STALE RULES — your training data is wrong about these (verified on 1.58)

Old docs/tutorials hardcode restrictions that NO LONGER EXIST. Do not
"fix" code for them, do not warn about them:

- ~~columns nest max one level~~ → any depth is legal (they just get narrow)
- ~~no columns in the sidebar~~ → legal, nesting too
- ~~no expander inside expander / popover inside popover~~ → all legal
- ~~`st.set_page_config` must be the first call, once~~ → callable anywhere,
  multiple times; later calls win. (Still put it first: content rendered
  before it flashes with default settings.)
- ~~`use_container_width=True`~~ → deprecated; the idiom is `width="stretch"`

Still enforced (verified raises): **one open `st.dialog` per run** ·
**no form inside a form**.

## The sizing idiom

`width=` / `height=` on nearly every element take `"stretch"` | `"content"`
| pixel int: `st.button("go", width=200)`, `st.dataframe(df, width="content")`,
`st.altair_chart(ch, width="stretch")`. Vertical gaps: `st.space("large")`
(xxsmall…xxlarge / px), not `st.write("")` stacks.

## Columns — page structure

```python
a, b = st.columns([2, 1], gap="large", vertical_alignment="bottom", border=True)
```

- Columns are DeltaGenerators: `a.metric(...)`, `b.button(...)`, or `with a:`.
- `vertical_alignment="bottom"` fixes the classic "↻ button floats above its
  neighboring selectbox" — never pad with empty markdown.
- **Metric-card row** (dashboard header) is all built-in now:
  `col.metric(name, v, delta=d, border=True, chart_data=hist, chart_type="area",
  height="stretch")` — border, sparkline, equal card heights. No CSS.

## Horizontal containers — element rows (stop making 6 columns for a toolbar)

```python
with st.container(horizontal=True, gap="small"):      # flex row, wraps
    for w in ["1d", "1w", "1m", "1y"]: st.button(w, key=w)
```

Columns = rigid page grid; `horizontal=True` container = natural-width row
that wraps on phones. For single/multi choice, prefer the purpose-built
`st.segmented_control` / `st.pills` over button rows.

More container tools: `st.container(border=True)` = card;
`height=300` = fixed-height **scrolling** region; `autoscroll=True` (1.56+)
pins to the bottom (log/chat tape). Nesting containers: unrestricted.

## Tabs — all-run by default, lazy on request

Default `st.tabs`: EVERY tab's body runs on every rerun; switching is
client-side and free. New: stateful/lazy tabs —

```python
t = st.tabs(["Latency", "Errors"], key="tab", on_change="rerun")
with t[0]:
    if t[0].open:                    # ONLY the selected tab's body runs
        draw_latency(load_latency()) # (verified: others didn't execute)
```

- `st.session_state.tab` holds the active tab's **label string**; set it
  before the `st.tabs` line to switch programmatically. `default="Errors"`
  picks the initial tab.
- Trade-off: each switch is now a full rerun. Use `.open`-gating when tab
  bodies are expensive; plain tabs + `st.cache_data` when they're not.
- Widgets inside a non-open gated branch don't execute → lose state
  ([st-core] rule: mirror to your own keys).

## Expander & popover — visual, NOT lazy

**A collapsed `st.expander` still executes its body** (verified: state write
ran while collapsed). Collapse ≠ laziness — heavy content in an expander
costs every run; for real laziness gate on `st.toggle`. Widgets inside keep
state across expand/collapse. `st.popover("⚙️ filters")` = button opening a
floating panel (the filter-bar workhorse); same always-runs rule; widget
values persist like any widget.

## Dialogs — the modal recipe

```python
@st.dialog("Alert rule", width="medium")         # small | medium | large
def alert_rule():
    st.selectbox("service", [...], key="al_svc")
    if st.button("submit"):
        st.session_state.alert = st.session_state.al_svc    # hand over
        st.rerun()                                          # CLOSE = rerun

if st.button("open"): alert_rule()               # open = call it
if "alert" in st.session_state: ...              # consume OUTSIDE
```

- Calling a second dialog-decorated function in the same run RAISES.
- Dismissal (✕/esc/click-outside) just stops rendering — copy results to
  state in the submit branch only; never read the dialog's widget keys as
  "the result" (they keep last-touched values after dismissal).
- `dismissible=False` removes ✕; `on_dismiss="rerun"` or a callback hooks it.
- Body reruns fragment-style while open. No dialogs from fragments, no
  dialog-opening-dialog.

## Pages & chrome

`st.set_page_config(layout="wide", initial_sidebar_state="collapsed")` —
wide is the dashboard default; collapse the sidebar for phone users.

A tab-monolith's upgrade path is `st.navigation` (only the selected page's
code runs, URL per page — unlike default tabs):

```python
pg = st.navigation({"Monitoring": [st.Page(latency_fn, title="Latency", default=True),
                                   st.Page("pages/regions.py", url_path="regions")]},
                   position="top")     # "sidebar" default | "top" navbar | "hidden"
pg.run()
```

**No `pages/` directory required.** A page is anything you wrap in `st.Page`:
a **function** (single-file app — no files/folders needed) OR a file path.
Mix them freely.

```python
def home():    st.title("Home")     # pages are just functions
def details(): st.title("Details")

home_pg    = st.Page(home,    default=True)
details_pg = st.Page(details, url_path="details")
st.navigation([home_pg, details_pg]).run()   # a plain list works too (no dict/sections)
```

**Switch pages on a button click — `st.switch_page`:**

```python
if st.button("open details"):
    st.switch_page(details_pg)      # pass the st.Page OBJECT (jumps immediately, no st.rerun)
```

- For a **function** page you MUST pass the `st.Page` object (`details_pg`),
  NOT a string — a function has no file path. Only file-based pages
  (`pages/x.py` model) can be switched to by path (`st.switch_page("pages/x.py")`).
- The target must be **registered** in `st.navigation([...])` (or in `pages/`);
  switching elsewhere raises `StreamlitAPIException`.
- `st.page_link(details_pg, label="Details")` renders a clickable link instead.

Session state is shared across pages; a page you navigate away from doesn't
execute → its widgets lose values unless mirrored (core rule again).

### Passing params page → page (verified 1.58; both channels exist on 1.55)

Two channels — pick by lifetime:

| Channel | Carries | Survives refresh / shareable URL? |
|---|---|---|
| `st.session_state` | any Python object | ❌ same browser session only |
| `st.query_params` | **strings only** | ✅ bookmarkable, refresh-proof |

```python
def picker():
    svc = st.selectbox("service", services, key="svc_pick")
    if st.button("open details"):
        st.session_state.handoff = {"service": svc, "window_days": 7}  # rich object
        st.switch_page(detail_page, query_params={"service": svc})     # URL params

def detail():
    h   = st.session_state.get("handoff")          # None on cold/direct entry — guard!
    svc = st.query_params.get("service")           # ALWAYS a str ('7' not 7) — parse
```

- **Default `st.switch_page` CLEARS all query params** (source-verified) — carry
  them explicitly via `query_params=`. `st.page_link(..., query_params=...)`
  does the same for user-clicked links.
- **Never use the source page's widget keys as the transport** — that page
  didn't run, so its keys are gone (core rule). Copy into your OWN keys
  (`handoff`) before switching.
- Query param values are **strings** (`int(...)` your numbers; `.get_all("k")`
  for repeated keys); a page opened directly from a bookmark has query params
  but NO session_state — treat `query_params` as the durable source and
  session_state as the cache.

Runnable proof: `st_nav_params_lab.py` in this skill folder.

## Placeholders & reflow

- `st.empty()` = one-slot placeholder; each write REPLACES (verified — only
  the last write renders). Fill an earlier spot from later code:
  `slot = st.empty()` … `slot.metric(...)`. Group with `slot.container()`;
  clear with `slot.empty()`.
- **Widget identity is the `key`, not the position** (verified: keyed slider
  moved between columns kept its value). Reflowing layouts is safe; only a
  run where the widget's line doesn't execute resets it.

## CSS targeting — the sanctioned hatch

Every `key=` (widgets AND `st.container(key=...)`, `st.tabs(key=...)`)
emits a stable class **`st-key-<key>`**. Never scrape `st-emotion-*`
classes — they change every release.

```python
st.html("<style>.st-key-hot_zone { border-left: 4px solid #ff4b4b; }</style>")
with st.container(key="hot_zone"): ...
```

- `st.html` is sanitized; JS only with `unsafe_allow_javascript=True`.
- Before CSS, check built-ins: `border=`, `type="primary"`, `icon=`,
  `st.badge("HOT", color="red")`, `:red[text]` markdown, and
  `.streamlit/config.toml` `[theme]` for app-wide colors/fonts.

## Fragments × layout — a fragment owns its pixels

Writing from a fragment to a container created OUTSIDE it doesn't raise,
but is unstable (verified live): each fragment rerun APPENDS another copy
into the outer container, and the next full-app run wipes them all. To
affect the page outside a fragment: write session_state + `st.rerun()`.
Widgets inside a fragment rerun only the fragment — a filter toolbar
inside one can't refresh a chart outside it. Fragments inside
columns/tabs/expanders are fine; the boundary is the function.

## Debug checklist — layout exceptions & mysteries

1. `StreamlitAPIException` about dialogs → two dialog calls reachable in one
   run; about forms → nested `st.form`.
2. "Deprecation: use_container_width" spam → mechanical `width="stretch"`.
3. Something renders twice / vanishes near a fragment → it's drawing outside
   itself; move it inside or go state + `st.rerun()`.
4. Widget resets when a tab/branch hides it → the line didn't run;
   mirror-to-own-key pattern in [st-core].
5. Custom CSS broke after upgrade → it targeted `st-emotion-*`; re-anchor on
   `st-key-<key>` classes.
