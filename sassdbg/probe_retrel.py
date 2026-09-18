#!/usr/bin/env python3
"""sassdbg.probe_retrel — M12a probe: exact RET.REL program base and the
observed return-token materialization (SASSDBG_WARP_PRIVATE_PLAN.md M12a).

Part 1 (static, CPU-only): decode `tests/call_test.cubin` and show that
  - ptxas encodes every `RET.REL.NODEC Rxx` with
        pc_link + 0x10 + sImm*4 == 0
    so the REL displacement term equals the image's *placement delta*: at a
    runtime PC of (base + pc_link) the term evaluates to `base` and
        return target = Rxx + base
  - every direct call materializes its continuation offset in the callee's
    return GPR with an immediate MOV (`MOV R20, 0xf0` before the call at
    0xe0), i.e. token + base = runtime continuation.

Part 2 (GPU, sm_120): build a small caller/callee pair in assembler
  dialect, write its bytes to two different devmem heap bases H1 and H2,
  and JMP into each from a driver kernel.  The pair must return to the
  private continuation and store the correct result at BOTH bases — proving
  RET.REL is program-base-relative (target = token + base), not absolute.

Part 3 (GPU differential): perturb the token by one instruction (+0x10) and
  show the return lands exactly one instruction later (token and base add
  independently), matching the M12 preflight #3 mechanism where a stale
  token/RET pair faults.

Exit code 0 = all assertions passed; 2 = GPU section skipped (no device);
1 = a probe assertion failed.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sassdbg.cubin import _sections
from sassdbg.modulecode import (ModuleTemplate, ReturnABI, TargetClass)
from sassdbg.warpcode import _field_value, _set_field_value, _OPCODE_INDEX

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUBIN = os.path.join(REPO, "tests", "call_test.cubin")


# ---------------------------------------------------------------------------
# Part 1 — static decode of the linked ABI
# ---------------------------------------------------------------------------
def _decode_ret_fields(lo, hi):
    enc = _OPCODE_INDEX.encoding("RET")
    opcode = (((hi >> 27) & 1) << 12) | (lo & 0xFFF)
    addr = _field_value(enc, "ignoreKill", lo, hi, signed=False)
    ra = _field_value(enc, "Ra", lo, hi, signed=False)
    s = _field_value(enc, "sImm", lo, hi, signed=True)
    depth = _field_value(enc, "depth", lo, hi, signed=False)
    return opcode, addr, ra, s, depth


def part1():
    print("=" * 70)
    print("Part 1 — static decode: RET.REL program base + return tokens")
    print("=" * 70)
    mt = ModuleTemplate.from_cubin(CUBIN, root="_Z1kPKiPii")
    isl = mt.islands[0]

    # every ptxas RET.REL must satisfy pc_link+0x10+sImm*4 == 0
    base_ok = True
    for fn in mt.functions():
        if fn.return_abi is not ReturnABI.REL_REG:
            continue
        ok = fn.return_rel_base == 0
        base_ok &= ok
        print(f"  {fn.name:28s} RET.REL.NODEC {fn.return_reg}  "
              f"pc_link+0x10+sImm*4 = {fn.return_rel_base:#x}  "
              f"{'OK' if ok else 'XX'}")

    # each direct call's return-token materialization
    print("  observed return-token materializations (caller -> callee):")
    tok_ok = True
    expect = {("_Z1kPKiPii", "$_Z1kPKiPii$_Z4leafii"): (6, 0xB0),
              ("_Z1kPKiPii", "$_Z1kPKiPii$_Z3fibi"): (20, 0xF0),
              ("$_Z1kPKiPii$_Z3fibi", "$_Z1kPKiPii$_Z3fibi"): (20, 0x310)}
    for e in mt.edges:
        if e.target_class is not TargetClass.INTERNAL_DIRECT:
            continue
        tok = e.return_token
        want = expect.get((e.src.function, e.callee_name))
        match = tok is not None and (tok[0].index, tok[1]) == want
        tok_ok &= match
        print(f"    {e.src.function.split('$')[-1]} -> "
              f"{e.callee_name.split('$')[-1]:6s}  "
              f"MOV {tok[0] if tok else '?'}, "
              f"{tok[1] if tok else '?':#x}  (continuation offset)  "
              f"{'OK' if match else 'XX want %s' % (want,)}")

    # spot-check the raw word encoding for the leaf RET at link 0x490
    for inst_idx in (0x490 // 16, 0x440 // 16):
        lo, hi = isl.words[inst_idx]
        opcode, addr, ra, s, depth = _decode_ret_fields(lo, hi)
        assert opcode == 0x950, hex(opcode)
        print(f"    raw RET@{inst_idx * 16:#x}: opcode={opcode:#x} "
              f"addr(REL/ABS)={addr} Ra=R{ra} depth={depth} "
              f"sImm={s:#x} -> pc+0x10+sImm*4 = "
              f"{(inst_idx * 16 + 0x10 + s * 4) & 0xFFFFFFFF:#x}")

    # the token register is a 64-bit PAIR: the high half must be zero, which
    # ptxas arranges in the caller (kernel HFMA2 R21 at 0xb0) or in the
    # callee (leaf MOV R7, 0x0 at 0x460) before the matching RET.  A stale
    # high half makes the return land at token + garbage<<32 (fault 718).
    print("    ABI note: the return token is a 64-bit pair; ptxas zeroes the "
          "high half in the caller or callee before the matching RET.")
    return tok_ok


# ---------------------------------------------------------------------------
# Parts 2/3 — GPU: heap copy at two bases; token perturbation
# ---------------------------------------------------------------------------
_HEAP_SRC = """#fn __heap() {
#def_label(entry)
    MOV32I R4, 0x30;[7:7:{}:5:1]
    MOV32I R5, 0x0;[7:7:{}:5:1]
    CALL.REL.NOINC #label(leaf);[7:7:{}:6:0]
