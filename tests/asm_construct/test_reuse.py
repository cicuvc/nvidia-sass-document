import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import assemble, CudaModule

# ---------------------------------------------------------------------------
# Operand reuse cache — FFMA runtime semantics on SM120 (RTX 5090).
#
# Encoding: the 6th schedule-bracket element is a 3-bit field overloaded as
# batch_t or the reuse hint {reuse_a=bit0, reuse_b=bit1, reuse_c=bit2}
# (opex bits [124:122]; see notes/sm90/arch/control_codes.md).  Setting a
# reuse bit on FFMA instruction N marks that register operand's value for the
# operand-reuse cache; instruction N+1 reading the SAME register in the SAME
# operand position reads it from the cache instead of the register file.
#
# Verified semantics (all silent — never an illegal-instruction fault):
#   Q2 same register / same slot after a reuse producer  -> correct
#   Q3 DIFFERENT register in the same slot               -> falls back to RF
#                                                          (fresh value)
#   Q4 register overwritten between producer and consumer -> fresh (write
#                                                          invalidates cache)
#   Q5 cache holds only to the immediately next instruction
#   Q6 cache is keyed per-slot (A/B/C), identity-checked
#   H1 HAZARD: reuse on a source register that is ALSO the producer's
#      destination (read-modify-write) -> the next instruction reads the
#      STALE pre-instruction value (data corruption, no fault)
#
# Values: R10=1.0 R11=2.0 R12=3.0 R13=4.0 R17=5.0 (R6 = out pointer).
# Registers R14-R16 fault the launch path for hand-built ELFs — see
# notes/sm90/arch/sm120_findings.md section 10; they are avoided here.
# ---------------------------------------------------------------------------

INIT = [
    "MOV32I R10, 0x3F800000;[7:7:{}:5:1]",
    "MOV32I R11, 0x40000000;[7:7:{}:5:1]",
    "MOV32I R12, 0x40400000;[7:7:{}:5:1]",
]

cases = []
def add(label, test_lines, store_reg, expect, reason=""):
    cases.append((label, test_lines, store_reg, expect, reason))

add("ctrl", ["FFMA R3, R10, R11, R12;[7:7:{}:8:1]"], "R3", 5.0,
    "plain FFMA, no reuse")
add("same-slot-same-reg",
    ["FFMA R3, R10, R11, R12;[7:7:{}:8:0:1]",
     "FFMA R4, R10, R11, R12;[7:7:{}:8:1]"], "R4", 5.0,
    "same reg same slot after reuse producer -> correct")
add("diff-reg-slot-A",
    ["FFMA R3, R10, R11, R12;[7:7:{}:8:0:1]",
     "FFMA R4, R13, R11, R12;[7:7:{}:8:1]"], "R4", 11.0,
    "different reg in slot A -> RF fallback (fresh 4*2+3)")
add("overwrite-A",
    ["FFMA R3, R10, R11, R12;[7:7:{}:8:0:1]",
     "MOV R10, R13;[7:7:{}:5:1]",
     "FFMA R4, R10, R11, R12;[7:7:{}:8:1]"], "R4", 11.0,
    "write to R10 between producer/consumer -> fresh (11), not stale (5)")
add("skip-one",
    ["FFMA R3, R10, R11, R12;[7:7:{}:8:0:1]",
     "FFMA R4, R13, R11, R12;[7:7:{}:8:1]",
     "FFMA R5, R10, R11, R12;[7:7:{}:8:1]"], "R5", 5.0,
    "cache only holds to the immediate next instruction")
add("reuse-B-diff",
    ["FFMA R3, R10, R11, R12;[7:7:{}:8:0:2]",
     "FFMA R4, R10, R13, R12;[7:7:{}:8:1]"], "R4", 7.0,
    "slot B different reg -> fresh (1*4+3)")
add("reuse-C-diff",
    ["FFMA R3, R10, R11, R12;[7:7:{}:8:0:4]",
     "FFMA R4, R10, R11, R13;[7:7:{}:8:1]"], "R4", 6.0,
    "slot C different reg -> fresh (1*2+4)")
add("cross-slot-A-to-B",
    ["FFMA R3, R10, R11, R12;[7:7:{}:8:0:1]",
     "FFMA R4, R11, R10, R12;[7:7:{}:8:1]"], "R4", 5.0,
    "reused R10 read in slot B (not A) -> RF fresh (2*1+3)")
