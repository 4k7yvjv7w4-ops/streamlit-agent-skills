---
name: st-paramtree
description: Schema-driven "advanced parameters" UI for Streamlit — render a deep tree of config settings from a plain nested dict (modal or inline) with search, presets, JSON import/export, per-branch change badges, conditional visibility, and a diff-from-defaults view. Use when an app has many (especially rarely-changed, nested) settings that would bloat the main UI, or when you need to serialize only what the user changed.
---

# st-paramtree — deep config trees from data, not widget code

Reusable module: `paramtree.py` in this skill folder — copy it next to your app
(only dependency: `streamlit`). Runnable proof of every claim:
`st_paramtree_lab.py` (`python -m streamlit run st-paramtree/st_paramtree_lab.py`).

**Version guard:** verified on Streamlit **1.59**, API-checked on **1.55**
(`st.dialog` needs ≥ 1.37; the module intentionally uses `use_container_width`,
correct for 1.55 — on 1.58+ it merely warns).

**When NOT to use:** a handful of flat settings → plain widgets are simpler.
Reach for this once the tree is deep or the parameter count is large.

## Quick start

```python
import streamlit as st
from paramtree import ParamTree

SCHEMA = {
    "Group": {                                # branch = dict WITHOUT "type"
        "Subgroup": {
            "mode":    {"type": "enum", "default": "med", "choices": ["low", "med", "high"]},
            "threads": {"type": "int", "default": 8, "min": 1, "max": 64},   # leaf = has "type"
            "verbose": {"type": "bool", "default": False, "help": "extra logging"},
        },
    },
}
tree = ParamTree(SCHEMA, namespace="settings",
                 presets={"Defaults": {}, "Fast": {"Group.Subgroup.mode": "low"}})

with st.sidebar:
    tree.open_button("⚙ Advanced ({n} overridden)")   # opens the modal

engine_input = tree.overrides()   # ONLY leaves ≠ default — serialize this, not values()
full_config  = tree.values()      # defaults merged with overrides
```

## Schema leaf keys

| key | types | meaning |
|---|---|---|
| `type` | all | `bool` `int` `float` `enum` `string` (+ registered customs) |
| `default` | all | baseline; defines what counts as an "override" |
| `help` | all | tooltip |
| `min`/`max`/`step`, `format` | int, float | bounds; float print format e.g. `"%.1f"` |
| `choices` | enum | options list |
| `visible_if` | all | `(dotted.path, op, value)` with op `==` `!=` `in` `not in`, **or** a callable `(values_dict) -> bool` |

Presets: `{name: {dotted_path: value}}`; `{}` = all defaults. Applied with
**replace** semantics (reset to defaults, then apply).

## API

| call | does |
|---|---|
| `ParamTree(schema, namespace=, presets=)` | `namespace` isolates state → several trees per app |
| `.open_button(label="⚙ ({n})")` | launcher button labelled with live override count |
| `.dialog(title=, width="large")` / `.render(container=None)` | modal / inline surface |
| `.values()` / `.overrides()` | full config / diff-from-defaults |
| `.apply(mapping)` / `.reset()` | set (replace semantics) / back to defaults |
| `.register_widget(type_name, fn)` | custom leaf type; `fn(label, spec, **kw)` must create ONE widget passing `key`/`on_change`/`args` from `kw` verbatim |

The modal ships with search (whole tree, by name/path), master-detail group
nav, per-branch "N changed" badges, presets, JSON import/export, raw editor,
reset.

## Multipage — dedicated editor pages, main page reads the store

A ParamTree's canonical store is app-wide `session_state`, so **the tree IS a
shared store across `st.navigation` pages — you don't "pass" config, you read
the same `namespace` from wherever you need it** (verified: a second
same-namespace ParamTree reads another page's edits with the tree unrendered).
Pattern for deep model config + rich per-topic editor pages (e.g. custom SLA
overrides, per-region alert rules, …):

- **Sidebar tree = shared chrome:** construct it in the ENTRY file, before
  `pg.run()`, so `open_button()` shows on every page. Rarely-touched model
  params live here.
- **Dedicated editor page per topic:** the page builds
  `ParamTree(SLA_SCHEMA, namespace="sla").render()` — the full inline surface
  (search / presets / import-export).
- **Main compute page just READS — no render:**
  ```python
  model = ParamTree(MODEL_SCHEMA, namespace="model").overrides()  # sidebar tree
  sla   = ParamTree(SLA_SCHEMA,   namespace="sla").overrides()    # same ns → same store
  run(engine_cfg=model, sla=sla)
  ```

Rules that make it robust:
- **Namespace + schema are the contract.** The editor page and the reader must
  use the SAME `namespace` AND the SAME schema object — put schemas in a
  `schemas.py` both import, so leaf paths line up.
- `overrides()` = the compact diff to hand the engine; `values()` = full
  resolved config. Serialize `overrides()`.
- **Store survives navigation, NOT a browser refresh / bookmarked direct entry**
  (session_state lifetime — see [st-layout] "Passing params page → page"). For a
  deep link that must carry config, persist `overrides()` to file/db (JSON
  export is built in) and reload it at the top; query_params is too small/
  string-only for a deep tree.
- **Per-ENTITY config** (a different threshold set per service) needs one store
  per entity — a single global namespace holds ONE config. Either
  `namespace=f"sla_{service_id}"` (one tree per entity), or harvest
  `overrides()` into your own `{entity: cfg}` dict on save.
- Don't render the same namespace twice in one run (gotcha below) — here each
  page renders its own tree once and the main page renders none, so you're safe.

## THE gotcha — why values don't live on widget keys

Streamlit **deletes a widget-keyed `session_state` entry as soon as that widget
stops rendering** — e.g. every time a modal closes. If widget keys were the
source of truth, every override would silently vanish on close (symptom: badge
says "3 overridden" inside the dialog, `overrides()` returns `{}` after).
So: canonical values live in ONE plain (non-widget) dict,
`st.session_state["__pt_<ns>_vals"]`; each widget is seeded from it and syncs
back via `on_change`. Preserve this if you modify the module.

Consequences:
- `overrides()`/`values()` read the canonical store → correct even with the
  dialog closed.
- `apply()` writes canonical store **and** live widget keys, and must run
  **before** the tree's widgets instantiate this run (Streamlit forbids
  mutating a widget's state after it renders) — hence presets/import/reset sit
  at the top of the dialog body.
- Widgets are created with `key=` and **no** `value=`/`index=` — they read the
  seeded `session_state[key]`.

## Other gotchas (verified)

- **Never render the same tree twice in one run** (`dialog()` + `render()`):
  shared widget keys collide → `StreamlitDuplicateElementKey`. Need both
  surfaces → second `ParamTree` with a different `namespace`.
- Embedding leaves in an `st.form`: Enter in a text input submits the form —
  pass `st.form(..., enter_to_submit=False)` if that surprises users.
- `visible_if` hides a leaf but keeps its value: a hidden overridden leaf still
  counts in `overrides()`. Reset it if hide-should-clear is desired.
- Testable headlessly: drive it with `streamlit.testing.v1.AppTest`
  (`at.selectbox(...).set_value(...).run()`) — the lab passes AppTest clean.
