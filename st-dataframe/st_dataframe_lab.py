"""st.dataframe / st.data_editor lab — runnable ground truth for skills/st-dataframe.md.

The FREE native table: column_config formatting, sparkline columns,
selection events, editing, Styler limits, Arrow dtype gotchas.
(The grid-matrix cross-ref: flat interactive grid with JS styling -> aggrid;
pivot/tree -> st-pivot; huge client-side exploration -> perspective;
everything in THIS lab needs none of those.)

Launch:  python -m streamlit run st_dataframe_lab.py
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="st.dataframe lab", layout="wide")

st.session_state.setdefault("runs", 0)
st.session_state.runs += 1

rng = np.random.default_rng(7)


@st.cache_data
def movers() -> pd.DataFrame:
    names = ["auth-api", "checkout", "search-api", "payments-gw", "media-cdn"]
    n = len(names)
    return pd.DataFrame(
        {
            "service": names,
            "p95_ms": [152.3, 340.1, 155.8, 305.4, 262.0],
            "d1_ms": [-3.8, +14.2, -1.3, +26.1, -8.4],
            "pct_1y": [0.22, 0.71, 0.30, 0.66, 0.45],          # 1y percentile
            "hist": [list(np.cumsum(rng.normal(0, 1, 30)) + 150) for _ in range(n)],
            "checks": [412, 238, 385, 129, 64],
            "req_mm": [8_450.0, 3_120.0, 7_900.0, 1_870.0, 640.0],   # requests, millions
            "last": pd.to_datetime("2026-07-03 14:00")
            + pd.to_timedelta(rng.integers(0, 120, n), unit="m"),
            "src": ["https://status.example.com"] * n,
        }
    )


with st.sidebar:
    st.title("st.dataframe lab")
    st.metric("full-script runs", st.session_state.runs)
    st.caption("Skill: `st-dataframe/SKILL.md`")

TABS = st.tabs(
    [
        "1 📋 Basics & toolbar",
        "2 🏷️ column_config",
        "3 📈 Sparkline columns",
        "4 🖱️ Selection → Python",
        "5 ✏️ data_editor",
        "6 🎨 Styler & limits",
        "7 🧬 Dtypes & Arrow",
    ]
)

# ================================================================ 1 basics
with TABS[0]:
    st.markdown(
        """
**`st.dataframe` ships a full toolbar for free** (hover, top-right): 🔍 search,
⬇ CSV download, ⛶ fullscreen. Plus client-side column sort, column resize/
reorder, **cell-range drag-select + Ctrl/Cmd-C copy to Excel** — none of this
needs AG Grid. It virtualizes rows, so 100k-row frames scroll fine
(`st.table` renders every cell as HTML — keep it under ~100 rows, static).
"""
    )
    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        st.dataframe(
            movers().drop(columns=["hist", "src"]),
            hide_index=True,                      # positional index is noise
            column_order=["service", "p95_ms", "d1_ms", "checks", "last"],
            row_height=32,
            placeholder="–",                      # NaN display text
        )
    with c2:
        st.code(
            '''st.dataframe(
    df,
    hide_index=True,             # kill the 0..n index column
    column_order=[...],          # subset + order, no df reshaping
    row_height=32,               # denser rows (px)
    placeholder="–",             # what NaN shows as
    height=400,                  # px -> internal scroll; "auto" = grow
)''',
            language="python",
        )
        st.caption("`column_order` beats `df[[...]]` — display-only pruning, "
                   "the frame itself keeps every column for the code below it.")

# =========================================================== 2 column_config
with TABS[1]:
    st.markdown(
        "**`column_config` is per-column presentation** — header, format, "
        "width, pinning, help — applied at display time; the DataFrame keeps "
        "raw numbers (unlike formatting with `.astype(str)` / f-strings, which "
        "destroys sorting)."
    )
    df = movers().drop(columns=["hist"])
    st.dataframe(
        df,
        hide_index=True,
        column_config={
            "service": st.column_config.TextColumn("Service", pinned="left"),
            "p95_ms": st.column_config.NumberColumn(
                "p95", format="%.0f ms", help="daily median"),
            "d1_ms": st.column_config.NumberColumn("Δ1d", format="%+.1f"),
            "pct_1y": st.column_config.ProgressColumn(
                "1y %ile", min_value=0, max_value=1, format="percent"),
            "req_mm": st.column_config.NumberColumn(
                "Requests (M)", format="compact"),          # 8.45K -> compact SI
            "checks": None,                             # None = hide column
            "last": st.column_config.DatetimeColumn(
                "Last print", format="HH:mm", timezone="America/New_York"),
            "src": st.column_config.LinkColumn(
                "Source", display_text="status"),     # or regex capture
        },
    )
    st.code(
        '''column_config={
    "p95_ms": st.column_config.NumberColumn("p95", format="%.0f ms"),
    "pct_1y":    st.column_config.ProgressColumn("1y %ile", min_value=0,
                                                 max_value=1, format="percent"),
    "requests":  st.column_config.NumberColumn(format="compact"),
    "checks":    None,                                   # hide
    "src":       st.column_config.LinkColumn(display_text="status"),
}
# format= takes printf ("%.0f ms", "%+d") OR a predefined string:
# "plain" "localized" "dollar" "euro" "yen" "percent" "compact"
# "scientific" "engineering" "accounting" "bytes"
# percent MULTIPLIES by 100: pass 0.22 to show 22%.''',
        language="python",
    )
    st.caption("Same `column_config` dict works on `st.data_editor` (tab 5); "
               "there Number/Text/Date columns also become the cell EDITORS "
               "with min/max/step/validate enforced.")

# ======================================================= 3 sparkline columns
with TABS[2]:
    st.markdown(
        "**A cell can hold a chart:** put a LIST of numbers in the cell, tag "
        "the column `LineChartColumn` / `AreaChartColumn` / `BarChartColumn`. "
        "The movers-table-with-history pattern, zero JS:"
    )
    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        st.dataframe(
            movers()[["service", "p95_ms", "d1_ms", "hist"]],
            hide_index=True,
            column_config={
                "service": "Service",  # plain string = just rename
                "p95_ms": st.column_config.NumberColumn("p95", format="%.0f"),
                "d1_ms": st.column_config.NumberColumn("Δ1d", format="%+.1f"),
                "hist": st.column_config.LineChartColumn(
                    "30d history", y_min=140, y_max=160),
            },
        )
    with c2:
        st.code(
            '''df["hist"] = [list(series) for series in histories]   # list per cell!
st.dataframe(df, column_config={
    "hist": st.column_config.LineChartColumn("30d", y_min=140, y_max=160),
})
# fix y_min/y_max for cross-row comparability, else each cell autoscales
# build the lists with groupby: agg(hist=("val", list))''',
            language="python",
        )
        st.caption("Sparklines are display-only (no tooltip/axis). For anything "
                   "richer, click-to-detail via selection (tab 4) + a real chart.")

# ===================================================== 4 selection -> Python
with TABS[3]:
    st.markdown(
        """