add("reuse-AC-diff",
    ["FFMA R3, R10, R11, R12;[7:7:{}:8:0:5]",
     "FFMA R4, R13, R11, R17;[7:7:{}:8:1]"], "R4", 13.0,
    "multi-reuse A+C with different consumer regs -> fresh (4*2+5)")

# ---- HAZARD: reuse on a source that is ALSO the destination --------------
add("hazard-RMW-A",
    ["FFMA R10, R10, R11, R12;[7:7:{}:8:0:1]",
     "FFMA R4, R10, R11, R12;[7:7:{}:8:1]"], "R4", 5.0,
    "STALE: R10 reused while dest; consumer gets pre-FFMA 1.0 (not 5.0)")
add("hazard-RMW-B",
    ["FFMA R10, R11, R10, R12;[7:7:{}:8:0:2]",
     "FFMA R4, R11, R10, R12;[7:7:{}:8:1]"], "R4", 5.0,
    "STALE: same hazard on slot B (2*1+3, not 2*5+3=13)")
add("hazard-RMW-C",
    ["FFMA R10, R11, R12, R10;[7:7:{}:8:0:4]",
     "FFMA R4, R11, R12, R10;[7:7:{}:8:1]"], "R4", 7.0,
    "STALE: same hazard on slot C (2*3+1, not 2*3+5=11)")
add("hazard-RMW-gap",
    ["FFMA R10, R10, R11, R12;[7:7:{}:8:0:1]",
     "FFMA R8, R13, R11, R12;[7:7:{}:8:1]",
     "FFMA R4, R10, R11, R12;[7:7:{}:8:1]"], "R4", 13.0,
    "one instruction gap -> fresh (hazard window is exactly 1 instr)")
add("hazard-RMW-ctrl",
    ["FFMA R10, R10, R11, R12;[7:7:{}:8:1]",
     "FFMA R4, R10, R11, R12;[7:7:{}:8:1]"], "R4", 13.0,
    "control without reuse -> fresh (5*2+3)")

lines = ["#fn reuse_test(out<256>) {",
         "    LDCU.64 UR4, c[0x0][0x358];[0:7:{}:1:0]",
         "    LDC.64 R6, #param(out);[0:7:{}:1:0]",
         "    MOV32I R13, 0x40800000;[7:7:{}:5:1]",
         "    MOV32I R17, 0x40A00000;[7:7:{}:5:1]"]
out_idx = 0
for label, test_lines, store_reg, expect, reason in cases:
    lines += ["    " + l for l in INIT]
    lines += ["    " + l for l in test_lines]
    lines.append(f"    STG.E desc[UR4][R6.64+0x{out_idx*4:X}], {store_reg};[0:1:{{0}}:1:0]")
    out_idx += 1
lines += ["    EXIT;[7:7:{}:5:0]",
          "}"]

cubin = assemble("\n".join(lines))
Path("x.cubin").write_bytes(cubin)
mod = CudaModule(cubin)
d = mod.devmem_alloc(4 * len(cases))
mod.launch("reuse_test", grid=(1,), block=(1,), args=[d])
mod.synchronize()
vals = struct.unpack(f"<{len(cases)}I", mod.device_read(d, 4 * len(cases)))
mod.devmem_free(d)

ok = True
print("=== Operand Reuse Cache (SM120) ===")
print(f"{'case':<18} {'got':>8} {'exp':>8}  note")
for (label, _tl, _sr, expect, reason), v in zip(cases, vals):
    status = "OK" if v == struct.unpack("<I", struct.pack("<f", expect))[0] else "FAIL"
    ok &= (status == "OK")
    print(f"{label:<18} {v:08x} {expect:>8.6g}  {reason}  [{status}]")

print()
print(f"=== {'ALL OK' if ok else 'FAILURES'} ===")
print("Findings (SM120):")
print("  reuse cache is identity-matched + write-invalidated; conventions")
print("  violations never fault (no ILLEGAL_INSTRUCTION).")
print("  HAZARD: reuse on a source register that is also the instruction's")
print("  destination serves the STALE pre-instruction value to the next")
print("  instruction (window = exactly 1 instruction).")
