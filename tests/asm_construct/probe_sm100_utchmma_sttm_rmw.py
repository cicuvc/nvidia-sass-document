#!/usr/bin/env python3
"""Build clean B200 UTCHMMA-RMW versus LDTM/STTM contention probes.

Warp 0 issues a configurable M128N128K16 BF16->F32 UTCHMMA stream.  The default
four-op form fills collector A, reuses it, and finally consumes it, so the timed
window removes repeated A reads while every MMA still performs a full D RMW.

UTCHMMA and UTCBAR are issued directly.  Their U-prefix already gives them
warp-scalar issue semantics; ptxas's ELECT/PLOP scaffolding implements the PTX
active-thread-group contract and is not a hardware issue requirement.  Options
expose plain/reuse, stream length, looping, and a pre-commit gap.

The whole issuing warp executes each U instruction.  Do not split out lane 0:
besides being redundant for warp-scalar issue, that leaves divergent execution
groups which must be reconverged before BAR.SYNC.  Every CTA barrier below is
therefore preceded by WARPSYNC.ALL as an explicit safety invariant.

Warps 1 and 5 reside on the same scheduler/subcore and issue a statically
unrolled STTM.x8 stream to columns disjoint from D.  Two warps are required to
saturate the ordinary STTM ingress.  Keeping them off warp 0's scheduler avoids
mistaking scalar issue contention for a TMEM-array write-port conflict.

For the read-side version, warp 1 rotates three LDTM.x16 destination groups and
three completion scoreboards.  This is the previously calibrated schedule that
reaches exactly 256 B/cycle/chunk with one warp.

The duplex mode runs STTM on warps 1/5 and LDTM on a selectable warp.  Warp 9
puts all three ordinary streams on the same subcore/chunk; warp 2 is the
cross-chunk control.  Separate column offsets avoid an address-level read/write
hazard while retaining the same chunk datapath.

Optionally warp 3 issues a naked UBLKCP stream.  G.S copies shared->global and
closes it with UTMACMDFLUSH/DEPBAR; S.G copies global->shared and closes it with
an independent transaction-counted mbarrier.  This lets the same generator
factor TMA/shared-array contention from ordinary and tensor TMEM traffic.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import assemble_kernel  # noqa: E402


def _one_mma(index: int, modifier: str, dreg: int,
             accumulate: bool = True) -> list[str]:
    del index  # retained so callers can keep simple indexed generation
    enable_d = "UPT" if accumulate else "!UPT"
    return [f"    UTCHMMA.1CTA{modifier} "
        "gdesc[{UR20,UR21}], gdesc[{UR22,UR23}], "
        f"tmem[UR{dreg}], tmem[UR14], idesc[{{UR15,UR16}}], URZ, {enable_d};"
        "[7:0:{}:12:1]"]


def _commit_ops(index: int = 0) -> list[str]:
    del index
    return ["    UTCBAR.1CTA [UR18], URZ;[7:0:{}:12:1]"]


def _mma_ops(mma_n: int, d_tiles: int, count: int = 4,
             precommit_nops: int = 0, accumulate: bool = True,
             commit_every: int = 0,
             readback_after_commit: bool = False,
             d_pattern: list[int] | None = None) -> list[str]:
    # PTX collector::a::{fill,use...,lastuse}.  Like ptxas, submit the whole
    # stream first and commit all preceding operations with one UTCBAR.
    if count < 2:
        raise ValueError("MMA stream must contain at least fill+lastuse")
    modifiers = ([".A_KEEP"] + [".A_REUSE.A_KEEP"] * (count - 2)
                 + [".A_REUSE"])
    pattern = d_pattern or list(range(d_tiles))
    dregs = ([10] * count if d_tiles == 1 else
             [30 + pattern[i % len(pattern)] for i in range(count)])
    lines: list[str] = ["    UMOV UR18, 0x600;[7:7:{}:1:0]"]
    for i, modifier in enumerate(modifiers):
        lines += _one_mma(i, modifier, dregs[i], accumulate)
        close = (i + 1 == count or
                 (commit_every and (i + 1) % commit_every == 0))
        if close:
            lines += ["    NOP;[7:7:{}:8:1]"] * precommit_nops
            lines += _commit_ops()
    lines += ["    #!mbarrier_wait(UR18, 0)",
              "    WARPSYNC.ALL;[7:7:{}:5:0]"]
    if readback_after_commit:
        regs = ",".join(f"R{r}" for r in range(80, 96))
        for tile in range(d_tiles):
            dreg = 10 if d_tiles == 1 else 30 + tile
            for offset in range(0, mma_n, 16):
                lines += [
                    f"    LDTM.x16 {{{regs}}}, "
                    f"tmem[UR{dreg}+{offset:#x}];[2:7:{{2}}:1:0]"
                ]
        lines += ["    NOP;[7:7:{2}:1:0]"]
    return lines


def _plain_mma_ops(count: int, d_tiles: int, mma_n: int,
                   precommit_nops: int = 0,
                   accumulate: bool = True, commit_every: int = 0,
                   readback_after_commit: bool = False,
                   d_pattern: list[int] | None = None) -> list[str]:
    pattern = d_pattern or list(range(d_tiles))
    dregs = ([10] * count if d_tiles == 1 else
             [30 + pattern[i % len(pattern)] for i in range(count)])
    lines: list[str] = ["    UMOV UR18, 0x600;[7:7:{}:1:0]"]
    for i, dreg in enumerate(dregs):
        lines += _one_mma(i, "", dreg, accumulate)
        close = (i + 1 == count or
                 (commit_every and (i + 1) % commit_every == 0))
        if close:
            lines += ["    NOP;[7:7:{}:8:1]"] * precommit_nops
            lines += _commit_ops()
    lines += ["    #!mbarrier_wait(UR18, 0)",
              "    WARPSYNC.ALL;[7:7:{}:5:0]"]
    if readback_after_commit:
        regs = ",".join(f"R{r}" for r in range(80, 96))
        for tile in range(d_tiles):
            dreg = 10 if d_tiles == 1 else 30 + tile
            for offset in range(0, mma_n, 16):
                lines += [
                    f"    LDTM.x16 {{{regs}}}, "
                    f"tmem[UR{dreg}+{offset:#x}];[2:7:{{2}}:1:0]"
                ]
        lines += ["    NOP;[7:7:{2}:1:0]"]
    return lines


def _looped_plain_mma_ops(count: int, unroll: int = 6,
                          precommit_nops: int = 0,
                          accumulate: bool = True) -> list[str]:
    """ptxas-style long stream: an unrolled burst plus a counted loop."""
    loops, tail = divmod(count, unroll)
    lines: list[str] = ["    UMOV UR18, 0x600;[7:7:{}:1:0]"]
    next_index = 0
    if loops:
        lines += [f"    MOV32I R20, {loops};[7:7:{{}}:5:1]",
                  "    #def_label(mma_outer_loop)"]
        for _ in range(unroll):
            lines += _one_mma(next_index, "", 10, accumulate)
            next_index += 1
        lines += [
            "    IADD3 R20, R20, -0x1, RZ;[7:7:{}:5:1]",
            "    ISETP.NE.AND P2, PT, R20, RZ, PT;[7:7:{}:13:1]",
            "    @P2 BRA #label(mma_outer_loop);[7:7:{}:5:0]",
        ]
    for _ in range(tail):
        lines += _one_mma(next_index, "", 10, accumulate)
        next_index += 1
    lines += ["    NOP;[7:7:{}:8:1]"] * precommit_nops
    lines += _commit_ops()
    lines += ["    #!mbarrier_wait(UR18, 0)"]
    return lines


def _sttm_ops(count: int) -> list[str]:
    regs = ",".join(f"R{i}" for i in range(24, 32))
    return [
        f"    STTM.x8 tmem[UR10+0x100], {{{regs}}};[7:7:{{}}:1:0]"
        for _ in range(count)
    ]


def _ldtm_ops(count: int, column_offset: int = 0x100) -> list[str]:
    if count % 3:
        raise ValueError("LDTM count must be divisible by three")
    lines: list[str] = []
    for i in range(count):
        sb = i % 3
        base = 32 + sb * 16
        regs = ",".join(f"R{r}" for r in range(base, base + 16))
        lines += [
            f"    LDTM.x16 {{{regs}}}, tmem[UR10+{column_offset:#x}];"
            f"[{sb}:7:{{{sb}}}:1:0]"
        ]
    return lines


def source(name: str, with_mma: bool, contender: str | None,
           contender_count: int, mma_n: int, distinct_d: bool,
           mma_count: int = 4, collector_reuse: bool = True,
           precommit_nops: int = 0, loop_unroll: int = 0,
           maxreg_count: int = 112, ldtm_count: int | None = None,
           sttm_count: int | None = None,
           accumulate: bool = True, duplex_ldtm_warp: int = 9,
           ublk_direction: str | None = None, ublk_size: int = 4096,
           ublk_copies: int = 32, d_tiles: int = 1,
           commit_every: int = 0,
           readback_after_commit: bool = False,
           d_pattern: list[int] | None = None) -> str:
    if ublk_direction not in (None, "gs", "sg"):
        raise ValueError("UBLKCP direction must be gs, sg, or None")
    if ublk_size % 16 or not 16 <= ublk_size <= 16384:
        raise ValueError("UBLKCP size must be 16..16384 and 16-byte aligned")
    if distinct_d:
        d_tiles = max(d_tiles, 2)
    if d_pattern:
        d_tiles = max(d_pattern) + 1
        if min(d_pattern) < 0:
            raise ValueError("D pattern entries must be non-negative")
    d_tile_stride = max(128, mma_n)
    if d_tiles < 1 or d_tiles * d_tile_stride > 512:
        raise ValueError("D tiles must fit in the 512 allocated TMEM columns")
    if commit_every < 0:
        raise ValueError("commit_every must be non-negative")
    with_sttm = contender in ("sttm", "duplex")
    with_ldtm = contender in ("ldtm", "duplex")
    ldtm_count = contender_count if ldtm_count is None else ldtm_count
    sttm_count = contender_count if sttm_count is None else sttm_count
    mma_commits = (1 if not with_mma or not commit_every else
                   (mma_count + commit_every - 1) // commit_every)
    total_mbarriers = 1 + (1 if ublk_direction == "sg" else 0)
    lines = [
        f"#fn {name}(out<8>) {{",
        f"    #pragma MAXREG_COUNT({maxreg_count})",
        "    #pragma SHARED(0x7000)",
        f"    #pragma NUM_MBARRIERS({total_mbarriers})",
        "    #pragma AT_ENTRY_FRAGMENT_TMEM_CTA1(1)",
        "    LDC.64 {R2,R3}, #param(out);[0:7:{}:1:0]",
        "    S2R R4, SR_TID.X;[1:7:{}:2:0]",
        "    SHR R5, R4, 0x5;[7:7:{1}:5:1]",
        "    LOP3.LUT R6, R4, 0x1f, RZ, 0xc0, !PT;[7:7:{}:5:1]",
        "    IMAD.WIDE.U32 {R8,R9}, R5, 0x10, {R2,R3};[7:7:{0}:5:1]",
        "    S2UR UR5, SR_CgaCtaId;[2:7:{}:1:0]",
        "    UMOV UR4, 0x400;[7:7:{}:1:0]",
        "    ULEA UR5, UR5, UR4, 0x18;[7:7:{2}:9:1]",
        "    ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(setup_wait);[7:7:{}:5:0]",
        "    #!tmem_alloc_1cta(UR5, 512)",
    ]
    lines += [
        "    UMOV UR18, 0x600;[7:7:{}:1:0]",
        f"    #!mbarrier_init(UR18, {mma_commits})",
    ]
    if ublk_direction == "sg":
        lines += [
            "    UMOV UR18, 0x700;[7:7:{}:1:0]",
            "    #!mbarrier_init(UR18, 1)",
        ]
    lines += [
        "    #def_label(setup_wait)",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    LDS R10, [UR5];[0:7:{}:1:0]",
        "    R2UR UR10, R10;[7:7:{0}:13:1]",
        # BF16 K-major, no-swizzle A/B descriptors.  A and B occupy disjoint
        # 4-KiB shared regions.
        "    UMOV UR20, 0x100080;[7:7:{}:1:0]",
        "    UMOV UR21, 0x4008;[7:7:{}:1:0]",
        "    UMOV UR22, 0x100180;[7:7:{}:1:0]",
        "    UMOV UR23, 0x4008;[7:7:{}:1:0]",
        "    UMOV UR14, 0x0;[7:7:{}:1:0]",
        # M128 N{64,128}, BF16/BF16 -> FP32.
        f"    UMOV UR15, {((8 << 24) | ((mma_n >> 3) << 17) | 0x490):#x};"
        "[7:7:{}:1:0]",
        "    UMOV UR16, 0x0;[7:7:{}:1:0]",
    ]
    if ublk_direction is not None:
        lines += [
            # Use out+0x1000 as a private global payload region.
            "    IADD3 R12, P5, R2, 0x1000, RZ;[7:7:{0}:5:1]",
            "    IADD3.X R13, R3, RZ, RZ, P5, !PT;[7:7:{}:5:1]",
            "    R2UR UR40, R12;[0:7:{}:1:0]",
            "    R2UR UR41, R13;[0:7:{}:1:0]",
            "    UMOV UR42, 0x3000;[7:7:{}:1:0]",
            "    UMOV UR43, 0x700;[7:7:{}:1:0]",
            f"    UMOV UR44, {ublk_size // 16:#x};[7:7:{{}}:1:0]",
            f"    MOV32I R0, {ublk_size * ublk_copies:#x};[7:7:{{}}:5:1]",
        ]
    if d_tiles > 1:
        for i in range(d_tiles):
            offset = i * d_tile_stride
            lines += [
                f"    UIADD3 UR{30 + i}, UPT, UPT, UR10, {offset:#x}, URZ;"
                "[7:7:{}:5:1]"
            ]
    for reg in range(24, 32):
        lines += [f"    MOV32I R{reg}, {0x3f800000 + reg:#x};"
                  "[7:7:{}:5:1]"]
    lines += [
        "    FENCE.VIEW.ASYNC.S;[7:7:{}:5:1]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
    ]
    if with_mma:
        lines += [
            "    ISETP.EQ.AND P1, PT, R5, RZ, PT;[7:7:{}:13:1]",
            "    @P1 BRA #label(mma_path);[7:7:{}:5:0]",
        ]
    if contender is not None:
        if with_sttm:
            lines += [
                "    ISETP.EQ.AND P2, PT, R5, 0x1, PT;[7:7:{}:13:1]",
                "    ISETP.EQ.OR P2, PT, R5, 0x5, P2;[7:7:{}:13:1]",
                "    @P2 BRA #label(sttm_path);[7:7:{}:5:0]",
            ]
        if with_ldtm:
            ldtm_warp = duplex_ldtm_warp if contender == "duplex" else 0x1
            lines += [
                f"    ISETP.EQ.AND P4, PT, R5, {ldtm_warp:#x}, PT;"
                "[7:7:{}:13:1]",
                "    @P4 BRA #label(ldtm_path);[7:7:{}:5:0]",
            ]
    if ublk_direction is not None:
        lines += [
            "    ISETP.EQ.AND P5, PT, R5, 0x3, PT;[7:7:{}:13:1]",
            "    @P5 BRA #label(ublk_path);[7:7:{}:5:0]",
        ]
    lines += ["    BRA #label(work_done);[7:7:{}:5:0]"]

    if with_mma:
        lines += [
            "    #def_label(mma_path)",
            "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:0]",
        ] + (_looped_plain_mma_ops(mma_count, loop_unroll, precommit_nops,
                                   accumulate)
             if loop_unroll else
             _mma_ops(mma_n, d_tiles, mma_count, precommit_nops,
                      accumulate, commit_every, readback_after_commit,
                      d_pattern)
             if collector_reuse else
             _plain_mma_ops(mma_count, d_tiles, mma_n, precommit_nops,
                            accumulate, commit_every,
                            readback_after_commit, d_pattern)) + [
            "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    ISETP.EQ.AND P0, PT, R6, RZ, PT;[7:7:{}:13:1]",
            "    @P0 STG.E.64.STRONG.GPU [{R8,R9}], {R16,R17};[7:0:{}:8:0]",
            "    @P0 STG.E.64.STRONG.GPU [{R8,R9}+8], {R18,R19};[7:1:{0}:8:0]",
            "    BRA #label(work_done);[7:7:{1}:5:0]",
        ]

    if with_sttm:
        lines += [
            "    #def_label(sttm_path)",
            "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:0]",
        ] + _sttm_ops(sttm_count) + [
            "    FENCE.VIEW.ASYNC.T;[7:7:{}:2:0]",
            "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    ISETP.EQ.AND P0, PT, R6, RZ, PT;[7:7:{}:13:1]",
            "    @P0 STG.E.64.STRONG.GPU [{R8,R9}], {R16,R17};[7:0:{}:8:0]",
            "    @P0 STG.E.64.STRONG.GPU [{R8,R9}+8], {R18,R19};[7:1:{0}:8:0]",
            "    BRA #label(work_done);[7:7:{1}:5:0]",
        ]

    if with_ldtm:
        ldtm_offset = 0x120 if contender == "duplex" else 0x100
        lines += [
            "    #def_label(ldtm_path)",
            "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:0]",
        ] + _ldtm_ops(ldtm_count, ldtm_offset) + [
            "    NOP;[7:7:{0,1,2}:1:0]",
            "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    ISETP.EQ.AND P0, PT, R6, RZ, PT;[7:7:{}:13:1]",
            "    @P0 STG.E.64.STRONG.GPU [{R8,R9}], {R16,R17};[7:0:{}:8:0]",
            "    @P0 STG.E.64.STRONG.GPU [{R8,R9}+8], {R18,R19};[7:1:{0}:8:0]",
            "    BRA #label(work_done);[7:7:{1}:5:0]",
        ]

    if ublk_direction is not None:
        lines += [
            "    #def_label(ublk_path)",
            "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:5:0]",
        ]
        if ublk_direction == "gs":
            lines += [
                "    UBLKCP.G.S {UR40,UR41}, [UR42], UR44;[7:2:{0}:1:0]"
                for _ in range(ublk_copies)
            ] + [
                "    UTMACMDFLUSH;[7:2:{2}:1:0]",
                "    DEPBAR.LE SB2, 0x0;[7:7:{}:5:1]",
            ]
        else:
            lines += [
                "    UBLKCP.S.G {UR42,UR43}, {UR40,UR41}, UR44;[7:2:{0}:1:0]"
                for _ in range(ublk_copies)
            ] + [
                "    ISETP.EQ.AND P6, PT, R6, RZ, PT;[7:7:{}:13:1]",
                "    @P6 SYNCS.ARRIVE.TRANS64.RED {RZ,RZ}, [RZ+UR43], R0;"
                "[7:2:{2}:1:0]",
                "    #def_label(ublk_poll)",
                "    SYNCS.PHASECHK.TRANS64.TRYWAIT P2, [RZ+UR43], RZ;"
                "[1:7:{}:2:0]",
                "    @!P2 BRA #label(ublk_poll);[7:7:{1}:5:0]",
            ]
        lines += [
            "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:5:0]",
            "    ISETP.EQ.AND P0, PT, R6, RZ, PT;[7:7:{}:13:1]",
            "    @P0 STG.E.64.STRONG.GPU [{R8,R9}], {R16,R17};[7:0:{}:8:0]",
            "    @P0 STG.E.64.STRONG.GPU [{R8,R9}+8], {R18,R19};[7:1:{0}:8:0]",
            "    BRA #label(work_done);[7:7:{1}:5:0]",
        ]

    lines += [
        "    #def_label(work_done)",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    ISETP.NE.AND P0, PT, R5, RZ, PT;[7:7:{}:13:1]",
        "    @P0 BRA #label(dealloc_done);[7:7:{}:5:0]",
        "    #!tmem_dealloc_1cta(UR5, 512)",
        "    #!tmem_relinquish_alloc_permit_1cta()",
        "    #def_label(dealloc_done)",
        "    WARPSYNC.ALL;[7:7:{}:5:0]",
        "    BAR.SYNC 0;[7:7:{}:5:1]",
        "    EXIT;[7:7:{}:5:0]",
        "}",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("sttm", "ldtm", "duplex", "ublk", "mma", "combined"),
                    required=True)
    ap.add_argument("--contender", choices=("sttm", "ldtm", "duplex"), default="sttm",
                    help="contender used by --mode combined")
    ap.add_argument("--count", type=int, default=128)
    ap.add_argument("--mma-n", type=int, choices=(64, 128), default=128)
    ap.add_argument("--mma-count", type=int, default=4)
    ap.add_argument("--no-collector-reuse", action="store_true")
    ap.add_argument("--overwrite", action="store_true",
                    help="disable input D, removing accumulator reads")
    ap.add_argument("--precommit-nops", type=int, default=0)
    ap.add_argument("--loop-unroll", type=int, default=0)
    ap.add_argument("--maxreg-count", type=int, default=112)
    ap.add_argument("--distinct-d", action="store_true",
                    help="alternate two aligned D tiles at columns 0 and 128")
    ap.add_argument("--d-tiles", type=int, default=1,
                    help="round-robin D tiles, spaced by --mma-n columns")
    ap.add_argument("--d-pattern",
                    help="comma-separated D tile indices, repeated as needed")
    ap.add_argument("--commit-every", type=int, default=0,
                    help="UTCBAR+wait every N MMAs (0: one final commit)")
    ap.add_argument("--readback-after-commit", action="store_true",
                    help="LDTM.x16 a rotating D slice after every commit")
    ap.add_argument("--sttm-count", type=int, dest="legacy_sttm_count",
                    help="STTM count per warp (also legacy alias for --count)")
    ap.add_argument("--ldtm-count", type=int,
                    help="LDTM count for duplex mode (default: --count)")
    ap.add_argument("--duplex-ldtm-warp", type=int, default=9,
                    help="warp id for duplex LDTM (9=same chunk as warps 1/5)")
    ap.add_argument("--ublk-direction", choices=("gs", "sg"))
    ap.add_argument("--ublk-size", type=int, default=4096)
    ap.add_argument("--ublk-copies", type=int, default=32)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--source-output", type=Path)
    ns = ap.parse_args()
    d_pattern = ([int(x, 0) for x in ns.d_pattern.split(",")]
                 if ns.d_pattern else None)
    if ns.mode == "ublk" and ns.ublk_direction is None:
        ap.error("--mode ublk requires --ublk-direction")
    if ns.loop_unroll and (ns.d_tiles != 1 or ns.commit_every or
                           ns.readback_after_commit):
        ap.error("loop-unroll is incompatible with D residency options")
    count = ns.legacy_sttm_count or ns.count
    contender = (ns.mode if ns.mode in ("sttm", "ldtm", "duplex") else
                 ns.contender if ns.mode == "combined" else None)
    name = ({"sttm": "sttm2_control", "ldtm": "ldtm1_control",
             "duplex": "duplex3_control",
             "ublk": f"ublk_{ns.ublk_direction}_control",
             "mma": "utchmma_rmw_only"}[ns.mode]
            if ns.mode != "combined" else
             f"utchmma_rmw_{ns.contender}"
             f"{ {'sttm': 2, 'ldtm': 1, 'duplex': 3}[ns.contender] }"
            f"_n{ns.mma_n}{f'_d{ns.d_tiles}' if ns.d_tiles > 1 else ''}"
            f"{f'_c{ns.commit_every}' if ns.commit_every else ''}"
            f"{'_rb' if ns.readback_after_commit else ''}")
    src = source(name, ns.mode in ("mma", "combined"), contender, count,
                 ns.mma_n, ns.distinct_d, ns.mma_count,
                 not ns.no_collector_reuse, ns.precommit_nops,
                 ns.loop_unroll, ns.maxreg_count, ns.ldtm_count,
                 ns.legacy_sttm_count, not ns.overwrite,
                 ns.duplex_ldtm_warp, ns.ublk_direction,
                 ns.ublk_size, ns.ublk_copies, ns.d_tiles,
                 ns.commit_every, ns.readback_after_commit, d_pattern)
    result = assemble_kernel(src, arch="sm100a", check_deps=False)
    ns.output.write_bytes(result.code)
    if ns.source_output:
        ns.source_output.write_text(src)
    print(f"wrote {ns.output} ({len(result.code)} bytes), "
          f"function _Z{len(name)}{name}")


if __name__ == "__main__":
    main()
