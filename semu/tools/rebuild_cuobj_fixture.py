#!/usr/bin/env python3
"""Rebuild the sm120 cuobjdump vector fixture from reproducible sources
(GAP-11).  Consumes:

  - repo CUDA kernels (tests/*.cu) that are built with nvcc -cubin;
  - the committed regen sources semu/tests/data/regen/*.cu.

Each cubin is disassembled with cuobjdump -sass and the extracted words are
merged into semu/tests/data/cuobj_vectors_sm120.json, preserving the existing
provenance records (cubin/kernel/pc/text/lo/hi) and adding the generator,
toolchain versions and input SHA-256 hashes to the meta block.

Regeneration is byte-identical when the same CUDA toolkit is used; when the
toolchain differs, the *word set* must still match (structure comparison in
decoder_cuobjdump_test.py is word-driven), and the meta records the toolchain
that produced the fixture.

Usage:
    rebuild_cuobj_fixture.py [--out OUT.json] [--arch sm_120]
"""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CUOBJDUMP = "/usr/local/cuda/bin/cuobjdump"
NVCC = "/usr/local/cuda/bin/nvcc"
DEFAULT_OUT = (Path(__file__).resolve().parent.parent /
               "tests" / "data" / "cuobj_vectors_sm120.json")

# cubin -> CUDA source (relative to REPO).  Prebuilt cubins already in the
# repo are used directly; regen sources are compiled on the fly.
REPO_CUBINS = {
    "pmtrig_test.cubin": "tests/pmtrig_test.cu",
    "tma_global.cubin": "tests/tma_global.cu",
    "tma_min.cubin": "tests/tma_min.cu",
    "tma_simple.cubin": "tests/tma_simple.cu",
    "tma_test.cubin": "tests/tma_test.cu",
}
REGEN_SOURCES = {
    "vecmix.cubin": "semu/tests/data/regen/vecmix.cu",
    "vecmix2.cubin": "semu/tests/data/regen/vecmix2.cu",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(cubin: Path, arch: str) -> list:
    import re
    p = subprocess.run([CUOBJDUMP, "-arch", arch, "-sass", str(cubin)],
                       text=True, capture_output=True)
    if p.returncode != 0:
        print(f"WARN: cuobjdump failed for {cubin.name}", file=sys.stderr)
        return []
    lines = p.stdout.splitlines()
    out = []
    kernel = None
    i = 0
    while i < len(lines):
        m = re.search(r"Function : (\S+)", lines[i])
        if m:
            kernel = m.group(1)
            i += 1
            continue
        m = re.match(r"\s*/\*([0-9a-fA-F]+)\*/\s+(.*?)\s*/\* 0x([0-9a-fA-F]{8,16}) \*/",
                     lines[i])
        if m:
            pc = int(m.group(1), 16)
            text = m.group(2).strip()
            lo = int(m.group(3), 16)
            hi = 0
            if i + 1 < len(lines):
                m2 = re.search(r"0x([0-9a-fA-F]{8,16})", lines[i + 1])
                if m2:
                    hi = int(m2.group(1), 16)
            out.append({"cubin": cubin.name, "kernel": kernel, "pc": pc,
                        "text": text, "lo": lo, "hi": hi})
        i += 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--arch", default="sm_120")
    args = ap.parse_args()
    out_path = Path(args.out)

    rows = []
    meta = {"generator": "semu/tools/rebuild_cuobj_fixture.py",
            "arch": args.arch, "sources": {}, "toolchain": {}}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # repo prebuilt cubins
        for cubin_name, src in REPO_CUBINS.items():
            cubin = REPO / "tests" / cubin_name
            if not cubin.is_file():
                # try rebuilding from source
                src_path = REPO / src
                if not src_path.is_file():
                    print(f"WARN: {cubin_name} and {src} missing",
                          file=sys.stderr)
                    continue
                cubin = td / cubin_name
                subprocess.run([NVCC, f"-arch={args.arch}", "-O3", "-cubin",
                                "-o", str(cubin), str(src_path)],
                               check=True, capture_output=True)
            meta["sources"][cubin_name] = sha256(cubin)
            rows.extend(extract(cubin, args.arch))
        # regen sources
        for cubin_name, src in REGEN_SOURCES.items():
            src_path = REPO / src
            cubin = td / cubin_name
            subprocess.run([NVCC, f"-arch={args.arch}", "-O3", "-cubin",
                            "-o", str(cubin), str(src_path)],
                           check=True, capture_output=True)
            meta["sources"][cubin_name] = sha256(cubin)
            rows.extend(extract(cubin, args.arch))

    # dedupe by (lo, hi), keep first occurrence
    seen = set()
    uniq = []
    for r in rows:
        if (r["lo"], r["hi"]) in seen:
            continue
        seen.add((r["lo"], r["hi"]))
        uniq.append(r)

    # toolchain provenance
    def tool_version(cmd, key):
        try:
            p = subprocess.run(cmd.split(), text=True, capture_output=True)
            lines = [l.strip() for l in p.stdout.splitlines() if l.strip()]
        except Exception:
            lines = []
        # Prefer the full `Cuda compilation tools, release X.Y, V...` line and
        # the `Build cuda_...` line; fall back to the first output line.  This
        # pins the exact toolkit so rebuild provenance is unambiguous across
        # machines/toolchains.
        rel = next((l for l in lines if "Cuda compilation tools" in l), None)
        build = next((l for l in lines if l.startswith("Build cuda_")), None)
        full = next((l for l in lines if "compiler." in l), None)
        if rel and build:
            return {"release": rel, "build": build}
        if full:
            return {"full": full}
        return {"line0": lines[0] if lines else "unknown"}
    meta["toolchain"]["cuobjdump"] = tool_version("/usr/local/cuda/bin/cuobjdump --version", "cuobjdump")
    meta["toolchain"]["nvcc"] = tool_version("/usr/local/cuda/bin/nvcc --version", "nvcc")

    meta["count"] = len(uniq)
    doc = {"meta": meta, "vectors": uniq}
    out_path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"wrote {out_path}: {len(uniq)} unique words "
          f"(from {len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
