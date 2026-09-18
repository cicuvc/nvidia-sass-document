"""Closed-set assembler built-ins expanded before final SASS layout.

This is intentionally not a general macro language.  Built-ins produce normal
``ParsedInstruction`` objects, after which label resolution, EIATTR inference,
dependency checking and encoding use the ordinary assembler pipeline.
"""

from __future__ import annotations

from .operand import OperandKind
from .sass_parser import parse_sass


_BUILTIN_PREFIX = "_builtin_"


def _collect_used(insts):
    used = {
        "r": set(), "ur": set(), "p": set(), "up": set(), "sb": set(),
    }
    for inst in insts:
        if inst.mnemonic.startswith(_BUILTIN_PREFIX):
            # Fixed input registers still belong to the user program.
            for op in inst.operands:
                if op.kind == OperandKind.UREG and op.value != 255:
                    used["ur"].add(int(op.value))
            continue
        if inst.pred is not None:
            used["up" if inst.pred_uniform else "p"].add(inst.pred)
        s = inst.sched
        for sb in (s.wr_sb, s.rd_sb):
            if sb < 6:
                used["sb"].add(sb)
        used["sb"].update(s.req_bits)
        for op in inst.operands:
            if op.kind == OperandKind.REG:
                regs = op.regs if op.regs is not None else [op.value]
                used["r"].update(int(v) for v in regs if v != 255)
            elif op.kind in (OperandKind.UREG, OperandKind.INDEXED_RF,
                             OperandKind.MEM_DESC):
                regs = op.regs if op.regs is not None else [op.value]
                used["ur"].update(int(v) for v in regs if v != 255)
            elif op.kind == OperandKind.PRED:
                if op.value != 7:
                    used["p"].add(int(op.value))
            elif op.kind == OperandKind.UPRED:
                if op.value != 7:
                    used["up"].add(int(op.value))
            elif op.kind == OperandKind.SB:
                used["sb"].add(int(op.value))
            if op.kind == OperandKind.MEM_ADDR and op.value != 255:
                used["r"].add(int(op.value))
            if (op.kind == OperandKind.MEM_DESC and
                    op.addr_reg != 255):
                used["r"].add(int(op.addr_reg))
            if op.addr_ureg not in (None, 255):
                used["ur"].add(int(op.addr_ureg))
            if op.cbank_reg not in (None, 255):
                used["r"].add(int(op.cbank_reg))
            if op.cx_ureg not in (None, 255):
                used["ur"].add(int(op.cx_ureg))
    return used


def _take(used: dict, kind: str, count: int, limit: int, builtin: str):
    values = [v for v in range(limit) if v not in used[kind]][:count]
    if len(values) != count:
        pretty = {"r": "GPR", "ur": "UR", "p": "P",
                  "up": "UP", "sb": "SB"}[kind]
        raise ValueError(
            f"#!{builtin} needs {count} unused {pretty} resource(s), "
            f"but only {len(values)} are globally unused")
    used[kind].update(values)
    return values


def _take_contiguous(used: dict, kind: str, count: int, limit: int,
                     builtin: str):
    """Reserve a naturally ordered register group from the global free set."""
    for first in range(limit - count + 1):
        values = list(range(first, first + count))
        if all(v not in used[kind] for v in values):
            used[kind].update(values)
            return values
    pretty = {"r": "GPR", "ur": "UR"}[kind]
    raise ValueError(
        f"#!{builtin} needs {count} contiguous unused {pretty} resources")


