#!/usr/bin/env python3
"""Run a repo probe script on a Modal H100 (sm_90).

Usage::

    modal run tools/modal_h100_probe.py --script tests/asm_construct/probe_alulite_latency.py
    modal run tools/modal_h100_probe.py --script tests/asm_construct/probe_alulite_latency.py --args "--reps 5"

The image bakes in ``assembler/`` + ``sm90.json`` (stable layers, rebuilt only
when they change).  The probe script text is shipped per-call, so iterating on
a probe does not rebuild the image.  The remote process runs with
``ASSEMBLER_ARCH=sm90`` so plain ``assemble(source)`` targets Hopper.
"""

from __future__ import annotations

import pathlib

import modal

REPO = pathlib.Path(__file__).resolve().parents[1]

IMAGE = (
    modal.Image.debian_slim(python_version="3.11")
    .add_local_dir(REPO / "assembler", "/repo/assembler")
    .add_local_file(REPO / "sm90.json", "/repo/sm90.json")
    .add_local_dir(REPO / "tests" / "asm_construct", "/repo/tests/asm_construct")
)

app = modal.App("h100-probe", image=IMAGE)


@app.function(gpu="H100", timeout=600)
def run_probe(script_name: str, args: str = "", timeout_s: int = 550) -> str:
    import os
    import subprocess

    target = pathlib.Path("/repo/tests/asm_construct") / script_name
    env = dict(os.environ, ASSEMBLER_ARCH="sm90")
    try:
        r = subprocess.run(
            ["python3", str(target), *args.split()],
            capture_output=True, text=True, cwd="/repo", env=env,
            timeout=timeout_s)
        return r.stdout + ("\n--- stderr ---\n" + r.stderr if r.stderr.strip() else "")
    except subprocess.TimeoutExpired:
        return "REMOTE TIMEOUT"


@app.local_entrypoint()
def main(script: str, args: str = ""):
    # script is a repo-relative path under tests/asm_construct (or a bare name)
    name = script.rsplit("/", 1)[-1]
    print(run_probe.remote(name, args))
