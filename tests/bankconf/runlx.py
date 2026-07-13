#!/usr/bin/env python3
# Driver for the L1<->shared interaction study. Runs ncu with the arbitration /
# gds / shared / total bank-conflict + wavefront metric set and prints one row
# per binary. Values are raw sums over the whole kernel (iters * warps).
import subprocess, sys, os, csv, io

PW = "c785ht8v"
METRICS = [
    ("l1tex__data_bank_conflicts_pipe_lsu_mem_shared_op_st.sum", "shSTc"),
    ("l1tex__data_bank_conflicts_pipe_lsu_mem_shared_op_ld.sum", "shLDc"),
    ("l1tex__data_bank_conflicts_pipe_lsu_mem_gds_op_ld.sum",    "glLDc"),
    ("l1tex__data_bank_conflicts_type_arbitration.sum",          "ARBc"),
    ("l1tex__data_bank_conflicts_pipe_lsu.sum",                  "TOTc"),
    ("l1tex__data_pipe_lsu_wavefronts_mem_shared_op_st.sum",     "shSTw"),
    ("l1tex__data_pipe_lsu_wavefronts_mem_shared_op_ld.sum",     "shLDw"),
    ("l1tex__t_output_wavefronts_pipe_lsu_mem_global_op_ld.sum", "glLDw"),
    ("l1tex__data_pipe_lsu_wavefronts.sum",                      "TOTw"),
    ("smsp__inst_executed_op_shared_st.sum",                     "iSHst"),
    ("smsp__inst_executed_op_global_ld.sum",                     "iGLld"),
]
MMAP = {m: s for m, s in METRICS}

def run(binpath, iters, nblk):
    cmd = ["sudo", "-S", "/usr/local/cuda/bin/ncu", "--csv",
           "--metrics", ",".join(m for m, _ in METRICS),
           "-c", "1", binpath, str(iters), str(nblk)]
    out = subprocess.run(cmd, input=PW + "\n", capture_output=True, text=True)
    rows = [r for r in csv.reader(io.StringIO(out.stdout)) if r]
    hdr = None; body = []
    for i, r in enumerate(rows):
        if "Metric Name" in r:
            hdr = r; body = rows[i+1:]; break
    if hdr is None:
        print("PARSE FAIL", binpath, file=sys.stderr); print(out.stdout[-600:], file=sys.stderr); return {}
    mi = hdr.index("Metric Name"); vi = hdr.index("Metric Value")
    vals = {}
    for r in body:
        if len(r) > max(mi, vi) and r[mi] in MMAP:
            vals[MMAP[r[mi]]] = r[vi]
    return vals

def main():
    iters = int(os.environ.get("ITERS", "2000"))
    nblk = int(os.environ.get("NBLK", "1"))
    bins = sys.argv[1:] or ["lx_G", "lx_S", "lx_GS", "lx_GSL"]
    cols = [s for _, s in METRICS]
    print(f"iters={iters} nblk={nblk}")
    print(f"{'bin':<8} " + " ".join(f"{c:>6}" for c in cols))
    for b in bins:
        p = os.path.join(os.path.dirname(__file__), b)
        v = run(p, iters, nblk)
        print(f"{b:<8} " + " ".join(f"{v.get(c,'-'):>6}" for c in cols))

if __name__ == "__main__":
    main()
