#!/usr/bin/env python3
# cp.async (LDGSTS) shared-write bank-conflict driver. Reuses run.py pattern gens.
import subprocess, sys, os, csv, io, tempfile
from run import pattern, analyze_v2, analyze_v4

PW = "c785ht8v"
BIN = os.environ.get("HARNESS_BIN", "./cp16")
if "cg" in os.path.basename(BIN):
    METRICS = [
        ("sm__sass_l1tex_data_bank_conflicts_pipe_lsu_mem_shared_op_ldgsts_cache_bypass.sum", "gsC"),
        ("sm__sass_l1tex_data_pipe_lsu_wavefronts_mem_shared_op_ldgsts_cache_bypass.sum",     "gsW"),
        ("smsp__inst_executed_op_ldgsts.sum",                            "gsI"),
        ("sm__sass_inst_executed_op_ldgsts_cache_access.sum",            "ca"),
        ("sm__sass_inst_executed_op_ldgsts_cache_bypass.sum",            "cg"),
    ]
else:
    METRICS = [
        ("l1tex__data_bank_conflicts_pipe_lsu_mem_shared_op_ldgsts.sum", "gsC"),
        ("l1tex__data_pipe_lsu_wavefronts_mem_shared_op_ldgsts.sum",     "gsW"),
        ("smsp__inst_executed_op_ldgsts.sum",                            "gsI"),
        ("sm__sass_inst_executed_op_ldgsts_cache_access.sum",            "ca"),
        ("sm__sass_inst_executed_op_ldgsts_cache_bypass.sum",            "cg"),
    ]
MMAP = {m: s for m, s in METRICS}

def run(pat):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tf:
        tf.write(" ".join(map(str, pat))); pf = tf.name
    cmd = ["sudo", "-S", "/usr/local/cuda/bin/ncu", "--csv",
           "--metrics", ",".join(m for m, _ in METRICS), "-c", "1", BIN, "x", pf]
    out = subprocess.run(cmd, input=PW + "\n", capture_output=True, text=True)
    os.unlink(pf)
    rows = [r for r in csv.reader(io.StringIO(out.stdout)) if r]
    hdr = None; body = []
    for i, r in enumerate(rows):
        if "Metric Name" in r: hdr = r; body = rows[i+1:]; break
    if hdr is None:
        print("PARSE FAIL", out.stdout[-500:], file=sys.stderr); return {}
    mi = hdr.index("Metric Name"); vi = hdr.index("Metric Value")
    return {MMAP[r[mi]]: r[vi] for r in body if len(r) > max(mi, vi) and r[mi] in MMAP}

def main():
    tests = sys.argv[1:]
    cols = [s for _, s in METRICS]
    is_v2 = "8" in os.path.basename(BIN); is_v4 = "16" in os.path.basename(BIN)
    hdr = f"{'pattern':<20} " + " ".join(f"{c:>5}" for c in cols)
    if is_v2: hdr += "  pWhl pHlf"
    if is_v4: hdr += "  pWhl pHlf pQtr"
    print(f"BIN={BIN}"); print(hdr)
    for spec in tests:
        pat = pattern(spec)
        v = run(pat)
        line = f"{spec:<20} " + " ".join(f"{v.get(c,'-'):>5}" for c in cols)
        if is_v2:
            pw, ph = analyze_v2(pat); line += f"  {pw:>4} {ph:>4}"
        if is_v4:
            pw, ph, pq = analyze_v4(pat); line += f"  {pw:>4} {ph:>4} {pq:>4}"
        print(line)

if __name__ == "__main__":
    main()
