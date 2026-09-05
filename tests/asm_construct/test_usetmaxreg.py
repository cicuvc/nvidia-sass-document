"""Real-device USETMAXREG / PTX setmaxnreg semantics (sm_120).

Faulting boundary cases run in fresh subprocesses because CUDA 700/715 poisons
the current context.  All resource-transfer kernels obey PTX's four-warp
warpgroup participation rule unless a comment explicitly says otherwise.
"""

import json
import struct
import subprocess
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, ROOT)

from assembler import CudaModule, assemble, assemble_flat  # noqa: E402


def execute(source, block=128, nwords=0):
    code = f"""
import json, struct, sys
sys.path.insert(0, {ROOT!r})
from assembler import CudaModule, assemble
src={source!r}; block={block}; nwords={nwords}
try:
    m=CudaModule(assemble(src))
    args=[]
    if nwords:
        d=m.devmem_alloc(nwords*4); m.device_write(d, bytes(nwords*4)); args=[d]
    m.launch('k', grid=(1,), block=(block,), args=args); m.synchronize()
    vals=list(struct.unpack('<'+'I'*nwords, m.device_read(d,nwords*4))) if nwords else []
    print(json.dumps({{'ok':True,'values':vals}}))
except Exception as e:
    print(json.dumps({{'ok':False,'error':str(e)}}))
"""
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    lines = [x for x in p.stdout.splitlines() if x.startswith("{")]
    return json.loads(lines[-1]) if lines else {"ok": False, "error": p.stderr[-300:]}


def head(initial):
    return f"""#fn k(out<8>) {{
 #pragma MAXREG_COUNT({initial})
 LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:2:0]
 LDC.64 {{R2,R3}}, #param(out);[1:7:{{}}:1:0]
 S2R R5, SR_TID.X;[5:7:{{}}:1:0]
"""


def try_source(target, *, initial=64, ur=False):
    operand = "UR8" if ur else f"0x{target:x}"
    setup = f" UMOV UR8, 0x{target:x};[7:7:{{}}:5:1]\n" if ur else ""
    return head(initial) + setup + f"""
 USETMAXREG.TRY_ALLOC.CTAPOOL UP0, {operand};[3:7:{{}}:2:0]
 BRA.U !UP0, #label(fail);[7:7:{{3}}:5:0]
 MOV32I R7, 1;[7:7:{{}}:5:1]
 BRA #label(store);[7:7:{{}}:5:1]
 #def_label(fail)
 MOV32I R7, 0;[7:7:{{}}:5:1]
 #def_label(store)
 IMAD.WIDE.U32 {{R2,R3}}, R5, 0x4, {{R2,R3}};[7:7:{{1,5}}:5:1]
 STG.E desc[{{UR4,UR5}}][{{R2,R3}}], R7;[7:7:{{0}}:1:0]
 EXIT;[7:7:{{}}:5:0]
}}"""


def pool_source(dec, inc, *, block=256):
    """WG0 donates registers; every other warpgroup competes for them."""
    return head(128) + f"""
 ISETP.LT.U32.AND P0, PT, R5, 128, PT;[7:7:{{5}}:13:1]
 @!P0 BRA #label(after_dec);[7:7:{{}}:5:1]
 USETMAXREG.DEALLOC.CTAPOOL 0x{dec:x};[2:7:{{}}:2:0]
 #def_label(after_dec)
 BAR.SYNC 0;[7:7:{{2}}:5:1]
 ISETP.LT.U32.AND P0, PT, R5, 128, PT;[7:7:{{}}:13:1]
 @P0 BRA #label(producer);[7:7:{{}}:5:1]
 USETMAXREG.TRY_ALLOC.CTAPOOL UP0, 0x{inc:x};[3:7:{{}}:2:0]
 BRA.U !UP0, #label(fail);[7:7:{{3}}:5:0]
 MOV32I R7, 1;[7:7:{{}}:5:1]
 BRA #label(store);[7:7:{{}}:5:1]
 #def_label(fail)
 MOV32I R7, 0;[7:7:{{}}:5:1]
 BRA #label(store);[7:7:{{}}:5:1]
 #def_label(producer)
 MOV32I R7, 2;[7:7:{{}}:5:1]
 #def_label(store)
 IMAD.WIDE.U32 {{R2,R3}}, R5, 0x4, {{R2,R3}};[7:7:{{0,1}}:5:1]
 STG.E desc[{{UR4,UR5}}][{{R2,R3}}], R7;[7:7:{{}}:1:0]
 EXIT;[7:7:{{}}:5:0]
}}"""


