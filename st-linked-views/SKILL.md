---
name: st-linked-views
description: Fast "dashboard" pages in Streamlit where a key input (a code, an id, a name) drives several LINKED tables and charts, and clicking one view filters the others — one cached DuckDB fetch per key, a fragment holding every linked view so clicks never re-query, selection→Python filter fan-out, Perspective as an optional explore panel. Use when the ask is "several tables and charts linked together reacting quickly to an input", when clicks feel slow because they re-run queries, or when deciding between Streamlit, Perspective and Dash for interactive linking.
---

# Linked views — one fetch per key, instant-feel linking (Streamlit 1.55+)

Runnable proof: `st_linked_views_lab.py` + `test_st_linked_views.py` (fetch
counter proves the discipline). Companions: [st-core] fragments, [st-duckdb]
the lake query, [st-dataframe] selection, [st-altair] charts, [st-perspective].

## The architecture — split the two kinds of fast

1. **Key input changes** (user types/picks a code) → a *server* trip is
   unavoidable. Make it ONE cached query returning a small bundle for ALL the
   views, and make the lake layout serve it (sort by the key inside each date
   partition → `WHERE key = X` is a zone-map hit; measured 10 ms vs 159 ms).
2. **Clicks between views** (row in table A filters table B + charts) → must
   never touch the lake. The bundle is already in memory; a click is a
   Python filter + a **fragment** rerun (hundreds of ms, no full page).

```python
service = st.selectbox("code", CODES, key="service")      # key input: OUTSIDE fragment

@st.cache_data(ttl="10m", show_spinner=False)
def fetch_bundle(code: str) -> dict[str, pd.DataFrame]:   # ONE lake pass per key
    cur = db().cursor()                                   # [st-duckdb]
    base = f"FROM events WHERE service = '{code}'"
    return {"regions": cur.execute(f"SELECT region, avg(latency_ms) avg_ms {base} GROUP BY 1").df(),
            "detail":  cur.execute(f"SELECT region, endpoint, sum(requests) requests {base} GROUP BY 1,2").df(),
            "daily":   cur.execute(f"SELECT date, region, avg(latency_ms) avg_ms {base} GROUP BY 1,2").df()}

def apply_selection(bundle, region):                      # PURE Python -> unit-testable
    if region is None: return bundle                      # nothing selected = all
    return {k: (v[v["region"] == region] if "region" in v and k != "regions" else v)
            for k, v in bundle.items()}

@st.fragment
def linked_views(bundle):                                 # EVERY linked view lives here
    ev = st.dataframe(bundle["regions"], on_select="rerun", selection_mode="single-row",
                      key="regions_grid", hide_index=True, width="stretch")
    rows = ev["selection"]["rows"]                        # [] when nothing selected
    region = bundle["regions"].iloc[rows[0]]["region"] if rows else None
    views = apply_selection(bundle, region)
    st.altair_chart(line_chart(views["daily"]), width="stretch")
    st.dataframe(views["detail"], hide_index=True, width="stretch")

bundle = fetch_bundle(service)                            # outside the fragment
linked_views(bundle)
```

## Rules (each verified by the lab/test)

- **Fetch outside, link inside.** `fetch_bundle()` is called in the main
  script and the bundle is passed INTO the fragment. A click reruns only the
  fragment, which re-uses the argument — the lab's fetch counter stays flat
  across reruns and clicks, and moves by exactly one per NEW key (cache hit
  when you come back to an old key).
- **The selector table never filters itself** — otherwise the clicked row
  disappears and the selection is lost. Filter siblings only.
- **Empty selection = "all"**: `rows == []` on first render and after
  deselect; never index `rows[0]` unguarded. `selection_mode="single-row"`
  (the `-required` variant is 1.56+ — don't emit it for 1.55).
- **Cache key = the code string only.** No DataFrame args to the cached
  function; derive everything from the key. Add `ttl` for live data.
- **Keep the bundle small** — aggregate in SQL, return the few hundred rows
  the views need, never the raw rows ([st-duckdb] results rule).
- Factor the filter into a pure function → test it directly (AppTest cannot
  click a grid). AppTest still proves the fetch discipline via the counter.

## Perspective's role here — supporting panel, not the fabric

`streamlit-perspective` is the best free-form pivot/chart explorer over the
same bundle, but (verified in [st-perspective]) **its clicks never reach
Python and separate viewers don't share a table** — so it cannot drive the
other widgets. Give it one expander: `perspective_static(bundle["detail"])`.

## When this isn't enough → zero-latency linking

If users need clicks with NO server trip at all, two verified routes:

- **Dash** — [dash-linked-views]: the same bundle in `dcc.Store` plus a
  10-line `clientside_callback` JavaScript template (copy verbatim) that
  filters rows and toggles per-category traces in the browser. Measured:
  zero `_dash-update-component` requests per click. This is the strongest
  argument for the Dash side of a strategic app.
- **Perspective workspace** — every view over ONE in-browser table with
  client-side filter propagation ([st-perspective] explains why the Streamlit
  component can't do this today; it needs a custom component + self-hosted JS).

Build this Streamlit version first; move to the Dash twin when click latency
is what users complain about.
