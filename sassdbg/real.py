"""sassdbg.real — M10: attach the debugger to a REAL nvcc cubin.

No source, no re-assembly: the cubin image is patched in memory before
cuModuleLoadData.  The target kernel's first two instructions (entry
trampoline window, 0x20 bytes) become

    LEPC {R8,R9}            # captures the kernel base (entry VA)
    JMP  <heap prologue>    # devmem VA, baked

and the heap prologue (arena+Layout.kprol; arena VA baked into its
MOV32I immediates — a real kernel has no dbgctrl parameter) reports the
base to CTRL_BASE, parks at the start gate, self-invalidates (hardened
IVALL), replays the two displaced instructions verbatim (lifted text
re-assembled — the corpus round-trip is byte-exact), then RETs to
entry+0x20.  Afterwards everything is the M9 machinery: orig inst 0/1
live at the heap replay slots (bps there patch devmem, covered by the
same IVALL), orig inst i>=2 at kernel_base + i*16.

Kernels with a text relocation overlapping the entry window are
rejected by sassdbg.cubin.load_kernel (the driver would apply the
reloc over the trampoline).
"""
import struct

from assembler import CudaModule, assemble_flat  # noqa: F401  (re-export)

from .cubin import load_kernel, KernelText  # noqa: F401
from .lift import lift, extract_params
from .patch import (Debugger, Layout, KPROL_SZ, _real_prologue_src,
                    _trampoline_src)


class CubinDebugger(Debugger):
    """Debugger for a real cubin kernel (no dialect source needed).

    `cubin_path` is loaded, the chosen kernel's entry gets the
    trampoline, and the patched image is what CudaModule loads.
    `self.source` is the lifted dialect text (for the stepper's Cfg).
    Launch with the kernel's own args (no dbgctrl is appended).
    """

    def __init__(self, cubin_path: str, func: str | None = None,
                 max_bps: int = 16, max_warps: int = 1):
        self.cubin_path = cubin_path
        self._kt = load_kernel(cubin_path, func)
        self.func = self._kt.func
        # lifted dialect text (orig-indexed) — the stepper's Cfg input
        self.source = lift(cubin_path, self._kt.func)[self._kt.func]
        self.res_params: list = []       # lifted text is absolute c[]
        self._base_delta = 0             # trampoline LEPC sits AT entry
        self._append_dbgctrl = False
        self.params = extract_params(
            open(cubin_path, "rb").read(), self._kt.func)

        # allocate the arena BEFORE module load: the trampoline JMP and
        # the prologue immediates bake its VA into the patched image.
        from .patch import Patcher
        self.patcher = Patcher()
        lay = Layout(max_bps, max_warps)
        arena = self.patcher.mod.devmem_alloc(lay.total)

        # heap prologue with the two displaced instructions replayed
        lines = [ln for ln in self.source.splitlines() if ";[" in ln]
        self.kprol_va = arena + lay.kprol
        psrc, self._replay_idx = _real_prologue_src(
            arena, self.kprol_va, lines[:2])
        penc = assemble_flat(psrc)
        assert 0 < len(penc) * 16 <= KPROL_SZ, "prologue too big"

        # patch the cubin: trampoline over the entry window
        tramp = assemble_flat(_trampoline_src(self.kprol_va))
        assert len(tramp) == 2
        data = bytearray(open(cubin_path, "rb").read())
        struct.pack_into("<QQ", data, self._kt.file_off, *tramp[0])
        struct.pack_into("<QQ", data, self._kt.file_off + 16, *tramp[1])

        self.mod = CudaModule(bytes(data))
        self._setup(max_bps, max_warps, arena=arena)
        # prologue image AFTER the arena zeroing in _setup
        self.mod.device_write(
            self.kprol_va,
            b"".join(struct.pack("<QQ", lo, hi) for lo, hi in penc))

    # -- site mapping: orig 0/1 live in the heap prologue ----------------
    def _site_va(self, orig_index: int) -> int:
        if orig_index < 2:
            return self.kprol_va + (self._replay_idx + orig_index) * 16
        return self.base() + orig_index * 16

    def _orig_word(self, orig_index: int) -> tuple[int, int]:
        return self._kt.words[orig_index]
