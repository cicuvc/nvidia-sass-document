"""tests/asm_construct/test_warpcode.py — M11b/M11c CPU-only unit tests.

Covers (SASSDBG_WARP_PRIVATE_PLAN.md section 14/M11b): address mapping,
alignment, overlays, epochs, masks, replay-plan cache keys, memory
budgeting, relocation/PC-sensitive rejection, materialization, dispatcher
assembly, wrapper ABI, and cubin entry patching — all without a GPU.
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sassdbg.warpcode import (  # noqa: E402
    AddressMap, Binding, CodeImageAnalyzer, CodeImageError,
    CodeMapError, CodeTemplate, Layout, LayoutError,
    Outcome, OverlayBatch, PrivateCodeSet, ReplayPlan, ScopeError,
    WarpState, _field_value, _OPCODE_INDEX,
)

from assembler import assemble_flat  # noqa: E402
from assembler.sass_parser import parse_kernel  # noqa: E402
from sassdbg.private import (  # noqa: E402
    BootstrapError, _checked_words, _dispatcher_src, _patch_cubin_entry,
    _m11d_handler_image, _m11d_stub_src, _source_wrapper, _trampoline_src,
)
from sassdbg.cubin import load_kernel  # noqa: E402


# A tiny valid kernel: internal relative BRA only.
_SRC = """#fn k(x<4>) {
    #pragma SHARED(0)
    MOV32I R1, 0x0;[7:7:{}:5:1]
