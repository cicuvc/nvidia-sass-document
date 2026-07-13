#!/usr/bin/env python3
# Global L1 read bank-conflict driver. Per-instruction (per-warp-load) normalized.
import subprocess, sys, os, csv, io, tempfile
from run import pattern

PW = "c785ht8v"
BIN = os.environ.get("HARNESS_BIN", "./gld1")
ITERS = int(os.environ.get("ITERS", "4000"))
METRICS = [
    ("l1tex__data_bank_conflicts_pipe_lsu_mem_gds_op_ld.sum", "gdsC"),
    ("l1tex__data_pipe_lsu_wavefronts_mem_lgds.sum",          "glW"),
    ("l1tex__t_sectors_pipe_lsu_mem_global_op_ld.sum",        "glSec"),
    ("l1tex__t_output_wavefronts_pipe_lsu_mem_global_op_ld.sum", "glTW"),
    ("smsp__inst_executed_op_global_ld.sum",                  "iGL"),
]
MMAP = {m: s for m, s in METRICS}

def run(pat):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tf:
        tf.write(" ".join(map(str, pat))); pf = tf.name
    cmd = ["sudo", "-S", "/usr/local/cuda/bin/ncu", "--csv",
           "--metrics", ",".join(m for m, _ in METRICS), "-c", "1", BIN, "x", pf, str(ITERS)]
    out = subprocess.run(cmd, input=PW + "\n", capture_output=True, text=True)
    os.unlink(pf)
    rows = [r for r in csv.reader(io.StringIO(out.stdout)) if r]
    idx = [i for i, r in enumerate(rows) if "Metric Name" in r]
    if not idx: print("PARSE FAIL", out.stdout[-400:], file=sys.stderr); return {}
    h = rows[idx[0]]; mi = h.index("Metric Name"); vi = h.index("Metric Value")
    return {MMAP[r[mi]]: r[vi] for r in rows[idx[0]+1:] if len(r) > vi and r[mi] in MMAP}

def main():
    tests = sys.argv[1:]
    print(f"BIN={BIN} iters={ITERS}  (values normalized per warp-load)")
    print(f"{'pattern':<16} {'gdsC/ld':>8} {'glW/ld':>7} {'glSec/ld':>9} {'glTW/ld':>8}")
    for spec in tests:
        pat = pattern(spec)
        v = run(pat)
        try:
            n = float(v.get("iGL", "0")) or 1.0
            def nz(k): 
                x = v.get(k); 
                return f"{float(x)/n:.3g}" if x not in (None, "") else "-"
            print(f"{spec:<16} {nz('gdsC'):>8} {nz('glW'):>7} {nz('glSec'):>9} {nz('glTW'):>8}")
        except Exception as e:
            print(spec, "ERR", v, e)

if __name__ == "__main__":
    main()
