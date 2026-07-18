"""st-flags lab — offline flag icons in markdown, st.dataframe, and AgGrid.

Run:  python -m streamlit run st_flags_lab.py

Tab 1: markdown <img> snippets + the Windows-emoji comparison
Tab 2: st.dataframe ImageColumn fed with data URIs (no AgGrid needed)
Tab 3: AgGrid cell renderer (guarded import; distinct-LUT payload)
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flag_emoji as fe

st.set_page_config(page_title="st-flags lab", layout="wide")
st.title("st-flags — flags that work on Windows and offline")

DATA = pd.DataFrame({
    "region_cc": ["us", "gb", "jp", "de", "sg", "br"],
    "region":    ["us-east-1", "eu-west-2", "ap-northeast-1",
                  "eu-central-1", "ap-southeast-1", "sa-east-1"],
    "ccy":       ["USD", "GBP", "JPY", "EUR", "SGD", "BRL"],
    "latency_ms": [110.0, 142.5, 95.2, 128.9, 88.4, 201.7],
})

tab1, tab2, tab3 = st.tabs(["1 · Markdown & the emoji trap",
                            "2 · st.dataframe ImageColumn", "3 · AgGrid renderer"])

# ------------------------------------------------ 1 · markdown + emoji ----
with tab1:
    st.caption(
        "Left: bundled Twemoji PNGs (render EVERYWHERE, incl. Windows). Right: "
        "real flag emoji — regional-indicator pairs that Windows shows as bare "
        "letters like 'US'. If the right column shows letters, that's the trap."
    )
    def emoji_flag(cc: str) -> str:
        return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in cc.upper())

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("PNG (always works)")
        for cc, label in [("us", "us-east-1"), ("gb", "eu-west-2"), ("jp", "ap-northeast-1")]:
            st.markdown(fe.flag_img(cc, label=label), unsafe_allow_html=True)
        st.markdown(fe.flag_img("APAC", label="APAC (alias → hub flag)"),
                    unsafe_allow_html=True)
        st.markdown(fe.flag_img("asia", label="asia (region globe)"),
                    unsafe_allow_html=True)
    with c2:
        st.subheader("Emoji (Windows shows letters)")
        for cc in ["US", "GB", "JP"]:
            st.markdown(f"{emoji_flag(cc)} {cc}")

    st.caption(f"{len(fe.available())} bundled assets · Twemoji, CC-BY 4.0 · "
               "zero network at runtime (base64 data URIs).")

# --------------------------------------------- 2 · native ImageColumn ----
with tab2:
    st.caption(
        "No AgGrid needed: map codes to data URIs into a column and use "
        "st.column_config.ImageColumn — verified it accepts data URIs. Keep the "
        "CODE column too so sorting stays on text, not on image HTML."
    )
    df2 = DATA.copy()
    df2["flag"] = df2["region_cc"].map(fe.flag_uri)
    df2["ccy_flag"] = df2["ccy"].map(fe.currency_uri)
    st.dataframe(
        df2[["flag", "region", "ccy_flag", "ccy", "latency_ms"]],
        column_config={
            "flag": st.column_config.ImageColumn("", width=32),
            "ccy_flag": st.column_config.ImageColumn("", width=32),
            "latency_ms": st.column_config.NumberColumn("p95 (ms)", format="%.1f"),
        },
        hide_index=True, width="stretch",
    )

# ------------------------------------------------- 3 · AgGrid renderer ----
with tab3:
    st.caption(
        "Cell values stay short codes ('us', 'USD'); the renderer holds ONE "
        "image per DISTINCT value in a JS lookup table, so the payload is tiny "
        "at any row count. Needs allow_unsafe_jscode=True (st-aggrid gotcha 2)."
    )
    try:
        from st_aggrid import AgGrid, GridOptionsBuilder

        gb = GridOptionsBuilder.from_dataframe(
            DATA[["region_cc", "ccy", "latency_ms"]])
        gb.configure_column("region_cc", header_name="Region",
                            cellRenderer=fe.cell_renderer(DATA["region_cc"].unique()))
        gb.configure_column("ccy", header_name="Currency",
                            cellRenderer=fe.cell_renderer(DATA["ccy"].unique(),
                                                          currency=True))
        gb.configure_column("latency_ms", header_name="p95 (ms)",
                            valueFormatter="x.toFixed(1)")
        go = gb.build(); go.pop("autoSizeStrategy", None)
        AgGrid(DATA[["region_cc", "ccy", "latency_ms"]], gridOptions=go,
               theme="balham", height=280, allow_unsafe_jscode=True, key="flags")
    except Exception as e:  # component can't register under AppTest — degrade
        st.info(f"st_aggrid unavailable here ({type(e).__name__}) — "
                "run the lab with `streamlit run` to see the grid.")
        st.dataframe(DATA, hide_index=True)
