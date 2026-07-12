"""st-paramtree lab — runnable proof of the schema-driven advanced-parameters UI.

Run:  python -m streamlit run st-paramtree/st_paramtree_lab.py

Demo domain is a generic media-export pipeline (video/audio/performance/output)
— deep tree, presets, conditional visibility. Swap in your own schema.
Also passes streamlit.testing.v1.AppTest with zero exceptions.
"""
from __future__ import annotations

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paramtree import ParamTree  # noqa: E402

# --------------------------------------------------------------------------
# Schema: branch = dict without "type"; leaf = dict with "type". Leaves carry
# their own metadata (default/bounds/choices/help/visible_if).
# --------------------------------------------------------------------------
SCHEMA = {
    "Video": {
        "Codec": {
            "codec":            {"type": "enum", "default": "H264", "choices": ["H264", "H265", "AV1", "COPY"],
                                 "help": "COPY passes the stream through untouched"},
            "quality":          {"type": "int", "default": 23, "min": 0, "max": 51, "step": 1,
                                 "help": "Constant rate factor (lower = better)",
                                 "visible_if": ("Video.Codec.codec", "!=", "COPY")},
            "two_pass":         {"type": "bool", "default": False,
                                 "visible_if": ("Video.Codec.codec", "!=", "COPY")},
            "max_bitrate_kbps": {"type": "int", "default": 8000, "min": 0, "max": 100000, "step": 500,
                                 "visible_if": ("Video.Codec.codec", "!=", "COPY")},
        },
        "Scaling": {
            "resolution": {"type": "enum", "default": "SOURCE", "choices": ["SOURCE", "720p", "1080p", "4K"]},
            "fps":        {"type": "enum", "default": "SOURCE", "choices": ["SOURCE", "24", "30", "60"]},
            "denoise":    {"type": "bool", "default": False},
        },
    },
    "Audio": {
        "Encode": {
            "codec":        {"type": "enum", "default": "AAC", "choices": ["AAC", "OPUS", "FLAC", "COPY"]},
            "bitrate_kbps": {"type": "int", "default": 192, "min": 64, "max": 512, "step": 32,
                             "visible_if": ("Audio.Encode.codec", "in", ["AAC", "OPUS"])},
        },
        "Loudness": {
            "normalize":             {"type": "bool", "default": False},
            "normalize_target_lufs": {"type": "float", "default": -14.0, "min": -30.0, "max": -5.0,
                                      "step": 0.5, "format": "%.1f",
                                      "visible_if": ("Audio.Loudness.normalize", "==", True)},
        },
    },
    "Performance": {
        "Compute": {
            "threads": {"type": "int",  "default": 8, "min": 1, "max": 64, "step": 1},
            "gpu":     {"type": "bool", "default": False},
            "hwaccel": {"type": "enum", "default": "NONE",
                        "choices": ["NONE", "NVENC", "QSV", "VIDEOTOOLBOX"],
                        "visible_if": ("Performance.Compute.gpu", "==", True)},
        },
    },
    "Output": {
        "Container": {
            "container":      {"type": "enum",   "default": "MP4", "choices": ["MP4", "MKV", "WEBM"]},
            "faststart":      {"type": "bool",   "default": True, "help": "Move index to front for streaming"},
            "metadata_title": {"type": "string", "default": ""},
        },
    },
}

# Named baselines; {} = all defaults. Applied with replace semantics.
PRESETS = {
    "Balanced (defaults)": {},
    "Draft (fast)": {
        "Video.Codec.codec": "H264",
        "Video.Codec.quality": 30,
        "Video.Scaling.resolution": "720p",
        "Performance.Compute.gpu": True,
        "Performance.Compute.hwaccel": "NVENC",
    },
    "Maximum quality": {
        "Video.Codec.codec": "H265",
        "Video.Codec.quality": 18,
        "Video.Codec.two_pass": True,
        "Video.Scaling.resolution": "4K",
        "Audio.Encode.codec": "FLAC",
    },
}

# --------------------------------------------------------------------------
st.set_page_config(page_title="paramtree lab", page_icon="🎛️", layout="wide")

# One instance; `namespace` lets several independent trees coexist in one app.
tree = ParamTree(SCHEMA, namespace="export", presets=PRESETS)

with st.sidebar:
    st.title("🎛️ Export job")
    st.caption("Schema-driven advanced parameters")
    st.divider()
    tree.open_button("⚙ Advanced settings ({n} overridden)")  # opens the modal

st.header("st-paramtree lab")
st.caption("Everything below derives from the schema — no per-widget UI code. "
           "Open **Advanced settings** in the sidebar; the job spec updates live.")

overrides = tree.overrides()
c1, c2 = st.columns(2)
with c1:
    st.subheader(f"Job spec · diff from defaults ({len(overrides)})")
    st.caption("What you'd send to your engine — only what changed.")
    st.json(overrides if overrides else {"note": "all defaults — nothing overridden"})
with c2:
    st.subheader("Full resolved config")
    st.json(tree.values())

st.divider()
st.caption("The tree also renders inline (sidebar/expander/column) via `tree.render()` "
           "instead of a modal — never both for the same tree in one run.")
