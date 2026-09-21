#!/usr/bin/env python3
"""Run an assembler probe script on a Modal B200 or H100.

Usage::

    modal run tools/modal_b200_probe.py \
      --gpu B200 --script tests/asm_construct/probe_icache_capacity.py \
      --args "--sizes-kib 32,48,64 --reps 3"

The image carries the assembler, ISA databases, and asm_construct probes so
scripts which generate heap-resident SASS after device allocation work without
ptxas or nvcc.  ``ASSEMBLER_ARCH`` is selected as sm100a for B200 and sm90 for
H100.
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
    .add_local_file(REPO / "sm90.json", "/repo/sm90.json")
    .add_local_file(REPO / "sm100.json", "/repo/sm100.json")
    .add_local_dir(REPO / "sassdbg", "/repo/sassdbg")
    .add_local_dir(REPO / "tests" / "asm_construct",
                   "/repo/tests/asm_construct")
)

app = modal.App("nvidia-assembler-probe", image=IMAGE)


def _run_probe(script_name: str, args: str, timeout_s: int, arch: str) -> str:
    import os
    import shlex
    import subprocess

    relative = pathlib.PurePosixPath(script_name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"script must be relative to /repo: {script_name!r}")
    if len(relative.parts) == 1:
        relative = pathlib.PurePosixPath("tests/asm_construct") / relative
    target = pathlib.Path("/repo") / relative
    env = dict(os.environ, ASSEMBLER_ARCH=arch)
    try:
        result = subprocess.run(
            ["python3", str(target), *shlex.split(args)],
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


@app.function(gpu="B200", timeout=1200)
def run_b200(script_name: str, args: str = "", timeout_s: int = 1100) -> str:
    return _run_probe(script_name, args, timeout_s, "sm100a")


@app.function(gpu="H100", timeout=1200)
def run_h100(script_name: str, args: str = "", timeout_s: int = 1100) -> str:
    return _run_probe(script_name, args, timeout_s, "sm90")


@app.local_entrypoint()
def main(script: str, args: str = "", gpu: str = "B200") -> None:
    runners = {"B200": run_b200, "H100": run_h100}
    try:
        runner = runners[gpu.upper()]
    except KeyError as exc:
        raise ValueError(f"unsupported GPU {gpu!r}; choose B200 or H100") from exc
    print(runner.remote(script, args))
