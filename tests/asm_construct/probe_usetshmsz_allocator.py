"""Probe shared-memory allocation quanta and fragmentation on sm_120.

The kernel parks resident CTAs and reports SR_VIRTUALSMID by CTAID. This measures
actual residency without relying on a finite spin interval.  Static shared
sizes can then be binary-searched at every occupancy transition; runtime
USETSHMSZ sizes use a fixed static declaration plus FLUSH.
"""

import argparse
import struct
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble
from assembler.runner import reset_context


GRID = 5000
CTRL_BYTES = 0x100 + 4 * GRID
EXPECTED_SMS = 170


def kernel_source(static_size: int, runtime_size: int | None = None) -> str:
    resize = ""
    if runtime_size is not None:
        resize = (f"    USETSHMSZ 0x{runtime_size:X};[7:7:{{}}:1:0]\n"
                  "    USETSHMSZ.FLUSH;[7:7:{}:1:0]\n")
    return f"""#fn k(ctrl<8>) {{
    #pragma SHARED(0x{static_size:X})
    LDC.64 {{R6,R7}}, #param(ctrl);[1:7:{{}}:1:0]
{resize}    S2R R0, SR_CTAID.X;[2:7:{{1}}:5:1]
    S2R R1, SR_VIRTUALSMID;[3:7:{{}}:5:1]
    IMAD.WIDE.U32 {{R8,R9}}, R0, 0x4, {{R6,R7}};[7:7:{{1,2}}:5:1]
    IADD3 R1, R1, 0x1, RZ;[7:7:{{3}}:5:1]
    STG.E.STRONG.GPU [{{R8,R9}}+0x100], R1;[7:7:{{}}:8:0]
#def_label(spin)
    LDG.E.STRONG.GPU R3, [{{R6,R7}}];[4:7:{{1}}:8:0]
    ISETP.EQ.AND P0, PT, R3, RZ, PT;[7:7:{{4}}:13:1]
    NANOSLEEP 0x100;[7:7:{{}}:5:1]
    @P0 BRA #label(spin);[7:7:{{}}:5:1]
    EXIT;[7:7:{{}}:5:0]
}}"""


def resident_hist(static_size: int, runtime_size: int | None = None,
                  *, block: int = 32) -> Counter:
    mod = CudaModule(assemble(kernel_source(static_size, runtime_size)))
    ctrl = mod.devmem_alloc(CTRL_BYTES)
    mod.device_write(ctrl, bytes(CTRL_BYTES))
    stream = CudaModule.stream_create()
    mod.launch("k", grid=(GRID,), block=(block,), args=[ctrl], stream=stream)

    started = time.time()
    min_settle = 1.0 if runtime_size is not None else 0.10
    last = None
    stable = 0
    deadline = time.time() + 3
    words = ()
    while time.time() < deadline:
        raw = mod.device_read(ctrl + 0x100, 4 * GRID)
        words = struct.unpack(f"<{GRID}I", raw)
        now = sum(v != 0 for v in words)
        stable = stable + 1 if now == last and now else 0
        last = now
        # The first static wave reports before USETSHMSZ.FLUSH backfill has
        # necessarily reached its final occupancy.  Never mistake that early
        # plateau for the allocator's steady state.
        if stable >= 5 and time.time() - started >= min_settle:
            break
        time.sleep(0.005)
    if not last:
        raise RuntimeError("no resident CTA reported before timeout")

    mod.device_write(ctrl, struct.pack("<I", 1))
    CudaModule.stream_sync(stream)
    CudaModule.stream_destroy(stream)
    result = Counter(v - 1 for v in words if v)
    mod.devmem_free(ctrl)
    vals = list(result.values())
    if len(result) != EXPECTED_SMS or min(vals) != max(vals):
        raise RuntimeError(
            f"non-uniform residency ({len(result)} SMs,"
            f" {min(vals)}..{max(vals)} CTA/SM); GPU may be busy")
    return result


def summary(hist: Counter) -> tuple[int, int, int, int]:
    vals = list(hist.values())
    return len(vals), min(vals), max(vals), sum(vals)


class ParkKernel:
    """Loaded/warmed parking kernel used for concurrent-kernel probes."""

    def __init__(self, static_size: int, runtime_size: int | None = None,
                 *, block: int = 32):
        self.mod = CudaModule(assemble(kernel_source(static_size, runtime_size)))
        self.ctrl = self.mod.devmem_alloc(CTRL_BYTES)
        self.stream = CudaModule.stream_create()
        self.block = block
        # Module/function lazy paths must be warm before another kernel parks.
        self.mod.device_write(self.ctrl, bytes(CTRL_BYTES))
        self.mod.device_write(self.ctrl, struct.pack("<I", 1))
        self.mod.launch("k", grid=(1,), block=(block,), args=[self.ctrl],
                        stream=self.stream)
        CudaModule.stream_sync(self.stream)
        self.clear()

    def clear(self) -> None:
        self.mod.device_write(self.ctrl, bytes(CTRL_BYTES))

    def launch(self, grid: int) -> None:
        self.mod.launch("k", grid=(grid,), block=(self.block,), args=[self.ctrl],
                        stream=self.stream)

    def snapshot(self, timeout: float = 1.25) -> Counter:
        started = time.time()
        deadline = time.time() + timeout
        last_words = ()
        last_n = -1
        stable = 0
        while time.time() < deadline:
            raw = self.mod.device_read(self.ctrl + 0x100, 4 * GRID)
            words = struct.unpack(f"<{GRID}I", raw)
            n = sum(v != 0 for v in words)
            stable = stable + 1 if n == last_n else 0
            last_n, last_words = n, words
            if stable >= 5 and time.time() - started >= 1.0:
                break
            time.sleep(0.005)
        return Counter(v - 1 for v in last_words if v)

    def release(self) -> None:
        self.mod.device_write(self.ctrl, struct.pack("<I", 1))

    def sync(self) -> None:
        CudaModule.stream_sync(self.stream)