def _expand_tmem_alloc_1cta(node, used, serial: int, entry_version: int):
    addr = int(node.operands[0].value)
    columns = int(node.operands[1].value)
    if addr == 255:
        raise ValueError("#!tmem_alloc_1cta output address cannot be URZ")
    if columns not in (32, 64, 128, 256, 512):
        raise ValueError(
            "#!tmem_alloc_1cta columns must be one of "
            "32, 64, 128, 256, or 512")
    units = columns // 32
    range_mask = (1 << units) - 1

    # The conservative v0 allocator never aliases a register mentioned by the
    # kernel.  A later liveness allocator can relax this without changing the
    # built-in's source contract.
    r_phase, r_one, r_mask, r_aux = _take(
        used, "r", 4, 255, "tmem_alloc_1cta")
    ur_part, ur_units, ur_mask = _take(
        used, "ur", 3, 79, "tmem_alloc_1cta")
    (pred,) = _take(used, "p", 1, 7, "tmem_alloc_1cta")
    (upred,) = _take(used, "up", 1, 7, "tmem_alloc_1cta")
    sb_exec, sb_mask_b, sb_result = _take(
        used, "sb", 3, 6, "tmem_alloc_1cta")

    retry = f"__bi_tmem_alloc_{serial}_retry"
    success = f"__bi_tmem_alloc_{serial}_success"
    done = f"__bi_tmem_alloc_{serial}_done"
    phase_addr = (f"[UR{ur_part}]" if entry_version == 1
                  else f"[UR{ur_part}+0x1c]")
    if entry_version == 1:
        # V1 packs the occupied-unit mask in the low 16 bits and the
        # allocation-head mask in the high 16 bits.
        mask_build = (f"""
IMAD.MOV.U32 R{r_mask}, RZ, RZ, 0x1ffff;[7:7:{{}}:5:1]
""" if units == 16 else f"""
IMAD.MOV.U32 R{r_mask}, RZ, RZ, {range_mask:#x};[7:7:{{}}:5:1]
SHF.L.U32 R{r_mask}, R{r_mask}, R{r_phase}, RZ;[7:7:{{}}:5:1]
SHF.L.U32 R{r_aux}, R{r_one}, R{r_phase}, RZ;[7:7:{{}}:5:1]
SHF.L.U32 R{r_aux}, R{r_aux}, 0x10, RZ;[7:7:{{}}:5:1]
LOP3.LUT R{r_mask}, R{r_aux}, R{r_mask}, RZ, 0xfc, !PT;[7:7:{{}}:5:1]
""")
        record = f"""
{mask_build}
IMAD.SHL.U32 R{r_phase}, R{r_phase}, 0x20, RZ;[7:7:{{}}:1:0]
UMOV UR{ur_mask}, 0x50;[7:7:{{}}:1:0]
ULEA UR{ur_mask}, UR{ur_units}, UR{ur_mask}, 0x18;[7:7:{{}}:9:1]
ATOMS.OR RZ, [UR{ur_mask}], R{r_mask};[7:{sb_exec}:{{}}:4:0]
STS [UR{addr}], R{r_phase};[7:{sb_result}:{{}}:1:0]
"""
    else:
        # V2 stores the occupied-unit and allocation-head masks separately.
        mask_build = (f"""
IMAD.MOV.U32 R{r_mask}, RZ, RZ, 0xffff;[7:7:{{}}:5:1]
IMAD.MOV.U32 R{r_aux}, RZ, RZ, 0x1;[7:7:{{}}:5:1]
""" if units == 16 else f"""
IMAD.MOV.U32 R{r_mask}, RZ, RZ, {range_mask:#x};[7:7:{{}}:5:1]
SHF.L.U32 R{r_mask}, R{r_mask}, R{r_phase}, RZ;[7:7:{{}}:4:1]
SHF.L.U32 R{r_aux}, R{r_one}, R{r_phase}, RZ;[7:7:{{}}:4:1]
""")
        record = f"""
{mask_build}
IMAD.SHL.U32 R{r_phase}, R{r_phase}, 0x20, RZ;[7:7:{{}}:4:1]
ATOMS.OR RZ, [UR{ur_part}+0x14], R{r_mask};[7:{sb_exec}:{{}}:4:0]
ATOMS.OR RZ, [UR{ur_part}+0x18], R{r_aux};[7:{sb_mask_b}:{{}}:4:0]
STS [UR{addr}], R{r_phase};[7:{sb_result}:{{}}:1:0]
"""

    # The elected lane owns the UTC operation; WARPSYNC makes the shared
    # result visible before the built-in returns.  Keep UR_units holding the
    # CTA id until V1 has formed its +0x50 bookkeeping address; UR_mask is the
    # retry operand/result instead.
    src = f"""
S2UR UR{ur_units}, SR_CgaCtaId;[{sb_exec}:7:{{}}:1:0]
UMOV UR{ur_part}, 0x40;[7:7:{{}}:1:0]
#coop_group
NOP;[7:7:{{}}:1:0]
ULEA UR{ur_part}, UR{ur_units}, UR{ur_part}, 0x18;[7:7:{{{sb_exec}}}:3:1]
LDS.U8 R{r_phase}, {phase_addr};[{sb_exec}:7:{{}}:2:0]
ISETP.NE.AND P{pred}, PT, R{r_phase}, RZ, PT;[7:7:{{{sb_exec}}}:13:1]
@P{pred} BPT.TRAP 0x1;[7:7:{{}}:5:0]
ELECT P{pred}, URZ, PT;[7:7:{{}}:13:1]
@!P{pred} BRA #label({done});[7:7:{{}}:5:0]
UMOV UR{ur_mask}, {units:#x};[7:7:{{}}:1:0]
IMAD.MOV.U32 R{r_one}, RZ, RZ, 0x1;[7:7:{{}}:4:1]
#def_label({retry})
DEPBAR.LE SB{sb_exec}, 0x36;[7:7:{{}}:4:0]
UTCATOMSWS.FIND_AND_SET.ALIGN UP{upred}, UR{ur_mask}, UR{ur_mask};[{sb_exec}:7:{{}}:2:0]
IMAD.U32 R{r_phase}, RZ, RZ, UR{ur_mask};[7:7:{{{sb_exec}}}:1:0]
BRA.U UP{upred}, #label({success});[7:7:{{}}:6:0]
NANOSLEEP 0x64;[7:7:{{}}:5:0]
UMOV UR{ur_mask}, {units:#x};[7:7:{{}}:5:1]
BRA #label({retry});[7:7:{{}}:5:0]
#def_label({success})
{record}
#def_label({done})
#coop_group
WARPSYNC.ALL;[7:7:{{{sb_exec},{sb_mask_b},{sb_result}}}:5:0]
"""
    expanded = parse_sass(src)
    for inst in expanded:
        if not inst.line:
            inst.line = node.line
    return expanded


