"""Vendor Bootstrap 5 CSS into skeleton/assets/ WITHOUT touching a CDN.

The CSS ships inside the Bootstrap-Flask wheel on PyPI, so this works wherever
`pip` works (corporate index/proxy):   python fetch_bootstrap_css.py
"""
import glob
import pathlib
import subprocess
import sys
import tempfile
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "skeleton" / "assets" / "bootstrap.min.css"
with tempfile.TemporaryDirectory() as tmp:
    subprocess.check_call([sys.executable, "-m", "pip", "download", "-q", "--no-deps",
                           "-d", tmp, "Bootstrap-Flask"])
    whl = zipfile.ZipFile(glob.glob(f"{tmp}/*.whl")[0])
    OUT.write_bytes(whl.read("flask_bootstrap/static/bootstrap5/css/bootstrap.min.css"))
print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
