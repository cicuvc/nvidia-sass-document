import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule, assemble_flat

# ---------------------------------------------------------------------------
# BREV / FLO / POPC — MUFU-class bit-manipulation ops (mio_pipe, VQ_MUFU)
# Verified on SM120.
#
#   BREV Rd, Rb            Rd = bit-reversed Rb (bit i <-> bit 31-i)
#   POPC Rd, [!]Rb         Rd = popcount of Rb (or of ~Rb with [~])
#   FLO[.U32|.S32][.SH] Rd, Pu, [!]Rb     find-leading-one (PTX bfind)
#
# FLO semantics (matches PTX bfind):
#   FLO.U32    (bfind.u32):            Rd = index of MSB set bit (0..31)
#   FLO        (bfind.s32, default):   Rd = index of MSB bit differing from
#                                      the sign bit (pos: same as u32; neg:
#                                      index of MSB of ~Rb)
#   FLO.U32.SH (bfind.shiftamt.u32):   Rd = clz(Rb)  (leading-zero count)
#   FLO.SH     (bfind.shiftamt.s32):   Rd = clz(~Rb) for negative input
#   degenerate (no bit found):         Rd = 0xFFFFFFFF, Pu = 0
#   valid:                             Rd = index,    Pu = 1
#   [~] inverts Rb before scanning (find leading zero).
#
# Gotchas: all three are mio_pipe DECOUPLED_RD_WR_SCBD — the result write
# needs a scoreboard (`wr`) that consumers `req`; the Pu predicate needs a
# long (~20 NOP) cross-pipe delay before an @P consumer reads it.
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = got == want
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<34} got 0x{got & 0xffffffff:08x} want 0x{want & 0xffffffff:08x}")

def build(lines):
    hdr = ["    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
           "    LDC.64 {R6,R7}, #param(out);[0:7:{}:1:0]"]
    src = "#fn k(out<8>) {\n" + "\n".join(hdr + lines) + "\n    EXIT;[7:7:{}:5:0]\n}"
    return assemble(src)

def run_battery(name, instr, values, pu=False):
    """Run a list of (value, expected_Rd[, expected_Pu]) through `instr`.
    instr has R0 as input, R3 as result, P1 as Pu output."""
    global ok
    lines = []
    for i, case in enumerate(values):
        v = case[0]
        lines.append(f"    MOV32I R0, 0x{v:08X};[7:7:{{}}:5:1]")
        lines.append(instr)
        lines += [f"    NOP;[7:7:{{}}:5:1]"] * 20
        if pu:
            lines.append(f"    @P1 MOV32I R10, 0x1;[7:7:{{}}:5:1]")
            lines.append(f"    @!P1 MOV32I R10, 0x0;[7:7:{{}}:5:1]")
        lines.append(f"    IADD3 R4, R3, RZ, RZ;[7:7:{{1}}:5:1]")
        lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{i*8:X}], R4;[0:1:{{0}}:1:0]")
        if pu:
            lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{i*8+4:X}], R10;[7:1:{{}}:1:0]")
    cubin = build(lines)
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    try:
        mod.launch("k", grid=(1,), block=(1,), args=[d])
        mod.synchronize()
        v = struct.unpack("<256I", mod.device_read(d, 1024))
        mod.devmem_free(d)
    except RuntimeError as e:
        print(f"{name}: ERR {str(e)[:40]}")
        ok = False
        return
    for i, case in enumerate(values):
        got_rd = v[i * 2]
        want_rd = case[1]
        good = got_rd == want_rd
        if pu:
            got_pu, want_pu = v[i * 2 + 1], case[2]
            good = good and got_pu == want_pu
            status = "OK" if good else \
                f"FAIL (Pu got={got_pu} want={want_pu})"
        else:
            status = "OK" if good else "FAIL"
        ok = ok and good
        print(f"  {case[0]:08x} -> {got_rd:08x} (want {want_rd:08x})  "
              f"{('Pu=' + (str(got_pu) if pu else '')):8} {status}")

# --- BREV ----------------------------------------------------------------
run_battery("BREV", "    BREV R3, R0;[1:7:{}:5:1]",
            [(0x00000000, 0x00000000),
             (0x00000001, 0x80000000),
             (0x80000000, 0x00000001),
             (0xFFFF0000, 0x0000FFFF),
             (0x55555555, 0xAAAAAAAA),
             (0x12345678, 0x1E6A2C48)])