def window_source(limit, reg):
    return f"""#fn k(out<8>) {{
 #pragma MAXREG_COUNT(128)
 LDCU.64 {{UR4,UR5}}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{{}}:2:0]
 LDC.64 {{R2,R3}}, #param(out);[1:7:{{}}:1:0]
 USETMAXREG.DEALLOC.CTAPOOL 0x{limit:x};[2:7:{{}}:2:0]
 MOV32I R{reg}, 0x12345678;[7:7:{{2}}:5:1]
 STG.E desc[{{UR4,UR5}}][{{R2,R3}}], R{reg};[7:7:{{0,1}}:1:0]
 EXIT;[7:7:{{}}:5:0]
}}"""


def grow_source(target, reg):
    """WG0 releases 64 registers/thread; WG1 grows and touches its new tail."""
    return head(128) + f"""
 ISETP.LT.U32.AND P0, PT, R5, 128, PT;[7:7:{{5}}:13:1]
 @!P0 BRA #label(after_dec);[7:7:{{}}:5:1]
 USETMAXREG.DEALLOC.CTAPOOL 0x40;[2:7:{{}}:2:0]
 #def_label(after_dec)
 BAR.SYNC 0;[7:7:{{2}}:5:1]
 ISETP.LT.U32.AND P0, PT, R5, 128, PT;[7:7:{{}}:13:1]
 @P0 EXIT;[7:7:{{}}:5:0]
 USETMAXREG.TRY_ALLOC.CTAPOOL UP0, 0x{target:x};[3:7:{{}}:2:0]
 BRA.U !UP0, #label(fail);[7:7:{{3}}:5:0]
 MOV32I R{reg}, 0x12345678;[7:7:{{}}:5:1]
 STG.E desc[{{UR4,UR5}}][{{R2,R3}}], R{reg};[7:7:{{0,1}}:1:0]
 EXIT;[7:7:{{}}:5:0]
 #def_label(fail)
 MOV32I R7, 0;[7:7:{{}}:5:1]
 STG.E desc[{{UR4,UR5}}][{{R2,R3}}], R7;[7:7:{{0,1}}:1:0]
 EXIT;[7:7:{{}}:5:0]
}}"""


def dealloc_source(target):
    return f"""#fn k() {{
 #pragma MAXREG_COUNT(128)
 USETMAXREG.DEALLOC.CTAPOOL 0x{target:x};[1:7:{{}}:2:0]
 EXIT;[7:7:{{1}}:5:0]
}}"""


def recycled_tail_source():
    return """#fn k(out<8>) {
 #pragma MAXREG_COUNT(128)
 LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:2:0]
 LDC.64 {R2,R3}, #param(out);[1:7:{}:1:0]
 MOV32I R100, 0xdeadbeef;[7:7:{}:5:1]
 USETMAXREG.DEALLOC.CTAPOOL 0x40;[2:7:{}:2:0]
 BAR.SYNC 0;[7:7:{2}:5:1]
 USETMAXREG.TRY_ALLOC.CTAPOOL UP0, 0x80;[3:7:{}:2:0]
 BRA.U !UP0, #label(fail);[7:7:{3}:5:0]
 STG.E desc[{UR4,UR5}][{R2,R3}], R100;[7:7:{0,1}:1:0]
 EXIT;[7:7:{}:5:0]
 #def_label(fail)
 MOV32I R7, 0xffffffff;[7:7:{}:5:1]
 STG.E desc[{UR4,UR5}][{R2,R3}], R7;[7:7:{0,1}:1:0]
 EXIT;[7:7:{}:5:0]
}"""


ok = True


