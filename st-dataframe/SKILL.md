---
name: st-dataframe
description: Streamlit's native table — st.dataframe, column_config, st.data_editor. Use when displaying or formatting a DataFrame, adding sparkline/progress/link columns, making a table clickable (selection driving other widgets), building an editable grid, styling cells, or debugging Arrow serialization / dtype / Styler errors.
---

# st.dataframe & st.data_editor (Streamlit 1.58.x) — the free native table

Runnable proof of every claim: `st_dataframe_lab.py` in this skill folder
(`python -m streamlit run ~/.roo/skills/st-dataframe/st_dataframe_lab.py`).
Verified on Streamlit **1.58**, API-checked on **1.55**. On 1.55 TWO
things in this skill don't exist yet: `selection_default=` and the
`single-row-required` selection mode (both 1.56+) — use plain
`single-row` and treat an empty selection as row 0 in code.

**Grid matrix (shared with the other grid skills):** display + formatting +
row-selection + editing → **this skill, native table** · JS-computed styling
or grouping UI → [streamlit-aggrid] · pivot/tree wired to Python →
[st-pivot] · huge-data client-side exploration → [perspective].
Most "I need AG Grid" asks are actually covered here for free.

## What you get without writing anything

Hover toolbar: 🔍 search, ⬇ CSV download, ⛶ fullscreen. Client-side column
sort/resize/reorder, cell-range drag-select + Ctrl/Cmd-C (pastes into Excel
as TSV). Rows are virtualized — 100k-row frames scroll fine. (`st.table` is
the opposite: static HTML, every cell rendered — keep it small; it does have
`border="horizontal"`/`hide_header` for report-style tables.)

## Display knobs

```python
st.dataframe(df, hide_index=True,            # kill the 0..n index
             column_order=["a", "b"],        # display-only subset+order
             row_height=32, height=400,      # denser rows / fixed px scroll
             placeholder="–")                # NaN display text
```

## column_config — formatting that keeps dtypes

NEVER format numbers by converting to strings (kills sorting). Presentation
is per-column config; the frame keeps raw values:

```python
column_config={
    "service": st.column_config.TextColumn("Service", pinned="left"),
    "p95":    st.column_config.NumberColumn("p95", format="%.0f ms"),
    "d1":     st.column_config.NumberColumn("Δ1d", format="%+.1f"),
    "pctl":   st.column_config.ProgressColumn("1y %ile", min_value=0,
                                              max_value=1, format="percent"),
    "req":    st.column_config.NumberColumn(format="compact"),   # 8.4K, 3.1M
    "noise":  None,                                              # hide column
    "name":   "Nice header",                       # bare string = rename only
    "last":   st.column_config.DatetimeColumn(format="HH:mm",
                                              timezone="America/New_York"),
    "url":    st.column_config.LinkColumn(display_text="open"),  # or regex capture
}
```

- `format=` takes printf (`"%.0f ms"`, `"%+d"`) or a predefined string:
  `plain localized dollar euro yen percent compact scientific engineering
  accounting bytes`. **`percent` multiplies by 100** — feed 0.22 for 22%.
- Column types: Text/Number/Checkbox/Selectbox/Multiselect/Date/Time/
  Datetime/List/Json/Link/Image/Progress + chart columns (below).
- The same dict powers `st.data_editor`, where Number/Text/Date configs
  become the cell EDITORS (min/max/step, `validate=` regex, `max_chars`).

## Sparkline columns — the movers-table pattern

A cell holding a LIST of numbers renders as a mini-chart:

```python
hist = daily.groupby("name").agg(hist=("vol", list)).reset_index()  # list per cell
st.dataframe(hist, column_config={
    "hist": st.column_config.LineChartColumn("30d", y_min=40, y_max=60)})
```

`LineChartColumn` / `AreaChartColumn` / `BarChartColumn`. Fix `y_min/y_max`
for cross-row comparability (else each cell autoscales). Display-only — no
tooltips; for detail use selection → real chart.

## Selection → Python (the free master-detail)