# --- POPC ----------------------------------------------------------------
run_battery("POPC", "    POPC R3, R0;[1:7:{}:5:1]",
            [(0x00000000, 0x00),
             (0xFFFFFFFF, 0x20),
             (0x80000000, 0x01),
             (0x0F0F0F0F, 0x10),
             (0x12345678, 0x0D)])
run_battery("POPC [~]", "    POPC R3, ~R0;[1:7:{}:5:1]",
            [(0x00000000, 0x20),
             (0xFFFFFFFF, 0x00),
             (0x0F0F0F0F, 0x10)])

# --- FLO.U32 (bfind.u32) with Pu -----------------------------------------
run_battery("FLO.U32", "    FLO.U32 R3, P1, R0;[1:7:{}:5:1]",
            [(0x00000001, 0x00, 1),
             (0x00000005, 0x02, 1),
             (0x80000000, 0x1F, 1),
             (0x0F0F0F0F, 0x1B, 1),
             (0xFFFFFFFF, 0x1F, 1),
             (0x00000000, 0xFFFFFFFF, 0)], pu=True)

# --- FLO.U32.SH (bfind.shiftamt.u32) -------------------------------------
run_battery("FLO.U32.SH", "    FLO.U32.SH R3, P1, R0;[1:7:{}:5:1]",
            [(0x00000005, 0x1D, 1),
             (0x00000001, 0x1F, 1),
             (0x80000000, 0x00, 1),
             (0xFFFFFFFF, 0x00, 1),
             (0x00000000, 0xFFFFFFFF, 0)], pu=True)

# --- FLO S32 (bfind.s32) -------------------------------------------------
run_battery("FLO.S32", "    FLO R3, P1, R0;[1:7:{}:5:1]",
            [(0x00000005, 0x02, 1),
             (0xFFFFFFF0, 0x03, 1),    # -16: MSB of ~b = 3
             (0x80000000, 0x1E, 1),    # -2^31: ~b = 0x7fffffff, MSB 30
             (0xFFFFFFFF, 0xFFFFFFFF, 0),
             (0x00000000, 0xFFFFFFFF, 0)], pu=True)

# --- FLO.SH (bfind.shiftamt.s32) -----------------------------------------
run_battery("FLO.SH", "    FLO.SH R3, P1, R0;[1:7:{}:5:1]",
            [(0x00000005, 0x1D, 1),
             (0xFFFFFFF0, 0x1C, 1),    # clz(0x0f) = 28
             (0x80000000, 0x01, 1),    # clz(0x7fffffff) = 1
             (0xFFFFFFFF, 0xFFFFFFFF, 0),
             (0x00000000, 0xFFFFFFFF, 0)], pu=True)

# --- FLO [~] (invert = find leading zero) --------------------------------
run_battery("FLO.U32 [~]", "    FLO.U32 R3, P1, ~R0;[1:7:{}:5:1]",
            [(0x0F0F0F0F, 0x1F, 1),    # ~b = 0xf0f0f0f0 -> MSB 31
             (0x00000001, 0x1F, 1),    # ~b = 0xfffffffe -> MSB 31
             (0xFFFFFFFF, 0xFFFFFFFF, 0)])

# --- offline encoding self-check: operand forms ---------------------------
enc = assemble_flat(
    "BREV R3, R0;[1:7:{}:5:1]\n"
    "BREV R3, 0x5;[1:7:{}:5:1]\n"
    "BREV R3, UR5;[1:7:{}:5:1]\n"
    "POPC R3, R0;[1:7:{}:5:1]\n"
    "POPC R3, ~R0;[1:7:{}:5:1]\n"
    "POPC R3, 0x5;[1:7:{}:5:1]\n"
    "POPC R3, UR5;[1:7:{}:5:1]\n"
    "FLO.U32 R3, R0;[1:7:{}:5:1]\n"
    "FLO R3, P1, R0;[1:7:{}:5:1]\n"
    "FLO.SH R3, R0;[1:7:{}:5:1]\n"
    "FLO.U32 R3, 0x5;[1:7:{}:5:1]\n"
    "FLO R3, UR5;[1:7:{}:5:1]\n")
def op(lo, hi):
    return ((hi >> 27) & 1) << 12 | (lo & 0xFFF)
expects = [0x301, 0x901, 0x1d01,
           0x309, 0x309, 0x909, 0x1d09,
           0x300, 0x300, 0x300, 0x900, 0x1d00]
assert [op(*e) for e in enc] == expects, \
    f"opcodes {[hex(op(*e)) for e in enc]} != {[hex(x) for x in expects]}"
print("encoding self-check: BREV/POPC/FLO RRR/RIR/RUR opcodes OK")

print(f"\n=== BREV / FLO / POPC: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
