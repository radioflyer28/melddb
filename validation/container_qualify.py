"""Entrypoint for a disposable official Python image with a read-only repo mount."""
import os
import subprocess
import sys

subprocess.run([sys.executable, "-m", "pip", "install", "uv"], check=True)
os.environ["UV_CACHE_DIR"] = "/tmp/uv-cache"
version = f"{sys.version_info.major}.{sys.version_info.minor}"
subprocess.run(["uv", "python", "install", version], check=True)
python = subprocess.check_output(["uv", "python", "find", "--managed-python", version], text=True).strip()
subprocess.run([python, "/repo/validation/qualify.py",
                "/repo/dist/melddb-0.1.0rc1-py3-none-any.whl", "/repo/dist/melddb-0.1.0rc1.tar.gz",
                "--output", f"/evidence/s11-linux-{sys.version_info.major}{sys.version_info.minor}.json"], check=True)