def external_case(a_static: int, a_runtime: int | None, a_grid: int,
                  b_static: int, b_grid: int = 170) -> tuple[Counter, Counter]:
    """Park A first, then snapshot how many B CTAs fit in A's free space."""
    reset_context()
    a = ParkKernel(a_static, a_runtime)
    b = ParkKernel(b_static)
    a.launch(a_grid)
    ah = a.snapshot()
    b.launch(b_grid)
    bh = b.snapshot()
    # Snapshot is complete; release both even when B could not enter at all.
    b.release()
    a.release()
    b.sync()
    a.sync()
    CudaModule.stream_destroy(b.stream)
    CudaModule.stream_destroy(a.stream)
    reset_context()
    return ah, bh


def static_transition(target_ctas: int, *, block: int = 32,
                      hi: int = 0x19000) -> int:
    """Largest byte declaration retaining >= target_ctas on every SM."""
    lo = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        try:
            h = resident_hist(mid, block=block)
            _, mn, _, _ = summary(h)
        except RuntimeError:
            mn = 0
        if mn >= target_ctas:
            lo = mid
        else:
            hi = mid - 1
    return lo


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transitions", action="store_true",
                    help="binary-search every static occupancy transition")
    ap.add_argument("--external", action="store_true",
                    help="run noisy cross-kernel admission diagnostics")
    ap.add_argument("--pool", action="store_true",
                    help="run reliable same-kernel free-capacity pooling probe")
    args = ap.parse_args()

    print("=== selected static allocation points (block 32) ===")
    for size in (0, 1, 127, 128, 129, 4096, 32768, 65536, 98304, 102400):
        try:
            h = resident_hist(size)
            nsm, mn, mx, total = summary(h)
            result = f"SMs={nsm} CTA/SM={mn}..{mx} total={total}"
        except RuntimeError as exc:
            result = "INVALID " + str(exc).split(":", 1)[0]
        print(f"size={size:6d}: {result}")

    if args.transitions:
        print("\n=== largest static size retaining N CTA/SM ===")
        for n in range(1, 9):
            edge = static_transition(n)
            print(f"N={n}: max request={edge} (0x{edge:x})")

    print("\n==== runtime resize selected points (static 64 KiB) ===")
    for size in (0x1000, 0x1800, 0x2000, 0x4000, 0x8000):
        h = resident_hist(0x10000, size)
        nsm, mn, mx, total = summary(h)
        print(f"target={size:6d}: SMs={nsm} CTA/SM={mn}..{mx} total={total}")

    if args.pool:
        print("\n=== same-kernel capacity pooling (static user 32 KiB) ===")
        initial_charge = 0x8000 + 0x400
        for target in (0x1000, 0x2000, 0x3000, 0x4000, 0x5000, 0x6000):
            reset_context()
            h = resident_hist(0x8000, target)
            nsm, mn, mx, total = summary(h)
            predicted = min(8, (102400 - initial_charge) // target + 1)
            print(f"target={target:5d}: CTA/SM={mn}..{mx},"
                  f" pool-prediction={predicted}, total={total}, SMs={nsm}")

    if args.external:
        print("\n=== external fragmentation / hole reuse (block 32) ===")
        cases = [
            # Full 3x32K occupancy: a tiny B is the no-free-space control.
            (0x8000, None, 510, 0x1000, "3x32K unchanged; add 4K"),
            # One large contiguous hole per SM, calibrating B=32K admission.
            (0x10000, 0x8000, 170, 0x8000, "1x64K->32K; add 32K"),
            (0x10000, 0x8000, 170, 68608, "1x64K->32K; add max"),
            (0x10000, 0x8000, 170, 68609, "1x64K->32K; add max+1"),
            # Three separated ~16K holes.  B=16K should fit individual holes;
            # B=32K only fits if free capacity is pooled/remapped/coalesced.
            (0x8000, 0x4000, 510, 0x4000, "3x32K->16K; add 16K"),
            (0x8000, 0x4000, 510, 0x8000, "3x32K->16K; add 32K"),
            (0x8000, 0x4000, 510, 0xC000, "3x32K->16K; add 48K"),
            (0x8000, 0x4000, 510, 52224, "3x32K->16K; add max"),
            (0x8000, 0x4000, 510, 52225, "3x32K->16K; add max+1"),
        ]
        for ast, art, ag, bst, label in cases:
            ah, bh = external_case(ast, art, ag, bst)
            as_ = summary(ah) if ah else (0, 0, 0, 0)
            bs_ = summary(bh) if bh else (0, 0, 0, 0)
            print(f"{label:<30} A={as_} B={bs_}")


if __name__ == "__main__":
    main()
