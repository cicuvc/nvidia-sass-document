import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from assembler import assemble, CudaModule
from fma_ref import is_denorm_bits

# ---------------------------------------------------------------------------
# FMNMX / FSET / FSETP — FP32 min-max / compare, bit-level verification (SM120).
# All three execute on int_pipe (integer pipe), not fmalighter.
#
# FMNMX  Rd = min/max(Ra, Rb); sense by the Pp@not bit (PT=MIN, !PT=MAX).
#        .NAN = IEEE-754-2019 minimum/maximum (NaN propagates to 0x7fffffff);
#        default nonan = IEEE-754-2008 minNum/maxNum (NaN -> the other op).
#        .XORSIGN = result magnitude from min/max, sign forced to sa^sb.
#        .FTZ flushes denormal inputs (and a denormal result).
# FSET   Rd = (Ra FCMP Rb) BOP Pp -> 0x00000000 / 0xFFFFFFFF.
# FSETP  Pu = (Ra FCMP Rb) BOP Pp,  Pv = !Pu.
# FCMP: F LT EQ LE GT NE GE NUM NAN LTU EQU LEU GTU NEU GEU T
#   ordered (no U): false when either operand is NaN
#   U versions: true when NaN involved (unordered); NUM=ordered, NAN=unordered
# ---------------------------------------------------------------------------

NAN = 0x7FFFFFFF

def isnan(x):
    return (x & 0x7F800000) == 0x7F800000 and (x & 0x7FFFFF) != 0


def fcmp(a, b, op):
    nan = isnan(a) or isnan(b)
    if op == "F": return 0
    if op == "T": return 1
    if op == "NUM": return 0 if nan else 1
    if op == "NAN": return 1 if nan else 0
    fa = struct.unpack("<f", struct.pack("<I", a))[0]
    fb = struct.unpack("<f", struct.pack("<I", b))[0]
    t = {"LT": fa < fb, "EQ": fa == fb, "LE": fa <= fb,
         "GT": fa > fb, "NE": fa != fb, "GE": fa >= fb,
         "LTU": fa < fb, "EQU": fa == fb, "LEU": fa <= fb,
         "GTU": fa > fb, "NEU": fa != fb, "GEU": fa >= fb}
    if nan:
        return 1 if op.endswith("U") else 0
    return 1 if t[op] else 0


def fsetp(a, b, op, bop, pp):
    c = fcmp(a, b, op)
    pu = {"AND": c & pp, "OR": c | pp, "XOR": c ^ pp}[bop]
    pv = {"AND": (1 - c) & pp, "OR": (1 - c) | pp, "XOR": (1 - c) ^ pp}[bop]
    return pu, pv


def _mm(a, b, is_max):
    """IEEE min/max on raw f32 bits (no NaN; ±0 handled)."""
    fa = struct.unpack("<f", struct.pack("<I", a))[0]
    fb = struct.unpack("<f", struct.pack("<I", b))[0]
    if fa == fb:
        if fa == 0:
            return (a & 0x7FFFFFFF) if is_max else (a | 0x80000000)
        return a
    if is_max:
        return a if fa > fb else b
    return a if fa < fb else b


def fmnmx(a, b, is_max, nan_prop=False, xorsign=False, ftz=False):
    if ftz:
        a = a & 0x80000000 if is_denorm_bits(a) else a
        b = b & 0x80000000 if is_denorm_bits(b) else b
    an, bn = isnan(a), isnan(b)
    if an or bn:
        if nan_prop or (an and bn):
            return NAN
        return b if an else a
    r = _mm(a, b, is_max)
    if xorsign:
        r = (r & 0x7FFFFFFF) | ((((a >> 31) ^ (b >> 31)) & 1) << 31)
    return r


def bits(f): return struct.unpack("<I", struct.pack("<f", f))[0]

# ---------------------------------------------------------------------------
# FMNMX cases
# ---------------------------------------------------------------------------
ONE, TWO, THREE = 0x3F800000, 0x40000000, 0x40400000
NEG1, NEG2 = 0xBF800000, 0xC0000000
PZ, NZ = 0x00000000, 0x80000000
NANQ, PINF, MINF = 0x7FC00000, 0x7F800000, 0xFF800000
DEN1 = 0x00000001

fm_cases = []
def addm(label, a, b, mods, is_max, exp):
    fm_cases.append((label, a, b, mods, is_max, exp))

# FSET register output: 1.0f (0x3f800000) for true, 0 for false; full form needs .BF
fs_cases = []
def addfs(label, a, b, op, bop, pp, exp):
    fs_cases.append((label, a, b, op, bop, pp, exp))

