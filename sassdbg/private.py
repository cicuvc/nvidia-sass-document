"""M11c warp-private heap-code bootstrap (no breakpoints yet).

`PrivateKernel.from_source()` preserves the original parameter offsets and
appends the debugger-control argument; `.from_cubin()` preserves the target
ABI exactly.  Both replace the entry with an immutable LEPC+JMP trampoline.  A
shared heap dispatcher computes the global warp id and jumps to that warp's
full private copy of the canonical function image.

This module deliberately stops at the M11c boundary: it creates, launches and
relaunches private copies, but does not patch breakpoint words.  M11d will
consume the `PrivateCodeSet` and state established here.
"""
from __future__ import annotations

import re
import struct
import time
from pathlib import Path

from assembler import (CudaModule, assemble, assemble_flat, assemble_kernel)
from assembler.sass_elf import CubinBuilder
from assembler.sass_parser import parse_kernel

from .cubin import load_kernel
from .warpcode import (CodeTemplate, Layout, PrivateCodeSet, WarpState)


# ctrl (Layout.ctrl == 0)
CTRL_MODULE_BASE = 0x00          # u64: entry LEPC (identical lane stores)
CTRL_GATE = 0x08                 # u32: host opens after every warp reports
CTRL_WARPS_PER_CTA = 0x0C        # u32: launch-time block warp count
CTRL_ACTIVE_WARPS = 0x10         # u32: diagnostic/bounds value

# Per-warp report in Layout.freeze_ctl + warp*FREEZE_STRIDE.  M11d owns the
# rest of that cache-line-separated slot.
DISPATCH_SELECTED = 0x00         # u64: actual JMX target loaded from table
DISPATCH_SEEN = 0x08             # u32: sequence-last ready flag


class BootstrapError(RuntimeError):
    """Warp-private dispatcher/bootstrap failure."""


def _pack(words) -> bytes:
    return b"".join(struct.pack("<QQ", lo, hi) for lo, hi in words)


def _trampoline_src(dispatcher_va: int) -> str:
    return f"""\
    LEPC {{R4,R5}};[7:7:{{}}:4:0]
    JMP 0x{dispatcher_va:x};[7:7:{{}}:6:0]
"""


def _dispatcher_src(lay: Layout, arena: int) -> str:
    """Immutable shared dispatcher.  R4/R5 arrive from the trampoline.

    It uses only R0-R5 (inside even an 8-register cubin's usable window),
    publishes the selected private base per warp, waits at a uniform gate,
    restores the architectural predicate baseline, then JMXes to original
    instruction zero in the private image.
    """
    table = arena + lay.code_base_table
    reports = arena + lay.freeze_ctl
    return f"""\
    MOV32I R2, 0x{arena & 0xFFFFFFFF:08x};[7:7:{{}}:5:1]
    MOV32I R3, 0x{arena >> 32:08x};[7:7:{{}}:5:1]
    S2R R0, SR_CTAID.X;[5:7:{{}}:5:1]
    S2R R1, SR_TID.X;[4:7:{{}}:5:1]
    STG.E.64.STRONG.GPU [{{R2,R3}}+0x{CTRL_MODULE_BASE:x}], {{R4,R5}};[7:0:{{}}:8:0]
    LDG.E.STRONG.GPU R4, [{{R2,R3}}+0x{CTRL_WARPS_PER_CTA:x}];[2:1:{{0}}:8:0]
    SHF.R.U32.HI R1, RZ, 0x5, R1;[7:7:{{4}}:5:1]
    IMAD R0, R0, R4, R1;[7:7:{{2,5}}:5:1]
    MOV32I R2, 0x{table & 0xFFFFFFFF:08x};[7:7:{{1}}:5:1]
    MOV32I R3, 0x{table >> 32:08x};[7:7:{{}}:5:1]
    IMAD.WIDE.U32 {{R2,R3}}, R0, 0x8, {{R2,R3}};[7:7:{{}}:5:1]
    LDG.E.64.STRONG.GPU {{R4,R5}}, [{{R2,R3}}];[2:1:{{}}:8:0]
    MOV32I R2, 0x{reports & 0xFFFFFFFF:08x};[7:7:{{1}}:5:1]
    MOV32I R3, 0x{reports >> 32:08x};[7:7:{{}}:5:1]
    IMAD.WIDE.U32 {{R2,R3}}, R0, 0x{lay.FREEZE_STRIDE:x}, {{R2,R3}};[7:7:{{}}:5:1]
    STG.E.64.STRONG.GPU [{{R2,R3}}+0x{DISPATCH_SELECTED:x}], {{R4,R5}};[7:0:{{2}}:8:0]
    MOV32I R1, 0x1;[7:7:{{0}}:5:1]
    STG.E.STRONG.GPU [{{R2,R3}}+0x{DISPATCH_SEEN:x}], R1;[7:1:{{}}:8:0]
#def_label(dispatch_gate)
    NANOSLEEP 0x100;[7:7:{{}}:5:1]
    MOV32I R2, 0x{arena & 0xFFFFFFFF:08x};[7:7:{{1}}:5:1]
    MOV32I R3, 0x{arena >> 32:08x};[7:7:{{}}:5:1]
    LDG.E.STRONG.GPU R1, [{{R2,R3}}+0x{CTRL_GATE:x}];[2:1:{{}}:8:0]
    ISETP.EQ.AND P1, PT, R1, RZ, PT;[7:7:{{2}}:13:1]
    @P1 BRA #label(dispatch_gate);[7:7:{{}}:6:0]
    R2P PR, RZ, 0x7F;[7:7:{{}}:13:1]
    JMX {{R4,R5}}, 0x0;[7:7:{{}}:6:0]
"""


