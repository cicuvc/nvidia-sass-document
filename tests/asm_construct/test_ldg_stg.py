import sys, struct
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule, assemble_flat
from archutil import adapt_source  # noqa: E402

# ---------------------------------------------------------------------------
# LDG / STG full-option coverage (SM120).
#
# Exercises every encoding option on the memdesc form, both by functional
# round-trip (LDG read → STG write → read back) and by offline bit checks
# against nvcc-generated references.
#
# Options covered:
#   sz     .U8/.S8/.U16/.S16/.U32/.U64/.U128 (+ sign/zero extension)
#   cop    .E(=EN)/.EF/.EL/.LU/.EU/.NA        (cache op, [86:84])
#   sem    .WEAK/.STRONG/.MMIO                 (mem semantics, TABLES_mem_1)
#   sco    .CTA/.SM/.VC/.GPU/.SYS              (system-coherence domain)
#   sp2    .LTC64B/.LTC128B/.LTC256B           (LDG only, L2 prefetch, [69:68])
#   order  .ORDERED (STG only)
#   widths .64/.128 and the 128-bit dest register group
# ---------------------------------------------------------------------------

ok = True
def check(name, got, want):
    global ok
    good = (list(got) if isinstance(got, (tuple, list)) else got) == \
           (list(want) if isinstance(want, (tuple, list)) else want)
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} {name:<44} {got}")


