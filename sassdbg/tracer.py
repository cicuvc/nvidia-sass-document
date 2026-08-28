"""sassdbg tracer — run an instrumented kernel and print the state trace.

Usage:
    python3 -m sassdbg.tracer kernel.sass [--block N] [--no-undo] [--dump-json]
    python3 -m sassdbg.tracer --demo          # built-in demo kernel

The kernel's first parameter must be a pointer to a workspace buffer (>= 4KiB)
the kernel may freely use; the tracer adds the hidden __trace parameter.
Launch is grid=(1,), block=(N,); the trace buffer is per-thread strided.
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from assembler import assemble, CudaModule                     # noqa: E402
from sassdbg.instrument import (                               # noqa: E402
    instrument, REC_SIZE, PER_THREAD_BYTES,
    KIND_STEP, KIND_REG, KIND_PRED, KIND_UREG, KIND_MEM, KIND_MEMOLD,
)

DEMO_KERNEL = """\
#fn k(p<8>) {
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
    LDC.64 {R6,R7}, #param(p);[1:7:{}:1:0]
    S2R R2, SR_TID.X;[0:7:{}:5:1]
    IMAD R3, R2, 5, RZ;[7:7:{}:5:0]
    IADD3 R4, R3, 0x100, RZ;[7:7:{}:5:0]
    SHF.L.U32 R5, R4, 2, RZ;[7:7:{}:5:0]
    ISETP.GT.AND P0, PT, R5, 0x200, PT;[7:7:{}:5:0]
    UIMAD UR8, UR2, UR4, URZ;[7:7:{}:5:0]
    @P0 STG.E desc[{UR4,UR5}][{R6,R7}+0x20], R5;[0:1:{}:1:0]
    @!P0 STG.E desc[{UR4,UR5}][{R6,R7}+0x24], R4;[0:1:{}:1:0]
    MOV32I R8, 0x3fc00000;[7:7:{}:5:0]
    FADD R9, R8, R8;[7:7:{}:5:0]
    IMAD.WIDE.U32 {R10,R11}, R3, 0x7, {R6,R7};[7:7:{}:5:0]
    EXIT;[7:7:{}:5:0]
}
"""


def decode_thread(buf: "bytes | bytearray", sidecar: dict):
    """Walk one thread's trace region in lockstep with the sidecar's expected
    per-step record sequence; return list of steps with their changes."""
    steps = {s["idx"]: s for s in sidecar["steps"]}
    out = []
    cur = None
    expected: list[dict] = []       # records of current step, in sidecar order
    eidx = 0                        # next expected record position
    for off in range(0, len(buf) - REC_SIZE + 1, REC_SIZE):
        hdr, _r, addr, d0, d1, d2, d3 = struct.unpack_from("<IIQ4I", buf, off)
        kind, aux = hdr & 0xFF, hdr >> 8
        if hdr == 0:
            break
        if kind == KIND_STEP:
            if cur:
                out.append(cur)
            s = steps.get(aux)
            cur = {"idx": aux, "text": s["text"] if s else "?", "changes": []}
            # sidecar order: pre_records + STEP + records
            expected = (s["records"] if s else [])
            eidx = 0
            # skip until the STEP entry itself, then continue after it
            while eidx < len(expected) and expected[eidx]["kind"] != KIND_STEP:
                eidx += 1
            eidx += 1
            continue
        if cur is None:
            break
        meta = expected[eidx] if eidx < len(expected) else None
        eidx += 1
        if kind == KIND_REG:
            n = (meta or {}).get("nregs", 1)
            cur["changes"].append(("REG", aux, [d0, d1, d2, d3][:n]))
        elif kind == KIND_PRED:
            cur["changes"].append(("PRED", None, d0))
        elif kind == KIND_UREG:
            n = (meta or {}).get("nregs", 1)
            cur["changes"].append(("UREG", aux, [d0, d1][:n]))
        elif kind in (KIND_MEM, KIND_MEMOLD):
            aoff = (meta or {}).get("addr_off", 0)
            data = {1: d0 & 0xFF, 2: d0 & 0xFFFF, 4: d0,
                    8: d0 | (d1 << 32), 16: (d0, d1, d2, d3)}.get(aux, d0)
            cur["changes"].append(("MEM" if kind == KIND_MEM else "MEMOLD",
                                   (addr + aoff, aux), data))
        else:
            cur["changes"].append(("???", hdr, None))
    if cur:
        out.append(cur)
    return out


def print_trace(tid: int, steps) -> None:
    regs: dict[int, int] = {}
    preds = 0
    print(f"--- thread {tid} ---")
    for st in steps:
        if not st["changes"]:
            continue
        parts = []
        for ch in st["changes"]:
            kind = ch[0]
            if kind == "REG":
                _, r, vals = ch
                for i, v in enumerate(vals):
                    old = regs.get(r + i, 0)
                    if old != v:
                        parts.append(f"R{r + i}: {old:#x} -> {v:#x}")
                    regs[r + i] = v
            elif kind == "PRED":
                v = ch[2] & 0x7F
                diff = v ^ preds
                for p in range(7):
                    if diff >> p & 1:
                        parts.append(f"P{p}: {(preds >> p) & 1} -> {(v >> p) & 1}")
                preds = v
            elif kind == "UREG":
                vals = ch[2] if isinstance(ch[2], list) else [ch[2]]
                for i, v in enumerate(vals):
                    parts.append(f"UR{ch[1] + i} = {v:#x}")
            elif kind == "MEM":
                (addr, sz), data = ch[1], ch[2]
                parts.append(f"ST [{addr:#x}]({sz}B) <- {data:#x}" if not isinstance(data, tuple)
                             else f"ST [{addr:#x}]({sz}B) <- {data}")
            elif kind == "MEMOLD":
                (addr, sz), data = ch[1], ch[2]
                parts.append(f"(old [{addr:#x}]({sz}B) = {data:#x})" if not isinstance(data, tuple)
                             else f"(old [{addr:#x}] = {data})")
        if parts:
            print(f"  [{st['idx']:3}] {st['text'][:64]:<64} | {'; '.join(parts)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sass", nargs="?",
                    help="kernel source (assembler dialect) or a .cubin to "
                         "lift + instrument")
    ap.add_argument("--func", help="kernel to pick out of a multi-kernel cubin")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--block", type=int, default=1)
    ap.add_argument("--no-undo", action="store_true")
    ap.add_argument("--dump-source", action="store_true",
                    help="print instrumented SASS and exit")
    args = ap.parse_args()

    # auto-allocated dummy args for lifted cubin kernels: pointer-sized
    # params get a fresh 64KiB device buffer, scalars get 0, wide params
    # (tensor maps etc.) get zeroed bytes
    auto_args: list = []

    if args.demo:
        source = DEMO_KERNEL
    elif args.sass and args.sass.endswith(".cubin"):
        from sassdbg.lift import lift, dump_cubin, normalize_source
        fns = lift(args.sass, func=args.func)
        if not fns:
            ap.error(f"no kernel {args.func or ''} in {args.sass}")
        name = args.func or next(iter(fns))
        source = normalize_source(fns[name])
        rf = next(f for f in dump_cubin(args.sass) if f.name == name)
        auto_args = ["ptr" if sz == 8 else ("zero" * 1 if sz <= 4 else sz)
                     for _o, _off, sz in rf.params]
    elif args.sass:
        source = Path(args.sass).read_text()
    else:
        ap.error("need a kernel source or --demo")

    ik = instrument(source, undo=not args.no_undo)
    if args.dump_source:
        print(ik.source)
        return 0

    # lifted kernels carry ptxas's original scheduling brackets — they are
    # authoritative, so skip the dependency checker for them
    mod = CudaModule(assemble(ik.source, check_deps=not auto_args))
    n = args.block
    trace = mod.devmem_alloc(n * ik.per_thread_bytes)
    launch_args = []
    allocs = []
    for a in auto_args:
        if a == "ptr":
            p = mod.devmem_alloc(65536)
            allocs.append(p)
            launch_args.append(p)
        elif a == "zero":
            launch_args.append(0)
        else:                       # wide value param (e.g. tensor map)
            launch_args.append(bytes(a))
    if not auto_args:               # dialect source: workspace + trace
        work = mod.devmem_alloc(4096)
        allocs.append(work)
        launch_args.append(work)
    launch_args.append(trace)
    mod.launch(ik.kernel_name, grid=(1,), block=(n,), args=launch_args)
    mod.synchronize()

    sidecar = __import__("json").loads(ik.sidecar())
    for tid in range(n):
        raw = mod.device_read(trace + tid * ik.per_thread_bytes, ik.per_thread_bytes)
        print_trace(tid, decode_thread(raw, sidecar))
    return 0


if __name__ == "__main__":
    sys.exit(main())
