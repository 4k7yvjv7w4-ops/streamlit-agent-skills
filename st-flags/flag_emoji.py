"""
flag_emoji — offline country-flag images for Streamlit / st_aggrid.

Reads flag PNGs from the local ./flags folder and serves them as base64
data URIs, so nothing is fetched over HTTP at runtime. Suitable for
locked-down / air-gapped environments.

Assets: Twemoji (https://github.com/jdecked/twemoji), CC-BY 4.0.

Quick use
---------
    import flag_emoji as fe

    # In st.markdown:
    st.markdown(fe.flag_img("us") + " USD", unsafe_allow_html=True)

    # In an AgGrid column (cell values are country codes like "us","eu"):
    from st_aggrid import AgGrid, GridOptionsBuilder
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_column("region",
                        cellRenderer=fe.cell_renderer(df["region"].unique()))
    AgGrid(df, gridOptions=gb.build(), allow_unsafe_jscode=True)

    # If the column holds currency codes (USD, EUR, ...):
    gb.configure_column("ccy",
                        cellRenderer=fe.cell_renderer(df["ccy"].unique(),
                                                      currency=True))
"""
from __future__ import annotations

import base64
import functools
import json
from pathlib import Path

FLAG_DIR = Path(__file__).resolve().parent / "flags"

# Currency -> ISO country code, for FX / rates tables.
CCY_TO_COUNTRY = {
    "USD": "us", "EUR": "eu", "GBP": "gb", "JPY": "jp", "CHF": "ch",
    "CAD": "ca", "AUD": "au", "NZD": "nz", "CNY": "cn", "CNH": "cn",
    "HKD": "hk", "SGD": "sg", "TWD": "tw", "KRW": "kr", "INR": "in",
    "SEK": "se", "NOK": "no", "DKK": "dk", "PLN": "pl", "CZK": "cz",
    "HUF": "hu", "RON": "ro", "TRY": "tr", "RUB": "ru", "UAH": "ua",
    "IDR": "id", "THB": "th", "MYR": "my", "PHP": "ph", "VND": "vn",
    "ZAR": "za", "AED": "ae", "SAR": "sa", "QAR": "qa", "ILS": "il",
    "EGP": "eg", "NGN": "ng", "MXN": "mx", "BRL": "br", "CLP": "cl",
    "COP": "co", "ARS": "ar", "PEN": "pe",
}

# Optional label -> asset aliases. Handy when a region label should show a
# specific hub's flag (e.g. an "APAC" column showing the Hong Kong flag).
# Aliases resolve BEFORE the on-disk lookup, so they can override a same-named
# file. Targets are any bundled asset name (country code or region globe).
ALIASES = {
    "apac": "hk",   # APAC region -> Hong Kong hub flag
    # "asia": "hk", # uncomment to show the HK flag instead of the globe
}


def _norm(value: str, currency: bool) -> str | None:
    """Map an input value to a bundled asset name, or None."""
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    key = v.lower()
    if key in ALIASES:          # aliases win, so a label can point at a hub flag
        return ALIASES[key]
    if currency:
        return CCY_TO_COUNTRY.get(v.upper())
    return key


@functools.lru_cache(maxsize=None)
def flag_uri(code: str) -> str | None:
    """base64 data URI for a country code (e.g. 'us'), or None if missing."""
    if not code:
        return None
    p = FLAG_DIR / f"{code.lower()}.png"
    if not p.exists():
        return None
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def currency_uri(ccy: str) -> str | None:
    """base64 data URI for a currency code (e.g. 'USD'), or None."""
    return flag_uri(CCY_TO_COUNTRY.get(str(ccy).upper(), ""))


def available() -> list[str]:
    """Country codes that actually have a bundled PNG."""
    return sorted(p.stem for p in FLAG_DIR.glob("*.png"))


def flag_img(value: str, size: int = 18, label: str | None = None,
             currency: bool = False) -> str:
    """
    An <img> HTML snippet for st.markdown(..., unsafe_allow_html=True).
    Falls back to the raw text if no flag is found.
    `label` overrides the trailing text (default: none).
    """
    code = _norm(value, currency)
    uri = flag_uri(code) if code else None
    if uri is None:
        return "" if label is None else str(label)
    tag = (f'<img src="{uri}" width="{size}" '
           f'style="vertical-align:-3px">')
    return tag if label is None else f"{tag} {label}"


def cell_renderer(values, size: int = 18, uppercase: bool = True,
                  currency: bool = False, show_label: bool = True):
    """
    Build an st_aggrid.JsCode cell renderer for a column whose values are
    country codes ('us','eu',...) or currency codes (currency=True).

    Only the *distinct* flags in `values` are embedded — once each — so the
    grid payload stays small regardless of row count. Cell values in your
    DataFrame stay as short strings; the images live in the renderer.
    """
    from st_aggrid import JsCode  # imported lazily so the module loads anywhere

    lut: dict[str, str] = {}
    for v in values:
        code = _norm(v, currency)
        uri = flag_uri(code) if code else None
        if uri is not None:
            lut[str(v)] = uri
    lut_json = json.dumps(lut)

    label_expr = (
        "''" if not show_label
        else ("' ' + String(p.value).toUpperCase()" if uppercase
              else "' ' + String(p.value)")
    )
    return JsCode(
        "function(p){"
        f"  var L={lut_json};"
        "   var u = L[p.value];"
        "   if(!u){return p.value;}"
        f'  return \'<img src="\' + u + \'" width="{size}" '
        "style=\"vertical-align:-3px\">' + " + label_expr + ";"
        "}"
    )