def _checked_words(body: str, name: str) -> list[tuple[int, int]]:
    src = f"#fn {name}() {{\n{body}}}\n"
    return assemble_kernel(src, check_deps=True).encoded


def _patch_cubin_entry(data: bytes, file_off: int,
                       dispatcher_va: int) -> bytes:
    """Return a module image with only its two-word entry window changed."""
    tramp = assemble_flat(_trampoline_src(dispatcher_va))
    if len(tramp) != 2:
        raise BootstrapError("entry trampoline is not two words")
    if file_off < 0 or file_off + 32 > len(data):
        raise BootstrapError(
            f"entry window {file_off:#x}..{file_off + 32:#x} "
            f"outside cubin of size {len(data):#x}")
    patched = bytearray(data)
    struct.pack_into("<QQ", patched, file_off, *tramp[0])
    struct.pack_into("<QQ", patched, file_off + 16, *tramp[1])
    return bytes(patched)


def _render_pragma(name: str, value) -> str:
    return f"    #pragma {name}({value})"


def _source_wrapper(source: str, dispatcher_va: int,
                    target_words: list[tuple[int, int]]) -> tuple[str, str]:
    decl = parse_kernel(source)
    original_param_src = [f"{p.name}<{p.size}>" for p in decl.params]
    params = ", ".join(original_param_src + ["dbgctrl<8>"])
    tramp = _trampoline_src(dispatcher_va)
    # Keep the source-debugger launch ABI (trailing dbgctrl) even though M11c's
    # immutable dispatcher has its arena VA baked after allocation.  M11d will
    # consume the same control argument for mutable breakpoint metadata.
    # Do not scan dispatcher/trampoline absolute immediates: the cubin
    # builder's intentionally simple field heuristic can read their address
    # bytes as R255 and inflate REGCOUNT to 256.  The dispatcher is audited to
    # use only R0-R5, whose allocation window is 8; scan only canonical target
    # words (the same input the ordinary source builder understands).
    computed = max(8, CubinBuilder._compute_regcount(target_words))
    declared = int(decl.attributes.get("MAXREG_COUNT", 0))
    attrs = dict(decl.attributes)
    attrs["MAXREG_COUNT"] = max(computed, declared)
    pragmas = "\n".join(_render_pragma(k, v)
                          for k, v in attrs.items())
    wrapper = f"#fn {decl.name}({params}) {{\n{pragmas}\n{tramp}}}\n"

    # Appending dbgctrl must not move any existing constant-bank offset.  The
    # private canonical words retain the original LDC immediates.
    original_params = assemble_kernel(source, check_deps=True).params
    wrapper_params = assemble_kernel(wrapper, check_deps=True).params
    if wrapper_params[:len(original_params)] != original_params:
        raise BootstrapError(
            f"wrapper parameter ABI changed: {original_params} -> "
            f"{wrapper_params}")
    if (len(wrapper_params) != len(original_params) + 1
            or wrapper_params[-1][2] != 8):
        raise BootstrapError(
            f"wrapper did not append an 8-byte dbgctrl: {wrapper_params}")
    return wrapper, decl.name


