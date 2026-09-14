#!/usr/bin/env python3
"""LDCU (sm_120 uniform load-constant) — all 8 encoding variants, constructed
from SASS and probed on silicon.

The sm_120 dump exposes eight `LDCU` classes, grouped by three *source*
families x {scalar, .256} x {with, without an optional uniform predicate}:

  opcode   class                            source form
  ------   ------------------------------   ---------------------------------
  0x17ac   ldcu_const_RCR_                  c[bank][URa + off18]      (bound)
  0x1bac   ldcu_const_RCxR_                c[URa][URb + off17]       (bindless CX)
  0x19ac   ldcu_ur_offs_ {,optional_upx}   [URa64 + off32] (, UPp)   (VA)
  0x1dac   ldcu_256_const_RCR_             .256 + word_mask          (bound)
  0x15ac   ldcu_256_const_RCxR_            .256 + word_mask          (bindless)
  0x13ac   ldcu_256_ur_offs_ {,optional}   .256 + word_mask (, UPp)  (VA)

`LDCU` is the sm_120 rename of sm_90 `ULDC` (udp_pipe, constant -> uniform
register file).  This probe (a) assembles every reachable form and prints its
encoding, (b) measures the byte-offset semantics of the `URa` index, (c)
measures the `.256` `word_mask` layout, and (d) measures the VA form's
`[!]UPp` zero-fill enable.  The bindless (`c[URx]`) form needs a
driver-provided constant handle and is reported rather than asserted.

Run:  python3 tests/asm_construct/probe_ldcu_variants.py
"""
from __future__ import annotations
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, assemble_flat, CudaModule  # noqa: E402
from assembler import arch  # noqa: E402
from tools.sass_disasm import SASSDisasm, load_db  # noqa: E402

OK = True


if "--va-case" in sys.argv:
    # usage: --va-case <set> <use>   set=T/F for UP0, '-' unset; use='-' = ALT
    _set, _use = sys.argv[sys.argv.index("--va-case") + 1:][:2]
    _setup = {"T": "UISETP.EQ.AND UP0, UPT, URZ, URZ, UPT;[7:7:{}:5:1]",
              "F": "UISETP.NE.AND UP0, UPT, URZ, URZ, UPT;[7:7:{}:5:1]",
              "-": "UMOV UR9, URZ;[7:7:{}:5:1]"}[_set]
    _guard = "" if _use == "-" else ", " + _use
    _src = (
        "#fn t(ptr<8>, out<1024>) {\n"
        "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]\n"
        "    LDC.64 {R6, R7}, #param(out);[1:7:{}:1:0]\n"
        "    LDCU.64 {UR6, UR7}, #param(ptr);[2:7:{}:1:0]\n"
        "    UMOV UR20, 0x11111111;[7:7:{}:5:1]\n"
        "    UMOV UR21, 0x22222222;[7:7:{}:5:1]\n"
        f"    {_setup}\n"
        "    UMOV UR13, URZ;[7:7:{}:5:1]\n"
        f"    LDCU.64 {{UR20,UR21}}, [UR6+0x0]{_guard};[3:7:{{2}}:1:0]\n"
        "    UMOV UR14, UR20;[7:7:{3}:5:1]\n"
        "    UMOV UR14, UR20;[7:7:{3}:5:1]\n"
        "    IADD3 R2, PT, PT, RZ, UR14, RZ;[7:7:{}:8:1]\n"
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R2;[7:7:{0,1}:1:0]\n"
        "    UMOV UR14, UR21;[7:7:{3}:5:1]\n"
        "    IADD3 R3, PT, PT, RZ, UR14, RZ;[7:7:{}:8:1]\n"
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x4], R3;[7:7:{0,1}:1:0]\n"
        "    EXIT;[7:7:{}:5:0]\n}")
    try:
        _m = CudaModule(assemble(_src, check_deps=False))
        _o = _m.devmem_alloc(64)
        _b = _m.devmem_alloc(256)
        _m.device_write(_b, struct.pack("<4I", 0xA1B2C3D4, 0x55667788, 3, 4))
        _m.launch("t", grid=(1,), block=(1,), args=[_b, _o])
        _m.synchronize()
        _lo, _hi = struct.unpack("<2I", _m.device_read(_o, 8))
        print(f"0x{_lo:08X} 0x{_hi:08X}")
    except Exception as _e:  # noqa: BLE001
        print(str(_e))
    sys.exit(0)


