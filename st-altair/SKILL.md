---
name: st-altair
description: Charts in Streamlit with Altair (Vega-Lite) — the default choice over Plotly. Use when plotting ANY data in Streamlit (line/bar/scatter/area/heatmap/box), theming a chart, making a chart clickable (selection driving other widgets), layering/faceting, or debugging MaxRowsError, blank charts, wrong axis types, or "chart doesn't fill the width".
---

# Altair in Streamlit (Altair 6.2.x / Streamlit 1.58.x)

**Pick a chart tool (do this first):**
- **Altair** — DEFAULT for everything below. Declarative, themed by Streamlit
  automatically, selections come back to Python (`on_select`). Start here.
- **`st.line_chart` / `st.bar_chart` / `st.area_chart` / `st.scatter_chart`** —
  a one-liner for a quick plot of a tidy DataFrame, no styling. Under the hood
  it IS Altair. Use when you don't need custom encodings/colors/interaction.
- **Plotly** (`st.plotly_chart`) — ONLY the escape hatch: 3D, WebGL for
  >100k-point scatter, or chart types Vega-Lite lacks (sankey, treemap, gauge).
  Heavier bundle, selection round-trip is clunkier. Don't reach for it by default.

Runnable proof of every claim: `altair_lab.py` in this skill folder
(`python -m streamlit run altair_lab.py`; it generates its own synthetic
latency data, no files needed). Verified on Altair **6.2.2**, Streamlit **1.58**.

## The one mental model

An Altair chart is a **spec built from a DataFrame**: pick a `mark_*`, then
`encode()` DataFrame COLUMNS onto visual channels (x, y, color, size, tooltip).
Streamlit renders it and applies its theme. Because the whole script reruns on
every interaction (see [st-core]), you **rebuild the chart from data each
run** — there is no figure to mutate, no `plt.show()`, no imperative state.

```python
import altair as alt
import streamlit as st

chart = (
    alt.Chart(df)                          # df is a tidy/long DataFrame
    .mark_line(point=True)                 # the mark
    .encode(
        x="date:T",                        # column:TYPE  (see cheat sheet)
        y="latency_ms:Q",
        color="service:N",
        tooltip=["date:T", "service:N", "latency_ms:Q"],
    )
    .properties(height=320, title="p95 latency")
)
st.altair_chart(chart, width="stretch")    # width="stretch" fills the column
```

## Encoding types — get this RIGHT or the chart is wrong, not broken

Every encoded column needs a one-letter type. Wrong type = silently wrong chart
(dates plotted as categories, numbers sorted as text), NOT an error.

| Suffix | Type | Use for | Axis behaviour |
|---|---|---|---|
| `:Q` | Quantitative | numbers you measure (latency_ms, requests) | continuous number axis |
| `:T` | Temporal | dates/timestamps | time axis, sorted chronologically |
| `:N` | Nominal | unordered categories (service, region) | discrete, one color/tick each |
| `:O` | Ordinal | ordered categories (percentile 50<75<90) | discrete but ordered |

Rules for a mid-size model to follow literally:
- A **date column → `:T`**. Never `:N` (you'll get one tick per distinct day,
  unsorted). Make sure it's real datetime: `df["date"] = pd.to_datetime(df["date"])`.
- A **number you plot on an axis → `:Q`**. A number that's really a category
  (percentile 50/75/90 as labels) → `:O`.
- A **text label → `:N`** (or `:O` if it has a natural order).
- Prefer the shorthand `"col:Q"`. The long form is `alt.X("col", type="quantitative")`
  — use it only when you also need `.title()`, `.scale()`, `.sort()`, `.axis()`.

## Gotcha 1 — MaxRowsError at 5000 rows (the #1 Altair error)

Altair refuses to embed **>5000 rows** by default and raises
`MaxRowsError` when Streamlit renders it. Empirically confirmed on 6.2.2. Three
fixes, in order of preference:

```python
# BEST: aggregate/downsample BEFORE plotting — a chart of 100k points is
# unreadable anyway. Plot a daily median, not every raw sample.
daily = df.groupby(["date", "service"], as_index=False)["latency_ms"].median()

# OR sample if you truly want raw points
plot_df = df.sample(4000, random_state=0) if len(df) > 5000 else df

# LAST RESORT: lift the cap (embeds all rows in the page → slow, big HTML)
alt.data_transformers.disable_max_rows()
```

