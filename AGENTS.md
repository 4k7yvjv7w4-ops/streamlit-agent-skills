# AGENTS.md — working in this repo

Guidance for an AI coding agent (or a human) editing this bundle. User-facing
overview lives in `README.md`; this file is the contributor/maintainer brief.

## What this is

Eleven self-contained Streamlit skills in Roo / `SKILL.md` format. Each skill is a
directory with a `SKILL.md` reference doc, optionally a runnable `*_lab.py`
proof and a `data/` folder. Written for a mid-size model (target: Qwen 3.6-27B)
that loads **one skill per task** (~2k tokens each), never all of them at once.

## Prime rule — keep the public bundle self-contained

This is a **public** bundle, deliberately decoupled from the private source
project it was distilled from. Examples, variable names, and sample data use
synthetic service-latency telemetry (services / regions / percentiles /
latency-ms / request counts). Never introduce identifiers from the private
project — real column names, data sources, internal paths, or UI labels. Do
**not** regenerate this bundle from the private codebase; it is maintained
directly.

**Guardrail:** `./check_generic.sh` greps every `.md`/`.py` and fails on any
private identifier. The identifier list is deliberately kept **out** of this
repo — it lives in a local, gitignored file `.check_generic.local` (one term
per line) so the terms themselves never ship. A tracked pre-commit hook
(`.githooks/pre-commit`) runs the check; a clone without the local file simply
skips it. Enable the hook once per clone:

```sh
git config core.hooksPath .githooks
```

Run `./check_generic.sh` before every commit; if it fails, rename the flagged
identifier to a synthetic equivalent (don't delete the check). Add any new
private identifier to `.check_generic.local`, never to a tracked file.

## Layout

| Dir | Covers | Lab |
|---|---|---|
| `st-core/` | execution model: reruns, session_state, callbacks, forms, caching, fragments — load for ANY Streamlit app | `st_core_lab.py` |
| `st-layout/` | columns, containers, tabs, expanders, dialogs, sidebar, multipage, sizing, CSS targeting | `st_layout_lab.py` + `st_nav_params_lab.py` (page→page params) |
| `st-dataframe/` | native table: `st.dataframe`, `column_config`, `st.data_editor` | `st_dataframe_lab.py` |
| `st-aggrid/` | interactive grids (AG Grid): selection→Python, styling, grouping, editing, license map | `aggrid_lab.py` + `data/` |
| `st-pivot/` | official pivot component: pivot / tree / flat modes, click→Python, conditional formatting | `st_pivot_lab.py` |
| `st-perspective/` | FINOS Perspective for client-side pivoting on large tables — CDN embed + CDN-free `streamlit-perspective` route | `perspective_offline_lab.py` |
| `st-altair/` | charts (default over Plotly): mark/encode, column:TYPE cheat, MaxRowsError, selection→Python, layer/facet | `altair_lab.py` |
| `st-paramtree/` | schema-driven deep-settings tree (modal/inline): search, presets, import/export, visible_if, diff-from-defaults; ships reusable `paramtree.py` | `st_paramtree_lab.py` |
| `st-connection/` | data access: st.connection (SQL/custom BaseConnection), cached queries + ttl, secrets.toml, no-re-query-per-rerun | `st_connection_lab.py` |
| `st-testing/` | headless testing with `AppTest`: drive widgets by key, inject secrets/query_params, assert no exceptions, limits | `st_testing_lab.py` + `test_st_testing.py` |
| `st-parquet/` | parquet/S3 data loading: hive partitioning, pushdown, S3 creds, overwrites, small-files, raw→aggregate rollups; companion to st-connection | `parquet_s3_demo.py` |

Every `SKILL.md` opens with the same 4-line "which grid/component to pick"
decision matrix so the skills cross-reference each other.

## Editing conventions

- Keep each skill self-contained and small (~200 lines / ~2k tokens).
- Prefer adding a demonstration to the lab over asserting a claim in prose.
- Gotchas must be **empirically confirmed** (run it), not lifted from docs.
- No agent-harness-specific idioms — this targets a plain mid-size model in an
  editor (VS Code / JupyterLab), not one specific tool.

## Verifying changes

- Labs are standalone apps: `python -m streamlit run <skill>/<lab>.py`.
- They also pass `streamlit.testing.v1.AppTest` with zero exceptions — run that
  as a smoke check after editing a lab.
- The aggrid lab needs its `data/`: `cd st-aggrid/data && python
  make_sample_data.py` regenerates the seeded parquets.

## Version discipline

- Verified on **Streamlit 1.58** / **streamlit-aggrid 1.2** /
  **streamlit-pivot 0.5**; the labs are the runnable proof.
- The intended deployment target runs **Streamlit 1.55**. Only three API deltas
  exist and all are 1.56+, so avoid or guard them:
  `st.container(autoscroll=)`, `st.dataframe(selection_default=)`,
  `selection_mode="single-row-required"`. The stale-rule notes in `st-layout`
  and `st-dataframe` hold on 1.55. Re-check pins when bumping any version.
