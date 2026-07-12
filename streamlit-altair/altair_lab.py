"""Altair pattern lab — Altair 6.2.x charts in Streamlit on synthetic latency telemetry.

Run:  python -m streamlit run altair_lab.py

One tab per pattern, each self-contained:
  1. Basics       — mark_line, the column:TYPE shorthand, width="stretch"
  2. Marks/encode — bar, scatter (color/size), heatmap (mark_rect), boxplot
  3. MaxRows      — the 5000-row MaxRowsError and the three fixes
  4. Selection    — on_select="rerun": click a point, fan out to another chart
  5. Compose      — layer (+), concat (| &), facet (small multiples)
  6. Theme/Plotly — Streamlit theme vs raw Vega, and when to switch to Plotly

Standalone: generates its own synthetic service-latency data (no files needed).
"""

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Altair lab", layout="wide")
st.title("Altair pattern lab")


# ---------------------------------------------------------------- data ----
@st.cache_data
def latency_long() -> pd.DataFrame:
    """Tidy/long telemetry: one row per (date, service, region), p95 latency."""
    rng = np.random.default_rng(0)
    dates = pd.date_range("2024-01-01", periods=90, freq="D")
    services = ["checkout", "search", "profile", "cart", "media"]
    regions = ["us-east-1", "eu-west-1", "ap-south-1"]
    rows = []
    base = {s: rng.uniform(80, 260) for s in services}
    for s in services:
        for rgn in regions:
            drift = rng.normal(0, 1.2, size=len(dates)).cumsum()
            for d, dr in zip(dates, drift):
                lat = max(15.0, base[s] + dr + rng.normal(0, 8))
                rows.append((d, s, rgn, round(lat, 1),
                             int(rng.integers(2_000, 900_000))))
    return pd.DataFrame(rows, columns=["date", "service", "region",
                                       "latency_ms", "requests"])


@st.cache_data
def latency_raw() -> pd.DataFrame:
    """A deliberately >5000-row frame to trigger MaxRowsError in tab 3."""
    df = latency_long()
    # explode each daily row into ~4 synthetic samples => well over 5000 rows
    reps = df.loc[df.index.repeat(4)].copy()
    reps["latency_ms"] += np.random.default_rng(1).normal(0, 6, len(reps)).round(1)
    return reps.reset_index(drop=True)


df = latency_long()

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["1 · Basics", "2 · Marks & encoding", "3 · MaxRows 5000", "4 · Selection → Python",
     "5 · Layer / concat / facet", "6 · Theme & Plotly"]
)


# --------------------------------------------------------- 1 · basics ----
with tab1:
    st.subheader("mark_line + the column:TYPE shorthand")
    st.caption(
        "Build a spec from a LONG DataFrame: pick a mark, encode COLUMNS onto x/y/color. "
        "`date:T` = temporal (time axis), `latency_ms:Q` = quantitative, `service:N` = "
        "nominal category. `width='stretch'` fills the column (not the deprecated "
        "`use_container_width`)."
    )
    daily = df.groupby(["date", "service"], as_index=False)["latency_ms"].median()
    chart = (
        alt.Chart(daily)
        .mark_line(point=False)
        .encode(
            x="date:T",
            y="latency_ms:Q",
            color="service:N",
            tooltip=["date:T", "service:N", "latency_ms:Q"],
        )
        .properties(height=340, title="p95 latency — daily median by service")
    )
    st.altair_chart(chart, width="stretch")
    st.code(
        'alt.Chart(daily).mark_line().encode(\n'
        '    x="date:T", y="latency_ms:Q", color="service:N")\n'
        'st.altair_chart(chart, width="stretch")', language="python")


