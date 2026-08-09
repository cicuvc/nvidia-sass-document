#!/usr/bin/env python3
"""Run tests/asm_construct/test_*.py in parallel across worker processes.

The tests are independent Python processes, so they can share the GPU
(driver multi-context) — wall-clock drops roughly with the job count.  A few
tests measure cycles/throughput and need the GPU to themselves; those run
serially after the parallel batch (or first, with --serial-first).

Usage:
    python3 tools/run_tests.py [-j N] [--timeout S] [--serial] [--verbose]
"""
import argparse
import concurrent.futures
import os
import subprocess
import sys
import time
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent.parent / "tests" / "asm_construct"

# Tests that must not share the GPU with concurrent kernels: either they
# measure absolute cycles/throughput (numbers drift) or they depend on
# per-stream driver state (access-policy window descriptors) that other
# workers can disturb.  They run serially after the parallel batch.
TIMING_SENSITIVE = {
    "test_mufu_latency",
    "test_mufu_throughput",
    "test_ffma_throughput",
    "test_depbar",
    "test_mufu",
    "test_cache_desc",          # cuStreamSetAttribute access-policy window
    "test_udp_int_forward",     # pipe-forwarding boundary sweep (issue-gap sensitive)
    "test_subcore_yield",       # subcore mapping + yield scheduler probe (cycles)
    "test_int_fma_forward",     # int/fmalighter GPR forwarding boundary sweep
    "test_int_cbu_forward",     # int->cbu (NANOSLEEP) forwarding, one launch per S
    "test_int_cbu_pred_forward",  # ISETP P0 -> @P0 BRA predicate forwarding sweep
    "test_udp_fma_forward",     # udp->fmalighter (FFMA RRU) forwarding sweep
    "test_int_mio_forward",     # int->mio (LDG address/AGU) forwarding sweep
    "test_fmal_mio_forward",    # fmal->mio (LDG address/AGU) forwarding sweep
    "test_mio_int_fma_forward", # mio(MUFU)->int/fmal, no scoreboard req
    "test_fp16_int_fma_forward",  # fp16(HADD2)->int/fmal forwarding sweep
    "test_udp_fe_forward",      # udp->fe (DEPBAR count) forwarding sweep
    "test_int_fp16_forward",    # int/fmal/fp16 -> fp16 forwarding sweep
    "test_fp16_mio_forward",    # fp16 -> mio (MUFU) forwarding sweep
    "test_fp16_cbu_forward",    # fp16 -> cbu (NANOSLEEP) forwarding sweep
    "test_cbu_forward",         # cbu(BMOV) -> int / mio forwarding sweep
    "test_udp_udp_mio_forward", # udp->udp / udp->mio(UR addr) forwarding sweep
    "test_mio_fp16_forward",    # mio(MUFU) -> fp16 forwarding sweep
    "test_pred_forward",        # HSETP2 P0 -> @P0 BRA predicate sweep
}


def run_one(name: str, timeout: float):
    path = TESTS_DIR / f"{name}.py"
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, str(path)],
                           capture_output=True, text=True, timeout=timeout)
        rc, tail, err = r.returncode, (r.stdout or "")[-300:], (r.stderr or "")
    except subprocess.TimeoutExpired:
        rc, tail, err = 124, f"TIMEOUT after {timeout:.0f}s", ""
    dt = time.time() - t0
    err_tail = [ln for ln in err.splitlines() if "[depcheck]" in ln][-2:]
    return rc, dt, tail.strip().splitlines()[-1] if tail.strip() else "", err_tail


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-j", "--jobs", type=int, default=min(4, os.cpu_count() or 1),
                    help="parallel worker count (default min(4, ncpu))")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--serial", action="store_true",
                    help="run everything serially (no parallelism)")
    ap.add_argument("--serial-first", action="store_true",
                    help="run timing-sensitive tests first (serial), then parallel")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    names = sorted(p.stem for p in TESTS_DIR.glob("test_*.py"))
    parallel = [n for n in names if n not in TIMING_SENSITIVE]
    serial = [n for n in names if n in TIMING_SENSITIVE]

    results: dict[str, tuple[int, float, str, list]] = {}
    t_start = time.time()

    def collect(batch, jobs):
        if args.serial or jobs == 1:
            for n in batch:
                results[n] = run_one(n, args.timeout)
        else:
            with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as ex:
                futs = {ex.submit(run_one, n, args.timeout): n for n in batch}
                for fut in concurrent.futures.as_completed(futs):
                    n = futs[fut]
                    results[n] = fut.result()

    if args.serial_first:
        print(f"serial (timing-sensitive): {', '.join(serial)}")
        collect(serial, 1)
        collect(parallel, args.jobs if not args.serial else 1)
    else:
        collect(parallel, args.jobs if not args.serial else 1)
        if serial:
            print(f"serial (timing-sensitive): {', '.join(serial)}")
            collect(serial, 1)

    # report
    fails = []
    print(f"\n{'test':34s} {'result':6s} {'time':>7s}  detail")
    print("-" * 70)
    for n in names:
        rc, dt, tail, err_tail = results[n]
        status = "ok" if rc == 0 else f"FAIL({rc})"
        if rc != 0:
            fails.append(n)
        print(f"{n:34s} {status:6s} {dt:6.1f}s  {tail}")
        if args.verbose and err_tail:
            for e in err_tail:
                print(f"      {e}")
    print(f"\n{'='*70}")
    print(f"total wall: {time.time()-t_start:.1f}s  tests: {len(names)}  "
          f"pass: {len(names)-len(fails)}  fail: {len(fails)}")
    if fails:
        print("FAILED:", ", ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
