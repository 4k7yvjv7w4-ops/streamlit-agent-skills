---
name: st-flags
description: Country / region / currency flag icons in Streamlit — offline Twemoji PNGs as base64 data URIs for st.markdown, st.dataframe ImageColumn, and AgGrid cell renderers. Use when showing flags next to countries, regions, or currency codes (USD, EUR…), when flag emoji render as bare letters ("US") on Windows, when images are needed inside grid cells, or in air-gapped/no-CDN environments. Ships flag_emoji.py + 67 bundled assets.
---

# st-flags — flag icons that work on Windows and offline

Reusable module: `flag_emoji.py` + bundled `flags/` (67 Twemoji PNGs: 64
countries + `emea`/`asia`/`americas` region globes, ~270 KB total, base64
data URIs at runtime — **zero network**). Runnable proof: `st_flags_lab.py`.
Verified on Streamlit **1.58**. Assets: Twemoji, **CC-BY 4.0 — keep the
attribution** (it's in the module docstring).

## THE gotcha — flag emoji don't render on Windows

A flag "emoji" is two regional-indicator characters (🇺🇸 = U+1F1FA U+1F1F8).
**Windows ships no flag glyphs** (Segoe UI Emoji omits them), so on
Chrome/Edge/Windows desktops users see bare letters — "US" — not a flag.
Do NOT emit emoji flags for a Windows-desktop audience; use the bundled
PNGs. (macOS/iOS/Android render them fine — hence the trap: it looks
perfect on the Mac where it was developed.)

```python
# emoji one-liner — ONLY when the audience is Mac/mobile:
def emoji_flag(cc):  # "US" -> 🇺🇸
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in cc.upper())
```

## Quick use (all verified in the lab)

```python
import flag_emoji as fe          # copy flag_emoji.py + flags/ next to your app

# 1) inline in markdown
st.markdown(fe.flag_img("us", label="us-east-1"), unsafe_allow_html=True)

# 2) native table — ImageColumn takes data URIs directly (no AgGrid needed)
df["flag"] = df["region_cc"].map(fe.flag_uri)        # data-URI column
st.dataframe(df, column_config={
    "flag": st.column_config.ImageColumn("", width=32)})

# 3) AgGrid cells — values stay short codes; images live in the renderer
gb.configure_column("region_cc",
    cellRenderer=fe.cell_renderer(df["region_cc"].unique()))
AgGrid(df, gridOptions=gb.build(), allow_unsafe_jscode=True)   # [st-aggrid] gotcha 2

# 4) currency codes -> country flags (USD->us, EUR->eu, GBP->gb, ...)
gb.configure_column("ccy",
    cellRenderer=fe.cell_renderer(df["ccy"].unique(), currency=True))
```

## API

| call | does |
|---|---|
| `flag_uri(code)` | base64 data URI for `"us"`/`"eu"`/`"asia"`…, `None` if no asset (lru_cached) |
| `currency_uri("USD")` | data URI via the currency→country map |
| `flag_img(value, size=18, label=, currency=)` | `<img>` snippet for `st.markdown(..., unsafe_allow_html=True)`; falls back to plain text when no asset |
| `cell_renderer(values, size=, currency=, uppercase=, show_label=)` | `JsCode` renderer for an AgGrid column of country/currency codes |
| `available()` | codes that actually have a bundled PNG |
| `ALIASES` | label→asset overrides (e.g. `"apac": "hk"` shows the hub's flag); resolve BEFORE disk lookup |

## Why it's built this way

- **Data URIs, not files/CDN** — nothing fetched at runtime, so it works
  air-gapped and inside AgGrid's sandboxed cells (same philosophy as
  [st-perspective]'s CDN-free route).
- **`cell_renderer` embeds only the DISTINCT flags, once each** — a 100k-row
  grid with 8 regions carries 8 images in the JS lookup table, not 100k.
  Your DataFrame keeps short string codes; sorting/filtering stay on the code.
- **Graceful fallback** — an unmapped value renders as its raw text, never a
  broken image.
- **Missing a country?** `python fetch_flags.py` on a machine WITH internet
  (edit `COUNTRIES` first), then ship the updated `flags/` folder. Runtime
  never needs the network.

## Gotchas

- AgGrid renderer needs `allow_unsafe_jscode=True` or it's silently dropped
  ([st-aggrid] gotcha 2). `ImageColumn`/markdown routes need no JsCode.
- `st.markdown` needs `unsafe_allow_html=True` for the `<img>` snippet.
- Region labels that aren't ISO codes (e.g. `us-east-1`, `APAC`) need either
  an `ALIASES` entry or a small `label -> cc` map in your app — the module
  looks up assets by name, it doesn't parse cloud-region strings.
- Sorting: keep the CODE as the cell value (the renderer only draws) — an
  `<img>`-in-value column would sort lexically on HTML.
- The currency map covers ~40 majors; extend `CCY_TO_COUNTRY` for exotics.