addfs("LT-12", ONE, TWO, "LT", "AND", "PT", 0x3F800000)
addfs("GT-12", ONE, TWO, "GT", "AND", "PT", 0)
addfs("LT-NaN", NANQ, ONE, "LT", "AND", "PT", 0)
addfs("LTU-NaN", NANQ, ONE, "LTU", "AND", "PT", 0x3F800000)
addfs("LT-OR-pp0", ONE, TWO, "LT", "OR", "!PT", 0x3F800000)
addfs("LT-XOR-pp0", ONE, TWO, "LT", "XOR", "!PT", 0x3F800000)
addfs("NEU-12", ONE, TWO, "NEU", "AND", "PT", 0x3F800000)

# plain min/max
addm("min-12", ONE, TWO, "", False, ONE)
addm("max-12", ONE, TWO, "", True, TWO)
addm("min-neg", NEG2, ONE, "", False, NEG2)
addm("max-neg", NEG2, ONE, "", True, ONE)
# ±0
addm("min-+0-0", PZ, NZ, "", False, NZ)          # min -> -0
addm("max-+0-0", PZ, NZ, "", True, PZ)         # max -> +0
# NaN: nonan (minNum) vs .NAN
addm("min-NaN1", NANQ, ONE, "", False, ONE)
addm("max-NaN1", NANQ, ONE, "", True, ONE)
addm("min-1NaN", ONE, NANQ, "", False, ONE)
addm("min-NaNNaN", NANQ, NANQ, "", False, NAN)
addm("min-NaN1.NAN", NANQ, ONE, ".NAN", False, NAN)
addm("max-NaN1.NAN", NANQ, ONE, ".NAN", True, NAN)
# XORSIGN
addm("xs-1-2", ONE, TWO, ".XORSIGN", False, ONE)
addm("xs-1-neg2", ONE, NEG2, ".XORSIGN", False, NEG2)   # sa^sb=1 -> -2
addm("xs-neg1-2", NEG1, TWO, ".XORSIGN", False, NEG1)
addm("xs-neg1-neg2", NEG1, NEG2, ".XORSIGN", False, TWO)  # sa^sb=0 -> +2
addm("xs-max", ONE, NEG2, ".XORSIGN", True, NEG1)        # max(1,-2)=1 -> sa^sb=1 -> -1
# FTZ
addm("ftz-den", DEN1, ONE, ".FTZ", False, 0)
addm("ftz-den-out", DEN1, DEN1, ".FTZ", False, 0)

# ---------------------------------------------------------------------------
# FSET / FSETP cases
# ---------------------------------------------------------------------------
# FCMP with a few operand pairs; Bop=AND with Pp=PT gives the raw comparison.
fc_cases = []
for op in ("F","LT","EQ","LE","GT","NE","GE","NUM","NAN",
           "LTU","EQU","LEU","GTU","NEU","GEU","T"):
    for a, b, tag in ((ONE, TWO, "12"), (NANQ, ONE, "N1"), (ONE, NANQ, "1N"),
                      (PZ, NZ, "z"), (PINF, ONE, "i")):
        fc_cases.append((f"{op}-{tag}", a, b, op, "AND", "PT"))

# Bop with Pp = 0/1 (via !PT / PT); plus one real predicate-register input.
def setp_pp(a, b, op, bop, pp_val):
    fc_cases.append((f"{op}-{bop}-pp{pp_val}", a, b, op, bop,
                     "PT" if pp_val else "!PT"))

setp_pp(NANQ, ONE, "LT", "OR", 1)     # 0 OR 1 = 1 (Pv = 1 OR 1 = 1)
setp_pp(ONE, TWO, "GT", "AND", 1)     # 0 AND 1 = 0 (Pv = 1 AND 1 = 1)
setp_pp(ONE, TWO, "LT", "XOR", 1)     # 1 XOR 1 = 0 (Pv = 0 XOR 1 = 1)
setp_pp(ONE, TWO, "LT", "XOR", 0)     # 1 XOR 0 = 1 (Pv = 0 XOR 0 = 0)
setp_pp(ONE, TWO, "LT", "OR", 0)      # 1 OR 0 = 1 (Pv = 0 OR 0 = 0)
setp_pp(ONE, TWO, "GT", "OR", 0)      # 0 OR 0 = 0 (Pv = 1 OR 0 = 1)
fc_cases.append(("LT-P2reg", NANQ, ONE, "LT", "OR", "P2"))  # real pred input

# ---------------------------------------------------------------------------
# Build kernel
# ---------------------------------------------------------------------------
FMNMX = [("FMN", *c) for c in fm_cases]
FCMP = [("FSP", *c) for c in fc_cases]

# Each FSETP case: ISETP to set P2, FSETP to P0/P1, P2R P0 and P1 out.
lines = ["#fn fmx_test(out<8>) {",
         "    LDCU.64 {UR4, UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
         "    LDC.64 {R6, R7}, #param(out);[0:7:{}:1:0]"]
out = 0