# ------------------------------------------------- 2 · marks & encoding ----
with tab2:
    st.subheader("One data set, four marks — pick the mark, encode the columns")
    st.caption(
        "Bars want ONE discrete axis (`service:N`). Scatter maps two `:Q` plus color/size. "
        "Heatmap = `mark_rect` with two discrete axes + a `:Q` color. Boxplot summarises a "
        "distribution per category. Note `percentile`-style labels would be `:O` (ordered)."
    )
    recent = df[df["date"] >= df["date"].max() - pd.Timedelta(days=14)]
    by_service = recent.groupby("service", as_index=False).agg(
        latency_ms=("latency_ms", "median"), requests=("requests", "sum"))

    c1, c2 = st.columns(2)
    with c1:
        bar = (
            alt.Chart(by_service).mark_bar()
            .encode(x="service:N", y="latency_ms:Q", color="service:N",
                    tooltip=["service:N", "latency_ms:Q"])
            .properties(height=280, title="Median latency by service (bar, :N x-axis)")
        )
        st.altair_chart(bar, width="stretch")

        heat = (
            alt.Chart(recent).mark_rect()
            .encode(x="region:N", y="service:N",
                    color=alt.Color("median(latency_ms):Q", title="median ms"),
                    tooltip=["service:N", "region:N", "median(latency_ms):Q"])
            .properties(height=240, title="Heatmap (mark_rect): service × region")
        )
        st.altair_chart(heat, width="stretch")
    with c2:
        scatter = (
            alt.Chart(by_service).mark_circle(size=160)
            .encode(x="requests:Q", y="latency_ms:Q", color="service:N",
                    size="requests:Q", tooltip=["service:N", "latency_ms:Q", "requests:Q"])
            .properties(height=280, title="Latency vs requests (scatter, two :Q)")
        )
        st.altair_chart(scatter, width="stretch")

        box = (
            alt.Chart(recent).mark_boxplot()
            .encode(x="service:N", y="latency_ms:Q", color="service:N")
            .properties(height=240, title="Latency distribution by service (boxplot)")
        )
        st.altair_chart(box, width="stretch")


# -------------------------------------------------------- 3 · maxrows ----
with tab3:
    st.subheader("MaxRowsError — Altair refuses >5000 rows by default")
    raw = latency_raw()
    st.caption(
        f"The raw frame has {len(raw):,} rows. Altair embeds the data in the page and caps "
        "it at 5000 — building the spec raises `MaxRowsError`. Below: the error caught live, "
        "then the three fixes (aggregate ▸ sample ▸ lift the cap)."
    )

    big = alt.Chart(raw).mark_point().encode(x="date:T", y="latency_ms:Q", color="service:N")
    try:
        big.to_dict()   # this is what st.altair_chart triggers internally
        st.warning("No MaxRowsError raised (cap already lifted this session).")
    except Exception as e:
        st.error(f"{type(e).__name__}: {str(e).splitlines()[0]}")

    st.markdown("**Fix 1 (best) — aggregate before plotting:**")
    agg = raw.groupby(["date", "service"], as_index=False)["latency_ms"].median()
    st.altair_chart(
        alt.Chart(agg).mark_line().encode(x="date:T", y="latency_ms:Q", color="service:N")
        .properties(height=260, title=f"Daily median — {len(agg):,} rows, well under 5000"),
        width="stretch")

    st.markdown("**Fix 2 — sample when you truly want raw points:**")
    sample = raw.sample(4000, random_state=0)
    st.altair_chart(
        alt.Chart(sample).mark_circle(size=12, opacity=0.3)
        .encode(x="requests:Q", y="latency_ms:Q", color="service:N")
        .properties(height=260, title=f"{len(sample):,}-row sample"),
        width="stretch")

    st.markdown("**Fix 3 (last resort) — lift the cap (heavy page, all rows embedded):**")
    st.code('alt.data_transformers.disable_max_rows()', language="python")


