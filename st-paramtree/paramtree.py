"""paramtree — a schema-driven "advanced parameters" UI for Streamlit.

Render an arbitrarily deep tree of configuration parameters from a plain-data
schema: no per-widget UI code, search, presets, import/export, per-branch
"changed" badges, conditional visibility, and a diff-from-defaults view.

Design in one line: values live in ONE canonical dict in st.session_state
(keyed by dotted path), never on widget keys — because Streamlit deletes a
widget-keyed session_state entry as soon as that widget stops rendering (e.g.
when a modal closes). Widgets seed from the canonical store and sync back on
change. "Overrides" are the leaves whose value differs from the schema default.

Only dependency: streamlit. Copy this file into your project and go.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Iterable

import streamlit as st

# ---------------------------------------------------------------------------
# Default widget renderers.  A renderer takes (label, spec, **kw) where kw
# carries key / help / on_change / args.  Register your own with
# ParamTree.register_widget(type_name, fn) to support extra leaf types.
# ---------------------------------------------------------------------------

def _w_bool(label, spec, **kw):
    st.checkbox(label, **kw)


def _w_int(label, spec, **kw):
    st.number_input(label, min_value=spec.get("min"), max_value=spec.get("max"),
                    step=spec.get("step", 1), **kw)


def _w_float(label, spec, **kw):
    st.number_input(label, min_value=spec.get("min"), max_value=spec.get("max"),
                    step=spec.get("step", 0.01), format=spec.get("format", "%.4f"), **kw)


def _w_enum(label, spec, **kw):
    st.selectbox(label, spec["choices"], **kw)


def _w_string(label, spec, **kw):
    st.text_input(label, **kw)


DEFAULT_WIDGETS: dict[str, Callable] = {
    "bool": _w_bool, "int": _w_int, "float": _w_float, "enum": _w_enum, "string": _w_string,
}


def _eval_condition(cond, values: dict) -> bool:
    """Evaluate a leaf's `visible_if`.

    Accepts a callable ``(values) -> bool`` or a tuple ``(path, op, value)`` with
    op in {"==", "!=", "in", "not in"}.
    """
    if cond is None:
        return True
    if callable(cond):
        return bool(cond(values))
    path, op, ref = cond
    left = values.get(path)
    if op == "==":
        return left == ref
    if op == "!=":
        return left != ref
    if op == "in":
        return left in ref
    if op == "not in":
        return left not in ref
    raise ValueError(f"unknown visible_if operator: {op!r}")


class ParamTree:
    """A schema-driven parameter tree.

    Parameters
    ----------
    schema : nested dict. A node is a *branch* if it has no ``type`` key and a
        *leaf* (a real parameter) if it does. Leaf spec keys: ``type`` (one of
        the registered widget types), ``default``, optional ``help``,
        type-specific keys (``min``/``max``/``step``/``format`` for numbers,
        ``choices`` for enums), and optional ``visible_if`` (see _eval_condition).
    namespace : unique string so multiple trees can coexist in one app without
        colliding in st.session_state.
    presets : optional ``{name: {dotted_path: value}}`` baselines; ``{}`` = all
        defaults. Applied with replace semantics.
    """

    def __init__(self, schema: dict, namespace: str = "params", presets: dict | None = None):
        self.schema = schema
        self.ns = namespace
        self.presets = presets or {}
        self._widgets = dict(DEFAULT_WIDGETS)
        self._store = f"__pt_{namespace}_vals"

    # ----- schema walking -------------------------------------------------
    def iter_leaves(self, node: dict | None = None, path: str = "") -> Iterable[tuple[str, dict]]:
        node = self.schema if node is None else node
        for key, spec in node.items():
            dotted = f"{path}.{key}" if path else key
            if isinstance(spec, dict) and "type" in spec:
                yield dotted, spec
            elif isinstance(spec, dict):
                yield from self.iter_leaves(spec, dotted)

    def defaults(self) -> dict:
        return {p: s["default"] for p, s in self.iter_leaves()}

    # ----- state ----------------------------------------------------------
    def ensure_seeded(self) -> None:
        """Create the canonical store on first use; pick up newly added leaves."""
        if self._store not in st.session_state:
            st.session_state[self._store] = self.defaults()
        else:
            store = st.session_state[self._store]
            for p, s in self.iter_leaves():
                store.setdefault(p, s["default"])

    def values(self) -> dict:
        """Full resolved config (defaults + overrides)."""
        self.ensure_seeded()
        return dict(st.session_state[self._store])

    def overrides(self) -> dict:
        """Only the leaves whose value differs from the schema default."""
        store = st.session_state.get(self._store, {})
        return {p: store.get(p, s["default"]) for p, s in self.iter_leaves()
                if store.get(p, s["default"]) != s["default"]}

    def apply(self, mapping: dict) -> None:
        """Replace semantics: reset all leaves to default, then apply `mapping`.

        Updates the canonical store AND live widget keys, so an open dialog
        reflects the change immediately. Call before the tree renders this run.
        """
        valid = dict(self.iter_leaves())
        new = {p: s["default"] for p, s in valid.items()}
        for p, v in mapping.items():
            if p in valid:
                new[p] = v
        st.session_state[self._store] = new
        for p, v in new.items():
            st.session_state[self._wkey(p)] = v

    def reset(self) -> None:
        self.apply({})

    def register_widget(self, type_name: str, render_fn: Callable) -> None:
        self._widgets[type_name] = render_fn

    # ----- internals ------------------------------------------------------
    def _wkey(self, path: str) -> str:
        return f"__pt_{self.ns}_w::{path}"

    def _k(self, name: str) -> str:
        return f"__pt_{self.ns}_{name}"

    def _sync(self, path: str) -> None:
        st.session_state[self._store][path] = st.session_state[self._wkey(path)]

    def _visible(self, spec: dict) -> bool:
        return _eval_condition(spec.get("visible_if"), st.session_state[self._store])

    def _override_count(self, node: dict, path: str) -> int:
        store = st.session_state.get(self._store, {})
        return sum(1 for p, s in self.iter_leaves(node, path)
                   if store.get(p, s["default"]) != s["default"])

    def _leaf(self, path: str, spec: dict) -> None:
        wkey = self._wkey(path)
        if wkey not in st.session_state:            # seed the ephemeral widget
            st.session_state[wkey] = st.session_state[self._store].get(path, spec["default"])
        render = self._widgets.get(spec["type"])
        if render is None:
            st.error(f"No widget registered for type {spec['type']!r} ({path})")
            return
        render(path.split(".")[-1], spec,
               key=wkey, help=spec.get("help"), on_change=self._sync, args=(path,))
        if st.session_state[self._store].get(path) != spec["default"]:
            st.caption(f"↳ changed · default `{spec['default']}`")

    def _branch(self, node: dict, path: str) -> None:
        leaves = [(k, s) for k, s in node.items() if isinstance(s, dict) and "type" in s]
        branches = [(k, s) for k, s in node.items() if isinstance(s, dict) and "type" not in s]
        visible = [(k, s) for k, s in leaves if self._visible(s)]
        if visible:
            cols = st.columns(2)
            for i, (k, s) in enumerate(visible):
                with cols[i % 2]:
                    self._leaf(f"{path}.{k}", s)
        for k, s in branches:
            n = self._override_count(s, f"{path}.{k}")
            title = k + (f"  ·  {n} changed" if n else "")
            with st.expander(title):
                self._branch(s, f"{path}.{k}")

    def _body(self) -> None:
        """Toolbar + presets + tree. Reused by dialog() and render()."""
        self.ensure_seeded()

        top = st.columns([3, 1, 1])
        query = top[0].text_input("Search", key=self._k("search"), label_visibility="collapsed",
                                  placeholder="🔍 filter by name or path…")
        top[1].metric("Overridden", len(self.overrides()))
        if top[2].button("Reset all", key=self._k("reset"), use_container_width=True):
            self.reset()
            st.toast("Reset to defaults")

        with st.expander("Presets · import / export · raw"):
            if self.presets:
                pc = st.columns([2, 1])
                preset = pc[0].selectbox("Preset baseline", list(self.presets), key=self._k("preset"))
                if pc[1].button("Apply preset", key=self._k("apply_preset"), use_container_width=True):
                    self.apply(self.presets[preset])
                    st.toast(f"Applied '{preset}'")

            io = st.columns(2)
            io[0].download_button("⬇ Export overrides", json.dumps(self.overrides(), indent=2),
                                  f"{self.ns}_overrides.json", "application/json",
                                  key=self._k("export"), use_container_width=True)
            up = io[1].file_uploader("Import overrides JSON", type="json", key=self._k("upload"),
                                     label_visibility="collapsed")
            if up is not None:
                sig = (up.name, up.size)
                if st.session_state.get(self._k("loaded_sig")) != sig:
                    try:
                        self.apply(json.load(up))
                        st.session_state[self._k("loaded_sig")] = sig
                        st.toast("Imported overrides")
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Bad JSON: {e}")

            raw_key = self._k("raw")
            if raw_key not in st.session_state:
                st.session_state[raw_key] = json.dumps(self.overrides(), indent=2)
            st.text_area("Raw overrides (edit, then apply)", key=raw_key, height=140)
            rc = st.columns(2)
            if rc[0].button("Apply raw JSON", key=self._k("apply_raw"), use_container_width=True):
                try:
                    self.apply(json.loads(st.session_state[raw_key]))
                    st.toast("Applied raw JSON")
                except Exception as e:  # noqa: BLE001
                    st.error(f"Bad JSON: {e}")
            if rc[1].button("Refresh from current", key=self._k("refresh_raw"), use_container_width=True):
                st.session_state[raw_key] = json.dumps(self.overrides(), indent=2)

        st.divider()

        if query:
            matches = [(p, s) for p, s in self.iter_leaves()
                       if query.lower() in p.lower() and self._visible(s)]
            st.caption(f"{len(matches)} match(es)")
            cols = st.columns(2)
            for i, (p, s) in enumerate(matches):
                with cols[i % 2]:
                    st.caption(p)
                    self._leaf(p, s)
        else:
            group = st.selectbox("Group", list(self.schema), key=self._k("group"))
            self._branch(self.schema[group], group)

    # ----- public rendering ----------------------------------------------
    def render(self, container=None) -> None:
        """Render the tree inline (e.g. inside a sidebar/expander/column).

        Note: don't render the same tree both inline and via dialog() in one run
        — they share widget keys and will collide. Use a second ParamTree with a
        different `namespace` if you truly need both surfaces at once.
        """
        if container is not None:
            with container:
                self._body()
        else:
            self._body()

    def dialog(self, title: str = "Advanced parameters", width: str = "large") -> None:
        """Open the tree in a modal dialog."""
        @st.dialog(title, width=width)
        def _modal():
            self._body()
            st.divider()
            if st.button("Done", key=self._k("done"), type="primary"):
                st.rerun()  # closing the dialog
        _modal()

    def open_button(self, label: str = "⚙ Advanced ({n} overridden)", **btn_kwargs) -> None:
        """A button labelled with the live override count that opens the dialog."""
        self.ensure_seeded()
        n = len(self.overrides())
        btn_kwargs.setdefault("use_container_width", True)
        if st.button(label.format(n=n), key=self._k("open"), **btn_kwargs):
            self.dialog()
