#!/usr/bin/env bash
# CPU-only phase gate runner (replaces `ctest` which is unavailable on this
# machine).  Runs the semu CTest suite of the build tree directly against the
# test executables + python drivers.
#
# Usage: tools/run_semu_cpu_gate.sh [build_dir]   (default semu/build)
set -u

ROOT=/home/cicuvc/cs/projects/nvidia-sass-document
BUILD="${1:-$ROOT/semu/build}"
SRC="$ROOT/semu/tests"
BIN="$BUILD/tests"
CLI="$BUILD/cli/semu"
CORPUS="$BUILD/semu_corpus.json"
L1TEX_DIR="${L1TEX_ARCH_DIR:-/home/cicuvc/cs/projects/arch/l1tex}"
PY="$(command -v python3 || echo python3)"

fail=0
npass=0
nfail=0

run() {
  local name="$1"; shift
  local logf="$BUILD/gate_${name//\//_}.log"
  if "$@" >"$logf" 2>&1; then
    npass=$((npass+1))
    printf 'PASS %-24s %s\n' "$name" "$*"
  else
    nfail=$((nfail+1)); fail=1
    printf 'FAIL %-24s %s\n' "$name" "$*"
    tail -25 "$logf" | sed 's/^/    | /'
  fi
}

# --- C++ L0 unit tests (CPU only) ---
for t in core decoder cubin memory cluster interp fp l1tex shared_bank global profiler subcore l2 race debugger tensor_map tensor mbarrier mock_backend api_compile; do
  run "cpp/$t" "$BIN/semu_test_$t"
done

# --- CLI smoke (python driver) ---
run "cli_smoke" "$PY" "$SRC/cli_smoke_test.py" "$CLI" "$SRC/data/empty_module.bin"

# --- manifest regeneration gates ---
run "manifest_regen" "$PY" "$SRC/manifest_regen_test.py" "$ROOT/sm120.json" "$SRC/../generated"
run "isa_regen" "$PY" "$SRC/isa_regen_test.py" "$ROOT/sm120.json" "$SRC/../generated"

# --- Phase 1 decoder gates (python, corpus on demand) ---
run "decoder_roundtrip" "$PY" "$SRC/decoder_roundtrip_test.py" "$CLI" "$CORPUS" "$ROOT/sm120.json"
run "decoder_ambig" "$PY" "$SRC/decoder_ambig_test.py" "$CLI" "$CORPUS" "$ROOT/sm120.json"
run "cond_differential" "$PY" "$SRC/cond_differential_test.py" "$CLI" "$CORPUS" "$ROOT/sm120.json"
run "decoder_cuobjdump" "$PY" "$SRC/decoder_cuobjdump_test.py" "$CLI" "$SRC/data/cuobj_vectors_sm120.json"
run "decoder_negative" "$PY" "$SRC/decoder_negative_test.py" "$CLI" "$CORPUS" "$ROOT/sm120.json"
run "cuobj_regen" "$PY" "$SRC/cuobj_regen_test.py"
run "decoder_cuobjdump_tamper" "$PY" "$SRC/decoder_cuobjdump_tamper_test.py" "$CLI"

# --- Phase 2 loader gates ---
run "cubin_load" "$PY" "$SRC/cubin_load_test.py" "$CLI"

# --- Phase 5 fuzz (CPU-only oracle here; the GPU differential is run
# separately: tools/diff_phase5.py / tools/fuzz_phase5.py --gpu) ---
run "fuzz_phase5" "$PY" "$SRC/fuzz_phase5_test.py" "$CLI" "$ROOT/tools/fuzz_phase5.py"

# --- Phase 9 tensor differential (C++ interpreter == python reference; CPU) ---
run "tensor_differential" "$PY" "$ROOT/tools/tensor_differential_test.py" "$CLI"

# --- Phase 5.5 l1tex oracle (C++ estimator == python reference; CPU only) ---
if [ -x "$BIN/semu_l1tex_cli" ] && [ -f "$L1TEX_DIR/unified_model.py" ]; then
  run "l1tex_oracle" "$PY" "$ROOT/tools/l1tex_oracle_check.py" "$BIN/semu_l1tex_cli" "$L1TEX_DIR"
else
  echo "SKIP l1tex_oracle (missing semu_l1tex_cli or $L1TEX_DIR/unified_model.py)"
fi

# --- Phase 8 profiler (LDGSTS corpus oracle + JSON schema compatibility) ---
if [ -x "$BIN/semu_l1tex_cli" ] && [ -f "$L1TEX_DIR/unified_model.py" ]; then
  run "profiler_report" "$PY" "$ROOT/tools/profiler_report_test.py" "$CLI" "$BIN/semu_l1tex_cli" "$L1TEX_DIR"
else
  echo "SKIP profiler_report (missing semu_l1tex_cli or unified_model.py)"
fi

echo
echo "gate: $npass passed, $nfail failed (total $((npass+nfail)))"
exit $fail