def check(name: str, good: bool, detail: str = "") -> None:
    global OK
    OK &= good
    print(f"{'ok  ' if good else 'FAIL'} {name:46s} {detail}")


# --------------------------------------------------------------------------
# A. encodings
# --------------------------------------------------------------------------
ENCODINGS = [
    # (label, expected opcode, asm)
    ("bound  RCR",           0x17AC, "LDCU.64 {UR6,UR7}, c[0x3][UR4+0x100]"),
    ("bindless RCxR",        0x1BAC, "LDCU.64 {UR6,UR7}, c[UR4][UR5+0x100]"),
    ("VA ur_offs (no UPp)",  0x19AC, "LDCU.64 {UR6,UR7}, [UR4+0x100]"),
    ("VA ur_offs (UP0)",     0x19AC, "LDCU.64 {UR6,UR7}, [UR4+0x100], UP0"),
    ("256 bound RCR",        0x1DAC,
     "LDCU.256 {UR8,UR9}, {UR4,UR5}, c[0x3][UR4+0x100], 0x33"),
    ("256 bindless RCxR",    0x15AC,
     "LDCU.256 {UR8,UR9}, {UR4,UR5}, c[UR14][UR5+0x100], 0x33"),
    ("256 VA ur_offs",       0x13AC,
     "LDCU.256 {UR8,UR9}, {UR4,UR5}, [UR6+0x100], 0x33"),
    ("256 VA ur_offs UP0",   0x13AC,
     "LDCU.256 {UR8,UR9}, {UR4,UR5}, [UR6+0x100], 0x33, UP0"),
]

print("== A. encodings (lo64 hi64) ==")
encs = {}
for label, expect_op, asm in ENCODINGS:
    try:
        (lo, hi), = assemble_flat(asm + ";[0:7:{}:1:0]")
    except Exception as e:  # noqa: BLE001
        check(f"{label}", False, f"assemble failed: {e}")
        continue
    op = ((hi >> 27) & 1) << 12 | (lo & 0xFFF)
    check(label, op == expect_op,
          f"op=0x{op:04x} exp=0x{expect_op:04x}  {lo:016x} {hi:016x}")
    encs[label] = (lo, hi)

# The .256 word_mask is a real, disassemblable field (LDG.256 shares it).
if encs:
    ds = SASSDisasm(load_db("sm120.json"))
    for label, (lo, hi) in encs.items():
        text, cls = ds.disasm(lo, hi)
        print(f"     disasm[{label:22s}] {text or '<no round-trip>':64s} ({cls})")

# --------------------------------------------------------------------------
# B. GPU: the bound-form URa is a BYTE offset added to the constant address
# --------------------------------------------------------------------------
print("\n== B. bound form c[0x0][URa+0x380] (in = 0x1122334455667788) ==")


def uridx_kernel(idx: int) -> str:
    return (
        "#fn t(in<8>, out<1024>) {\n"
        "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]\n"
        "    LDC.64 {R6, R7}, #param(out);[1:7:{}:1:0]\n"
        f"    UMOV UR12, 0x{idx:X};[2:7:{{}}:5:1]\n"
        "    LDCU UR20, c[0x0][UR12+0x380];[3:7:{2}:1:0]\n"
        "    UMOV UR13, UR20;[7:7:{3}:5:1]\n"
        "    UMOV UR13, UR20;[7:7:{3}:5:1]\n"
        "    UMOV UR21, UR20;[7:7:{3}:5:1]\n"
        "    IADD3 R2, PT, PT, RZ, UR21, RZ;[7:7:{}:8:1]\n"
        "    STG.E desc[{UR4,UR5}][{R6,R7}+0x0], R2;[7:7:{0,1}:1:0]\n"
        "    EXIT;[7:7:{}:5:0]\n}")