#def_label(loop)
    IADD3 R1, R1, 0x1, RZ;[7:7:{}:5:1]
    ISETP.LT.AND P0, PT, R1, 0x10, PT;[7:7:{}:13:1]
    @P0 BRA #label(loop);[7:7:{}:6:0]
    STG.E.STRONG.GPU [RZ+0x1000], R1;[7:1:{}:8:0]
    EXIT;[7:7:{}:5:0]
}
"""


def _template():
    return CodeTemplate.from_source(_SRC, "k")


def _fake_patch(slot, _base=0):
    # deterministic non-assembler patch word (CPU-only, no DB needed
    # for overlay tests): the slot number as both halves.
    return (0xDEAD0000 | slot, 0xBEEF0000 | slot)


class TestAddressMapping(unittest.TestCase):
    def test_roundtrip(self):
        t = _template()
        m = AddressMap(t)
        m.set_base(0, 0x7f00000000)
        for i in range(t.n_insts):
            va = m.site_va(0, i)
            self.assertEqual(m.orig_index(0, va), i)

    def test_site_va_bounds(self):
        t = _template()
        m = AddressMap(t)
        m.set_base(0, 0x1000)
        with self.assertRaises(CodeMapError):
            m.site_va(0, -1)
        with self.assertRaises(CodeMapError):
            m.site_va(0, t.n_insts)

    def test_hit_misaligned_rejected(self):
        t = _template()
        m = AddressMap(t)
        m.set_base(0, 0x1000)
        with self.assertRaises(CodeMapError):
            m.orig_index(0, 0x1008)          # mid-instruction
        with self.assertRaises(CodeMapError):
            m.orig_index(0, 0x0FF8)          # below base

    def test_hit_outside_copy(self):
        t = _template()
        m = AddressMap(t)
        m.set_base(0, 0x1000)
        with self.assertRaises(CodeMapError):
            m.orig_index(0, 0x1000 + t.size + 0x40)

    def test_unplaced_warp(self):
        t = _template()
        m = AddressMap(t)
        with self.assertRaises(CodeMapError):
            m.code_base(0)

    def test_base_alignment(self):
        t = _template()
        m = AddressMap(t)
        with self.assertRaises(CodeMapError):
            m.set_base(0, 0x1008)

    def test_distinct_warp_bases(self):
        t = _template()
        m = AddressMap(t)
        m.set_base(0, 0x10000)
        m.set_base(1, 0x20000)
        self.assertEqual(m.site_va(1, 2) - m.site_va(0, 2), 0x10000)
        self.assertEqual(m.orig_index(1, m.site_va(1, 2)), 2)


class TestLayout(unittest.TestCase):
    def test_regions_16b_aligned(self):
        lay = Layout(4, 8, 0x123)
        for name in ("ctrl", "code_base_table", "code_epoch", "park_mode",
                     "freeze_ctl", "bp_masks", "stubs", "handlers",
                     "thunks", "hslots", "cmdseq", "cmdbuf", "results",
                     "frames", "dispatcher", "code"):
            off = getattr(lay, name)
            self.assertEqual(off % 16, 0, f"{name} at {off:#x}")

    def test_code_stride_0x100(self):
        lay = Layout(4, 8, 0x123)
        self.assertGreaterEqual(lay.code_stride, 0x100)
        self.assertEqual(lay.code_stride % 0x100, 0)
        self.assertGreaterEqual(lay.code_stride, 0x123 + 15 & ~15)

    def test_code_regions_0x100_separated(self):
        lay = Layout(4, 3, 0x40)
        # adjacent warps never share a fetch line
        for w in range(3):
            self.assertEqual(lay.code_va(0, w) % 0x100, 0)
        # thunk arenas 0x100-aligned and 0x100-multiple sized
        self.assertEqual(lay.thunks % 0x100, 0)
        self.assertEqual(lay.thunk_arena % 0x100, 0)

    def test_freeze_cache_line_separated(self):
        lay = Layout(2, 4, 0x100)
        self.assertEqual(lay.FREEZE_STRIDE % 0x80, 0)  # >= cacheline

    def test_budget_refusal(self):
        # fits
        lay = Layout(2, 2, 0x100, budget=Layout(2, 2, 0x100).total)
        self.assertGreater(lay.total, 0)
        # one extra warp's code must overflow a tight budget
        with self.assertRaises(LayoutError):
            Layout(2, 3, 0x100, budget=Layout(2, 2, 0x100).total)

    def test_bad_params(self):
        with self.assertRaises(LayoutError):
            Layout(0, 0, 0x100)
        with self.assertRaises(LayoutError):
            Layout(1, 1, 8)
        with self.assertRaises(LayoutError):
            Layout(1, 1, 0x100, thunk_arena=0x180)

    def test_report_totals(self):
        lay = Layout(4, 8, 0x200)
        sizes = lay.region_sizes()
        self.assertEqual(sum(sizes.values()) <= lay.total, True)
        self.assertIn("code", sizes)
        self.assertIn("total", lay.report())
        self.assertEqual(sizes["code"], 8 * lay.code_stride)

    def test_accessors_bounds(self):
        lay = Layout(4, 2, 0x100)
        with self.assertRaises(LayoutError):
            lay.code_va(0, 2)
        with self.assertRaises(LayoutError):
            lay.stub_va(0, 4)


class TestAnalyzer(unittest.TestCase):
    def _cls(self, words, **kw):
        return CodeImageAnalyzer().analyze(words, **kw)

    def test_plain_ops_pi(self):
        words = assemble_flat(
            "IADD3 R1, R2, 0x3, RZ;[7:7:{}:5:1]\n"
            "MOV R4, R5;[7:7:{}:4:1]\n"
            "STG.E.STRONG.GPU [RZ+0x100], R1;[7:1:{}:8:0]\n")
        for c in self._cls(words):
            self.assertIs(c.outcome, Outcome.POSITION_INDEPENDENT)

    def test_internal_bra_pi(self):
        src = ("BRA #label(t);[7:7:{}:6:0]\n"
               "NOP;[7:7:{}:8:0]\n"
               "#def_label(t)\n"
               "EXIT;[7:7:{}:5:0]\n")
        words = assemble_flat(src)
        self.assertIs(self._cls(words)[0].outcome,
                      Outcome.POSITION_INDEPENDENT)

    def test_bra_in_function_pi(self):
        # a BRA whose target stays in-function is PI (the delta is
        # preserved by the copy); the out-of-bounds rejection is
        # covered by test_bra_out_of_bounds_synthetic below.
        src = ("BRA #label(t);[7:7:{}:6:0]\n"
               "NOP;[7:7:{}:8:0]\n"
               "#def_label(t)\n"
               "EXIT;[7:7:{}:5:0]\n")
        words = assemble_flat(src)
        self.assertIs(self._cls(words)[0].outcome,
                      Outcome.POSITION_INDEPENDENT)

    def test_bra_out_of_bounds_synthetic(self):
        # craft a BRA whose sImm points past a 1-instruction image
        w = assemble_flat("BRA #label(t);[7:7:{}:6:0]\n"
                          "#def_label(t)\n"
                          "EXIT;[7:7:{}:5:0]\n")
        self.assertEqual(len(w), 2)
        # take only the first word: its target (index 1) stays inside
        # a 2-word image, so use a 1-word image with that word's sImm
        cls = self._cls(w[:1])
        self.assertIs(cls[0].outcome, Outcome.UNSUPPORTED)
        self.assertIn("leaves the function", cls[0].reason)

    def test_pc_sensitive_rejected(self):
        for src in ("LEPC {R8,R9};[7:7:{}:4:0]",
                    "RPCMOV Rpc.LO, R0;[7:7:{}:4:0]",
                    "CCTL.I.IVALL;[7:7:{}:4:0]",
                    "RET.ABS.NODEC PT, {R4,R5}, 0x0;[7:7:{}:13:1]"):
            words = assemble_flat(src)
            c = self._cls(words)[0]
            self.assertIs(c.outcome, Outcome.UNSUPPORTED, src)
            self.assertTrue(c.reason)

    def test_jmp_rewrite_and_reject(self):
        VA = 0x7f8a00001000
        words = assemble_flat(
            f"JMP 0x{VA + 0x20:x};[7:7:{{}}:6:0]\n"
            "NOP;[7:7:{}:8:0]\n"
            "EXIT;[7:7:{}:5:0]\n")
        # in-range with the right link base -> REWRITE to index 2
        c = self._cls(words, link_base=VA)[0]
        self.assertIs(c.outcome, Outcome.REWRITE, c.reason)
        self.assertEqual(c.rewrite_index, 2)
        # wrong base -> out of range -> UNSUPPORTED
        c2 = self._cls(words, link_base=VA - 0x1000)[0]
        self.assertIs(c2.outcome, Outcome.UNSUPPORTED)
        # no link base at all -> UNSUPPORTED
        c3 = self._cls(words)[0]
        self.assertIs(c3.outcome, Outcome.UNSUPPORTED)

    def test_relocation_rejected(self):
        words = assemble_flat(
            "NOP;[7:7:{}:8:0]\nNOP;[7:7:{}:8:0]\n")
        self.assertEqual(len(words), 2)
        c = CodeImageAnalyzer().analyze(words, reloc_offsets=(16,))[1]
        self.assertIs(c.outcome, Outcome.UNSUPPORTED)
        self.assertIn("relocation", c.reason)
        # instruction 0 is clean
        self.assertIs(CodeImageAnalyzer().analyze(
            words, reloc_offsets=(16,))[0].outcome,
            Outcome.POSITION_INDEPENDENT)

    def test_validate_lists_failures(self):
        words = assemble_flat(
            "LEPC {R8,R9};[7:7:{}:4:0]\n"
            "CCTL.I.IVALL;[7:7:{}:4:0]\n")
        with self.assertRaises(CodeImageError) as cm:
            CodeImageAnalyzer().validate(words)
        self.assertIn("[0]", str(cm.exception))
        self.assertIn("[1]", str(cm.exception))

    def test_jmp_field_decode_roundtrip(self):
        # the analyzer's field decode must reproduce the encoded VA
        VA = 0x1234567890
        lo, hi = assemble_flat(f"JMP 0x{VA:x};[7:7:{{}}:6:0]")[0]
        enc = _OPCODE_INDEX.encoding("JMP")
        self.assertEqual(_field_value(enc, "Sb", lo, hi, False) * 4, VA)

    def test_materialize_rewrites_internal_absolute_jmp(self):
        old = 0x7f8a00001000
        new = 0x7f8b00002000
        words = tuple(assemble_flat(
            f"JMP 0x{old + 0x20:x};[7:7:{{}}:6:0]\n"
            "NOP;[7:7:{}:8:0]\n"
            "EXIT;[7:7:{}:5:0]\n"))
        classifications = CodeImageAnalyzer().validate(
            words, link_base=old)
        t = CodeTemplate("j", words, 999, classifications,
                         tuple(ReplayPlan(i, "verbatim")
                               for i in range(len(words))))
        placed = t.materialize(new)
        enc = _OPCODE_INDEX.encoding("JMP")
        got = _field_value(enc, "Sb", *placed[0], signed=False) * 4
        self.assertEqual(got, new + 0x20)
        # Only the immediate field changed; untouched words stay exact.
        self.assertEqual(placed[1:], words[1:])


class TestTemplate(unittest.TestCase):
    def test_from_source(self):
        t = _template()
        self.assertGreater(t.n_insts, 3)
        self.assertEqual(t.size, t.n_insts * 16)
        self.assertTrue(all(
            c.outcome is Outcome.POSITION_INDEPENDENT
            for c in t.classifications))

    def test_from_source_rejects_pc_sensitive(self):
        src = ("#fn k() {\n"
               "    LEPC {R8,R9};[7:7:{}:4:0]\n"
               "    EXIT;[7:7:{}:5:0]\n"
               "}\n")
        with self.assertRaises(CodeImageError):
            CodeTemplate.from_source(src, "bad")

    def test_replay_plans(self):
        t = _template()
        plans = {p.orig_index: p for p in t.replay_plans}
        self.assertEqual(len(plans), t.n_insts)
        # the loop-back predicated BRA becomes an absolute-JMP plan
        bra = next(p for p in t.replay_plans
                   if p.kind == "bra_abs")
        tgt_idx = bra.target_index
        self.assertIsNotNone(tgt_idx)
        expanded = bra.expand(code_base=0x5000)
        self.assertTrue(any(f"0x{0x5000 + tgt_idx * 16:x}" in ln
                            for ln in expanded))
        self.assertTrue(all("{tgt}" not in ln for ln in expanded))
        # plain instruction verbatim
        some = next(p for p in t.replay_plans if p.kind == "verbatim")
        self.assertEqual(some.expand(0x5000), some.lines)

    def test_replay_cache_keys(self):
        t1 = _template()
        t2 = _template()          # same source, distinct template ids
        self.assertNotEqual(t1.template_id, t2.template_id)
        p1 = next(p for p in t1.replay_plans if p.kind == "bra_abs")
        p2 = next(p for p in t2.replay_plans if p.kind == "bra_abs"
                  and p.target_index == p1.target_index)
        self.assertNotEqual(p1.key(t1.template_id), p2.key(t2.template_id))
        # same template+index -> same key (stable across calls)
        self.assertEqual(p1.key(t1.template_id), p1.key(t1.template_id))
        # distinct indices -> distinct keys
        keys = {p.key(t1.template_id) for p in t1.replay_plans}
        self.assertEqual(len(keys), t1.n_insts)


class TestBootstrapStatic(unittest.TestCase):
    """M11c assembly/ABI checks that do not require a CUDA device."""

    def test_dispatcher_fits_and_trampoline_is_two_words(self):
        t = _template()
        lay = Layout(0, 4, t.size)
        arena = 0x7F8000000000
        words = _checked_words(_dispatcher_src(lay, arena), "dispatch")
        self.assertGreater(len(words), 8)
        self.assertLessEqual(len(words) * 16, lay.DISPATCHER_SZ)
        self.assertEqual(len(assemble_flat(
            _trampoline_src(arena + lay.dispatcher))), 2)

    def test_m11d_stub_and_handler_fit_with_clean_dependencies(self):
        t = _template()
        lay = Layout(4, 4, t.size)
        arena = 0x7F8000000000
        stub = _checked_words(
            _m11d_stub_src(lay, arena, 3, 2), "m11d_stub")
        handler, retline = _m11d_handler_image(lay, arena, 0)
        self.assertLessEqual(len(stub) * 16, lay.STUB_SZ)
        self.assertLessEqual(len(handler), lay.HANDLER_STRIDE)
        self.assertEqual(retline, len(handler) - 16)

    def test_source_wrapper_preserves_abi_attrs_and_regcount(self):
        src = """#fn attr(p0<4>, p1<8>) {
    #pragma SHARED(64)
    #pragma SHADER_TYPE(1)
    MOV32I R20, 0x1;[7:7:{}:5:1]
    EXIT;[7:7:{}:5:0]
}
"""
        t = CodeTemplate.from_source(src, "attr")
        wrapper, name = _source_wrapper(
            src, 0x7F8000010000, list(t.words))
        decl = parse_kernel(wrapper)
        self.assertEqual(name, "attr")
        self.assertEqual([(p.name, p.size, p.ordinal) for p in decl.params],
                         [("p0", 4, 0), ("p1", 8, 8),
                          ("dbgctrl", 8, 16)])
        self.assertEqual(decl.attributes["SHARED"], 64)
        self.assertEqual(decl.attributes["SHADER_TYPE"], 1)
        self.assertGreaterEqual(decl.attributes["MAXREG_COUNT"], 24)
        self.assertLess(decl.attributes["MAXREG_COUNT"], 256)

    def test_real_cubin_patch_changes_only_entry_window(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "m2_smoke.cubin")
        with open(path, "rb") as f:
            raw = f.read()
        kt = load_kernel(path)
        dispatcher = 0x7F8000123400
        patched = _patch_cubin_entry(raw, kt.file_off, dispatcher)
        self.assertEqual(patched[:kt.file_off], raw[:kt.file_off])
        self.assertEqual(patched[kt.file_off + 32:], raw[kt.file_off + 32:])
        self.assertEqual(
            patched[kt.file_off:kt.file_off + 32],
            b"".join(struct.pack("<QQ", *w) for w in
                     assemble_flat(_trampoline_src(dispatcher))))

    def test_real_cubin_patch_checks_entry_bounds(self):
        with self.assertRaises(BootstrapError):
            _patch_cubin_entry(bytes(31), 0, 0x7F8000123400)


class TestBreakpointsAndOverlays(unittest.TestCase):
    def _set(self, nwarps=2, **kw):
        return PrivateCodeSet(_template(), nwarps,
                              patch_word_fn=_fake_patch, **kw)

    def test_arm_all_pregate(self):
        s = self._set()
        bp = s.arm(1)
        self.assertEqual(sorted(bp.bindings), [0, 1])
        for b in bp.bindings.values():
            self.assertTrue(b.armed)
            self.assertEqual(b.stop_mask, 0xFFFFFFFF)
        self.assertEqual(bp.canonical_word, s.template.words[1])
        self.assertEqual(bp.stub_slot, 0)

    def test_arm_explicit_warps_and_masks(self):
        s = self._set(3)
        bp = s.arm(2, warps=[0, 2], lane_masks={0: 0x1, 2: 0xF0})
        self.assertEqual(bp.bindings[0].stop_mask, 0x1)
        self.assertEqual(bp.bindings[2].stop_mask, 0xF0)
        self.assertNotIn(1, bp.bindings)

    def test_arm_omitted_scope_rejected_when_running(self):
        s = self._set()
        s.instances[0].state = WarpState.RUNNING
        with self.assertRaises(ScopeError):
            s.arm(1)
        # explicit scope on a safe warp still fine
        s.arm(2, warps=[1])

    def test_arm_write_legal_only_at_boundary(self):
        s = self._set()
        s.instances[1].state = WarpState.RUNNING
        with self.assertRaises(ScopeError):
            s.arm(1, warps=[0, 1])
        s.instances[1].state = WarpState.FROZEN
        s.arm(1, warps=[0, 1])        # FROZEN is a safe boundary

    def test_double_arm_rejected(self):
        s = self._set()
        s.arm(1)
        with self.assertRaises(Exception):
            s.arm(1)

    def test_disarm_reuses_free_stub_without_collision(self):
        s = self._set(nwarps=1)
        a = s.arm(0)
        b = s.arm(1)
        self.assertEqual((a.stub_slot, b.stub_slot), (0, 1))
        s.disarm(a)
        c = s.arm(2)
        self.assertEqual(c.stub_slot, 0)
        self.assertNotEqual(c.stub_slot, b.stub_slot)

    def test_overlay_patches_only_armed(self):
        s = self._set()
        bp = s.arm(1)
        batch = s.compute_overlay()
        self.assertEqual([(w, i) for w, i, _ in batch.writes],
                         [(0, 1), (1, 1)])
        self.assertEqual(batch.epochs, [(0, 1), (1, 1)])
        s.commit(batch)
        self.assertEqual(s.instances[0].applied, {1: bp.id})
        self.assertTrue(s.instances[0].dirty)

    def test_overlay_idempotent(self):
        s = self._set()
        s.arm(1)
        s.commit(s.compute_overlay())
        b2 = s.compute_overlay()
        self.assertEqual(b2.writes, [])
        self.assertEqual(b2.epochs, [])

    def test_disarm_restores_canonical(self):
        s = self._set()
        bp = s.arm(1)
        s.commit(s.compute_overlay())
        s.disarm(bp)
        batch = s.compute_overlay()
        self.assertEqual([(w, i) for w, i, _ in batch.writes],
                         [(0, 1), (1, 1)])
        # restored word equals the canonical image
        for w, i, word in batch.writes:
            self.assertEqual(word, s.template.words[i])
        s.commit(batch)
        self.assertEqual(s.instances[0].applied, {})

    def test_zero_mask_removes_patch(self):
        s = self._set()
        bp = s.arm(1)
        s.commit(s.compute_overlay())
        s.set_break_mask(bp, 0, 0)
        batch = s.compute_overlay()
        self.assertIn((0, 1), [(w, i) for w, i, _ in batch.writes])
        self.assertEqual(batch.epochs, [(0, 2)])
        # warp 1 untouched this batch
        self.assertNotIn(1, [w for w, _ in batch.epochs])

    def test_epoch_monotonic(self):
        s = self._set()
        bp1 = s.arm(1)
        s.commit(s.compute_overlay())
        e1 = s.instances[0].code_epoch
        bp2 = s.arm(3)
        s.commit(s.compute_overlay())
        e2 = s.instances[0].code_epoch
        self.assertEqual(e2, e1 + 1)
        # no-change batch does not bump
        s.commit(s.compute_overlay())
        self.assertEqual(s.instances[0].code_epoch, e2)

    def test_overlay_writes_before_epochs(self):
        s = self._set()
        s.arm(1)
        batch = s.compute_overlay()
        # the transaction exposes words first, generations last
        self.assertIsInstance(batch, OverlayBatch)
        self.assertTrue(all(isinstance(w[2], tuple) and len(w[2]) == 2
                            for w in batch.writes))

    def test_image_reflects_patches(self):
        s = self._set()
        bp = s.arm(2, warps=[0])
        s.commit(s.compute_overlay())
        img = s.instances[0].image()
        self.assertEqual(img[2], bp.bindings[0].patch_word)
        self.assertEqual(img[1], s.template.words[1])
        # warp 1 image stays canonical
        self.assertEqual(s.instances[1].image(), list(s.template.words))

    def test_instance_place_and_hit(self):
        s = self._set()
        s.arm(1)
        s.commit(s.compute_overlay())
        inst = s.instances[0]
        inst.place(0x7f00010000)
        self.assertEqual(inst.base, 0x7f00010000)
        va = s.amap.site_va(0, 1)
        self.assertEqual(s.amap.orig_index(0, va), 1)
        with self.assertRaises(CodeMapError):
            inst.place(0x7f00010008)

    def test_binding_defaults(self):
        b = Binding()
        self.assertFalse(b.armed)
        self.assertEqual(b.stop_mask, 0xFFFFFFFF)
        self.assertIsNone(b.patch_word)
        self.assertEqual(b.epoch, 0)


class TestCubinTemplate(unittest.TestCase):
    """Real-cubin path; skipped when nvcc is unavailable (CPU-only)."""

    def _cubin(self):
        if not shutil.which("nvcc"):
            self.skipTest("nvcc not available")
        src = ("__global__ void kern(int *p) {\n"
               "  int i = threadIdx.x;\n"
               "  p[i] = i * 3 + 1;\n"
               "}\n")
        d = tempfile.mkdtemp(prefix="wc_")
        cu = os.path.join(d, "k.cu")
        cub = os.path.join(d, "k.cubin")
        open(cu, "w").write(src)
        subprocess.run(["nvcc", "-arch=sm_120", "-cubin", "-o", cub, cu],
                       check=True, capture_output=True)
        return cub

    def test_from_cubin_clean_kernel(self):
        cub = self._cubin()
        t = CodeTemplate.from_cubin(cub)
        self.assertGreater(t.n_insts, 4)
        self.assertTrue(all(
            c.outcome in (Outcome.POSITION_INDEPENDENT, Outcome.REWRITE)
            for c in t.classifications))
        # cubin templates get verbatim replay plans only
        self.assertTrue(all(p.kind == "verbatim"
                            for p in t.replay_plans))


if __name__ == "__main__":
    unittest.main(verbosity=2)
