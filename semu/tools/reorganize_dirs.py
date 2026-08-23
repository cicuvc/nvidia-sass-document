#!/usr/bin/env python3
"""Reorganize semu/src and semu/include into subsystem directories and
rewrite every `#include <semu/X.hpp>` reference to the new path.

Groups (src dirs mirror include dirs):
  core/     status fault word version capability hb_clock (+ api.hpp)
  context/  context mock_backend
  exec/     cluster debugger execution subcore_scheduler
  memory/   memory memory_service l1tex_model shared_bank global_model
            l2_events race_detector memory_events
  tensor/   tensor tensor_map mbarrier
  fp/       fp fast_fp
  profiler/ profiler
  decoder/  decoder decoded_base decoded_access shape_in
  cubin/    cubin
  interpreter/ interpreter

Interpreter/cubin/decoder sources are already in subtrees and stay.
Run from semu/:  python3 tools/reorganize_dirs.py
"""
import subprocess
from pathlib import Path

GROUPS = {
    "core": ["api", "capability", "fault", "hb_clock", "status", "version",
             "word"],
    "context": ["context", "mock_backend"],
    "exec": ["cluster", "debugger", "execution", "subcore_scheduler"],
    "memory": ["global_model", "l1tex_model", "l2_events", "memory",
               "memory_events", "memory_service", "race_detector",
               "shared_bank"],
    "tensor": ["mbarrier", "tensor", "tensor_map"],
    "fp": ["fast_fp", "fp"],
    "profiler": ["profiler"],
    "decoder": ["decoder", "decoded_access", "decoded_base", "shape_in"],
    "cubin": ["cubin"],
    "interpreter": ["interpreter"],
}

INCLUDE = Path("include/semu")
SRC = Path("src")

# src name -> category (name.cpp lives under the same group as the header)
def category_of(name):
    for g, names in GROUPS.items():
        if name in names:
            return g
    return None


def git(*args):
    subprocess.run(["git", *args], check=True)


def main():
    # ---- move headers ----
    for g, names in GROUPS.items():
        (INCLUDE / g).mkdir(parents=True, exist_ok=True)
        for n in names:
            src = INCLUDE / f"{n}.hpp"
            if src.exists():
                git("mv", str(src), str(INCLUDE / g / f"{n}.hpp"))

    # ---- move sources ----
    for cpp in sorted(SRC.glob("*.cpp")):
        g = category_of(cpp.stem)
        if g is None:
            print(f"skip {cpp} (no group)")
            continue
        (SRC / g).mkdir(parents=True, exist_ok=True)
        git("mv", str(cpp), str(SRC / g / cpp.name))

    # ---- build the include-rewrite table ----
    def new_include(name):
        g = category_of(name)
        if g is None:
            raise ValueError(f"no group for {name}")
        return f"<semu/{g}/{name}.hpp>"

    rewrite = {f"<semu/{n}.hpp>": new_include(n) for n in
               [n for names in GROUPS.values() for n in names if
                category_of(n)]}

    def transform(text):
        for old, new in rewrite.items():
            text = text.replace(f"#include {old}", f"#include {new}")
        return text

    # ---- rewrite every TU/header under src, include, cli, tests, generated ----
    for base in (Path("src"), Path("include"), Path("cli"), Path("tests"),
                 Path("generated")):
        for p in base.rglob("*"):
            if p.is_file() and p.suffix in (".cpp", ".hpp", ".h", ".cu"):
                text = p.read_text(errors="ignore")
                out = transform(text)
                if out != text:
                    p.write_text(out)

    # ---- CMake source list ----
    cmake = Path("src/CMakeLists.txt")
    text = cmake.read_text()
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            for g, names in GROUPS.items():
                for n in names:
                    if line == f"{n}.cpp":
                        raw = raw.replace(f"{n}.cpp", f"{g}/{n}.cpp")
        lines.append(raw)
    cmake.write_text("\n".join(lines))

    # ---- generator template: it emits <semu/word.hpp> ----
    gen = Path("tools/gen_isa.py")
    t = gen.read_text()
    if "#include <semu/word.hpp>" in t:
        gen.write_text(t.replace("#include <semu/word.hpp>",
                                 "#include <semu/core/word.hpp>"))
    print("done. files moved and includes rewritten; run regen + build.")


if __name__ == "__main__":
    main()