def _expand_tmem_dealloc_1cta(node, used, serial: int, entry_version: int):
    addr = int(node.operands[0].value)
    columns = int(node.operands[1].value)
    if addr == 255:
        raise ValueError("#!tmem_dealloc_1cta input address cannot be URZ")
    if columns not in (32, 64, 128, 256, 512):
        raise ValueError(
            "#!tmem_dealloc_1cta columns must be one of "
            "32, 64, 128, 256, or 512")
    units = columns // 32
    range_mask = (1 << units) - 1

    r_base, r_bit, r_mask, r_lane, r_tmp = _take(
        used, "r", 5, 255, "tmem_dealloc_1cta")
    ur_part, ur_bit, ur_vote, ur_reduce, ur_head_reduce = _take(
        used, "ur", 5, 79, "tmem_dealloc_1cta")
    (pred,) = _take(used, "p", 1, 7, "tmem_dealloc_1cta")
    sb_base, sb_mask, sb_reduce = _take(
        used, "sb", 3, 6, "tmem_dealloc_1cta")

    if entry_version == 1:
        form_mask = (f"""
IMAD.MOV.U32 R{r_bit}, RZ, RZ, 0x1ffff;[7:7:{{}}:5:1]
""" if units == 16 else f"""
IMAD.MOV.U32 R{r_bit}, RZ, RZ, {range_mask:#x};[7:7:{{}}:5:1]
SHF.L.U32 R{r_bit}, R{r_bit}, R{r_base}, RZ;[7:7:{{}}:5:1]
IMAD.MOV.U32 R{r_tmp}, RZ, RZ, 0x1;[7:7:{{}}:5:1]
SHF.L.U32 R{r_tmp}, R{r_tmp}, R{r_base}, RZ;[7:7:{{}}:5:1]
SHF.L.U32 R{r_mask}, R{r_tmp}, 0x10, RZ;[7:7:{{}}:5:1]
LOP3.LUT R{r_bit}, R{r_mask}, R{r_bit}, RZ, 0xfc, !PT;[7:7:{{}}:4:1]
""")
        verify_masks = f"""
LDS R{r_base}, [UR{ur_part}];[{sb_mask}:7:{{}}:1:0]
LOP3.LUT R{r_tmp}, R{r_bit}, 0xffff, RZ, 0xc0, !PT;[7:7:{{}}:2:0:1]
LOP3.LUT R{r_mask}, R{r_bit}, 0xffff, R{r_base}, 0x80, !PT;[7:7:{{{sb_mask}}}:4:1]
ISETP.NE.AND P{pred}, PT, R{r_mask}, R{r_tmp}, PT;[7:7:{{}}:13:1]
@P{pred} BPT.TRAP 0x1;[7:7:{{}}:5:0]
SHF.R.U32.HI R{r_base}, RZ, 0x10, R{r_base};[7:7:{{}}:2:0]
SHF.R.U32.HI R{r_tmp}, RZ, 0x10, R{r_bit};[7:7:{{}}:4:1]
LOP3.LUT R{r_mask}, R{r_tmp}, 0xffff, R{r_base}, 0x80, !PT;[7:7:{{}}:4:1]
ISETP.NE.AND P{pred}, PT, R{r_mask}, R{r_tmp}, PT;[7:7:{{}}:13:1]
@P{pred} BPT.TRAP 0x1;[7:7:{{}}:5:0]
"""
        clear_masks = f"""
@P{pred} ATOMS.AND RZ, [UR{ur_part}], R{r_tmp};[7:{sb_base}:{{}}:4:0]
"""
        reduce_head = ""
        final_waits = f"{sb_base},{sb_mask},{sb_reduce}"
        mask_offset = 0x50
    else:
        form_mask = (f"""
IMAD.MOV.U32 R{r_bit}, RZ, RZ, 0xffff;[7:7:{{}}:5:1]
IMAD.MOV.U32 R{r_tmp}, RZ, RZ, 0x1;[7:7:{{}}:5:1]
""" if units == 16 else f"""
IMAD.MOV.U32 R{r_bit}, RZ, RZ, {range_mask:#x};[7:7:{{}}:5:1]
SHF.L.U32 R{r_bit}, R{r_bit}, R{r_base}, RZ;[7:7:{{}}:4:1]
IMAD.MOV.U32 R{r_tmp}, RZ, RZ, 0x1;[7:7:{{}}:5:1]
SHF.L.U32 R{r_tmp}, R{r_tmp}, R{r_base}, RZ;[7:7:{{}}:4:1]
""")
        verify_masks = f"""
LDS R{r_mask}, [UR{ur_part}+0x14];[{sb_mask}:7:{{}}:1:0]
LOP3.LUT R{r_mask}, R{r_mask}, R{r_bit}, RZ, 0xc0, !PT;[7:7:{{{sb_mask}}}:4:1]
ISETP.NE.AND P{pred}, PT, R{r_mask}, R{r_bit}, PT;[7:7:{{}}:13:1]
@P{pred} BPT.TRAP 0x1;[7:7:{{}}:5:0]
LDS R{r_mask}, [UR{ur_part}+0x18];[{sb_mask}:7:{{}}:2:0]
LOP3.LUT R{r_mask}, R{r_mask}, R{r_tmp}, RZ, 0xc0, !PT;[7:7:{{{sb_mask}}}:4:1]
ISETP.NE.AND P{pred}, PT, R{r_mask}, R{r_tmp}, PT;[7:7:{{}}:13:1]
@P{pred} BPT.TRAP 0x1;[7:7:{{}}:5:0]
LOP3.LUT R{r_mask}, RZ, R{r_tmp}, RZ, 0x33, !PT;[7:7:{{}}:4:1]
"""
        clear_masks = f"""
@P{pred} ATOMS.AND RZ, [UR{ur_part}+0x14], R{r_tmp};[7:{sb_base}:{{}}:4:0]
@P{pred} ATOMS.AND RZ, [UR{ur_part}+0x18], R{r_mask};[7:{sb_mask}:{{}}:1:0]
"""
        # ptxas performs a separate warp reduction for the head bitmap even
        # though every participating lane normally computes the same value.
        # This distinction is invisible for a 32-column allocation because
        # its occupied and head masks are identical, but is required for the
        # wider allocation protocol.
        reduce_head = f"""
REDUX UR{ur_head_reduce}, R{r_mask};[{sb_reduce}:7:{{}}:2:0]
IMAD.U32 R{r_mask}, RZ, RZ, UR{ur_head_reduce};[7:7:{{{sb_reduce}}}:4:1]
"""
        final_waits = f"{sb_base},{sb_mask},{sb_reduce}"
        mask_offset = 0x40

    src = f"""
LDS R{r_base}, [UR{addr}];[{sb_base}:7:{{}}:1:0]
S2UR UR{ur_reduce}, SR_CgaCtaId;[{sb_mask}:7:{{}}:1:0]
UMOV UR{ur_part}, {mask_offset:#x};[7:7:{{}}:1:0]
ULEA UR{ur_part}, UR{ur_reduce}, UR{ur_part}, 0x18;[7:7:{{{sb_mask}}}:9:1]
#coop_group
NOP;[7:7:{{}}:1:0]
LOP3.LUT R{r_base}, R{r_base}, 0xffff, RZ, 0xc0, !PT;[7:7:{{{sb_base}}}:4:1]
SHF.R.U32.HI R{r_base}, RZ, 0x5, R{r_base};[7:7:{{}}:4:1]
{form_mask}
{verify_masks}
R2UR UR{ur_bit}, R{r_bit};[7:7:{{}}:1:0]
VOTEU.ANY UR{ur_vote}, UPT, PT;[7:7:{{}}:1:0]
S2R R{r_lane}, SR_LANEID;[{sb_base}:7:{{}}:1:0]
UFLO.U32 UR{ur_vote}, UR{ur_vote};[7:7:{{}}:10:1]
ULOP3.LUT UR{ur_bit}, URZ, UR{ur_bit}, URZ, 0x33, !UPT;[7:7:{{}}:6:1]
IMAD.U32 R{r_tmp}, RZ, RZ, UR{ur_bit};[7:7:{{}}:4:1]
{reduce_head}
REDUX UR{ur_reduce}, R{r_tmp};[{sb_reduce}:7:{{}}:2:0]
UTCATOMSWS.AND URZ, UR{ur_bit};[7:{sb_mask}:{{}}:1:0]
ISETP.EQ.U32.AND P{pred}, PT, R{r_lane}, UR{ur_vote}, PT;[7:7:{{{sb_base}}}:1:0]
IMAD.U32 R{r_tmp}, RZ, RZ, UR{ur_reduce};[7:7:{{{sb_reduce}}}:12:1]
{clear_masks}
#coop_group
WARPSYNC.ALL;[7:7:{{{final_waits}}}:5:0]
"""
    expanded = parse_sass(src)
    for inst in expanded:
        if not inst.line:
            inst.line = node.line
    return expanded


