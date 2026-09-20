import sys
sys.path.insert(0, "/repo/tests/asm_construct")
sys.path.insert(0, "/repo")
import probe_sm90_rates as p
for op in ("ffma", "iadd3", "imad", "hfma2"):
    r = p.run(op, "[7:7:{}:1:0]")
    print(f"{op:8s} [1:0] no-reuse: {r:.3f} cyc/inst", flush=True)