**`on_select="rerun"` turns the table into an input widget.** The call then
returns `{"selection": {"rows": [...], "columns": [...], "cells": [...]}}`
(verified shape). `rows` are **positional indices into the frame you passed**
— use `df.iloc[rows]`, NOT `.loc`; UI sorting does not renumber them.
"""
    )
    c1, c2 = st.columns([3, 2], gap="large")
    df = movers().drop(columns=["hist", "src"])
    with c1:
        ev = st.dataframe(
            df,
            key="sel_grid",
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row-required",   # radio-like: always one row
            selection_default={"selection": {"rows": [0]}},
            column_config={"pct_1y": None, "req_mm": None},
        )
        row = df.iloc[ev.selection.rows[0]]
        st.metric(row["service"], f'{row["p95_ms"]:.0f} ms', delta=f'{row["d1_ms"]:+.1f}')
    with c2:
        st.code(
            '''ev = st.dataframe(df, key="g", on_select="rerun",
                  selection_mode="single-row-required",   # always exactly 1
                  selection_default={"selection": {"rows": [0]}})
picked = df.iloc[ev.selection.rows]        # POSITIONAL -> iloc

# modes (combinable list): single-row / single-row-required / multi-row
#                          single-column / multi-column
#                          single-cell  / multi-cell
# same event also in st.session_state.g["selection"]
# every selection click = one rerun -- cache the table's data''',
            language="python",
        )
        st.markdown(
            "- master-detail: selected row drives a chart/table below — the "
            "free replacement for most 'I need AG Grid selection' asks\n"
            "- `single-row-required` + `selection_default` = no empty state "
            "to handle\n"
            "- column/cell modes exist but row selection is the workhorse"
        )

# ============================================================= 5 data_editor
with TABS[4]:
    st.markdown(
        """
