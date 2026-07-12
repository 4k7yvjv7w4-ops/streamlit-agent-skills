"""AgGrid pattern lab — streamlit-aggrid (1.2.x) techniques on synthetic latency telemetry.

Run:  python -m streamlit run aggrid_lab.py

One tab per pattern, each self-contained:
  1. Basics        — GridOptionsBuilder defaults, formatters, pinned columns
  2. Heatmap       — JsCode cellStyle conditional coloring (latency movers)
  3. Selection     — row click drives a chart below the grid (master/detail)
  4. Grouping      — rowGroup + aggFunc, dynamic group-by, drag-to-group [enterprise]
  5. Editable      — editable cells, dropdown editor, reading edits back
  6. Multi-detail  — one selection fans out to metrics + grids + chart
  7. Formatting    — every styling axis (cell/column/row/condition) + compact mode
  8. Excel-ish     — range selection, Σ/avg status bar, range copy [enterprise]
  9. Perspective   — same data in FINOS perspective-viewer (free pivot engine)
 10. st-pivot      — official streamlit-pivot component (config/clicks reach Python)
 11. Weighted avg  — weighted-average aggFunc, the JsCode that returns 0 [enterprise]

Deliberately standalone: reads the bundled synthetic parquets in data/.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode

AGG = Path(__file__).resolve().parent / "data"          # bundled synthetic data


def build_opts(gb: GridOptionsBuilder) -> dict:
    """gb.build() minus the autoSizeStrategy that from_dataframe() injects.

    st-aggrid 1.2.x's from_dataframe() adds autoSizeStrategy {type: fitGridWidth},
    which OVERRIDES explicit per-column widths — and collapses every column to
    min-width (36px) if it fires while the component iframe still measures 0px.
    Pop it whenever you size columns by hand.
    """
    go = gb.build()
    go.pop("autoSizeStrategy", None)
    return go

st.set_page_config(page_title="AgGrid lab", layout="wide")
st.title("AgGrid pattern lab")


def lic(*specs: tuple[str, str]) -> None:
    """License chips at the top of a tab: kind = free | ent | alt."""
    color = {"free": "green", "ent": "orange", "alt": "blue"}
    st.markdown(" ".join(f":{color[k]}-badge[{label}]" for label, k in specs))


def pview(df: pd.DataFrame, config: dict, height: int = 420) -> None:
    """One-way <perspective-viewer> embed (CDN); config = viewer.restore() payload."""
    import json

    import streamlit.components.v1 as components

    components.html(
        f"""
        <link rel="stylesheet" crossorigin
              href="https://cdn.jsdelivr.net/npm/@finos/perspective-viewer@3/dist/css/themes.css"/>
        <style> perspective-viewer {{ height: {height}px; width: 100%; }} </style>
        <perspective-viewer theme="Pro Light"></perspective-viewer>
        <script type="module">
            import perspective from "https://cdn.jsdelivr.net/npm/@finos/perspective@3/dist/cdn/perspective.js";
            import "https://cdn.jsdelivr.net/npm/@finos/perspective-viewer@3/dist/cdn/perspective-viewer.js";
            import "https://cdn.jsdelivr.net/npm/@finos/perspective-viewer-datagrid@3/dist/cdn/perspective-viewer-datagrid.js";
            import "https://cdn.jsdelivr.net/npm/@finos/perspective-viewer-d3fc@3/dist/cdn/perspective-viewer-d3fc.js";
            const table = await (await perspective.worker()).table({json.dumps(df.to_dict("records"))});
            const viewer = document.querySelector("perspective-viewer");
            await viewer.load(table);
            const cfg = {json.dumps(config)};
            await viewer.restore(cfg);
            // per-column styles: v2 nested them in plugin_config.columns, v3 moved
            // them to a top-level columns_config — send both, extra keys are ignored
            if (cfg.plugin_config && cfg.plugin_config.columns) {{
                await viewer.restore({{plugin: cfg.plugin,
                                       plugin_config: cfg.plugin_config,
                                       columns_config: cfg.plugin_config.columns}});
            }}
        </script>
        """,
        height=height + 20,
    )


with st.expander("🔑 License map — what needs AG Grid Enterprise, and the free routes"):
    st.markdown(
        """
| Feature | Tab | License | Free route to the same result |
|---|---|---|---|
| Sort · filter · floating filter · pagination · pinning | 1 | ✅ Community | — |
| All styling: JsCode `cellStyle`, class rules, row styles, `custom_css` | 2 · 7 | ✅ Community | — |
| Selection events back into Python (master/detail, fan-out) | 3 · 6 | ✅ Community | — |
| Cell editing + dropdown editors | 5 | ✅ Community | — |
| Row grouping / aggregation / pivot mode | 4 · 11 | 🔒 Enterprise | pandas `groupby` → flat grid (expander in tab 4) · Perspective (tab 9) |
| Weighted-average aggFunc (weight-carrying value) | 11 | 🔒 Enterprise | pandas `np.average(weights=…)` → flat grid (expander in tab 11) |
| Drag-to-group panel | 4 | 🔒 Enterprise | `st.multiselect` rebuilding gridOptions (tab 4) |
| Range selection + live Σ/avg status bar | 8 | 🔒 Enterprise | `st.dataframe` + Python metrics (expander in tab 8) — close, not identical |
| Range copy to clipboard (TSV → Excel) | 8 | 🔒 Enterprise | `st.dataframe` native drag-select + Ctrl/Cmd+C (free, built into Streamlit) |
| Set filter · context menu · Excel export · master-detail rows | not used | 🔒 Enterprise | default filters are free · two linked grids (tab 6) · `st.download_button` |
| — Pivot alternatives compared — | 9 · 10 | 🆓 both | Perspective (tab 9): fastest, column pivots, one-way. **streamlit-pivot (tab 10): official, drag-drop, Excel export, drill-down, events back to Python** |