Do NOT reach for `disable_max_rows()` first — it makes the page heavy. Aggregate.

## Gotcha 2 — width, theme, and the tidy-data shape

- **Fill the container:** `st.altair_chart(chart, width="stretch")`. The old
  `use_container_width=True` is deprecated — don't emit it. Don't ALSO set
  `.properties(width=...)` to a fixed number if you want stretch; they fight.
- **Theme:** Streamlit auto-applies its theme (`theme="streamlit"`, the
  default). Pass `theme=None` to get raw Altair/Vega colors instead.
- **Feed LONG (tidy) data:** one row per observation, a column to split
  `color=`/`facet=` on. A wide frame (one column per service) does NOT encode
  directly — `df.melt(...)` to long first. This is the most common "my chart is
  blank / only shows one line" cause.
- **Reset the index:** encode real columns. `df.reset_index()` if the thing you
  want on x (e.g. date) is sitting in the index.

## Gotcha 3 — mark vs encode mismatches

- `mark_bar()` with `x:Q,y:Q` draws nothing useful — bars want one discrete axis
  (`x="service:N"`). 
- `mark_line()` across categories connects them in row order — sort with
  `x=alt.X("date:T", sort="ascending")` or ensure the frame is sorted.
- Empty chart? Check: real datetime for `:T`, no all-NaN column, long shape.

## Pattern — selection driving other widgets (Altair's killer feature)

Clicks come back to Python — the Plotly round-trip Streamlit couldn't do well.
`on_select="rerun"` + a named param via `.add_params()` + a stable `key`.

```python
brush = alt.selection_point(fields=["service"], name="pick")   # click a mark
chart = (
    alt.Chart(df).mark_circle(size=90)
    .encode(x="requests:Q", y="latency_ms:Q", color="service:N",
            opacity=alt.condition(brush, alt.value(1), alt.value(0.25)))
    .add_params(brush)
)
event = st.altair_chart(chart, on_select="rerun", key="scatter", width="stretch")

# selection lands in the return value AND st.session_state["scatter"]
picked = event["selection"].get("pick", [])        # list of {"service": ...} dicts
if picked:
    name = picked[0]["service"]
    st.line_chart(history_for(name))               # fan out to any other widget
```

- `selection_point()` = click (add `fields=[...]` to select by value; omit for
  single marks). `selection_interval()` = drag a box (great for brushing x-range).
- Empty selection = empty list/dict — always guard before indexing.
- `selection_mode=` on `st.altair_chart` limits to `"point"`/`"interval"`.

## Pattern — layer, concat, facet (composition operators)

```python
line = alt.Chart(df).mark_line().encode(x="date:T", y="latency_ms:Q")
band = alt.Chart(df).mark_area(opacity=0.2).encode(x="date:T", y="lo:Q", y2="hi:Q")
combo = band + line                                  # LAYER (overlay, shared axes)

left | right                                         # HCONCAT side by side
top  & bottom                                        # VCONCAT stacked

# small multiples — one panel per category, no Python loop
alt.Chart(df).mark_line().encode(x="date:T", y="latency_ms:Q").facet(
    facet="service:N", columns=3)
```

Layer only charts with compatible axes. For independent charts use concat.

## Common marks (quick reference)

`mark_line` (trends over `:T`) · `mark_point`/`mark_circle` (scatter) ·
`mark_bar` (one `:N`/`:O` axis) · `mark_area` (stacked/filled) ·
`mark_rect` (heatmap: `x:N|O`, `y:N|O`, `color:Q`) · `mark_boxplot`
(distribution by category) · `mark_tick` (1-D strip). Add `tooltip=[...]` to
any of them for free hover.

## When to use Plotly instead (be honest)

Reach for `st.plotly_chart` only for: **3D** surfaces/scatter, **WebGL**
scatter of >100k points (`mark_*` in Vega-Lite is SVG — it bogs down), or chart
types Vega-Lite doesn't have (**sankey, treemap, gauge, radar**). For maps, use
`st.map`/`st.pydeck_chart`. Everything else — line, bar, scatter, area,
heatmap, box, faceted small-multiples, interactive selection — is Altair, and
Altair themes and round-trips selections better inside Streamlit.