class PrivateKernel:
    """M11c no-breakpoint runtime for source kernels and real cubins."""

    def __init__(self, template: CodeTemplate, *, max_warps: int,
                 max_bps: int, budget: int | None, module_builder,
                 func: str, append_dbgctrl: bool):
        self.template = template
        self.max_warps = max_warps
        self.func = func
        self._append_dbgctrl = append_dbgctrl
        self.lay = Layout(max_bps, max_warps, template.size, budget=budget)
        self.codes = PrivateCodeSet(template, max_warps, max_bps=max_bps)

        # Establish the process-global context and allocate executable storage
        # before loading the target module: the trampoline bakes dispatcher_va.
        self.owner = CudaModule(assemble(
            "#fn __sassdbg_owner() {\n"
            "    EXIT;[7:7:{}:5:0]\n}\n"))
        self.arena = self.owner.devmem_alloc(self.lay.total)
        if self.arena % 0x100:
            raise BootstrapError(
                f"arena base {self.arena:#x} is not 0x100-aligned")
        self.owner.devmem_set(self.arena, 0, self.lay.total // 4)

        for w, inst in enumerate(self.codes.instances):
            inst.stride = self.lay.code_stride
            inst.place(self.lay.code_va(self.arena, w))

        dsrc = _dispatcher_src(self.lay, self.arena)
        self.dispatcher_words = _checked_words(dsrc, "__dispatch_check")
        if not 0 < len(self.dispatcher_words) * 16 <= self.lay.DISPATCHER_SZ:
            raise BootstrapError("dispatcher exceeds reserved slot")
        self._write_dispatcher()
        self._write_code_images(range(max_warps))
        self._write_code_base_table()

        module_bytes = module_builder(
            self.arena + self.lay.dispatcher,
            list(self.dispatcher_words) + list(template.words))
        self.mod = CudaModule(module_bytes)
        self.stream = CudaModule.stream_create()
        self.n_warps = 0
        self.warps_per_cta = 0
        self._module_base: int | None = None

    @classmethod
    def from_source(cls, source: str, func: str | None = None, *,
                    max_warps: int = 1, max_bps: int = 0,
                    budget: int | None = None) -> "PrivateKernel":
        decl = parse_kernel(source)
        if func is not None and func != decl.name:
            raise BootstrapError(
                f"source defines {decl.name!r}, not requested {func!r}")
        template = CodeTemplate.from_source(source, decl.name)

        def build(dispatcher_va, _executable_words):
            wrapper, _ = _source_wrapper(
                source, dispatcher_va, list(template.words))
            return assemble(wrapper, check_deps=True)

        return cls(template, max_warps=max_warps, max_bps=max_bps,
                   budget=budget, module_builder=build, func=decl.name,
                   append_dbgctrl=True)

    @classmethod
    def from_cubin(cls, cubin_path: str | Path, func: str | None = None, *,
                   max_warps: int = 1, max_bps: int = 0,
                   budget: int | None = None) -> "PrivateKernel":
        path = str(cubin_path)
        kt = load_kernel(path, func)
        template = CodeTemplate.from_cubin(path, kt.func)

        def build(dispatcher_va, _executable_words):
            return _patch_cubin_entry(
                Path(path).read_bytes(), kt.file_off, dispatcher_va)

        return cls(template, max_warps=max_warps, max_bps=max_bps,
                   budget=budget, module_builder=build, func=kt.func,
                   append_dbgctrl=False)

    def _padded_image(self, warp: int) -> bytes:
        words = list(self.template.materialize(
            self.codes.instances[warp].base))
        nop = assemble_flat("NOP;[7:7:{}:8:0]")[0]
        n = self.lay.code_stride // 16
        words.extend([nop] * (n - len(words)))
        return _pack(words)

    def _write_code_images(self, warps) -> None:
        for w in warps:
            self.owner.device_write(
                self.codes.instances[w].base, self._padded_image(w))

    def _write_code_base_table(self) -> None:
        raw = b"".join(struct.pack("<Q", i.base)
                       for i in self.codes.instances)
        self.owner.device_write(
            self.arena + self.lay.code_base_table, raw)

    def _write_dispatcher(self) -> None:
        nop = assemble_flat("NOP;[7:7:{}:8:0]")[0]
        words = list(self.dispatcher_words)
        words.extend([nop] * (self.lay.DISPATCHER_SZ // 16 - len(words)))
        self.owner.device_write(
            self.arena + self.lay.dispatcher, _pack(words))

    @staticmethod
    def _one_dim(x) -> tuple[int, int, int]:
        t = tuple(x)
        if not t or len(t) > 3:
            raise ValueError(f"bad launch dimension {x!r}")
        t = t + (1,) * (3 - len(t))
        if t[1:] != (1, 1):
            raise ValueError("M11c supports only 1-D grid/block")
        return t

    def launch(self, args: list, grid=(1,), block=(32,)) -> None:
        grid3 = self._one_dim(grid)
        block3 = self._one_dim(block)
        wpc = (block3[0] + 31) // 32
        total = grid3[0] * wpc
        if total > self.max_warps:
            raise ValueError(
                f"launch needs {total} warps, max_warps={self.max_warps}")
        if self.n_warps and any(
                i.state not in (WarpState.UNLAUNCHED, WarpState.DONE)
                for i in self.codes.instances[:self.n_warps]):
            raise BootstrapError("previous launch is still active")

        # Canonical reconstruction on every launch.  No active warp has ever
        # fetched these words at this point; no IVALL is required at the gate.
        self._write_code_images(range(total))
        self.owner.devmem_set(self.arena + self.lay.ctrl, 0,
                              self.lay.CTRL_SZ // 4)
        self.owner.devmem_set(self.arena + self.lay.freeze_ctl, 0,
                              self.max_warps * self.lay.FREEZE_STRIDE // 4)
        self.owner.device_write(
            self.arena + CTRL_WARPS_PER_CTA,
            struct.pack("<II", wpc, total))
        self.n_warps = total
        self.warps_per_cta = wpc
        self._module_base = None
        for w, inst in enumerate(self.codes.instances):
            inst.state = WarpState.GATED if w < total else WarpState.UNLAUNCHED
        launch_args = list(args)
        if self._append_dbgctrl:
            launch_args.append(self.arena)
        self.mod.launch(self.func, grid=grid3, block=block3, args=launch_args,
                        stream=self.stream)

    def _rd(self, va: int, fmt: str):
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, self.owner.device_read(va, size))

    def dispatch_report(self, warp: int) -> tuple[int, int]:
        if not 0 <= warp < self.n_warps:
            raise IndexError(warp)
        va = (self.arena + self.lay.freeze_ctl
              + warp * self.lay.FREEZE_STRIDE)
        selected, seen = self._rd(va, "<QI")
        return selected, seen

    def wait_ready(self, timeout: float = 5.0) -> list[int]:
        if not self.n_warps:
            raise BootstrapError("kernel not launched")
        t0 = time.time()
        while True:
            reports = [self.dispatch_report(w) for w in range(self.n_warps)]
            bad = [w for w, (selected, seen) in enumerate(reports)
                   if seen != 1 or selected != self.codes.instances[w].base]
            if not bad:
                break
            if CudaModule.stream_query(self.stream):
                CudaModule.stream_sync(self.stream)
                raise BootstrapError(
                    f"target exited before dispatcher gate; bad warps {bad}")
            if time.time() - t0 > timeout:
                raise TimeoutError(
                    f"dispatcher ready timeout; bad warps {bad}")
            time.sleep(0.001)
        lo, hi = self._rd(self.arena + CTRL_MODULE_BASE, "<II")
        self._module_base = lo | (hi << 32)
        if not self._module_base:
            raise BootstrapError("dispatcher did not report module entry")
        return [x[0] for x in reports]

    @property
    def module_base(self) -> int:
        if self._module_base is None:
            self.wait_ready()
        assert self._module_base is not None
        return self._module_base

    def code_base(self, warp: int) -> int:
        return self.codes.instances[warp].base

    def release(self) -> None:
        self.wait_ready()
        self.owner.device_write(
            self.arena + CTRL_GATE, struct.pack("<I", 1))
        for inst in self.codes.instances[:self.n_warps]:
            inst.state = WarpState.RUNNING

    def wait_done(self, timeout: float = 120.0) -> None:
        t0 = time.time()
        while not CudaModule.stream_query(self.stream):
            if time.time() - t0 > timeout:
                raise TimeoutError("private target still running")
            time.sleep(0.005)
        CudaModule.stream_sync(self.stream)
        for inst in self.codes.instances[:self.n_warps]:
            inst.state = WarpState.DONE


__all__ = [
    "BootstrapError", "PrivateKernel",
    "CTRL_MODULE_BASE", "CTRL_GATE", "CTRL_WARPS_PER_CTA",
    "CTRL_ACTIVE_WARPS", "DISPATCH_SELECTED", "DISPATCH_SEEN",
]