def _expand_tmem_relinquish(node, used, serial: int, entry_version: int):
    r_one, = _take(
        used, "r", 1, 255, "tmem_relinquish_alloc_permit_1cta")
    ur_part, ur_cga = _take(
        used, "ur", 2, 79, "tmem_relinquish_alloc_permit_1cta")
    pred, = _take(
        used, "p", 1, 7, "tmem_relinquish_alloc_permit_1cta")
    sb_addr, sb_phase = _take(
        used, "sb", 2, 6, "tmem_relinquish_alloc_permit_1cta")
    done = f"__bi_tmem_relinquish_{serial}_done"
    phase_addr = (f"[UR{ur_part}]" if entry_version == 1
                  else f"[UR{ur_part}+0x1c]")
    src = f"""
S2UR UR{ur_cga}, SR_CgaCtaId;[{sb_addr}:7:{{}}:1:0]
ELECT P{pred}, URZ, PT;[7:7:{{}}:1:0]
#coop_group
NOP;[7:7:{{}}:1:0]
UMOV UR{ur_part}, 0x40;[7:7:{{{sb_addr}}}:2:0]
ULEA UR{ur_part}, UR{ur_cga}, UR{ur_part}, 0x18;[7:7:{{}}:9:1]
@!P{pred} BRA #label({done});[7:7:{{}}:5:0]
IMAD.MOV.U32 R{r_one}, RZ, RZ, 0x1;[7:7:{{}}:1:0]
UVIRTCOUNT.DEALLOC.SMPOOL 0x80;[7:7:{{}}:4:0]
STS.U8 {phase_addr}, R{r_one};[7:{sb_phase}:{{}}:1:0]
#def_label({done})
#coop_group
WARPSYNC.ALL;[7:7:{{{sb_phase}}}:5:0]
"""
    expanded = parse_sass(src)
    for inst in expanded:
        if not inst.line:
            inst.line = node.line
    return expanded