# params: in @0x380, out @0x388  -> URa byte offset 0/4 reaches low/high word,
# 8 reaches the next 8-byte slot (the `out` pointer's low word, non-zero).
IN = 0x1122334455667788


def uridx_value(idx: int):
    mod = CudaModule(assemble(uridx_kernel(idx), check_deps=False))
    out = mod.devmem_alloc(1024)
    mod.device_write(out, bytes(1024))
    mod.launch("t", grid=(1,), block=(1,), args=[IN, out])
    mod.synchronize()
    v = struct.unpack("<1I", mod.device_read(out, 4))[0]
    mod.devmem_free(out)
    return v


try:
    v0 = uridx_value(0)
    v4 = uridx_value(4)
    check("URa=0  -> low word 0x55667788", v0 == 0x55667788, f"got 0x{v0:08X}")
    check("URa=4  -> high word 0x11223344", v4 == 0x11223344, f"got 0x{v4:08X}")
except Exception as e:  # noqa: BLE001
    check("URa byte-offset probe", False, str(e))

# --------------------------------------------------------------------------
# C. GPU: .256 word_mask = masked *compaction* (32-byte block)
# --------------------------------------------------------------------------
# params a,b,c,d (8 bytes each) => words 0..7:
#   0,1=A  2,3=B  4,5=C  6,7=D
print("\n== C. .256 word_mask: bit i selects 32-bit word i; selected words "
      "compact into URd (bits 0-3) / URd2 (bits 4-7) ==")
A, B, C, D = 0xAAAAAAAAAAAAAAAA, 0xBBBBBBBBBBBBBBBB, \
            0xCCCCCCCCCCCCCCCC, 0xDDDDDDDDDDDDDDDD
WORDS = [A & 0xFFFFFFFF, (A >> 32) & 0xFFFFFFFF,
         B & 0xFFFFFFFF, (B >> 32) & 0xFFFFFFFF,
         C & 0xFFFFFFFF, (C >> 32) & 0xFFFFFFFF,
         D & 0xFFFFFFFF, (D >> 32) & 0xFFFFFFFF]


def mask_kernel(mask: int) -> str:
    lo = bin(mask & 0xF).count("1")
    hi = bin((mask >> 4) & 0xF).count("1")
    gd = {4: "{UR4,UR5,UR6,UR7}", 2: "{UR4,UR5}", 1: "UR4", 0: "URZ"}[lo]
    gd2 = {4: "{UR8,UR9,UR10,UR11}", 2: "{UR8,UR9}", 1: "UR8", 0: "URZ"}[hi]
    regs = ([8 + i for i in range(hi)] if hi else []) + \
           ([4 + i for i in range(lo)] if lo else [])
    body = ""
    for i, ur in enumerate(regs):
        body += (
            f"    UMOV UR13, UR{ur};[7:7:{{3}}:5:1]\n"
            f"    UMOV UR13, UR{ur};[7:7:{{3}}:5:1]\n"
            f"    UMOV UR21, UR{ur};[7:7:{{3}}:5:1]\n"
            f"    IADD3 R2, PT, PT, RZ, UR21, RZ;[7:7:{{}}:8:1]\n"
            f"    STG.E desc[{{UR14,UR15}}][{{R6,R7}}+0x{i*4:X}], R2;"
            f"[7:7:{{0,1}}:1:0]\n")
    return (
        "#fn t(a<8>, b<8>, c<8>, d<8>, out<1024>) {\n"
        "    LDCU.64 {UR14, UR15}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]\n"
        "    LDC.64 {R6, R7}, #param(out);[1:7:{}:1:0]\n"
        f"    LDCU.256 {gd2}, {gd}, c[0x0][0x380], 0x{mask:X};[2:7:{{}}:1:0]\n"
        "    UMOV UR13, UR4;[7:7:{2}:5:1]\n"
        "    UMOV UR13, UR8;[7:7:{2}:5:1]\n" + body +
        "    EXIT;[7:7:{}:5:0]\n}")