```python
ev = st.dataframe(df, key="g", on_select="rerun",
                  selection_mode="single-row-required",     # radio-like; 1.56+
                  selection_default={"selection": {"rows": [0]}})   # 1.56+
# On 1.55 use selection_mode="single-row" and default to row 0 yourself:
#   rows = ev.selection.rows or [0]
picked = df.iloc[ev.selection.rows]        # POSITIONAL indices -> iloc, never .loc
```

- Event shape (verified): `{"selection": {"rows": [...], "columns": [...],
  "cells": [...]}}` — also mirrored to `st.session_state.g`.
- Modes (single or list): `single-row`, `single-row-required` (1.56+; always
  exactly one — pair with `selection_default` and there's no empty state to
  handle), `multi-row`, `single/multi-column`, `single/multi-cell`.
- Row indices are positions in the frame AS PASSED; UI sorting doesn't
  renumber them.
- Every selection click is a full rerun — cache the table's data
  ([streamlit-core]).

## st.data_editor — editable grid

```python
edited = st.data_editor(df, key="ed",
    num_rows="dynamic",              # fixed | dynamic | add | delete
    disabled=["name"],               # read-only columns (True = all)
    column_config={
        "level": st.column_config.NumberColumn(min_value=0, step=5, required=True),
        "dir":   st.column_config.SelectboxColumn(options=["wider", "tighter"]),
        "tags":  st.column_config.MultiselectColumn(options=[...],
                                                    accept_new_options=True),
    })
```

- **The return value is the edited frame; the input is never mutated.**
  Compute from `edited`, not from `df`.
- The raw diff (verified shape) sits in `st.session_state.ed`:
  `{"edited_rows": {row_pos: {col: val}}, "added_rows": [...],
  "deleted_rows": [row_pos, ...]}`.
- Categorical dtype → dropdown editor automatically (verified).
- **Positional-edit footgun:** `edited_rows` is keyed by row POSITION. If
  the input frame re-sorts/refilters between runs while the same `key`
  holds edits, pending edits re-apply to whatever row now sits at that
  position. Freeze row order while editing (cache; sort only on save), or
  change the `key` when the input changes to reset the editor.

## Styler — cell color only, know the walls

`st.dataframe(df.style...)` works for value-dependent per-cell CSS — the one
thing `column_config` can't do:

```python
st.dataframe(df.style.map(lambda v: "color: #d33" if v > 0 else "color: #2a2",
                          subset=["d1"])
                     .format({"d1": "{:+.1f}"}))
```

Verified limits: `.background_gradient()` requires **matplotlib** (import
error otherwise — verify it is installed in your environment; else use a manual
`.map` with rgba backgrounds); Styler rendering hard-caps at **262,144
cells** (`StreamlitAPIException`; raise via
`pd.set_option("styler.render.max_elements", n)` — better: slice first).
Styler colors are display-only (not in the CSV download). Prefer
`column_config` for everything except conditional color.

## Dtypes & Arrow — the silent string conversion

Data crosses to the browser as Arrow. A mixed-type object column
(`[1, "x", 2.5]`) does NOT raise — Streamlit catches the `ArrowInvalid` and
**auto-converts the column to strings**, with only a server-log warning
(verified). Symptoms: lexicographic sort, number formats ignored. Fix
upstream:

```python
df["p95_ms"] = pd.to_numeric(df["p95_ms"], errors="coerce")
df["date"]   = pd.to_datetime(df["date"])
df["bucket"] = df["bucket"].astype("category")    # + free editor dropdown
```

Nullable dtypes (Int64/boolean), tz-aware timestamps, Decimal: all fine.
Parquet round-trips preserve dtypes; CSV does not.

## Debug checklist

1. Numbers sort wrong / format ignored → object dtype; check the server log
   for "Serialization of dataframe to Arrow table was unsuccessful".
2. `ImportError: matplotlib` → `.background_gradient` on a venv without it;
   use `.map` with explicit colors.
3. `StreamlitAPIException: ... maximum number of cells` → Styler cell cap;
   slice the frame or raise `styler.render.max_elements`.
4. Selected rows map to wrong data → used `.loc` with positional indices;
   it's `df.iloc[ev.selection.rows]`.
5. Edits vanish or land on wrong rows → input frame changed order/shape
   under a live `key`; freeze order or rotate the key.
6. Edits "don't save" → code reads the input `df` instead of the editor's
   return value.
