#!/usr/bin/env python3
"""Build raw-SASS UTCCP/STTM write-path interaction probes for B200."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble_kernel  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "tests/asm_construct/tcgen05_alloc_sm100.sass"
ANCHOR = """    LDS R5, [UR5];[2:7:{}:1:0]
    ISETP.NE.AND P0, PT, R0, RZ, PT;[7:7:{0}:13:1]
    @!P0 LDC.64 {R2,R3}, c[0x0][0x380];[2:7:{}:2:0]
    @!P0 STG.E desc[{UR8,UR9}][{R2,R3}], R5;[7:0:{2}:1:0]
    #coop_group
    NOP;[7:7:{}:1:0]"""


def make_source(mode: str, *, batches: int = 32,
                cp_per_batch: int = 16,
                st_per_batch: int = 128,
                st_column: int = 0,
                cp_schedule: str = "serial",
                cp_first_wait: bool = False,
                cp_shape: str = "128x256") -> tuple[str, str]:
    if mode not in ("cp", "st", "mix"):
        raise ValueError(mode)
    if st_column not in (0, 8):
        raise ValueError(st_column)
    if cp_schedule not in ("serial", "none", "round6"):
        raise ValueError(cp_schedule)
    cp_modes = {
        "128x256": "",
        "warpx2_02_13": ".2x64dp128bit_lw02_lw13",
        "warpx2_01_23": ".2x64dp128bit_lw01_lw23",
        "warpx4": ".4x32dp128bit",
    }
    if cp_shape not in cp_modes:
        raise ValueError(cp_shape)
    name = f"raw_{mode}_c{st_column}"
    source = TEMPLATE.read_text()
    source = source.replace("#fn alloc32(out<8>) {", f"#fn {name}(out<8>) {{", 1)
    source = source.replace(
        "    #pragma REGCOUNT(12)",
        "    #pragma REGCOUNT(48)\n"
        "    #pragma NUM_MBARRIERS(1)", 1)
    source = source.replace("    #pragma SHARED(4)",
                            "    #pragma SHARED(0x2000)", 1)

    lines = [
        "    LDS R5, [UR5];[2:7:{}:1:0]",
        "    ISETP.NE.AND P0, PT, R0, RZ, PT;[7:7:{0}:13:1]",
        "    @!P0 LDC.64 {R2,R3}, c[0x0][0x380];[2:7:{}:2:0]",
        "    R2UR UR10, R5;[7:7:{2}:13:1]",
        # No-swizzle descriptor for shared byte address 0x900:
        # base>>4 | LBO(16 B)<<16, SBO(128 B)<<32, base-offset bit 46.
        "    UMOV UR12, 0x10090;[7:7:{}:1:0]",
        "    UMOV UR13, 0x4008;[7:7:{}:1:0]",
        "    UMOV UR16, 0x800;[7:7:{}:1:0]",
        "    UMOV UR14, 0x1;[7:7:{}:1:0]",
        "    UIADD3 UR14, UPT, UPT, -UR14, 0x100000, UR15;[7:7:{}:5:1]",
        "    USHF.L.U32 UR15, UR14, 0xb, UR15;[7:7:{}:5:1]",
        "    USHF.L.U32 UR14, UR14, 0x1, UR14;[7:7:{}:5:1]",
        "    BSSY B0, #label(init_join);[7:7:{}:1:0]",
        "    @P0 BRA #label(init_join);[7:7:{}:5:0]",
        "    SYNCS.EXCH.64 URZ, [UR16], UR14;[1:7:{}:5:1]",
        "    #def_label(init_join)",
        "    BSYNC B0;[7:7:{1}:5:0]",
        "    FENCE.VIEW.ASYNC.S;[7:7:{}:5:1]",
        "    CS2R {R16,R17}, SR_CLOCKLO;[7:7:{}:1:0]",
        f"    UMOV UR20, 0x{batches:x};[7:7:{{}}:1:0]",
        "    #def_label(hot_loop)",
    ]

    if mode in ("cp", "mix"):
        lines += [
            "    BSSY B0, #label(cp_join);[7:7:{}:1:0]",
            "    @P0 BRA #label(cp_join);[7:7:{}:5:0]",
        ]
        lines += [
            "    PLOP3.LUT P0, PT, PT, PT, PT, 0x80, 0x8;"
            "[7:7:{}:13:1]",
            "    #def_label(cp_elect)",
            "    @P0 ELECT P1, URZ, PT;[7:7:{}:1:0]",
        ]
        for i in range(cp_per_batch):
            if cp_schedule == "serial":
                sched = "[7:0:{0}:12:1]"
            elif cp_schedule == "none":
                sched = "[7:7:{}:1:0]"
            else:
                sb = i % 6
                sched = f"[7:{sb}:{{{sb}}}:1:0]"
            lines.append(
                f"    UTCCP.T.S{cp_modes[cp_shape]} "
                "tmem[UR10], gdesc[{UR12,UR13}];"
                + sched)
        lines += [
            "    @P1 PLOP3.LUT P0, PT, P1, PT, PT, 0x8, 0x80;"
            "[7:7:{}:2:0]",
            "    PLOP3.LUT P1, PT, PT, PT, PT, 0x8, 0x80;"
            "[7:7:{}:11:1]",
            "    @P0 BRA.U.ANY #label(cp_elect);[7:7:{}:5:0]",
        ]
        lines += [
            "    #def_label(cp_join)",
            "    BSYNC B0;[7:7:{}:5:0]",
        ]

    if mode in ("st", "mix"):
        addr = "tmem[UR10]" if st_column == 0 else "tmem[UR10+0x8]"
        for _ in range(st_per_batch):
            lines.append(
                f"    STTM.x8 {addr}, {{R24,R25,R26,R27,R28,R29,R30,R31}};"
                "[7:7:{}:1:0]")

    lines += [
        "    UIADD3 UR20, UPT, UPT, UR20, -0x1, URZ;[7:7:{}:5:1]",
        "    UISETP.NE.AND UP0, UPT, UR20, URZ, UPT;[7:7:{}:1:0]",
        "    BRA.U UP0, #label(hot_loop);[7:7:{}:5:0]",
    ]

    cp_wait = []
    if mode in ("cp", "mix"):
        cp_wait = [
            "    BSSY B0, #label(cp_wait_join);[7:7:{}:1:0]",
            "    @P0 BRA #label(cp_wait_join);[7:7:{}:5:0]",
            "    PLOP3.LUT P0, PT, PT, PT, PT, 0x80, 0x8;"
            "[7:7:{}:4:1]",
            "    #def_label(commit_elect)",
            "    @P0 ELECT P2, URZ, PT;[7:7:{}:13:1]",
            "    UTCBAR.1CTA [UR16], URZ;[7:0:{}:1:0]",
            "    @P2 PLOP3.LUT P0, PT, P2, PT, PT, 0x8, 0x80;"
            "[7:7:{}:2:0]",
            "    PLOP3.LUT P2, PT, PT, PT, PT, 0x8, 0x80;"
            "[7:7:{}:1:0]",
            "    @P0 BRA.U.ANY #label(commit_elect);[7:7:{}:12:1]",
            "    MOV32I R20, 0x0;[7:7:{}:5:1]",
            "    #def_label(cp_wait)",
            "    SYNCS.PHASECHK.TRANS64.TRYWAIT P1, [RZ+UR16], R20;"
            "[1:7:{}:2:0]",
            "    @!P1 BRA #label(cp_wait);[7:7:{1}:5:0]",
            "    #def_label(cp_wait_join)",
            "    BSYNC B0;[7:7:{}:5:0]",
        ]
    st_wait = (["    FENCE.VIEW.ASYNC.T;[7:7:{}:2:0]"]
               if mode in ("st", "mix") else [])
    if mode == "mix" and cp_first_wait:
        lines += cp_wait + st_wait
    else:
        lines += st_wait + cp_wait
    lines += [
        "    CS2R {R18,R19}, SR_CLOCKLO;[7:7:{}:1:0]",
        "    @!P0 STG.E.128 desc[{UR8,UR9}][{R2,R3}], "
        "{R16,R17,R18,R19};[7:0:{2}:1:0]",
    ]

    if ANCHOR not in source:
        raise ValueError("allocator payload anchor not found")
    return name, source.replace(ANCHOR, "\n".join(lines), 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("cp", "st", "mix"))
    ap.add_argument("--st-column", type=int, choices=(0, 8), default=0)
    ap.add_argument("--batches", type=int, default=32)
    ap.add_argument("--cp-per-batch", type=int, default=16)
    ap.add_argument("--st-per-batch", type=int, default=128)
    ap.add_argument("--cp-schedule", choices=("serial", "none", "round6"),
                    default="serial")
    ap.add_argument(
        "--cp-first-wait", action="store_true",
        help="in mixed mode, commit/wait UTCCP before the STTM fence")
    ap.add_argument(
        "--cp-shape",
        choices=("128x256", "warpx2_02_13", "warpx2_01_23", "warpx4"),
        default="128x256",
        help="UTCCP shape/multicast mode (SASS spelling is selected here)")
    ap.add_argument("--output", type=Path)
    ns = ap.parse_args()
    name, source = make_source(
        ns.mode, batches=ns.batches, cp_per_batch=ns.cp_per_batch,
        st_per_batch=ns.st_per_batch, st_column=ns.st_column,
        cp_schedule=ns.cp_schedule, cp_first_wait=ns.cp_first_wait,
        cp_shape=ns.cp_shape)
    output = ns.output or Path(f"/tmp/{name}.cubin")
    result = assemble_kernel(source, arch="sm100a", check_deps=False)
    output.write_bytes(result.code)
    print(f"{name} -> {output} ({len(result.code)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