`enable_enterprise_modules=True` loads the enterprise build in **trial mode**
(console notice) — fine locally, license required to ship. With it `False`,
🔒 features simply don't activate; everything else in this lab still works.
"""
    )


# ---------------------------------------------------------------- data ----
@st.cache_data
def load_latency_movers() -> pd.DataFrame:
    """p95 latency by service: latest level + 1w change, one row per service."""
    df = pd.read_parquet(AGG / "latency.parquet")
    df = df[df["percentile"] == 95.0].copy()
    # displayable level: real-user (RUM) median where present, else synthetic probe
    df["latency_ms"] = df["rum_ms_median"].fillna(df["probe_ms_median"])
    df = df.dropna(subset=["latency_ms"])
    df["date"] = pd.to_datetime(df["date"])
    last = df["date"].max()
    cur = (
        df[df["date"] > last - pd.Timedelta(days=5)]
        .groupby(["service", "team"])
        .agg(latency_ms=("latency_ms", "median"), n=("n", "sum"), requests=("requests_sum", "sum"))
        .reset_index()
    )
    prev = (
        df[(df["date"] <= last - pd.Timedelta(days=5)) & (df["date"] > last - pd.Timedelta(days=12))]
        .groupby("service")["latency_ms"]
        .median()
        .rename("prev_ms")
    )
    out = cur.merge(prev, on="service", how="inner")
    out["chg_1w_ms"] = out["latency_ms"] - out["prev_ms"]
    return out[out["n"] >= 3].sort_values("chg_1w_ms", ascending=False)


@st.cache_data
def load_latency_history() -> pd.DataFrame:
    df = pd.read_parquet(AGG / "latency.parquet")
    df = df[df["percentile"] == 95.0].copy()
    df["latency_ms"] = df["rum_ms_median"].fillna(df["probe_ms_median"])
    df["date"] = pd.to_datetime(df["date"])
    return df.dropna(subset=["latency_ms"])[["date", "service", "latency_ms", "n"]]


@st.cache_data
def load_latency_full() -> pd.DataFrame:
    """All percentiles, with request volume — feeds the multi-detail tab."""
    df = pd.read_parquet(AGG / "latency.parquet")
    df["latency_ms"] = df["rum_ms_median"].fillna(df["probe_ms_median"])
    df["date"] = pd.to_datetime(df["date"])
    return df.dropna(subset=["latency_ms"])[
        ["date", "service", "percentile", "latency_ms", "n", "requests_sum"]
    ]


@st.cache_data
def load_region_matrix() -> pd.DataFrame:
    """Wide region × percentile matrix of last-week median latency — Excel-shaped."""
    r = load_regions()
    recent = r[r["date"] > r["date"].max() - pd.Timedelta(days=5)]
    piv = (
        recent.groupby(["region", "percentile"])["lat_ms"].median().unstack()
        .reindex(columns=[50.0, 75.0, 90.0, 95.0, 99.0])
    )
    piv.columns = [f"p{c:g}" for c in piv.columns]
    piv = piv.dropna(thresh=4).round(4).reset_index()
    piv["n_checks"] = piv["region"].map(recent.groupby("region")["n"].sum())
    return piv.sort_values("n_checks", ascending=False).reset_index(drop=True)


@st.cache_data
def load_regions() -> pd.DataFrame:
    df = pd.read_parquet(AGG / "regions.parquet")
    df = df[df["check_type"] == "http"].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["lat_ms"] = df["level_median"] * 1000
    return df.dropna(subset=["lat_ms"])


tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11, tab12 = st.tabs(
    ["1 · Basics", "2 · Heatmap (JsCode)", "3 · Selection → chart", "4 · Grouping 🔒",
     "5 · Editable", "6 · Multi-detail", "7 · Formatting", "8 · Excel-ish 🔒",
     "9 · Perspective 🆓", "10 · st-pivot 🆓", "11 · Weighted avg 🔒",
     "12 · Pivot mode (split-by) 🔒"]
)


# --------------------------------------------------------- 1 · basics ----
with tab1:
    st.subheader("GridOptionsBuilder defaults, number formatting, pinning")
    lic(("✅ 100% Community — free", "free"))
    st.caption(
        "Pattern: `from_dataframe` → `configure_default_column` for grid-wide behavior "
        "→ per-column overrides. `valueFormatter` is a JS expression string (no JsCode needed)."
    )
    df = load_latency_movers().head(200)

    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(sortable=True, filter=True, resizable=True, floatingFilter=True)
    gb.configure_column("service", header_name="Service", pinned="left", width=260)
    gb.configure_column("team", header_name="Team", width=110)
    # simple JS expression formatters — ms with 1 decimal, requests in millions
    gb.configure_column("latency_ms", header_name="p95 (ms)", valueFormatter="x.toFixed(1)", width=100)
    gb.configure_column("prev_ms", header_name="prev wk (ms)", valueFormatter="x.toFixed(1)", width=110)
    gb.configure_column("chg_1w_ms", header_name="Δ1w (ms)", valueFormatter="x.toFixed(1)", width=100)
    gb.configure_column(
        "requests", header_name="Requests (M)", valueFormatter="(x / 1e6).toFixed(0)", width=120
    )
    gb.configure_column("n", header_name="samples", width=90)
    gb.configure_grid_options(pagination=True, paginationPageSize=25)

    # build_opts, not gb.build() — see the autoSizeStrategy gotcha at the top
    AgGrid(df, gridOptions=build_opts(gb), theme="balham", height=520, key="basics")

    with st.expander("🟣 Closest with Perspective"):
        st.caption(
            "Maps: sorting (config panel), filtering (Where section), numeric precision "
            "(`plugin_config.columns.fixed`). Doesn't map: column pinning, pagination, "
            "floating filter row — Perspective scrolls and filters instead."
        )
        pview(
            df[["service", "team", "latency_ms", "chg_1w_ms", "n"]],
            {"plugin": "Datagrid",
             "columns": ["service", "team", "latency_ms", "chg_1w_ms", "n"],
             "sort": [["chg_1w_ms", "desc"]],
             "plugin_config": {"columns": {"latency_ms": {"fixed": 1},
                                           "chg_1w_ms": {"fixed": 1}}}},
        )

    with st.expander("🟩 Closest with st-pivot"):
        st.caption(
            "Maps: sorting (initial `row_sort` + header menus), filtering (header menu "
            "top-N / value filters), number formats. Doesn't map: pinning, pagination, "
            "floating filter row."
        )
        try:
            from streamlit_pivot import st_pivot_table

            # "pure flat table" mode: ALL string columns as row dims +
            # repeat_row_labels=True (no label merging) = dataframe-like display.
            # caveats: dims always sit left of values; rows sharing all dim
            # values aggregate into one; null dims are DROPPED unless
            # null_handling="separate"; original row order isn't preserved.
            st_pivot_table(
                df[["service", "team", "latency_ms", "chg_1w_ms", "n"]]
                .reset_index(drop=True),
                key="sp1", rows=["service", "team"],
                values=["latency_ms", "chg_1w_ms", "n"],
                aggregation={"latency_ms": "avg", "chg_1w_ms": "avg", "n": "sum"},
                number_format={"latency_ms": ",.1f", "chg_1w_ms": ",.1f", "n": ",.0f"},
                row_sort={"by": "value", "direction": "desc", "value_field": "chg_1w_ms"},
                repeat_row_labels=True, null_handling="separate",
                show_totals=False, max_height=360, enable_drilldown=False,
            )
        except Exception as e:
            st.error(f"streamlit-pivot unavailable: {e} — restart the server after installing.")


# -------------------------------------------------------- 2 · heatmap ----
with tab2:
    st.subheader("Conditional cell styling with JsCode")
    lic(("✅ 100% Community — free", "free"))
    st.caption(
        "Pattern: `cellStyle` takes a JS function of `params`; return a style dict. "
        "Requires `allow_unsafe_jscode=True`. Here: Δ1w colored red/green by sign and magnitude."
    )
    df = load_latency_movers()
    biggest = pd.concat([df.head(30), df.tail(30)])  # slowdowns + speedups

    chg_style = JsCode(
        """
        function(params) {
            if (params.value == null) { return {}; }
            const v = params.value;
            const a = Math.min(Math.abs(v) / 25.0, 1.0);   // full color at ±25ms
            if (v > 0) { return {backgroundColor: `rgba(214, 39, 40, ${0.15 + 0.5*a})`}; }
            if (v < 0) { return {backgroundColor: `rgba(44, 160, 44, ${0.15 + 0.5*a})`}; }
            return {};
        }
        """
    )
    level_style = JsCode(
        """
        function(params) {
            // degraded services in bold
            if (params.value > 1000) { return {fontWeight: 'bold', color: '#d62728'}; }
            return {};
        }
        """
    )

    gb = GridOptionsBuilder.from_dataframe(biggest)
    gb.configure_default_column(sortable=True, filter=True, resizable=True)
    gb.configure_column("service", header_name="Service", pinned="left", width=260)
    gb.configure_column("latency_ms", header_name="p95 (ms)", valueFormatter="x.toFixed(1)",
                        cellStyle=level_style, width=110)
    gb.configure_column("chg_1w_ms", header_name="Δ1w (ms)", valueFormatter="x.toFixed(1)",
                        cellStyle=chg_style, width=110, sort="desc")
    gb.configure_column("prev_ms", hide=True)
    gb.configure_column("requests", header_name="Requests (M)",
                        valueFormatter="(x / 1e6).toFixed(0)", width=120)

    AgGrid(biggest, gridOptions=build_opts(gb), theme="balham", height=560,
           allow_unsafe_jscode=True, key="heatmap")

    with st.expander("🟣 Closest with Perspective"):
        st.caption(
            "Maps: built-in numeric styling modes — pos/neg background colors and value "
            "gradients per column (also settable in the column's UI menu). Doesn't map: "
            "arbitrary JS logic like 'bold above 1000ms' — built-in modes only."
        )
        pview(
            biggest[["service", "latency_ms", "chg_1w_ms"]],
            {"plugin": "Datagrid", "columns": ["service", "latency_ms", "chg_1w_ms"],
             "sort": [["chg_1w_ms", "desc"]],
             "plugin_config": {"columns": {
                 "chg_1w_ms": {"fixed": 1, "number_bg_mode": "color",
                               "pos_bg_color": "#d62728", "neg_bg_color": "#2ca02c"},
                 "latency_ms": {"fixed": 1, "number_bg_mode": "gradient",
                              "bg_gradient": 1500}}}},
        )

    with st.expander("🟩 Closest with st-pivot"):
        st.caption(
            "Maps: `conditional_formatting` color_scale rules — the diverging scale "
            "anchored at `mid_value: 0` is EXACTLY the JsCode red/green-by-sign heatmap. "
            "Doesn't map: arbitrary JS ('bold above 1000ms')."
        )
        try:
            from streamlit_pivot import st_pivot_table

            st_pivot_table(
                biggest[["service", "latency_ms", "chg_1w_ms"]].reset_index(drop=True),
                key="sp2", rows=["service"], values=["latency_ms", "chg_1w_ms"],
                aggregation="avg", number_format=",.1f",
                row_sort={"by": "value", "direction": "desc", "value_field": "chg_1w_ms"},
                conditional_formatting=[
                    {"type": "color_scale", "apply_to": ["chg_1w_ms"],
                     "min_color": "#2ca02c", "mid_color": "#ffffff",
                     "max_color": "#d62728", "mid_value": 0},
                    {"type": "color_scale", "apply_to": ["latency_ms"],
                     "min_color": "#ffffff", "max_color": "#d62728"},
                ],
                show_totals=False, max_height=380, enable_drilldown=False,
            )
        except Exception as e:
            st.error(f"streamlit-pivot unavailable: {e}")


# ------------------------------------------------- 3 · selection → chart ----
with tab3:
    st.subheader("Row selection driving a detail chart")
    lic(("✅ 100% Community — free", "free"))
    st.caption(
        "Pattern: `configure_selection('single')` + `update_mode=SELECTION_CHANGED`; the script "
        "reruns on click and `resp.selected_rows` comes back as a DataFrame (1.x API, None if empty)."
    )
    movers = load_latency_movers().head(100)

    gb = GridOptionsBuilder.from_dataframe(
        movers[["service", "team", "latency_ms", "chg_1w_ms", "n"]]
    )
    gb.configure_default_column(sortable=True, filter=True)
    gb.configure_selection(selection_mode="single", use_checkbox=False)
    gb.configure_column("service", header_name="Service", width=280)
    gb.configure_column("latency_ms", header_name="p95 (ms)", valueFormatter="x.toFixed(1)")
    gb.configure_column("chg_1w_ms", header_name="Δ1w (ms)", valueFormatter="x.toFixed(1)")

    left, right = st.columns([1, 1])
    with left:
        resp = AgGrid(
            movers[["service", "team", "latency_ms", "chg_1w_ms", "n"]],
            gridOptions=build_opts(gb),
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            theme="balham",
            height=480,
            key="select",
        )
    with right:
        sel = resp.selected_rows  # DataFrame or None in st-aggrid 1.x
        if sel is not None and len(sel):
            name = sel.iloc[0]["service"]
            hist = load_latency_history()
            hist = hist[hist["service"] == name].sort_values("date")
            # weekly median smooths the day-to-day sampling noise
            wk = hist.set_index("date")["latency_ms"].resample("W").median().dropna()
            st.markdown(f"**{name}** — p95 latency, weekly median ({len(hist)} samples)")
            st.line_chart(wk, height=420)
        else:
            st.info("Click a row to load its latency history.")

    with st.expander("🟣 Closest with Perspective"):
        st.caption(
            "No events back to Python, so the detail chart moves INSIDE the viewer: the "
            "filter pill plays the role of the row click (open ⚙, edit the service "
            "filter to switch names) and plugin = Y Line draws the history. All client-side."
        )
        hist3 = load_latency_history()
        hist3 = hist3[hist3["service"].isin(movers.head(12)["service"])]
        pview(
            hist3.assign(date=hist3["date"].dt.strftime("%Y-%m-%d")),
            {"plugin": "Y Line", "group_by": ["date"], "columns": ["latency_ms"],
             "aggregates": {"latency_ms": "avg"},
             "filter": [["service", "==", movers.iloc[0]["service"]]],
             "settings": True},
            height=440,
        )

    with st.expander("🟩 Closest with st-pivot — the click DOES reach Python"):
        st.caption(
            "FULL parity, unlike Perspective: `on_cell_click` fires a rerun and the "
            "payload's `filters` dict names the row — Python draws the chart. Click a cell."
        )
        try:
            from streamlit_pivot import st_pivot_table

            st_pivot_table(
                movers.head(40)[["service", "latency_ms", "chg_1w_ms"]]
                .reset_index(drop=True),
                key="sp3", rows=["service"], values=["latency_ms", "chg_1w_ms"],
                aggregation="avg", number_format=",.1f",
                row_sort={"by": "value", "direction": "desc", "value_field": "chg_1w_ms"},
                show_totals=False, max_height=300, enable_drilldown=False,
                on_cell_click=lambda: None,
            )
            pay = (st.session_state.get("sp3") or {}).get("cell_click") or {}
            nm3 = pay.get("filters", {}).get("service")
            if nm3:
                h3 = load_latency_history()
                wk3 = (h3[h3["service"] == nm3].set_index("date")["latency_ms"]
                       .resample("W").median().dropna())
                st.markdown(f"**{nm3}** — clicked in the pivot, charted by Python:")
                st.line_chart(wk3, height=240)
            else:
                st.info("Click a cell above — Python receives the row and draws the chart here.")
        except Exception as e:
            st.error(f"streamlit-pivot unavailable: {e}")


# ------------------------------------------------------- 4 · grouping ----
with tab4:
    st.subheader("Row grouping + aggregation inside the grid")
    lic(("🔒 Enterprise: rowGroup · aggFunc · drag-to-group panel", "ent"),
        ("Free routes: pandas groupby (expander below) · Perspective (tab 9)", "alt"))
    st.caption(
        "Pattern: feed LONG data and let the grid pivot — `rowGroup=True` on the group column, "
        "`aggFunc` on values. Two ways to make grouping dynamic: a Streamlit widget rebuilding "
        "gridOptions (server-side rerun, shown here), or `rowGroupPanelShow='always'` — drag a "
        "column header into the strip above the grid to regroup client-side, no rerun."
    )
    group_by = st.multiselect(
        "Group rows by (order = nesting)", ["region", "pctl"], default=["region"], key="grp_cols"
    )
    regs = load_regions()
    recent = regs[regs["date"] > regs["date"].max() - pd.Timedelta(days=7)].copy()
    recent["pctl"] = recent["percentile"].map(lambda t: f"p{t:g}")
    view = recent[["region", "pctl", "lat_ms", "n", "requests_sum"]]

    # gotcha: AG Grid's built-in 'avg' aggFunc returns an OBJECT ({count, value})
    # on group rows so nested groups can re-weight — a plain "x.toFixed(3)"
    # expression throws there. Unwrap in a JsCode formatter instead.
    avg_fmt = JsCode(
        """
        function(params) {
            let v = params.value;
            if (v == null) { return ''; }
            if (typeof v === 'object') { v = v.value; }
            return v == null ? '' : Number(v).toFixed(1);
        }
        """
    )

    gb = GridOptionsBuilder.from_dataframe(view)
    gb.configure_column("region", header_name="Region", width=110, enableRowGroup=True)
    gb.configure_column("pctl", header_name="Percentile", width=90, enableRowGroup=True)
    # repeated configure_column calls MERGE into the same columnDef
    for i, col in enumerate(group_by):
        gb.configure_column(col, rowGroup=True, rowGroupIndex=i, hide=True)
    gb.configure_column("lat_ms", header_name="Latency (ms)", aggFunc="avg",
                        valueFormatter=avg_fmt, width=110)
    gb.configure_column("n", header_name="Samples", aggFunc="sum", width=100)
    gb.configure_column("requests_sum", header_name="Requests (bn)", aggFunc="sum",
                        valueFormatter="x == null ? '' : (x / 1e9).toFixed(1)", width=150)
    gb.configure_grid_options(
        groupDefaultExpanded=0,   # collapsed; click a group to expand
        rowGroupPanelShow="always",  # the drag-to-group strip
        autoGroupColumnDef={
            "headerName": " / ".join({"region": "Region", "pctl": "Percentile"}[c] for c in group_by)
                          or "Group",
            "minWidth": 160,
            # suppressCount drops the "(45)" row-count suffix on group rows
            "cellRendererParams": {"suppressCount": True},
        },
        suppressAggFuncInHeader=True,
    )

    # key includes the grouping so a change remounts the grid cleanly
    AgGrid(view, gridOptions=build_opts(gb), theme="balham", height=560,
           allow_unsafe_jscode=True, key=f"grouping-{'-'.join(group_by) or 'flat'}",
           enable_enterprise_modules=True)
    st.caption(
        "Note: rowGroup/aggFunc are AG Grid *enterprise* features — fine for local experiments "
        "(watermark-free in st-aggrid builds), but check licensing before shipping."
    )

    with st.expander("🆓 Free equivalent — pandas does the rollup, community grid displays it"):
        roll = (
            view.groupby(group_by or ["region"], as_index=False)
            .agg(lat_ms=("lat_ms", "mean"), n=("n", "sum"), requests_sum=("requests_sum", "sum"))
            .sort_values("n", ascending=False)  # rank by sample count
        )
        fgb = GridOptionsBuilder.from_dataframe(roll)
        fgb.configure_default_column(sortable=True, filter=True, width=110)
        fgb.configure_column("lat_ms", header_name="Latency (ms)",
                             valueFormatter="x == null ? '' : x.toFixed(1)")
        fgb.configure_column("n", header_name="Samples")
        fgb.configure_column("requests_sum", header_name="Requests (bn)",
                             valueFormatter="x == null ? '' : (x / 1e9).toFixed(1)")
        # NO enable_enterprise_modules here — this grid is 100% community
        AgGrid(roll, gridOptions=build_opts(fgb), theme="balham", height=300,
               key=f"free-roll-{'-'.join(group_by) or 'flat'}")
        st.caption(
            "Identical numbers, zero license: pandas aggregates, the grid just displays. "
            "What you give up is the in-grid expand/collapse tree — for drill-down use the "
            "master/detail pattern (tab 6) or Perspective (tab 9)."
        )

    with st.expander("🟣 Closest with Perspective — this is its home turf"):
        st.caption(
            "Row grouping IS Perspective's core model: group_by = the tree, split_by = "
            "column pivot (which AG Grid community can't do at all), aggregates per "
            "column, drag-to-re-pivot in the panel. Full version with settings: tab 9."
        )
        r4 = load_regions()
        r4 = r4[r4["date"] > r4["date"].max() - pd.Timedelta(days=7)]
        pview(
            r4.assign(pctl=r4["percentile"])[["region", "pctl", "lat_ms", "n"]],
            {"plugin": "Datagrid", "group_by": ["region"], "split_by": ["pctl"],
             "columns": ["lat_ms"], "aggregates": {"lat_ms": "avg"},
             "plugin_config": {"columns": {"lat_ms": {"fixed": 3}}}},
        )

    with st.expander("🟩 Closest with st-pivot — tree parity"):
        st.caption(
            "`row_layout='hierarchy'` = the AG Grid grouping tree: chevrons per group, "
            "level-wide collapse via the breadcrumb, subtotals per level, drag-to-re-pivot "
            "chips. Free and official. Full workout in tab 10."
        )
        try:
            from streamlit_pivot import st_pivot_table

            sp4 = recent.assign(pctl=recent["percentile"]).rename(
                columns={"lat_ms": "latency", "n": "samples"}
            )[["region", "pctl", "latency", "samples"]].reset_index(drop=True)
            st_pivot_table(
                sp4, key="sp4", rows=["region", "pctl"], values=["latency", "samples"],
                aggregation={"latency": "avg", "samples": "sum"},
                number_format={"latency": ",.3f", "samples": ",.0f"},
                dimension_format={"pctl": ",.0f"},
                row_layout="hierarchy", show_totals=False, max_height=380,
                enable_drilldown=False,
                style=[{"stripe_color": None,
                        "row_header": {"background_color": "#e3f2fd"},
                        "subtotal": {"background_color": "#e3f2fd"}}],
            )
        except Exception as e:
            st.error(f"streamlit-pivot unavailable: {e}")


# ------------------------------------------------------- 5 · editable ----
with tab5:
    st.subheader("Editable cells + reading edits back into Python")
    lic(("✅ 100% Community — free", "free"))
    st.caption(
        "Pattern: `editable=True` per column, `agSelectCellEditor` for dropdowns, "
        "`update_mode=VALUE_CHANGED` reruns on each edit; `resp.data` is the edited DataFrame. "
        "Persist across reruns via session_state keyed on the *original* data."
    )
    if "watchlist" not in st.session_state:
        st.session_state.watchlist = (
            load_latency_movers().head(8)[["service", "latency_ms", "chg_1w_ms"]]
            .assign(alert_ms=lambda d: (d["latency_ms"] * 1.2).round(0), action="watch")
            .reset_index(drop=True)
        )

    gb = GridOptionsBuilder.from_dataframe(st.session_state.watchlist)
    gb.configure_column("service", header_name="Service", editable=False, width=280)
    gb.configure_column("latency_ms", header_name="p95 (ms)", editable=False,
                        valueFormatter="x.toFixed(1)")
    gb.configure_column("chg_1w_ms", header_name="Δ1w (ms)", editable=False,
                        valueFormatter="x.toFixed(1)")
    gb.configure_column("alert_ms", header_name="Alert (ms) ✏️", editable=True,
                        type=["numericColumn"], cellStyle={"backgroundColor": "#fff3cd"})
    gb.configure_column(
        "action", header_name="Action ✏️", editable=True,
        cellEditor="agSelectCellEditor",
        cellEditorParams={"values": ["page", "watch", "mute"]},
        cellStyle={"backgroundColor": "#fff3cd"},
    )

    resp = AgGrid(
        st.session_state.watchlist,
        gridOptions=build_opts(gb),
        update_mode=GridUpdateMode.VALUE_CHANGED,
        theme="balham",
        height=320,
        key="editable",
    )
    edited = pd.DataFrame(resp.data)
    st.session_state.watchlist = edited

    triggered = edited[edited["latency_ms"] >= pd.to_numeric(edited["alert_ms"], errors="coerce")]
    if len(triggered):
        st.error(f"Alerts triggered: {', '.join(triggered['service'])}")
    else:
        st.success("No alerts triggered — edit an alert level below a service's current latency to test.")
    with st.expander("Edited DataFrame as Python sees it"):
        st.dataframe(edited, use_container_width=True)

    with st.expander("🟣 Closest with Perspective"):
        st.caption(
            "The datagrid edits too (enable via the ✏️ toggle in the plugin settings if "
            "typing does nothing) — but edits change the BROWSER's copy only. Python "
            "never sees them; there is no resp.data round-trip like above."
        )
        pview(
            st.session_state.watchlist,
            {"plugin": "Datagrid", "settings": False,
             "plugin_config": {"editable": True,
                               "columns": {"latency_ms": {"fixed": 1},
                                           "chg_1w_ms": {"fixed": 1}}}},
            height=320,
        )

    with st.expander("🟩 Closest without AG Grid — st.data_editor (st-pivot doesn't edit)"):
        st.caption(
            "st-pivot is read-only (a pivot, not a data entry grid). The free Streamlit "
            "answer for THIS pattern is built-in `st.data_editor`: editable cells, "
            "dropdown columns, edits back in Python — no component needed."
        )
        st.data_editor(
            st.session_state.watchlist.copy(),
            column_config={
                "action": st.column_config.SelectboxColumn(
                    "Action ✏️", options=["page", "watch", "mute"]),
                "alert_ms": st.column_config.NumberColumn("Alert (ms) ✏️"),
            },
            disabled=["service", "latency_ms", "chg_1w_ms"],
            hide_index=True, key="sp5",
        )
        st.caption("Demo copy — edits here don't feed the alert logic above.")


# ---------------------------------------------------- 6 · multi-detail ----
with tab6:
    st.subheader("One selection fanning out to several linked boxes")
    lic(("✅ 100% Community — free", "free"))
    st.caption(
        "Pattern: ONE master grid holds the selection; every other widget (metrics, detail "
        "grids, chart) derives from `resp.selected_rows` on the rerun. Detail grids get a key "
        "that includes the selection so they remount with fresh data instead of patching state."
    )
    movers = load_latency_movers().head(100)

    gb = GridOptionsBuilder.from_dataframe(
        movers[["service", "team", "latency_ms", "chg_1w_ms", "n"]]
    )
    gb.configure_default_column(sortable=True, filter=True)
    gb.configure_selection(selection_mode="single", use_checkbox=False)
    gb.configure_column("service", header_name="Service", width=280)
    gb.configure_column("team", header_name="Team", width=110)
    gb.configure_column("latency_ms", header_name="p95 (ms)", valueFormatter="x.toFixed(1)", width=100)
    gb.configure_column("chg_1w_ms", header_name="Δ1w (ms)", valueFormatter="x.toFixed(1)", width=100)
    gb.configure_column("n", header_name="samples", width=90)

    resp = AgGrid(
        movers[["service", "team", "latency_ms", "chg_1w_ms", "n"]],
        gridOptions=build_opts(gb),
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        theme="balham",
        height=260,
        key="master",
    )

    sel = resp.selected_rows
    if sel is None or not len(sel):
        st.info("Click a service above — metrics, percentile curve, recent samples and chart fill in below.")
    else:
        row = sel.iloc[0]
        name = row["service"]
        full = load_latency_full()
        ent = full[full["service"] == name]
        last = ent["date"].max()
        week = ent[ent["date"] > last - pd.Timedelta(days=7)]

        st.markdown(f"#### {name}")

        # --- box 1: metric strip ------------------------------------------
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("p95 latency", f"{row['latency_ms']:.0f} ms", f"{row['chg_1w_ms']:+.0f} ms 1w",
                  delta_color="inverse")
        m2.metric("Samples (1w, all pctls)", int(week["n"].sum()))
        m3.metric("Requests (1w)", f"{week['requests_sum'].sum() / 1e6:,.0f}M")
        m4.metric("Pctls seen (1w)", week["percentile"].nunique())

        c1, c2 = st.columns(2)

        # --- box 2: percentile curve (latest week, median by percentile) ---
        with c1:
            st.markdown("**Percentile curve — latest week**")
            curve = (
                week.groupby("percentile")
                .agg(latency_ms=("latency_ms", "median"), prints=("n", "sum"))
                .reset_index()
                .rename(columns={"percentile": "pctl"})
            )
            cgb = GridOptionsBuilder.from_dataframe(curve)
            cgb.configure_column("pctl", header_name="Percentile", width=100)
            cgb.configure_column("latency_ms", header_name="Latency (ms)",
                                 valueFormatter="x.toFixed(1)", width=110)
            cgb.configure_column("n_checks", header_name="Checks", width=90)
            AgGrid(curve, gridOptions=build_opts(cgb), theme="balham",
                   height=220, key=f"curve-{name}")

        # --- box 3: recent 5y prints (daily) --------------------------------
        with c2:
            st.markdown("**Recent p95 samples — daily**")
            recent5 = (
                ent[ent["percentile"] == 95.0]
                .sort_values("date", ascending=False)
                .head(10)
                .assign(date=lambda d: d["date"].dt.strftime("%Y-%m-%d"))
            )[["date", "latency_ms", "n", "requests_sum"]]
            rgb = GridOptionsBuilder.from_dataframe(recent5)
            rgb.configure_column("date", header_name="Date", width=110)
            rgb.configure_column("latency_ms", header_name="Latency (ms)",
                                 valueFormatter="x.toFixed(1)", width=110)
            rgb.configure_column("n", header_name="Samples", width=90)
            rgb.configure_column("requests_sum", header_name="Requests (M)",
                                 valueFormatter="(x / 1e6).toFixed(1)", width=120)
            AgGrid(recent5, gridOptions=build_opts(rgb), theme="balham",
                   height=220, key=f"recent-{name}")

        # --- box 4: history chart ------------------------------------------
        wk5 = (
            ent[ent["percentile"] == 95.0]
            .set_index("date")["latency_ms"].resample("W").median().dropna()
        )
        st.markdown("**p95 — weekly median**")
        st.line_chart(wk5, height=260)

    with st.expander("🟣 Closest with Perspective — client-side fan-out"):
        st.caption(
            "Selection can't reach Python, but views CAN link in the browser: one "
            "dropdown drives the filter on BOTH viewers (percentile rollup + history line) "
            "in plain JS. The fan-out happens client-side; Streamlit never reruns."
        )
        import json as _json

        import streamlit.components.v1 as _components

        top10 = movers.head(10)["service"].tolist()
        f6 = load_latency_full()
        f6 = f6[f6["service"].isin(top10)]
        f6 = f6.assign(date=f6["date"].dt.strftime("%Y-%m-%d"))
        _components.html(
            f"""
            <link rel="stylesheet" crossorigin
                  href="https://cdn.jsdelivr.net/npm/@finos/perspective-viewer@3/dist/css/themes.css"/>
            <style>
              .row {{ display: flex; gap: 8px; }}
              .row perspective-viewer {{ flex: 1; height: 380px; }}
              #pick {{ margin-bottom: 8px; font-size: 14px; padding: 4px 8px; }}
            </style>
            <select id="pick"></select>
            <div class="row">
              <perspective-viewer id="pg" theme="Pro Light"></perspective-viewer>
              <perspective-viewer id="pl" theme="Pro Light"></perspective-viewer>
            </div>
            <script type="module">
                import perspective from "https://cdn.jsdelivr.net/npm/@finos/perspective@3/dist/cdn/perspective.js";
                import "https://cdn.jsdelivr.net/npm/@finos/perspective-viewer@3/dist/cdn/perspective-viewer.js";
                import "https://cdn.jsdelivr.net/npm/@finos/perspective-viewer-datagrid@3/dist/cdn/perspective-viewer-datagrid.js";
                import "https://cdn.jsdelivr.net/npm/@finos/perspective-viewer-d3fc@3/dist/cdn/perspective-viewer-d3fc.js";
                const names = {_json.dumps(top10)};
                const worker = await perspective.worker();
                const table = await worker.table({_json.dumps(f6.to_dict("records"))});
                const pg = document.getElementById("pg"), pl = document.getElementById("pl");
                await pg.load(table);
                await pl.load(table);
                const sel = document.getElementById("pick");
                for (const n of names) {{
                    const o = document.createElement("option");
                    o.value = o.textContent = n;
                    sel.appendChild(o);
                }}
                async function apply(n) {{
                    await pg.restore({{plugin: "Datagrid", group_by: ["percentile"],
                                       columns: ["latency_ms", "n"],
                                       aggregates: {{latency_ms: "avg", n: "sum"}},
                                       filter: [["service", "==", n]]}});
                    await pl.restore({{plugin: "Y Line", group_by: ["date"],
                                       columns: ["latency_ms"],
                                       aggregates: {{latency_ms: "avg"}},
                                       filter: [["service", "==", n]]}});
                }}
                sel.addEventListener("change", e => apply(e.target.value));
                await apply(names[0]);
            </script>
            """,
            height=440,
        )

    with st.expander("🟩 Closest with st-pivot — full fan-out parity"):
        st.caption(
            "The cell-click payload reaches Python, so the ENTIRE fan-out works: click an "
            "service in the team tree → metrics + chart below, any widget you like. "
            "This is the piece Perspective can't do."
        )
        try:
            from streamlit_pivot import st_pivot_table

            st_pivot_table(
                movers.head(40)[["service", "team", "latency_ms", "chg_1w_ms", "n"]]
                .reset_index(drop=True),
                key="sp6", rows=["team", "service"],
                values=["latency_ms", "chg_1w_ms"], aggregation="avg",
                number_format=",.1f", row_layout="hierarchy",
                show_totals=False, max_height=320, enable_drilldown=False,
                on_cell_click=lambda: None,
            )
            pay6 = (st.session_state.get("sp6") or {}).get("cell_click") or {}
            nm6 = pay6.get("filters", {}).get("service")
            if nm6:
                # same fan-out layout as the AG Grid version above: metric strip,
                # then sub-table and graph SIDE BY SIDE — the click payload is
                # ordinary Python state, so the layout is entirely free
                row6 = movers[movers["service"] == nm6]
                if len(row6):
                    r6 = row6.iloc[0]
                    a6, b6, c6 = st.columns(3)
                    a6.metric("p95 latency", f"{r6['latency_ms']:.0f} ms")
                    b6.metric("Δ1w", f"{r6['chg_1w_ms']:+.0f} ms")
                    c6.metric("Samples", int(r6["n"]))
                full6 = load_latency_full()
                e6 = full6[full6["service"] == nm6]
                left6, right6 = st.columns(2)
                with left6:
                    st.markdown(f"**{nm6} — percentile curve, latest week**")
                    wk6d = e6[e6["date"] > e6["date"].max() - pd.Timedelta(days=7)]
                    curve6 = (
                        wk6d.groupby("percentile")
                        .agg(latency_ms=("latency_ms", "median"), prints=("n", "sum"))
                        .reset_index()
                        .rename(columns={"percentile": "pctl"})
                        .round(1)
                    )
                    st.dataframe(curve6, hide_index=True, use_container_width=True)
                with right6:
                    st.markdown("**p95 — weekly median**")
                    wk6 = (e6[e6["percentile"] == 95.0].set_index("date")["latency_ms"]
                           .resample("W").median().dropna())
                    st.line_chart(wk6, height=240)
            else:
                st.info("Click a service cell in the tree — metrics, percentile curve and "
                        "chart fill in below, same layout as the AG Grid version above.")
        except Exception as e:
            st.error(f"streamlit-pivot unavailable: {e}")


# ------------------------------------------------------ 7 · formatting ----
with tab7:
    st.subheader("Every formatting axis: cell / column / row / condition")
    lic(("✅ 100% Community — all styling axes are free", "free"))
    st.caption(
        "Numbers via `valueFormatter` · per-COLUMN static `cellStyle` dict · per-CELL "
        "conditional `cellStyle` JsCode · condition→CSS-class via `cellClassRules` + "
        "`custom_css` · per-ROW `getRowStyle` JsCode and `rowClassRules`. "
        "Compact toggle: `rowHeight`/`headerHeight` + font-size via `custom_css`."
    )
    compact = st.toggle("Compact mode", value=True, key="fmt_compact")
    mat = load_region_matrix()
    pctl_cols = [c for c in mat.columns if c.startswith("p")]

    CORE = ["us-east-1", "us-west-2", "eu-west-1", "eu-central-1"]
    EDGE = ["ap-south-1", "ap-northeast-1", "sa-east-1", "af-south-1"]

    # per-CELL: continuous color scale on the latency level (blue low → red high)
    scale_style = JsCode(
        """
        function(params) {
            const v = params.value;
            if (v == null) { return {}; }
            const t = Math.max(0, Math.min(1, v / 500.0));  // 0..500ms → 0..1
            return {backgroundColor: `rgba(${Math.round(255*t)}, 80, ${Math.round(255*(1-t))}, 0.18)`};
        }
        """
    )
    # per-ROW: bold the core regions (style object version)
    core_row = JsCode(
        f"""
        function(params) {{
            if (params.data && {CORE!r}.includes(params.data.region)) {{
                return {{fontWeight: 'bold', backgroundColor: '#f0f6ff'}};
            }}
            return null;
        }}
        """
    )

    gb = GridOptionsBuilder.from_dataframe(mat)
    gb.configure_default_column(sortable=True, resizable=True, width=92)
    gb.configure_column("region", header_name="Region", pinned="left", width=110)
    for c in pctl_cols:
        gb.configure_column(
            c, header_name=c,
            # NUMBER format: 2dp + trailing % (string expression, x = value)
            valueFormatter="x == null ? '' : x.toFixed(0) + ' ms'",
            cellStyle=scale_style,
            # condition → CSS class (classes styled via custom_css below)
            cellClassRules={"lat-hot": "x > 400", "lat-fast": "x < 120"},
        )
    # per-COLUMN static style: tint the p99 column (the tail everyone pages on).
    # gotcha: configure_column REPLACES omitted kwargs (header_name falls back
    # to the field name), so repeat everything this column needs.
    gb.configure_column("p99", header_name="p99", cellStyle={"backgroundColor": "#fff7e0"},
                        valueFormatter="x == null ? '' : x.toFixed(0) + ' ms'",
                        cellClassRules={"lat-hot": "x > 400", "lat-fast": "x < 120"})
    gb.configure_column("n_checks", header_name="Checks", width=90,
                        valueFormatter="x == null ? '' : x.toLocaleString()")
    gb.configure_grid_options(
        getRowStyle=core_row,
        # per-ROW: condition → class (EDGE currencies italic, via custom_css)
        rowClassRules={"edge-row": f"{EDGE!r}.includes(data.region)"},
        rowHeight=24 if compact else 40,
        headerHeight=26 if compact else 40,
    )

    AgGrid(
        mat, gridOptions=build_opts(gb), theme="balham",
        height=480 if compact else 640,
        allow_unsafe_jscode=True, key=f"fmt-{compact}",
        custom_css={
            ".ag-cell": {"font-size": "11px" if compact else "13px"},
            ".ag-header-cell-text": {"font-size": "11px" if compact else "13px"},
            ".lat-hot": {"font-weight": "700", "color": "#b30000"},
            ".lat-fast": {"color": "#0050b3", "font-style": "italic"},
            ".edge-row": {"font-style": "italic"},
        },
    )
    st.caption(
        "Precedence when several rules hit one cell: cellStyle (JsCode) beats class rules; "
        "row styles sit under cell styles. p99 column shows static tint under the scale. "
        "Core-region rows bold+blue (getRowStyle), edge regions italic (rowClassRules), >400ms bold red / "
        "fast (<120ms) blue italic (cellClassRules)."
    )

    with st.expander("🟣 Closest with Perspective"):
        st.caption(
            "Maps: per-column precision + gradient backgrounds (the heatmap look). "
            "Doesn't map: row-level rules (core-region bold), CSS classes, condition-specific "
            "styles beyond pos/neg, and row-height/density control."
        )
        m7 = mat.melt(id_vars=["region"], value_vars=pctl_cols,
                      var_name="pctl", value_name="latency").dropna()
        pview(
            m7.assign(pctl=m7["pctl"].str[1:].astype(float)),
            {"plugin": "Datagrid", "group_by": ["region"], "split_by": ["pctl"],
             "columns": ["latency"], "aggregates": {"latency": "avg"},
             "plugin_config": {"columns": {"latency": {"fixed": 2,
                                                    "number_bg_mode": "gradient",
                                                    "bg_gradient": 14}}}},
        )

    with st.expander("🟩 Closest with st-pivot"):
        st.caption(
            "Per-COLUMN rules by making each percentile its own value field (no split_by): "
            "gradient on p99 ONLY · tail (p99−p50) red when wide (`threshold gt 200`) · "
            "cells ≥ 400ms bold (`threshold` with `bold: True`) · toolbar hidden on demand "
            "(`interactive=False`; `show_sections=False` keeps it as a one-line summary, "
            "`locked=True` = viewer mode). Density via `style='compact'`."
        )
        try:
            from streamlit_pivot import st_pivot_table

            hide7 = st.checkbox("Hide the config toolbar (interactive=False)", key="sp7_hide")
            ycols = list(pctl_cols)  # p50…p99 names used as-is
            sp7w = mat.copy()
            sp7w["tail_ms"] = sp7w["p99"] - sp7w["p50"]
            st_pivot_table(
                sp7w[["region"] + ycols + ["tail_ms"]].reset_index(drop=True),
                key=f"sp7-{hide7}", rows=["region"], values=ycols + ["tail_ms"],
                aggregation="avg", number_format=",.2f",
                conditional_formatting=[
                    # ONE column only — gradient on the p99 tail
                    {"type": "color_scale", "apply_to": ["p99"],
                     "min_color": "#ffffff", "max_color": "#d62728"},
                    # wide tails red (the yellow bg comes from
                    # data_cell_by_measure below — region layer, so it also
                    # paints EMPTY cells, which threshold rules never match)
                    {"type": "threshold", "apply_to": ["tail_ms"],
                     "conditions": [{"operator": "gt", "value": 200,
                                     "color": "#d62728"}]},
                    # bold the slow bucket — anything ≥ 400ms
                    {"type": "threshold", "apply_to": ycols,
                     "conditions": [{"operator": "gte", "value": 400, "bold": True}]},
                ],
                # style list = preset + overrides: light-blue ROW-LABEL column
                # (row_header region) + static yellow on the slope measure
                style=["compact",
                       {"stripe_color": None,   # striping blends over row_header
                        "row_header": {"background_color": "#e3f2fd"},
                        "data_cell_by_measure": {
                            "tail_ms": {"background_color": "#fff9c4"}}}],
                show_totals=False, max_height=430,
                enable_drilldown=False, interactive=not hide7,
                # empty cells ("-", e.g. a region missing p99 samples) are NEVER hit
                # by value rules — NaN fails every condition, so they stay
                # unstyled. null_handling={"tail_ms": "zero"} would coerce
                # them to 0.00 (and pick up the yellow), but that fabricates a
                # number for a missing sample — left off on purpose.
            )
            st.caption(
                "Initial collapse level: not a Python parameter in 0.5.0 — collapsed "
                "state lives in the frontend config (persists across reruns per `key`, "
                "exportable via toolbar Copy Config). Emulate 'load collapsed' by "
                "starting with fewer row dims (rows=['region']) and letting users drag "
                "the next level in, or collapse via the breadcrumb (tab 10)."
            )
        except Exception as e:
            st.error(f"streamlit-pivot unavailable: {e}")


# ------------------------------------------------------- 8 · excel-ish ----
with tab8:
    st.subheader("Excel-style range selection, live Σ/avg status bar, range copy")
    lic(("🔒 Enterprise: cellSelection · statusBar Σ/avg · range clipboard", "ent"),
        ("Closest free route: st.dataframe (expander below)", "alt"))
    st.caption(
        "Enterprise: `cellSelection=True` (drag a range like Excel), `statusBar` with "
        "`agAggregationComponent` (Sum / Average / Count / Min / Max of the selected range, "
        "bottom right), clipboard module (Ctrl/Cmd+C copies the range as TSV — pastes "
        "straight into Excel). Ctrl+A selects the whole grid."
    )
    mat = load_region_matrix()
    pctl_cols = [c for c in mat.columns if c.startswith("p")]

    gb = GridOptionsBuilder.from_dataframe(mat)
    gb.configure_default_column(sortable=True, resizable=True, width=92)
    gb.configure_column("region", header_name="Region", pinned="left", width=110)
    for c in pctl_cols:
        gb.configure_column(c, header_name=c,
                            valueFormatter="x == null ? '' : x.toFixed(1)")
    gb.configure_column("n_checks", header_name="Checks", width=90)
    gb.configure_grid_options(
        cellSelection=True,            # AG Grid ≥32.2 name (enableRangeSelection before)
        rowHeight=26,
        headerHeight=28,
        statusBar={
            "statusPanels": [
                {"statusPanel": "agTotalRowCountComponent", "align": "left"},
                {"statusPanel": "agAggregationComponent", "align": "right"},
            ]
        },
    )

    AgGrid(mat, gridOptions=build_opts(gb), theme="balham", height=520,
           allow_unsafe_jscode=True, key="excel", enable_enterprise_modules=True)
    st.caption(
        "Drag across cells → the status bar updates live. The aggregation only counts "
        "numeric cells, so mixed ranges behave like Excel. Copy needs the page to be "
        "focused (click the grid first)."
    )

    with st.expander("🆓 Free alternative — st.dataframe: native range-copy + Python-side Σ/avg"):
        st.caption(
            "Streamlit's built-in grid copies ranges for free: drag-select cells, "
            "Ctrl/Cmd+C, paste into Excel. The Σ/avg half is approximated in Python: "
            "tick rows / click column headers below and metrics compute on the rerun — "
            "close, but a rerun per selection instead of a live status bar."
        )
        # index on region: row labels for free, and no ::auto_unique_id:: artifact
        # (hide_index + selections makes Streamlit expose its internal row id)
        ev = st.dataframe(
            mat.set_index("region"), on_select="rerun",
            selection_mode=["multi-row", "multi-column"], key="glide_free",
        )
        sel_rows = list(ev.selection.rows)
        sel_cols = [c for c in ev.selection.columns if c in pctl_cols] or pctl_cols
        if sel_rows:
            vals = mat.iloc[sel_rows][sel_cols].to_numpy().ravel()
            vals = vals[~pd.isna(vals)]
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Count", len(vals))
            m2.metric("Sum", f"{vals.sum():.2f}")
            m3.metric("Average", f"{vals.mean():.2f}")
            m4.metric("Min", f"{vals.min():.2f}")
            m5.metric("Max", f"{vals.max():.2f}")
        else:
            st.info("Tick rows (and optionally click column headers) → Σ/avg/min/max appear here.")

    with st.expander("🟣 Closest with Perspective"):
        st.caption(
            "No range selection, no live Σ/avg of a dragged rectangle. The Perspective "
            "way: you PIVOT for your sums (group_by → per-group and grand-total "
            "aggregates) and export/copy from the toolbar (CSV / Arrow / PNG). "
            "Different mental model, same numbers."
        )
        m8 = mat.melt(id_vars=["region"], value_vars=pctl_cols,
                      var_name="pctl", value_name="latency").dropna()
        pview(
            m8.assign(pctl=m8["pctl"].str[1:].astype(float)),
            {"plugin": "Datagrid", "group_by": ["region"], "split_by": ["pctl"],
             "columns": ["latency"], "aggregates": {"latency": "avg"},
             "plugin_config": {"columns": {"latency": {"fixed": 3}}}},
        )

    with st.expander("🟩 Closest with st-pivot"):
        st.caption(
            "Still no ad-hoc range Σ/avg (that stays AG Grid enterprise-only). What it "
            "DOES have built-in: grand totals + subtotals, and the toolbar exports to "
            "**Excel/CSV/TSV/clipboard** — the copy-to-Excel half, officially supported."
        )
        try:
            from streamlit_pivot import st_pivot_table

            sp8 = mat.melt(id_vars=["region"], value_vars=pctl_cols,
                           var_name="pctl", value_name="latency").dropna()
            sp8["pctl"] = sp8["pctl"].str[1:].astype(float)
            st_pivot_table(
                sp8[["region", "pctl", "latency"]].reset_index(drop=True),
                key="sp8", rows=["region"], columns=["pctl"], values=["latency"],
                aggregation="avg", number_format=",.3f",
                dimension_format={"pctl": ",.0f"},
                show_totals=True, max_height=420, enable_drilldown=False,
                export_filename="region_matrix",
            )
        except Exception as e:
            st.error(f"streamlit-pivot unavailable: {e}")


# ----------------------------------------------------- 9 · perspective ----
with tab9:
    st.subheader("Same data in FINOS Perspective — free pivot engine")
    lic(("🆓 Apache-2.0 — free replacement for enterprise pivoting", "free"))
    st.caption(
        "Apache-2.0 alternative for the *enterprise* half of AG Grid: `group_by` + "
        "`split_by` (row AND column pivots), full aggregate set, expression columns, "
        "chart plugins — all free, all client-side (WASM). Embedded one-way via "
        "`components.html` + CDN: clicks do NOT come back to Python. "
        "Drag columns between Group By / Split By in the side panel; right-click a "
        "column header for aggregates; try plugin = Heatmap."
    )

    import json

    import streamlit.components.v1 as components

    r = load_regions()
    recent = r[r["date"] > r["date"].max() - pd.Timedelta(days=30)].copy()
    # numeric percentile → split_by headers sort 50,75,…,99 (strings would sort lexically)
    recs = recent.assign(
        date=recent["date"].dt.strftime("%Y-%m-%d"),
        pctl=recent["percentile"],
        requests_mm=(recent["requests_sum"] / 1e6).round(1),
    )[["date", "region", "pctl", "lat_ms", "n", "requests_mm"]].to_dict("records")

    components.html(
        f"""
        <link rel="stylesheet" crossorigin
              href="https://cdn.jsdelivr.net/npm/@finos/perspective-viewer@3/dist/css/themes.css"/>
        <style> perspective-viewer {{ height: 620px; width: 100%; }} </style>
        <perspective-viewer theme="Pro Light"></perspective-viewer>
        <script type="module">
            import perspective from
                "https://cdn.jsdelivr.net/npm/@finos/perspective@3/dist/cdn/perspective.js";
            import "https://cdn.jsdelivr.net/npm/@finos/perspective-viewer@3/dist/cdn/perspective-viewer.js";
            import "https://cdn.jsdelivr.net/npm/@finos/perspective-viewer-datagrid@3/dist/cdn/perspective-viewer-datagrid.js";
            import "https://cdn.jsdelivr.net/npm/@finos/perspective-viewer-d3fc@3/dist/cdn/perspective-viewer-d3fc.js";

            const data = {json.dumps(recs)};
            const worker = await perspective.worker();
            const table = await worker.table(data);
            const viewer = document.querySelector("perspective-viewer");
            await viewer.load(table);
            await viewer.restore({{
                plugin: "Datagrid",
                group_by: ["region"],
                split_by: ["pctl"],
                columns: ["lat_ms"],
                aggregates: {{ lat_ms: "avg" }},
                sort: [["n", "desc"]],
                settings: true,
            }});
        </script>
        """,
        height=650,
    )
    st.caption(
        f"{len(recs):,} long rows (last 30 days) pivoted client-side. What Perspective "
        "lacks vs AG Grid enterprise: Excel-style range Σ/avg status bar, and events "
        "back into Streamlit (no selection → other-widgets pattern without a custom "
        "bidirectional component). Needs internet for the CDN."
    )



# ------------------------------------------------------- 10 · st-pivot ----
with tab10:
    st.subheader("streamlit-pivot — the OFFICIAL pivot component")
    lic(("🆓 Official Streamlit component (pip install streamlit-pivot) — free", "free"),
        ("Unlike Perspective: config/click events DO come back to Python", "alt"))
    st.caption(
        "BI pivot from the Streamlit team: drag-and-drop field config, per-measure "
        "aggregation, weighted-average synthetic measures (the `latency (wt)` column, a "
        "drill-down-correct ratio-of-sums), subtotals, conditional formatting, Excel/CSV/clipboard export, "
        "click-to-drill-down source panel — and the current config + cell clicks land "
        "back in Python (`result['config']`, `st.session_state[key]`), which Perspective "
        "can't do. Try dragging `samples` out, right-clicking a header, or clicking a cell."
    )
    try:
        from streamlit_pivot import st_pivot_table

        r10 = load_regions()
        r10 = r10[r10["date"] > r10["date"].max() - pd.Timedelta(days=7)].copy()
        # reset_index or the drill-down panel shows a __index_level_0__ column
        src = r10.assign(pctl=r10["percentile"]).rename(
            columns={"lat_ms": "latency", "n": "samples"}
        )[["region", "pctl", "latency", "samples"]].reset_index(drop=True)
        # weighted-avg source: precompute the PRODUCT so Σ = Σ(latency·samples);
        # the synthetic measure below divides it by Σsamples per cell/level
        src["lat_x_samp"] = src["latency"] * src["samples"]

        layout = st.radio(
            "Row layout", ["region × pctl (matrix)", "region → pctl tree (collapse, like AG Grid)"],
            horizontal=True, key="stpivot_layout",
        )
        if layout.startswith("region ×"):
            kwargs = dict(rows=["region"], columns=["pctl"], values=["latency"])
        else:
            # row_layout="hierarchy" = the AG Grid grouping tree: one indented
            # column, expand/collapse chevrons, subtotals auto-enabled per level.
            # Blue tree column across ALL drill-down levels: leaf labels are the
            # row_header region, parent/group rows are the subtotal region.
            kwargs = dict(rows=["region", "pctl"], values=["latency", "samples"],
                          row_layout="hierarchy",
                          style=[{"stripe_color": None,
                                  "row_header": {"background_color": "#e3f2fd"},
                                  "subtotal": {"background_color": "#e3f2fd"}}])

        result = st_pivot_table(
            src,
            key=f"stpivot-{layout[:5]}",
            aggregation={"latency": "avg", "samples": "sum"},
            number_format={"latency": ",.3f", "samples": ",.0f"},
            dimension_format={"pctl": ",.0f"},
            # weighted mean as a ratio-of-sums — recomputed at every drill-down
            # level (sample-weighted, so noisy low-sample cells don't dominate).
            # NOTE 'avg' latency vs this column differ; the gap IS the weighting.
            synthetic_measures=[{
                "id": "wavg_latency", "label": "latency (wt)",
                "operation": "sum_over_sum",
                "numerator": "lat_x_samp", "denominator": "samples",
                "format": ",.3f",
            }],
            show_totals=False,
            max_height=520,
            enable_drilldown=True,
            export_filename="latency_pivot",
            **kwargs,
        )
        with st.expander("What Python gets back (`result['config']`)"):
            st.json(result.get("config", {}), expanded=False)
    except Exception as e:
        st.error(f"streamlit-pivot failed to load: {e}")
        st.caption("Component uses Streamlit Components V2 — may need a newer Streamlit.")


# -------------------------------------------------- 11 · weighted avg ----
with tab11:
    st.subheader("Weighted-average aggregation — the aggFunc that returns 0")
    lic(("🔒 Enterprise: rowGroup + custom aggFunc", "ent"),
        ("Free route: pandas np.average(weights=…) → flat grid (expander below)", "alt"))
    st.caption(
        "Group latency **region → percentile** and roll it up as a **request-weighted** "
        "mean, not a flat mean — a busy region should dominate its own average. The trap: "
        "an aggFunc runs on GROUP rows where `params.data` is undefined and `params.values` "
        "holds only latency, so it can't see the request weights. Fix: a `valueGetter` folds "
        "each leaf into `{value, weight}`; the aggFunc weights, divides, and returns the "
        "same shape so it re-weights correctly at EVERY level — **expand a region, then a "
        "percentile: each level is a true weighted mean, never an average-of-averages.**"
    )

    regs = load_regions()
    recent = regs[regs["date"] > regs["date"].max() - pd.Timedelta(days=7)].copy()
    recent["pctl"] = recent["percentile"].map(lambda t: f"p{t:g}")
    view = recent[["region", "pctl", "lat_ms", "requests_sum"]].rename(
        columns={"lat_ms": "latency_ms", "requests_sum": "requests"}
    )

    # leaf -> {value, weight}; group rows return null so the aggFunc handles them
    weighted_value = JsCode(
        """
        function(p) {
            if (!p.data) { return null; }              // group node -> aggFunc runs
            return {value: p.data.latency_ms, weight: p.data.requests};
        }
        """
    )
    # runs on group rows; each child (leaf or sub-group) carries .value + .weight,
    # so this same function re-weights correctly at every level of the tree
    weighted_avg = JsCode(
        """
        function(p) {
            let vw = 0, w = 0;
            p.values.forEach(function(o) {
                if (o && o.weight) { vw += o.value * o.weight; w += o.weight; }
            });
            // w===0 (empty / all-zero-weight group) -> null, NOT 0: avoids the
            // 0/0 = NaN and a fake "0ms" reading; weight 0 makes a parent skip it.
            // toString renders the object; a string "x.toFixed(1)" formatter would THROW.
            return {value: w ? vw / w : null, weight: w,
                    toString: function() { return this.value == null ? '' : this.value.toFixed(1); }};
        }
        """
    )
    # the WRONG version most people write — reaches for the sibling weight column,
    # which is undefined on group rows, so every group prints 0.0
    naive_broken = JsCode(
        """
        function(p) {
            let vw = 0, w = 0;
            p.values.forEach(function(v) {
                const wt = p.data ? p.data.requests : undefined;   // undefined on groups
                vw += v * wt; w += wt;
            });
            const out = w ? vw / w : 0;
            return isNaN(out) ? 0 : out;
        }
        """
    )

    show_broken = st.toggle(
        "Show the broken aggFunc (reads the weight off params.data → all zeros)",
        value=False, key="wavg_broken",
    )

    gb = GridOptionsBuilder.from_dataframe(view)
    # two group levels so drill-down is demonstrable: region -> percentile
    gb.configure_column("region", header_name="Region", rowGroup=True,
                        rowGroupIndex=0, hide=True, enableRowGroup=True)
    gb.configure_column("pctl", header_name="Percentile", rowGroup=True,
                        rowGroupIndex=1, hide=True, enableRowGroup=True)
    gb.configure_column(
        "latency_ms", header_name="Latency (req-weighted ms)",
        valueGetter=naive_broken if show_broken else weighted_value,
        aggFunc="avg" if show_broken else weighted_avg,
        # the broken path uses built-in avg on a plain number so it renders SOMETHING
        # (0.0) rather than [object Object]; the fixed path renders via toString
        valueFormatter=(JsCode("function(p){ return p.value == null ? '' : Number(p.value).toFixed(1); }")
                        if show_broken else None),
        width=210,
    )
    gb.configure_column("requests", header_name="Requests", aggFunc="sum",
                        valueFormatter="x == null ? '' : (x / 1e6).toFixed(1) + 'M'", width=140)
    gb.configure_grid_options(
        groupDefaultExpanded=0,   # collapsed; expand region, then percentile
        autoGroupColumnDef={"headerName": "Region / Percentile", "minWidth": 190,
                            "cellRendererParams": {"suppressCount": True}},
        suppressAggFuncInHeader=True,
    )

    AgGrid(view, gridOptions=build_opts(gb), theme="balham", height=460,
           allow_unsafe_jscode=True, key=f"wavg-{show_broken}",
           enable_enterprise_modules=True)

    # ground truth: pandas weighted mean per region, so the grid is verifiable
    truth = (
        view.groupby("region")
        .apply(lambda g: np.average(g["latency_ms"], weights=g["requests"]),
               include_groups=False)
        .round(1).rename("weighted_ms").reset_index()
        .merge(view.groupby("region")["latency_ms"].mean().round(1)
               .rename("flat_ms").reset_index(), on="region")
        .sort_values("weighted_ms", ascending=False)
    )
    st.caption(
        "The region-level group row equals `np.average(latency, weights=requests)` over "
        "ALL its leaves (table below) — and each percentile sub-level is the same ratio on "
        "its own slice, because the weights carry through the tree. Flip the toggle to watch "
        "the common `params.data.requests` mistake collapse every group to 0.0. "
        "Zero-weight safety: the `w ? … : null` guard means an all-zero-requests group "
        "renders blank (not a divide-by-zero NaN or a fake 0.0ms), and any single "
        "zero-request leaf is skipped rather than poisoning its group."
    )

    with st.expander("🆓 Free & less fragile — pandas weighted mean → flat community grid"):
        st.caption(
            "No enterprise modules, no JsCode: `np.average(weights=…)` per group, community "
            "grid just displays it. `weighted_ms` vs `flat_ms` shows how much the weighting "
            "moves each region. Prefer this unless users need to drag grouping client-side."
        )
        fgb = GridOptionsBuilder.from_dataframe(truth)
        fgb.configure_default_column(sortable=True, filter=True, width=140)
        fgb.configure_column("region", header_name="Region", width=120)
        fgb.configure_column("weighted_ms", header_name="Weighted (ms)",
                             valueFormatter="x == null ? '' : x.toFixed(1)")
        fgb.configure_column("flat_ms", header_name="Flat mean (ms)",
                             valueFormatter="x == null ? '' : x.toFixed(1)")
        AgGrid(truth, gridOptions=build_opts(fgb), theme="balham", height=300,
               key="wavg-free")
# ------------------------------------------- 12 · pivot mode (split-by) ----
with tab12:
    st.subheader("Pivot mode — split a column's VALUES into columns")
    lic(("🔒 Enterprise: pivotMode + colDef.pivot (the split-by)", "ent"),
        ("Free routes: streamlit-pivot columns= (tab 10) · Perspective split_by (tab 9)", "alt"))
    st.caption(
        "`pivotMode=True` + `pivot=True` on a dimension column turns that column's "
        "VALUES into columns — AG Grid's answer to Perspective `split_by` / a "
        "spreadsheet column pivot. Here region values become columns, rows grouped "
        "by percentile, each cell = avg latency. Community CANNOT pivot columns."
    )
    pr = load_regions()
    recent = pr[pr["date"] > pr["date"].max() - pd.Timedelta(days=7)].copy()
    recent["pctl"] = recent["percentile"].map(lambda t: f"p{t:g}")
    view = recent[["pctl", "region", "lat_ms", "n"]]

    # gotcha: auto-generated pivot columns don't inherit ANY valueFormatter
    # (not the measure's, not defaultColDef's), and rounding the INPUT doesn't
    # help because the grid re-aggregates. The fix is the processPivotResultColDef
    # grid callback — it runs per generated pivot column, set the formatter there.
    fmt_pivot_cols = JsCode(
        """
        function(colDef) {
            colDef.valueFormatter = function(p) {
                return p.value == null ? '' : Number(p.value).toFixed(1);
            };
            return colDef;
        }
        """
    )

    gb = GridOptionsBuilder.from_dataframe(view)
    gb.configure_column("pctl", header_name="Percentile", rowGroup=True, hide=True)  # ROW dim
    gb.configure_column("region", pivot=True)          # VALUES → columns (the split-by)
    gb.configure_column("lat_ms", header_name="ms", aggFunc="avg")
    gb.configure_column("n", hide=True)
    gb.configure_grid_options(
        pivotMode=True,                                # the switch that enables column pivot
        processPivotResultColDef=fmt_pivot_cols,       # format the generated split columns
        autoGroupColumnDef={"headerName": "Percentile", "minWidth": 140,
                            "cellRendererParams": {"suppressCount": True}},
        suppressAggFuncInHeader=True,
    )
    AgGrid(view, gridOptions=build_opts(gb), theme="balham", height=430,
           allow_unsafe_jscode=True, key="pivotmode", enable_enterprise_modules=True)
    st.caption(
        "Each region value is now its own column. Flip `pivotMode` off and the same "
        "config reads as plain row grouping. For the free equivalent use streamlit-pivot "
        "`columns=[\"region\"]` (tab 10) or Perspective `split_by` (tab 9)."
    )