def mask_run(mask: int):
    lo = bin(mask & 0xF).count("1")
    hi = bin((mask >> 4) & 0xF).count("1")
    regs = ([8 + i for i in range(hi)] if hi else []) + \
           ([4 + i for i in range(lo)] if lo else [])
    mod = CudaModule(assemble(mask_kernel(mask), check_deps=False))
    out = mod.devmem_alloc(256)
    mod.device_write(out, bytes(256))
    mod.launch("t", grid=(1,), block=(1,), args=[A, B, C, D, out])
    mod.synchronize()
    v = list(struct.unpack(f"<{max(len(regs),1)}I",
                           mod.device_read(out, max(len(regs), 1) * 4)))
    mod.devmem_free(out)
    # expected: words whose bit is set, compacted per nibble
    low = [WORDS[i] for i in range(4) if mask & (1 << i)]
    high = [WORDS[i] for i in range(4, 8) if mask & (1 << i)]
    return v, high + low  # read order: hi group first, then lo group


try:
    for mask in (0x01, 0x05, 0x0A, 0x0F, 0x10, 0x30, 0x33, 0x55, 0xAA, 0xFF):
        v, exp = mask_run(mask)
        check(f"mask=0x{mask:02X}", v == exp,
              f"got {[hex(x) for x in v]} exp {[hex(x) for x in exp]}")
except Exception as e:  # noqa: BLE001
    check("word_mask probe", False, str(e))

# --------------------------------------------------------------------------
# D. GPU: the VA / bindless sources need a driver handle
# --------------------------------------------------------------------------
# A CUDA 700 poisons the whole context, so each case runs in its own process.
import subprocess  # noqa: E402

# D. GPU: the VA form is a uniform global load; UPp is its zero-fill enable
# --------------------------------------------------------------------------
# A fault would poison the whole context, so each case runs in its own process.
import subprocess  # noqa: E402

print("\n== D. VA form [URa64+off] with a real global pointer: "
      "UPp is an active-low zero-fill enable ==")
# global buffer = {0xA1B2C3D4, 0x55667788}; dest pre-set to 0x11111111/0x22222222
LOAD = "0xA1B2C3D4 0x55667788"
ZERO = "0x00000000 0x00000000"
VA_CASES = [
    ("-", "-", LOAD, "no predicate (ALT !UPT) -> load"),
    ("-", "!UPT", LOAD, "!UPT -> load"),
    ("-", "UPT", ZERO, "UPT (true) -> zero-fill"),
    ("T", "UP0", ZERO, "UP0 true  -> zero-fill"),
    ("F", "UP0", LOAD, "UP0 false -> load"),
    ("T", "!UP0", LOAD, "!UP0 true  -> load"),
    ("F", "!UP0", ZERO, "!UP0 false -> zero-fill"),
]
for setv, use, exp, label in VA_CASES:
    r = subprocess.run([sys.executable, __file__, "--va-case", setv, use],
                       capture_output=True, text=True, timeout=300)
    got = (r.stdout.strip().splitlines() or ["<no output>"])[-1]
    check(label, got == exp, f"got {got} exp {exp}")

print("\n" + ("=== LDCU variant probe: ALL CHECKS OK ===" if OK
              else "=== LDCU variant probe: FAILURES ==="))
sys.exit(0 if OK else 1)
