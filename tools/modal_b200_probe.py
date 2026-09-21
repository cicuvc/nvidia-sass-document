#!/usr/bin/env python3
"""Run an assembler probe script on a Modal B200 (sm_100a).

Usage::

    modal run tools/modal_b200_probe.py \
      --script tests/asm_construct/probe_icache_capacity.py \
      --args "--sizes-kib 32,48,64 --reps 3"

The image carries the assembler, sm100 database, and asm_construct probes so
scripts which generate heap-resident SASS after device allocation work without
ptxas or nvcc.  Plain ``assemble``/``assemble_flat`` calls target sm100a via
``ASSEMBLER_ARCH``.
"""

from __future__ import annotations

import pathlib

import modal


REPO = pathlib.Path(__file__).resolve().parents[1]

IMAGE = (
    modal.Image.from_registry(
        "nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.11"
    )
    .entrypoint([])
    .add_local_dir(REPO / "assembler", "/repo/assembler")
    .add_local_file(REPO / "sm100.json", "/repo/sm100.json")
    .add_local_dir(REPO / "sassdbg", "/repo/sassdbg")
    .add_local_dir(REPO / "tests" / "asm_construct",
                   "/repo/tests/asm_construct")
)

app = modal.App("b200-assembler-probe", image=IMAGE)


@app.function(gpu="B200", timeout=1200)
def run_probe(script_name: str, args: str = "", timeout_s: int = 1100) -> str:
    import os
    import subprocess

    relative = pathlib.PurePosixPath(script_name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"script must be relative to /repo: {script_name!r}")
    if len(relative.parts) == 1:
        relative = pathlib.PurePosixPath("tests/asm_construct") / relative
    target = pathlib.Path("/repo") / relative
    env = dict(os.environ, ASSEMBLER_ARCH="sm100a")
    try:
        result = subprocess.run(
            ["python3", str(target), *args.split()],
            capture_output=True,
            text=True,
            cwd="/repo",
            env=env,
            timeout=timeout_s,
        )
        output = result.stdout
        if result.stderr.strip():
            output += "\n--- stderr ---\n" + result.stderr
        if result.returncode:
            output += f"\n--- exit code {result.returncode} ---\n"
        return output
    except subprocess.TimeoutExpired:
        return "REMOTE TIMEOUT"


@app.local_entrypoint()
def main(script: str, args: str = "") -> None:
    print(run_probe.remote(script, args))