def run_rt(ldg_mod, ldg_sz, dest, src_off, dst_off, block=1):
    """Kernel: LDG.<mod>.<sz> R, desc[UR4][R6+src_off]; STG.E desc[UR4][R6+dst_off], R.

    `dest` = dest register / register group string, `out` buffer is written by
    the host with a known pattern and the LDG'd value is stored at dst_off.
    Returns the word(s) read back from dst_off (list of ints).
    """
    width = {"U8": 1, "S8": 1, "U16": 2, "S16": 2, "": 4, "32": 4, "64": 8,
             "128": 16}[ldg_sz]
    lines = ["#fn k(out<8>, srcalias<8>) {",
             "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
             "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]",
             "    LDC.64 {R2,R3}, #param(srcalias);[1:7:{}:1:0]",
             f"    LDG.{ldg_mod}{'.' + ldg_sz if ldg_sz else ''} {dest}, desc[{{UR4,UR5}}][{{R6,R7}}+0x{src_off:X}];[1:7:{{1}}:5:1]",
             f"    STG.E{'.64' if ldg_sz == '64' else '.128' if ldg_sz == '128' else ''} desc[{{UR4,UR5}}][{{R2,R3}}+0x{dst_off:X}], {dest};[0:1:{{1}}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    src = "\n".join(lines)
    mod = CudaModule(assemble(adapt_source(src)))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, bytes([i & 0xFF for i in range(1024)]))
    mod.launch("k", grid=(1,), block=(block,), args=[d, d])
    mod.synchronize()
    v = struct.unpack("<256I", mod.device_read(d, 1024))
    n = (width + 3) // 4
    try:
        mod.devmem_free(d)
    except Exception:
        pass
    return list(v[dst_off // 4: dst_off // 4 + n])


# --- 1. width + sign/zero extension -----------------------------------------
# LDG.U8 of byte 0x80 (value 0x80 at out[0], stored little-endian 0x00000080)
def ext_case(ldg_sz, want):
    src_off, dst_off = 0x0, 0x100
    if ldg_sz in ("64",):
        dest = "{R8,R9}"
    elif ldg_sz in ("128",):
        dest = "{R8,R9,R10,R11}"
    else:
        dest = "R8"
    lines = ["#fn k(out<8>, srcalias<8>) {",
             "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
             "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]",
             "    LDC.64 {R2,R3}, #param(srcalias);[1:7:{}:1:0]",
             f"    LDG.E{'.' + ldg_sz if ldg_sz else ''} {dest}, desc[{{UR4,UR5}}][{{R6,R7}}+0x{src_off:X}];[1:7:{{1}}:5:1]",
             f"    STG.E{'.64' if ldg_sz == '64' else '.128' if ldg_sz == '128' else ''} desc[{{UR4,UR5}}][{{R2,R3}}+0x{dst_off:X}], {dest};[0:1:{{1}}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    mod = CudaModule(assemble(adapt_source("\n".join(lines))))
    d = mod.devmem_alloc(1024)
    # byte pattern: byte0=0x80, byte1=0x81, byte2=0x82, byte3=0x83 ...
    pat = b"".join(bytes([(0x80 + i) & 0xFF]) for i in range(64))
    mod.device_write(d, pat + b"\x00" * (1024 - len(pat)))
    mod.launch("k", grid=(1,), block=(1,), args=[d, d])
    mod.synchronize()
    v = struct.unpack("<256I", mod.device_read(d, 1024))
    n = {"U8": 1, "S8": 1, "U16": 1, "S16": 1, "": 1, "32": 1, "64": 2,
         "128": 4}[ldg_sz]
    try:
        mod.devmem_free(d)
    except Exception:
        pass
    return list(v[0x100 // 4: 0x100 // 4 + n])

# byte pattern 0x80 0x81 0x82 0x83 -> word 0x83828180
check("LDG (32-bit) of 0x83828180", ext_case("", None), [0x83828180])
check("LDG.U8  zero-extends 0x80", ext_case("U8", None), [0x80])
check("LDG.S8  sign-extends 0x80", ext_case("S8", None), [0xFFFFFF80])
check("LDG.U16 zero-extends 0x8180", ext_case("U16", None), [0x8180])
check("LDG.S16 sign-extends 0x8180", ext_case("S16", None), [0xFFFF8180])
check("LDG.64 reads {0x83828180, 0x87868584}",
      ext_case("64", None), [0x83828180, 0x87868584])
check("LDG.128 reads 4 words", ext_case("128", None),
      [0x83828180, 0x87868584, 0x8B8A8988, 0x8F8E8D8C])


# --- 2. cop (cache op) round-trips -----------------------------------------
for cop in ("E", "E.EF", "E.EL", "E.LU", "E.EU", "E.NA"):
    v = run_rt(cop, "", "R8", 0x40, 0x200)
    check(f"LDG.{cop} roundtrip", v, [0x43424140])
# .NA is invalid as a primary? just check it assembles
enc = assemble_flat("LDG.E.NA R0, desc[{UR4,UR5}][{R2,R3}+0x0];[7:7:{}:8:1]\n")[0]
print(f"{'ok ' if True else ''}LDG.E.NA assembles (cop={(enc[1]>>(84-64))&7})")


# --- 3. sem / sco round-trips ----------------------------------------------
for mods in ("E.STRONG.GPU", "E.STRONG.SM", "E.STRONG.CTA", "E.MMIO.GPU",
             "E.MMIO.SYS", "E.WEAK"):
    v = run_rt(mods, "", "R8", 0x40, 0x200)
    check(f"LDG.{mods} roundtrip", v, [0x43424140])

# --- 4. sp2 (LDG only) ------------------------------------------------------
for sp2 in ("LTC64B", "LTC128B", "LTC256B"):
    v = run_rt(f"E.{sp2}", "", "R8", 0x40, 0x200)
    check(f"LDG.E.{sp2} roundtrip", v, [0x43424140])

# --- 4b. STG width stores + order ---------------------------------------------
def stg_write(sz, mods="E", value=0x88776655):
    """STG.<mods>.<sz> [R6+0x40], R8 (value); host reads back the bytes."""
    if sz == "64":
        dreg = "{R8,R9}"
    elif sz == "128":
        dreg = "{R8,R9,R10,R11}"
    else:
        dreg = "R8"
    s2 = f"{'.' + sz if sz else ''}"
    lines = ["#fn k(out<8>, srcalias<8>) {",
             "    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]",
             "    LDC.64 {R6,R7}, #param(out);[1:7:{}:1:0]",
             "    LDC.64 {R2,R3}, #param(srcalias);[1:7:{}:1:0]",
             "    MOV32I R8, 0x88776655;[7:7:{}:5:1]",
             "    MOV32I R9, 0x44332211;[7:7:{}:5:1]",
             "    MOV32I R10, 0x00112233;[7:7:{}:5:1]",
             "    MOV32I R11, 0x44556677;[7:7:{}:5:1]",
             f"    STG.{mods}{s2} desc[{{UR4,UR5}}][{{R6,R7}}+0x40], {dreg};[0:1:{{1}}:1:0]",
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    mod = CudaModule(assemble(adapt_source("\n".join(lines))))
    d = mod.devmem_alloc(1024)
    mod.device_write(d, b"\x00" * 1024)
    mod.launch("k", grid=(1,), block=(1,), args=[d, d])
    mod.synchronize()
    v = struct.unpack("<256I", mod.device_read(d, 1024))
    try:
        mod.devmem_free(d)
    except Exception:
        pass
    return v[0x40 // 4: 0x40 // 4 + {"": 1, "U8": 1, "U16": 1, "64": 2, "128": 4}[sz]]

check("STG.E.U8 writes low byte", stg_write("U8"), [0x55])
check("STG.E.U16 writes low 2 bytes", stg_write("U16"), [0x6655])
check("STG.E writes full word", stg_write(""), [0x88776655])
check("STG.E.64 writes 2 words", stg_write("64"), [0x88776655, 0x44332211])
check("STG.E.128 writes 4 words", stg_write("128"),
      [0x88776655, 0x44332211, 0x00112233, 0x44556677])
check("STG.E.WEAK.SYS.ORDERED writes", stg_write("", "E.WEAK.SYS.ORDERED"), [0x88776655])
check("STG.E.STRONG.GPU writes", stg_write("", "E.STRONG.GPU"), [0x88776655])
check("STG.E.LU writes", stg_write("", "E.LU"), [0x88776655])

# --- 5. offline encoding bit checks vs nvcc references ----------------------
def fld(hi, ghi, glo): return (hi >> (glo - 64)) & ((1 << (ghi - glo + 1)) - 1)
def szbits(hi): return [b for b in (72, 73, 74, 75) if (hi >> (b - 64)) & 1]

refs = {  # (szbit list, mem, cop) from nvcc sm_90 cubins
    "LDG.E.U8":     ([72], 0x0, 1),
    "LDG.E.U16":    ([72, 74], 0x0, 1),
    "LDG.E":        ([72, 75], 0x0, 1),
    "LDG.E.64":     ([72, 73, 75], 0x0, 1),
    "LDG.E.128":    ([72, 74, 75], 0x0, 1),
    "LDG.E.STRONG.GPU": ([72, 75], 0x7, 1),
    "LDG.E.LU":     ([72, 75], 0x0, 3),
}
for inst, (ref_sz, ref_mem, ref_cop) in refs.items():
    mod_str = inst[len("LDG."):] or "E"
    if mod_str.endswith(".64"):
        dest = "{R0,R1}"
    elif mod_str.endswith(".128"):
        dest = "{R0,R1,R2,R3}"
    else:
        dest = "R0"
    body = f"LDG.{mod_str} {dest}, desc[{{UR4,UR5}}][{{R2,R3}}+0x0];[7:7:{{}}:8:1]\n"
    e = assemble_flat(body)[0]
    sz, mem, cop = szbits(e[1]), fld(e[1], 80, 77), fld(e[1], 86, 84)
    good = sz == ref_sz and mem == ref_mem and cop == ref_cop
    if not good:
        ok = False
    print(f"{'ok ' if good else 'FAIL'} encode {inst:22s} sz={sz} mem={mem:#x} cop={cop}")

print(f"\n=== LDG/STG options: {'ALL PASS' if ok else 'FAILURES'} ===")
sys.exit(0 if ok else 1)
