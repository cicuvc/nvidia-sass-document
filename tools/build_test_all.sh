#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# One-shot build + CPU-gate runner across the semu build trees.
#
# Trees (4):
#   dev   -> semu/build          (Debug, plain)
#   asan  -> semu/build-asan     (Debug + ASan/UBSan via SEMU_ENABLE_SANITIZERS)
#   rel   -> semu/build-rel      (Release, -O3 -DNDEBUG)
#   tsan  -> semu/build-tsan     (Debug + TSan via SEMU_ENABLE_TSAN)
#
# The script (re)configures each selected tree with the tree-appropriate
# CMake options (idempotent: existing caches are updated in place, so any
# custom flags you set by hand are preserved), then builds it and runs the
# CPU gate for it (tools/run_semu_cpu_gate.sh <build_dir>).
#
# Usage:
#   tools/build_test_all.sh                # all 4 trees
#   tools/build_test_all.sh -d -a          # dev + asan only
#   tools/build_test_all.sh -d -n          # dev: build+test without configure
#   tools/build_test_all.sh -d -j 12       # pass -j to the build (ninja flag)
#
# Options:
#   -d | -a | -r | -t   select tree(s); repeat to combine.  Default: all four.
#   -n                  skip the CMake configure step (build + test only).
#   -j <N>              build parallelism, forwarded to ninja (default: none).
#   -h                  this help.
#
# Exit status: 0 when every selected tree built AND its gate passed; 1 when
# any step failed (output lists which tree/step failed).
# ---------------------------------------------------------------------------
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SEMU="$ROOT/semu"
GATE="$ROOT/tools/run_semu_cpu_gate.sh"
CONDA_ENV="${SEMU_CONDA_ENV:-blkw}"
LLVM="/opt/LLVM-23.0.0git-Linux-X64"

# --- tree registry -----------------------------------------------------------
# getopts tags: d=dev, a=asan, r=rel, t=tsan (single letters).  The tree
# directories and per-tree CMake options are keyed by the same single letter.
declare -A TREES=(
  [d]=build
  [a]=build-asan
  [r]=build-rel
  [t]=build-tsan
)
declare -A TREE_NAMES=([d]=dev [a]=asan [r]=rel [t]=tsan)
declare -A TREE_OPTS=(
  [d]=""
  [a]="-DSEMU_ENABLE_SANITIZERS=ON"
  [r]="-DCMAKE_BUILD_TYPE=Release"
  [t]="-DSEMU_ENABLE_TSAN=ON"
)

selected=()
no_configure=0
parallel=""
while getopts "darnj:h" opt; do
  case "$opt" in
    d|a|r|t) selected+=("$opt") ;;
    n) no_configure=1 ;;
    j) parallel="-j $OPTARG" ;;
    h) sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "usage: $0 [-d|-a|-r|-t]... [-n] [-j N]" >&2; exit 2 ;;
  esac
done
if [ "${#selected[@]}" -eq 0 ]; then
  selected=(d a r t)
fi

# --- environment ---------------------------------------------------------------
# Prefer the conda env that carries ninja/cmake/python; fall back to PATH.
if [ -x "/home/cicuvc/miniconda3/envs/$CONDA_ENV/bin/python3" ]; then
  export PATH="/home/cicuvc/miniconda3/envs/$CONDA_ENV/bin:$PATH"
fi
if [ -x "$LLVM/bin/clang++" ] && ! command -v clang++ >/dev/null 2>&1; then
  export PATH="$LLVM/bin:$PATH"
fi
export L1TEX_ARCH_DIR="${L1TEX_ARCH_DIR:-/home/cicuvc/cs/projects/arch/l1tex}"

# --- run -----------------------------------------------------------------------
fail=0
for tag in "${selected[@]}"; do
  dir="${TREES[$tag]}"
  bdir="$SEMU/$dir"
  echo ""
  echo "============================================================"
  echo "  tree: ${TREE_NAMES[$tag]:-?}  ($bdir)"
  echo "============================================================"

  # 1) configure (idempotent) unless -n
  if [ "$no_configure" -eq 0 ]; then
    # shellcheck disable=SC2086
    if ! cmake -S "$SEMU" -B "$bdir" -G Ninja ${TREE_OPTS[$tag]} \
         -DCMAKE_C_COMPILER="$LLVM/bin/clang" \
         -DCMAKE_CXX_COMPILER="$LLVM/bin/clang++" \
         -DSEMU_WERROR=ON; then
      echo "FAIL ^ $tag: cmake configure" >&2
      fail=1
      continue
    fi
  fi

  # 2) build
  if ! cmake --build "$bdir" ${parallel}; then
    echo "FAIL ^ $tag: build" >&2
    fail=1
    continue
  fi

  # 3) CPU gate (36 tests)
  if ! bash "$GATE" "$bdir"; then
    echo "FAIL ^ $tag: gate" >&2
    fail=1
    continue
  fi
  echo "PASS ^ $tag: build + gate"
done

echo ""
if [ "$fail" -eq 0 ]; then
  echo "build_test_all: ALL TREES PASSED (${#selected[@]} selected)"
else
  echo "build_test_all: FAILURES PRESENT" >&2
fi
exit "$fail"