def check(name, condition, detail=""):
    global ok
    ok &= condition
    print(f"{'ok ' if condition else 'FAIL'} {name:<46} {detail}")


try:
    CudaModule(assemble("#fn k() { EXIT;[7:7:{}:5:0] }"))
except RuntimeError:
    print("--- no CUDA device; USETMAXREG checks SKIPPED ---")
    sys.exit(0)


# Both encoded operand forms, including the UR form never emitted by ptxas.
enc = assemble_flat("""USETMAXREG.TRY_ALLOC.CTAPOOL UP0, 0x80;[2:7:{}:5:1]
USETMAXREG.TRY_ALLOC.CTAPOOL UP0, UR8;[2:7:{}:5:1]
USETMAXREG.DEALLOC.CTAPOOL UR10;[2:7:{}:5:1]""")
check("immediate and UR encodings assemble", len(enc) == 3, repr(enc))

# No donated registers: equality is a successful no-op, growth reports false.
for target, want in [(64, 1), (65, 0)]:
    r = execute(try_source(target), 128, 128)
    check(f"TRY_ALLOC {target}: no-pool result", r["ok"] and set(r["values"]) == {want}, str(r)[:100])
r = execute(try_source(64, ur=True), 128, 128)
check("UR target form has identical semantics", r["ok"] and set(r["values"]) == {1}, str(r)[:100])

# Exact CTA-pool accounting.  Counts need not be multiples of 8 at SASS level.
for dec, inc, want in [(64, 192, 1), (64, 200, 0), (24, 232, 1), (24, 233, 0)]:
    r = execute(pool_source(dec, inc), 256, 256)
    consumer = r.get("values", [])[128:]
    check(f"pool 128->{dec}, peer 128->{inc}", r["ok"] and set(consumer) == {want}, str(r)[:110])

# One donated pool can satisfy exactly one of two requesting warpgroups.
r = execute(pool_source(64, 192, block=384), 384, 384)
vals = r.get("values", [])
heads = vals[::32]
requester_groups = [vals[128:256], vals[256:384]]
check("TRY_ALLOC is atomic at warpgroup granularity",
      r["ok"] and len(vals) == 384 and set(vals[:128]) == {2}
      and all(len(set(group)) == 1 for group in requester_groups)
      and sorted(next(iter(set(group))) for group in requester_groups) == [0, 1],
      f"warp heads={heads}")

# The owned window ends two architectural registers before N.
r = execute(window_source(64, 61), 128, 1)
check("DEALLOC 64 leaves R61 usable", r["ok"] and r["values"] == [0x12345678], str(r))
r = execute(window_source(64, 62), 128, 1)
check("DEALLOC 64 makes R62 unavailable", not r["ok"] and "715" in r["error"], str(r))

# Successful growth exposes the new tail with the same N-2 boundary.
r = execute(grow_source(192, 189), 256, 1)
check("TRY_ALLOC 192 makes R189 usable", r["ok"] and r["values"] == [0x12345678], str(r))
r = execute(grow_source(192, 190), 256, 1)
check("TRY_ALLOC 192 leaves R190 unavailable", not r["ok"] and "715" in r["error"], str(r))

# PTX specifies newly acquired contents as undefined.  On this sm_120 the
# released R100 value is consistently discarded and reads back as zero after
# reacquisition; callers must not rely on either zeroing or preservation.
r = execute(recycled_tail_source(), 128, 1)
check("reacquired tail does not preserve old R100",
      r["ok"] and r["values"] == [0], str(r))

# Native SASS accepts [8, current] for DEALLOC; PTX narrows this to [24,256]
# and multiples of 8.  Wrong direction and values above 256 are illegal.
for target, want_ok in [(8, True), (7, False), (128, True), (129, False)]:
    r = execute(dealloc_source(target), 128, 0)
    check(f"DEALLOC raw boundary {target}", r["ok"] == want_ok,
          "OK" if r["ok"] else r.get("error", "")[:70])
r = execute(try_source(257), 128, 128)
check("TRY_ALLOC >256 is illegal", not r["ok"] and "715" in r["error"], str(r))

print(f"\n=== USETMAXREG semantics: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