def _expand_mbarrier_init(node, used, serial: int):
    addr = int(node.operands[0].value)
    count = int(node.operands[1].value)
    if addr == 255:
        raise ValueError("#!mbarrier_init address cannot be URZ")
    if not 0 <= count < (1 << 20):
        raise ValueError("#!mbarrier_init count must fit in 20 bits")

    ur_lo, ur_hi = _take_contiguous(
        used, "ur", 2, 79, "mbarrier_init")
    (pred,) = _take(used, "p", 1, 7, "mbarrier_init")
    sb_value, sb_sync = _take(used, "sb", 2, 6, "mbarrier_init")
    done = f"__bi_mbarrier_init_{serial}_done"
    # mbarrier.init stores two copies of -count in the physical v0 word:
    # low20<<1 and low20<<43.  SYNCS.EXCH consumes the consecutive UR pair.
    src = f"""
ELECT P{pred}, URZ, PT;[7:7:{{}}:13:1]
@!P{pred} BRA #label({done});[7:7:{{}}:5:0]
UMOV UR{ur_lo}, {count:#x};[{sb_value}:7:{{}}:1:0]
UIADD3 UR{ur_lo}, UPT, UPT, -UR{ur_lo}, 0x100000, URZ;[7:7:{{{sb_value}}}:5:1]
USHF.L.U32 UR{ur_hi}, UR{ur_lo}, 0xb, URZ;[7:7:{{}}:5:1]
USHF.L.U32 UR{ur_lo}, UR{ur_lo}, 0x1, URZ;[7:7:{{}}:5:1]
SYNCS.EXCH.64 URZ, [RZ+UR{addr}], UR{ur_lo};[{sb_sync}:{sb_value}:{{{sb_value}}}:5:1]
#def_label({done})
WARPSYNC.ALL;[7:7:{{{sb_sync}}}:5:0]
"""
    expanded = parse_sass(src)
    for inst in expanded:
        if not inst.line:
            inst.line = node.line
    return expanded