**`st.data_editor` = editable grid.** The RETURN VALUE is the edited frame —
your input is never mutated. The raw diff lives in
`st.session_state[key]` as `{"edited_rows": {}, "added_rows": [], "deleted_rows": []}`
(verified shape); `edited_rows` is keyed by **row POSITION**.
"""
    )
    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        watch = pd.DataFrame(
            {
                "name": ["auth-api", "checkout", "media-cdn"],
                "threshold_ms": [450.0, 250.0, 180.0],
                "direction": pd.Categorical(
                    ["slower than", "slower than", "faster than"],
                    categories=["slower than", "faster than"]),
                "tags": [["core", "beta"], ["core"], ["edge"]],
                "active": [True, True, False],
            }
        )
        edited = st.data_editor(
            watch,
            key="wl",
            num_rows="dynamic",                    # + row adder & 🗑 delete
            disabled=["name"],                     # read-only columns
            hide_index=True,
            column_config={
                "threshold_ms": st.column_config.NumberColumn(
                    "Alert level (ms)", min_value=0, max_value=2000, step=5,
                    format="%.0f", required=True),
                "direction": st.column_config.SelectboxColumn(
                    "Trigger", options=["slower than", "faster than"]),
                "tags": st.column_config.MultiselectColumn(
                    "Tags", options=["core", "edge", "beta", "batch"],
                    accept_new_options=True),
                "active": st.column_config.CheckboxColumn("On"),
            },
        )
        st.write("diff:", st.session_state.wl)
        st.caption(f"{int(edited['active'].sum())} active alerts — computed from "
                   "the RETURN value, not the input frame.")
    with c2:
        st.code(
            '''edited = st.data_editor(df, key="wl",
    num_rows="dynamic",          # "fixed" | "dynamic" | "add" | "delete"
    disabled=["name"],           # or disabled=True for view-only cells
    column_config={...})         # Number/Selectbox/Multiselect/Checkbox
                                 # column = the EDITOR + validation

# categorical dtype -> dropdown automatically (verified)
# edits DON'T touch your input df; consume the return value
# st.session_state.wl = {"edited_rows": {2: {"active": True}},
#                        "added_rows": [...], "deleted_rows": [1]}''',
            language="python",
        )
        st.warning(
            "**Positional-edit footgun:** `edited_rows` keys are row positions. "
            "If the input frame is re-sorted/refiltered between runs while the "
            "same `key` holds pending edits, the edits re-apply to WHOSE ROW IS "
            "AT THAT POSITION NOW. Freeze the frame's order while editing "
            "(cache it; sort only on save), or reset the editor by changing "
            "`key` when the input changes."
        )

# ========================================================== 6 Styler & limits
with TABS[5]:
    st.markdown(
        """
**Pandas `Styler` works through `st.dataframe`** for per-CELL conditional
color — the one thing `column_config` can't do. Know the walls (verified):
`Styler.background_gradient` needs **matplotlib** installed (raises
ImportError without it — it's not in this venv); any Styler render is capped
at **262,144 cells** (`StreamlitAPIException`, raise it via
`pd.set_option("styler.render.max_elements", n)`).
"""
    )
    c1, c2 = st.columns([3, 2], gap="large")
    df = movers()[["service", "p95_ms", "d1_ms", "pct_1y"]]
    with c1:
        def hot(v):  # matplotlib-free conditional style
            if v > 0.6: return "background-color: rgba(255,75,75,.25)"
            if v < 0.3: return "background-color: rgba(33,195,84,.25)"
            return ""
        st.dataframe(
            df.style
              .map(hot, subset=["pct_1y"])
              .map(lambda v: f"color: {'#d33' if v > 0 else '#2a2'}", subset=["d1_ms"])
              .format({"p95_ms": "{:.1f}", "d1_ms": "{:+.1f}", "pct_1y": "{:.0%}"}),
            hide_index=True,
        )
    with c2:
        st.code(
            '''st.dataframe(df.style
    .map(hot, subset=["pct_1y"])          # per-cell CSS, no matplotlib
    .format({"d1_ms": "{:+.1f}"}))        # Styler format wins over dtype
# .background_gradient(cmap=...)  needs matplotlib installed
# >262_144 cells raises -> pd.set_option("styler.render.max_elements", n)
# Styler colors also export in the CSV download? NO - display only.''',
            language="python",
        )
        st.markdown(
            "Precedence: prefer `column_config` for format/rename/width "
            "(editor-compatible, no cell cap); Styler ONLY for value-dependent "
            "cell color. `st.data_editor` accepts a Styler but edits+styles "
            "don't recompute together — style the RETURN of the editor if you "
            "need both."
        )

# ========================================================== 7 dtypes & Arrow
with TABS[6]:
    st.markdown(
        """
**Everything crosses to the browser as Arrow.** A mixed-type `object` column
(`[1, "x", 2.5]`) is NOT an error: Streamlit catches the ArrowInvalid and
**auto-converts the column to strings**, logging a warning server-side
(verified). Your numbers silently become text — sort goes lexicographic,
formats stop applying. Fix dtypes upstream, don't rely on the rescue.
"""
    )
    c1, c2 = st.columns(2, gap="large")
    with c1:
        bad = pd.DataFrame({"mixed": [1, "x", 2.5], "clean": [1.0, 2.0, 3.0]})
        st.dataframe(bad, hide_index=True)
        st.caption("`mixed` rendered — as strings. The only trace is a server-log "
                   "warning. `1` now sorts before `2.5` only by luck of string order.")
    with c2:
        st.code(
            '''# the usual sources of object columns:
df["p95_ms"] = pd.to_numeric(df["p95_ms"], errors="coerce")   # str -> float+NaN
df["date"]   = pd.to_datetime(df["date"])                     # str -> ts
df["bucket"] = df["bucket"].astype("category")     # + data_editor dropdown
# Int64/boolean nullable dtypes, Decimal, tz-aware ts: all fine via Arrow
# parquet round-trip (e.g. data/*.parquet) preserves dtypes -- CSV does not''',
            language="python",
        )
    st.divider()
    st.markdown("**When you've outgrown this:** JS-computed styling, grouping "
                "UI, tree data → [streamlit-aggrid]; pivot UI → [st-pivot]; "
                "millions of rows client-side → [perspective]. For everything "
                "else on this page, the native table is the right tool.")