def emit_fmnmx(label, a, b, mods, is_max, exp):
    global out
    lines.append("    MOV32I R10, 0x%08X;[7:7:{}:5:1]" % a)
    lines.append("    MOV32I R11, 0x%08X;[7:7:{}:5:1]" % b)
    pmod = "!PT" if is_max else "PT"
    lines.append(f"    FMNMX{mods} R4, R10, R11, {pmod};[7:7:{{}}:8:1]")
    lines.append("    MOV R20, RZ;[7:7:{}:15:1]")
    lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{out*4:X}], R4;[0:1:{{0}}:1:0]")
    out += 1

def emit_fsetp(label, a, b, op, bop, pp):
    global out
    lines.append("    MOV32I R10, 0x%08X;[7:7:{}:5:1]" % a)
    lines.append("    MOV32I R11, 0x%08X;[7:7:{}:5:1]" % b)
    if pp not in ("PT", "!PT"):
        lines.append(f"    ISETP.EQ.AND P2, PT, R10, R10, PT;[7:7:{{}}:8:1]")  # P2=1
    lines.append(f"    FSETP.{op}.{bop} P0, P1, R10, R11, {pp};[7:7:{{}}:8:1]")
    lines.append("    P2R R4, PR, RZ, 0x1;[7:7:{}:8:1]")
    lines.append("    P2R R5, PR, RZ, 0x2;[7:7:{}:8:1]")
    lines.append("    MOV R20, RZ;[7:7:{}:15:1]")
    lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{out*4:X}], R4;[0:1:{{0}}:1:0]")
    lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{(out+1)*4:X}], R5;[0:1:{{0}}:1:0]")
    out += 2

for c in FMNMX:
    emit_fmnmx(*c[1:])
for label, a, b, op, bop, pp, exp in fs_cases:
    lines.append("    MOV32I R10, 0x%08X;[7:7:{}:5:1]" % a)
    lines.append("    MOV32I R11, 0x%08X;[7:7:{}:5:1]" % b)
    lines.append(f"    FSET.BF.{op}.{bop} R4, R10, R11, {pp};[7:7:{{}}:8:1]")
    lines.append("    MOV R20, RZ;[7:7:{}:15:1]")
    lines.append(f"    STG.E desc[{{UR4,UR5}}][{{R6,R7}}+0x{out*4:X}], R4;[0:1:{{0}}:1:0]")
    out += 1
for c in FCMP:
    emit_fsetp(*c[1:])
lines += ["    EXIT;[7:7:{}:5:0]", "}"]

cubin = assemble("\n".join(lines))
Path("x.cubin").write_bytes(cubin)

# ---------------------------------------------------------------------------
# Run and compare
# ---------------------------------------------------------------------------
mod = CudaModule(cubin)
d = mod.devmem_alloc(4 * out)
mod.launch("fmx_test", grid=(1,), block=(1,), args=[d])
mod.synchronize()
vals = struct.unpack(f"<{out}I", mod.device_read(d, 4 * out))
mod.devmem_free(d)

ok = True
fails = 0
vi = 0
for label, a, b, mods, is_max, exp in fm_cases:
    got = vals[vi]; vi += 1
    if got != exp:
        ok = False; fails += 1
        if fails <= 12:
            print(f"FAIL FMNMX {label:<14} got={got:08x} exp={exp:08x}")
for label, a, b, op, bop, pp, exp in fs_cases:
    got = vals[vi]; vi += 1
    if got != exp:
        ok = False; fails += 1
        if fails <= 20:
            print(f"FAIL FSET {label:<12} got={got:08x} exp={exp:08x}")
for label, a, b, op, bop, pp in fc_cases:
    pu, pv = vals[vi], vals[vi+1] >> 1; vi += 2
    pp_val = 1 if pp == "PT" else (0 if "!" in pp else 1)
    epu, epv = fsetp(a, b, op, bop, pp_val)
    if pu != epu or pv != epv:
        ok = False; fails += 1
        if fails <= 20:
            print(f"FAIL FSETP {label:<16} got=({pu},{pv}) exp=({epu},{epv})")

print(f"=== {len(fm_cases)} FMNMX + {len(fs_cases)} FSET + {len(fc_cases)} FSETP, "
      f"{'ALL OK' if ok else f'{fails} FAILURES'} ===")
print("FMNMX: PT=min !PT=max; nonan=minNum (NaN->other), .NAN=propagate,")
print("       .XORSIGN = min/max magnitude, sign = sa^sb; .FTZ flushes")
print("FSET:  output 1.0f for true, 0 for false (NOT all-ones); needs .BF")
print("FSETP: Pu=(cmp) BOP Pp, Pv=(!cmp) BOP Pp (NOT !Pu for OR);")
print("       ordered cmp false on NaN, U true on NaN; NUM/NAN/F/T")