def _expand_mbarrier_arrive(node, used, serial: int):
    addr = int(node.operands[0].value)
    if addr == 255:
        raise ValueError("#!mbarrier_arrive address cannot be URZ")
    (sb_sync,) = _take(used, "sb", 1, 6, "mbarrier_arrive")
    src = f"""
SYNCS.ARRIVE.TRANS64.A1T0 {{RZ,RZ}}, [RZ+UR{addr}], RZ;[{sb_sync}:7:{{}}:5:1]
NOP;[7:7:{{{sb_sync}}}:5:0]
"""
    expanded = parse_sass(src)
    for inst in expanded:
        if not inst.line:
            inst.line = node.line
    return expanded


def _expand_mbarrier_wait(node, used, serial: int):
    addr = int(node.operands[0].value)
    phase = int(node.operands[1].value)
    if addr == 255:
        raise ValueError("#!mbarrier_wait address cannot be URZ")
    if phase not in (0, 1):
        raise ValueError("#!mbarrier_wait phase must be 0 or 1")
    r_phase, r_hint = _take(used, "r", 2, 255, "mbarrier_wait")
    (pred,) = _take(used, "p", 1, 7, "mbarrier_wait")
    (sb_sync,) = _take(used, "sb", 1, 6, "mbarrier_wait")
    poll = f"__bi_mbarrier_wait_{serial}_poll"
    encoded_phase = phase << 31
    src = f"""
MOV32I R{r_phase}, {encoded_phase:#x};[7:7:{{}}:5:1]
MOV32I R{r_hint}, 0x100;[7:7:{{}}:5:1]
#def_label({poll})
SYNCS.PHASECHK.TRANS64.TRYWAIT P{pred}, [RZ+UR{addr}], R{r_phase};[{sb_sync}:7:{{}}:2:0]
@!P{pred} NANOSLEEP.SYNCS R{r_hint};[7:7:{{{sb_sync}}}:5:1]
@!P{pred} SYNCS.PHASECHK.TRANS64 P{pred}, [RZ+UR{addr}], R{r_phase};[{sb_sync}:7:{{}}:2:0]
@!P{pred} BRA #label({poll});[7:7:{{{sb_sync}}}:5:0]
"""
    expanded = parse_sass(src)
    for inst in expanded:
        if not inst.line:
            inst.line = node.line
    return expanded