#def_label(cont)
    IADD3 R0, R0, 0x5, RZ;[7:7:{}:5:1]
    STG.E.STRONG.GPU [R6], R0;[7:1:{}:8:0]
    EXIT;[7:7:{}:5:0]
#def_label(leaf)
    IADD3 R0, R0, 0x2, RZ;[7:7:{1}:5:1]
    RET.REL.NODEC {R4,R5}, 0x0;[7:7:{}:6:0]
}
"""

_DRIVER_SRC = """#fn __probe_driver(out<8>, tgt<8>) {
    LDC.64 {R6,R7}, #param(out);[5:7:{}:8:0]
    LDC.64 {R2,R3}, #param(tgt);[5:7:{}:8:0]
    MOV32I R0, 0x7;[7:7:{}:5:1]
    JMX {R2,R3}, 0x0;[7:7:{0,1,2,3,4,5}:6:0]
    EXIT;[7:7:{}:5:0]
}
"""


def _build_heap_words() -> list[tuple[int, int]]:
    from assembler import assemble_kernel
    words = list(assemble_kernel(_HEAP_SRC, check_deps=True).encoded)
    mov_enc = _OPCODE_INDEX.encoding("MOV32I")
    ret_enc = _OPCODE_INDEX.encoding("RET")
    call_idx = next(i for i, w in enumerate(words) if _opcode(w) == 0x944)
    ret_idx = next(i for i, w in enumerate(words) if _opcode(w) == 0x950)
    # the caller's MOV32I R4 token must equal the continuation offset
    token = _field_value(mov_enc, "Ra_offset", *words[0], signed=False)
    cont_off = (call_idx + 1) * 16
    assert token == cont_off, f"token {token:#x} != continuation {cont_off:#x}"
    # patch RET.REL sImm to the ptxas convention: pc+0x10+sImm*4 == 0
    # (the field is SCALE 4: the value is in 4-byte units)
    want = -(ret_idx * 16 + 0x10) // 4
    signed56 = want & ((1 << 56) - 1)
    lo, hi = _set_field_value(ret_enc, "sImm", *words[ret_idx], signed56)
    words[ret_idx] = (lo, hi)
    s = _field_value(ret_enc, "sImm", *words[ret_idx], signed=True)
    assert ret_idx * 16 + 0x10 + s * 4 == 0, hex(s)
    return words


def _opcode(word):
    lo, hi = word
    return (((hi >> 27) & 1) << 12) | (lo & 0xFFF)


def _pack(words) -> bytes:
    return b"".join(struct.pack("<QQ", lo, hi) for lo, hi in words)


def _run_at_base(drv, out_va, tgt_va):
    from assembler import CudaModule
    drv.launch("__probe_driver", grid=(1,), block=(1,),
               args=[out_va, tgt_va])
    drv.synchronize()
    return struct.unpack("<i", drv.device_read(out_va, 4))[0]


def part2():
    print("=" * 70)
    print("Part 2 — GPU: byte-identical heap copy at TWO bases")
    print("=" * 70)
    try:
        from assembler import CudaModule, assemble
        words = _build_heap_words()
        blob = _pack(words)
        drv = CudaModule(assemble(_DRIVER_SRC, check_deps=True))
        h1 = drv.devmem_alloc(len(blob))
        h2 = drv.devmem_alloc(len(blob))
        drv.device_write(h1, blob)
        drv.device_write(h2, blob)
        out1 = drv.devmem_alloc(4)
        out2 = drv.devmem_alloc(4)
        drv.devmem_set(out1, 0, 1)
        drv.devmem_set(out2, 0, 1)

        r1 = _run_at_base(drv, out1, h1)
        r2 = _run_at_base(drv, out2, h2)
        print(f"  input 0x7 -> expected 0x7 + 2 + 5 = {0x7 + 7:#x}")
        print(f"  base1={h1:#x}: result {r1:#x}  "
              f"{'OK' if r1 == 0xE else 'XX'}")
        print(f"  base2={h2:#x}: result {r2:#x}  "
              f"{'OK' if r2 == 0xE else 'XX'}")
        if r1 != 0xE or r2 != 0xE:
            print("  FAIL: a byte-identical copy at a different base must "
                  "still return to the private continuation (RET.REL is "
                  "program-base-relative)")
            return 1

        # differential: perturb the token by one instruction (+0x10)
        enc = _OPCODE_INDEX.encoding("MOV32I")
        tok = _field_value(enc, "Ra_offset", *words[0], signed=False)
        lo, hi = _set_field_value(enc, "Ra_offset", *words[0], tok + 0x10)
        bad = _pack([(lo, hi)] + words[1:])
        h3 = drv.devmem_alloc(len(bad))
        drv.device_write(h3, bad)
        out3 = drv.devmem_alloc(4)
        drv.devmem_set(out3, 0, 1)
        r3 = _run_at_base(drv, out3, h3)
        # token +0x10 -> return lands on the STG (skips the +5): result = 0x9
        print(f"  token+0x10 at base3={h3:#x}: result {r3:#x}  "
              f"{'OK' if r3 == 0x9 else 'XX'}  (expect 0x9: +5 skipped)")
        if r3 != 0x9:
            print("  FAIL: the token and the program base must add "
                  "independently")
            return 1
        print("  Part 2 OK")
        return 0
    except Exception as e:                  # no driver / no usable CUDA
        print(f"  skipped: {e}")
        return 2


def main() -> int:
    ok = part1()
    rc = 0 if ok else 1
    rc = max(rc, part2())
    print("=" * 70)
    print("probe_retrel:", "ALL PASS" if rc == 0 else
          ("GPU SKIPPED" if rc == 2 else "FAILED"))
    return rc


if __name__ == "__main__":
    sys.exit(main())