# ------------------------------------------------- 4 · selection → python ----
with tab4:
    st.subheader("Click a point → Python reruns → fan out to another chart")
    st.caption(
        "`on_select='rerun'` + a named `selection_point` param + a stable `key`. The click "
        "lands in the return value AND `st.session_state[key]`. This round-trip is the piece "
        "Plotly does clumsily in Streamlit. Click a bubble to load that service's history."
    )
    by_service = df.groupby("service", as_index=False).agg(
        latency_ms=("latency_ms", "median"), requests=("requests", "sum"))

    pick = alt.selection_point(fields=["service"], name="pick")
    picker = (
        alt.Chart(by_service).mark_circle(size=200)
        .encode(x="requests:Q", y="latency_ms:Q", color="service:N",
                opacity=alt.condition(pick, alt.value(1.0), alt.value(0.25)),
                tooltip=["service:N", "latency_ms:Q", "requests:Q"])
        .add_params(pick)
        .properties(height=300, title="Click a service bubble")
    )
    event = st.altair_chart(picker, on_select="rerun", key="picker", width="stretch")

    # selection is a list of {"service": ...} dicts; empty until a click
    sel = (event.get("selection") or {}) if hasattr(event, "get") else {}
    chosen = [d.get("service") for d in sel.get("pick", []) if isinstance(d, dict)]
    if chosen:
        name = chosen[0]
        st.markdown(f"**{name}** — daily median latency (driven by the click above)")
        hist = (df[df["service"] == name]
                .groupby("date", as_index=False)["latency_ms"].median())
        st.altair_chart(
            alt.Chart(hist).mark_area(opacity=0.5, line=True)
            .encode(x="date:T", y="latency_ms:Q").properties(height=240),
            width="stretch")
    else:
        st.info("No selection yet — click a bubble to fan out to its history chart.")


# ------------------------------------------------ 5 · layer/concat/facet ----
with tab5:
    st.subheader("Composition operators: + layer · | & concat · .facet() small multiples")
    st.caption(
        "`a + b` overlays (shared axes). `a | b` puts charts side by side, `a & b` stacks "
        "them. `.facet()` draws one panel per category with NO Python loop."
    )
    one = df[df["service"] == "checkout"].groupby("date", as_index=False).agg(
        latency_ms=("latency_ms", "median"))
    one["roll7"] = one["latency_ms"].rolling(7, min_periods=1).mean()

    raw_line = alt.Chart(one).mark_line(opacity=0.4).encode(x="date:T", y="latency_ms:Q")
    smooth = alt.Chart(one).mark_line(color="crimson").encode(x="date:T", y="roll7:Q")
    st.markdown("**Layer (`+`)** — raw + 7-day rolling mean on shared axes:")
    st.altair_chart((raw_line + smooth).properties(height=260, title="checkout latency"),
                    width="stretch")

    st.markdown("**Facet** — one panel per service, `columns=3`:")
    daily = df.groupby(["date", "service"], as_index=False)["latency_ms"].median()
    facet = (
        alt.Chart(daily).mark_line()
        .encode(x="date:T", y="latency_ms:Q", color="service:N")
        .properties(height=150, width=220)
        .facet(facet="service:N", columns=3)
    )
    st.altair_chart(facet)


# --------------------------------------------------- 6 · theme & plotly ----
with tab6:
    st.subheader("Streamlit theme vs raw Vega — and when to switch to Plotly")
    st.caption(
        "Streamlit auto-themes charts (`theme='streamlit'`, the default). Pass `theme=None` "
        "for raw Altair/Vega colors. Toggle to compare."
    )
    raw_theme = st.toggle("Use raw Vega theme (theme=None)", value=False, key="raw_theme")
    daily = df.groupby(["date", "service"], as_index=False)["latency_ms"].median()
    ch = (alt.Chart(daily).mark_line()
          .encode(x="date:T", y="latency_ms:Q", color="service:N")
          .properties(height=320))
    st.altair_chart(ch, width="stretch", theme=None if raw_theme else "streamlit")

    st.markdown(
        "**Reach for `st.plotly_chart` ONLY for:** 3D surfaces/scatter · WebGL scatter of "
        ">100k points (Vega-Lite marks are SVG and bog down) · chart types Vega-Lite lacks "
        "(sankey, treemap, gauge, radar). Maps → `st.map` / `st.pydeck_chart`. Everything "
        "else — line, bar, scatter, area, heatmap, box, facets, click-selection — stays Altair."
    )