def expand_builtins(kernel):
    """Expand built-in nodes in *kernel* and apply their required ABI attrs."""
    builtin_nodes = [i for i in kernel.instructions
                     if i.mnemonic.startswith(_BUILTIN_PREFIX)]
    if not builtin_nodes:
        return

    explicit_v1 = bool(int(kernel.attributes.get(
        "AT_ENTRY_FRAGMENT_TMEM_CTA1", 0)))
    explicit_v2 = bool(int(kernel.attributes.get(
        "AT_ENTRY_FRAGMENT_TMEM_CTA1_V2", 0)))
    if explicit_v1 and explicit_v2:
        raise ValueError(
            "TMEM builtins cannot select both CTA1 V1 and V2 entry fragments")
    # CubinBuilder's established ABI is V1 when TCGEN05_1CTA_USED is present
    # and the V2 marker is absent.  Thus an unversioned builtin follows V1;
    # adding only the V2 entry-fragment pragma silently selects V2 lowering.
    entry_version = 2 if explicit_v2 else 1

    tmem_nodes = [i for i in builtin_nodes if i.mnemonic.startswith(
        "_builtin_tmem_")]

    # Initial TMEM lifecycle is deliberately strict: one allocation scope, closed
    # before relinquishing its CTA permit.  This catches the exact omission
    # that makes the driver ATEXIT guard trap with CUDA error 721.
    expected = [
        "_builtin_tmem_alloc_1cta_",
        "_builtin_tmem_dealloc_1cta_",
        "_builtin_tmem_relinquish_alloc_permit_1cta_",
    ]
    actual = [i.mnemonic for i in tmem_nodes]
    if tmem_nodes and actual != expected:
        pretty = " -> ".join(name.removeprefix("_builtin_").removesuffix("_")
                             for name in expected)
        raise ValueError(
            "initial TMEM builtin lifecycle must be exactly " + pretty)
    if tmem_nodes:
        alloc, dealloc, _ = tmem_nodes
    if (tmem_nodes and
            (alloc.operands[0].value != dealloc.operands[0].value or
             alloc.operands[1].value != dealloc.operands[1].value)):
        raise ValueError(
            "#!tmem_dealloc_1cta must use the same shared-address UR and "
            "column count as #!tmem_alloc_1cta")
    used = _collect_used(kernel.instructions)
    init_addrs = {int(i.operands[0].value) for i in builtin_nodes
                  if i.mnemonic == "_builtin_mbarrier_init_"}
    if init_addrs:
        inferred = len(init_addrs)
        declared = int(kernel.attributes.get("NUM_MBARRIERS", inferred))
        if declared < inferred:
            raise ValueError(
                f"NUM_MBARRIERS({declared}) is smaller than the "
                f"{inferred} syntactically distinct mbarrier init addresses")
        kernel.attributes["NUM_MBARRIERS"] = declared
    out = []
    serial = 0
    for inst in kernel.instructions:
        # Macro-local temporaries die at the end of each built-in, so distinct
        # built-ins may safely reuse the same globally-unused physical pool.
        macro_used = {kind: set(values) for kind, values in used.items()}
        if inst.mnemonic == "_builtin_tmem_alloc_1cta_":
            kernel.attributes["TCGEN05_1CTA_USED"] = 1
            out.extend(_expand_tmem_alloc_1cta(
                inst, macro_used, serial, entry_version))
            serial += 1
        elif inst.mnemonic == "_builtin_tmem_dealloc_1cta_":
            kernel.attributes["TCGEN05_1CTA_USED"] = 1
            out.extend(_expand_tmem_dealloc_1cta(
                inst, macro_used, serial, entry_version))
            serial += 1
        elif inst.mnemonic == \
                "_builtin_tmem_relinquish_alloc_permit_1cta_":
            kernel.attributes["TCGEN05_1CTA_USED"] = 1
            out.extend(_expand_tmem_relinquish(
                inst, macro_used, serial, entry_version))
            serial += 1
        elif inst.mnemonic == "_builtin_mbarrier_init_":
            out.extend(_expand_mbarrier_init(
                inst, macro_used, serial))
            serial += 1
        elif inst.mnemonic == "_builtin_mbarrier_arrive_":
            out.extend(_expand_mbarrier_arrive(
                inst, macro_used, serial))
            serial += 1
        elif inst.mnemonic == "_builtin_mbarrier_wait_":
            out.extend(_expand_mbarrier_wait(
                inst, macro_used, serial))
            serial += 1
        elif inst.mnemonic.startswith(_BUILTIN_PREFIX):
            raise ValueError(f"unsupported assembler builtin {inst.mnemonic}")
        else:
            out.append(inst)
    kernel.instructions = out
