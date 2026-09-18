"""tests/asm_construct/test_modulecode.py — M12a CPU-only unit tests.

Covers (SASSDBG_WARP_PRIVATE_PLAN.md section 14/M12a): complete native
symbol/relocation parsing, Mercury capsule segregation, ModuleTemplate /
TextIsland / FunctionTemplate / CodeLoc / CallEdge / SCC / ownership-policy
unit tests, and the RET.REL program-base / return-token conventions.  All
runs without a GPU (the cubin is compiled by nvcc only if absent).
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

from sassdbg.cubin import (  # noqa: E402
    CapsuleRelocation, NativeRelocation, _sections, callgraph_records,
    capsule_relocations, capsule_symbols, native_funcs,
    native_relocations, native_symbols, text_reloc_offsets,
)
from sassdbg.modulecode import (  # noqa: E402
    ModuleTemplate, OwnershipPolicy, Placement, RegSpec, ReturnABI,
    Stepping, TargetClass, sccs, recursive_scc,
)


TESTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CUBIN = os.path.join(TESTS_DIR, "call_test.cubin")
CU = os.path.join(TESTS_DIR, "call_test.cu")


def _is_merc_section(name: str) -> bool:
    return name.startswith(".nv.merc.") or name.startswith(".nv.capmerc.")


def _ensure_cubin():
    if os.path.exists(CUBIN):
        return
    if not shutil.which("nvcc"):
        raise unittest.SkipTest("nvcc not available")
    subprocess.run(["nvcc", "-arch=sm_120", "-O3", "-cubin",
                    "-o", CUBIN, CU], check=True, capture_output=True)


def _call_test_data():
    _ensure_cubin()
    with open(CUBIN, "rb") as f:
        return f.read()


class TestNativeSymbols(unittest.TestCase):
    def test_func_symbols(self):
        data = _call_test_data()
        secs = _sections(data)
        funcs = native_funcs(data, secs)
        got = {(s.name, s.value, s.size) for s in funcs}
        self.assertIn(("_Z1kPKiPii", 0x0, 1408), got)
        self.assertIn(("$_Z1kPKiPii$_Z3fibi", 0x140, 784), got)
        self.assertIn(("$_Z1kPKiPii$_Z4leafii", 0x450, 304), got)

    def test_native_symbols_exclude_mercury(self):
        data = _call_test_data()
        secs = _sections(data)
        names = {s.name for s in native_symbols(data, secs)}
        self.assertIn("_Z1kPKiPii", names)
        self.assertNotIn(".nv.merc.symtab", names)

    def test_capsule_symbols_segregated(self):
        data = _call_test_data()
        secs = _sections(data)
        cap = capsule_symbols(data, secs)
        self.assertGreater(len(cap), 0)
        # the two tables are distinct objects referencing different sections
        cap_sh = {s.shndx for s in cap}
        nat_sh = {s.shndx for s in native_symbols(data, secs)}
        self.assertNotEqual(cap_sh, nat_sh)
        # native FUNC symbols live in the native .text section
        for s in native_funcs(data, secs):
            self.assertEqual(secs[s.shndx].name, ".text._Z1kPKiPii")
        # capsule FUNC symbols mirror the same names but live in the
        # capmerc text section — a separate Mercury address space
        cap_funcs = [s for s in cap if (s.info & 0xF) == 2 and s.shndx]
        self.assertGreaterEqual(len(cap_funcs), 3)
        for s in cap_funcs:
            self.assertTrue(_is_merc_section(secs[s.shndx].name))


class TestRelocations(unittest.TestCase):
    def test_native_relocations_parsed(self):
        data = _call_test_data()
        secs = _sections(data)
        rel = native_relocations(data, secs)
        # only .rela.debug_frame carries native records here
        self.assertTrue(all(r.section == ".rela.debug_frame" for r in rel))
        self.assertTrue(all(r.type == 2 for r in rel))
        self.assertTrue(all(r.symbol == "_Z1kPKiPii" for r in rel))
        self.assertTrue(all(isinstance(r, NativeRelocation) for r in rel))
        self.assertTrue(all(not r.mercury for r in rel))

    def test_capsule_relocations_offsets_not_native(self):
        data = _call_test_data()
        secs = _sections(data)
        cap = capsule_relocations(data, secs)
        self.assertTrue(cap)
        self.assertTrue(all(isinstance(r, CapsuleRelocation) for r in cap))
        self.assertTrue(all(r.mercury for r in cap))
        self.assertTrue(all(r.section.startswith(".nv.merc.rela.") for r in cap))
        # a Mercury offset need not align to a native 16-byte instruction
        # boundary (0xcc is mid-instruction), so it can never be projected
        # onto a native instruction index.
        self.assertTrue(any(r.offset % 16 != 0 for r in cap))

    def test_mercury_segregation_total(self):
        data = _call_test_data()
        secs = _sections(data)
        from sassdbg.cubin import relocations
        rel = relocations(data, secs)
        native = [r for r in rel if not r.mercury]
        capsule = [r for r in rel if r.mercury]
        self.assertTrue(all(r.offset < 0x580 for r in native))
        self.assertTrue(capsule)

    def test_text_reloc_offsets_native_only(self):
        data = _call_test_data()
        secs = _sections(data)
        func = "_Z1kPKiPii"
        # native .rela.text.<func> is empty -> no offsets
        self.assertEqual(text_reloc_offsets(data, secs, func), [])
        # the mercury variant is opt-in and must NOT feed native checks:
        # its offsets are Mercury-space positions (one is not even a native
        # 16-byte instruction boundary), never native instruction indices.
        merc = text_reloc_offsets(data, secs, func, include_mercury=True)
        self.assertTrue(merc)
        self.assertTrue(any(o % 16 != 0 for o in merc))


class TestCallgraphPlaceholder(unittest.TestCase):
    def test_placeholder_identical_across_modules(self):
        """CUDA 13.1 -cubin .nv.callgraph is a fixed 32-byte placeholder:
        the same records appear in a 1-function and a 3-function cubin, so it
        cannot be a call-graph cross-check."""
        data = _call_test_data()
        secs = _sections(data)
        recs = callgraph_records(data, secs)
        self.assertEqual(len(recs), 4)
        self.assertEqual(recs[0], (0, 0xFFFFFFFF))
        # identical to the single-function m2_smoke image
        other_path = os.path.join(TESTS_DIR, "m2_smoke.cubin")
        with open(other_path, "rb") as f:
            other = f.read()
        self.assertEqual(callgraph_records(other, _sections(other)), recs)


class TestModuleTemplate(unittest.TestCase):
    def setUp(self):
        _ensure_cubin()
        self.mt = ModuleTemplate.from_cubin(CUBIN, root="_Z1kPKiPii")

    def test_one_island_three_functions(self):
        self.assertEqual(len(self.mt.islands), 1)
        isl = self.mt.islands[0]
        self.assertEqual(isl.name, ".text._Z1kPKiPii")
        self.assertEqual(isl.link_base, 0)
        self.assertEqual(isl.size, 0x580)
        self.assertEqual(isl.n_insts, 88)
        self.assertEqual(len(isl.functions), 3)

    def test_function_ranges(self):
        by = {f.name: f for f in self.mt.functions()}
        self.assertEqual(by["_Z1kPKiPii"].offset, 0x0)
        self.assertEqual(by["$_Z1kPKiPii$_Z3fibi"].offset, 0x140)
        self.assertEqual(by["$_Z1kPKiPii$_Z4leafii"].offset, 0x450)
        self.assertEqual(by["$_Z1kPKiPii$_Z3fibi"].n_insts, 784 // 16)
        self.assertEqual(by["$_Z1kPKiPii$_Z4leafii"].n_insts, 304 // 16)
        # instruction slice present
        self.assertEqual(len(by["$_Z1kPKiPii$_Z4leafii"].words), 19)

    def test_return_abi_decoded(self):
        by = {f.name: f for f in self.mt.functions()}
        # fib and leaf own their RETs
        for name, reg in [("$_Z1kPKiPii$_Z3fibi", 20),
                          ("$_Z1kPKiPii$_Z4leafii", 6)]:
            fn = by[name]
            self.assertEqual(fn.return_abi, ReturnABI.REL_REG, name)
            self.assertEqual(fn.return_reg, RegSpec("R", reg), name)
            # ptxas encodes RET.REL so pc_link+0x10+sImm*4 == 0: the REL
            # term is the image's program base delta, zero at link time.
            self.assertEqual(fn.return_rel_base, 0, name)
        # the kernel FUNC symbol spans the whole section but owns no RET
        # (its body exits); the nested fib/leaf RETs must not leak in.
        kern = by["_Z1kPKiPii"]
        self.assertEqual(kern.return_abi, ReturnABI.UNKNOWN)
        self.assertIsNone(kern.return_reg)

    def test_innermost_function_at(self):
        isl = self.mt.islands[0]
        # the kernel symbol spans the whole section but must not mask fib/leaf
        fn = isl.function_at(0x140)
        self.assertEqual(fn.name, "$_Z1kPKiPii$_Z3fibi")
        fn = isl.function_at(0x450)
        self.assertEqual(fn.name, "$_Z1kPKiPii$_Z4leafii")
        fn = isl.function_at(0x0)
        self.assertEqual(fn.name, "_Z1kPKiPii")

    def test_call_edges(self):
        edges = self.mt.edges
        self.assertEqual(len(edges), 3)
        got = {}
        for e in edges:
            got[(e.src.function, e.callee_name)] = e
        self.assertIn(("_Z1kPKiPii", "$_Z1kPKiPii$_Z4leafii"), got)
        self.assertIn(("_Z1kPKiPii", "$_Z1kPKiPii$_Z3fibi"), got)
        self.assertIn(("$_Z1kPKiPii$_Z3fibi", "$_Z1kPKiPii$_Z3fibi"), got)

    def test_edge_target_class_and_abi(self):
        e = [x for x in self.mt.edges
             if x.callee_name == "$_Z1kPKiPii$_Z4leafii"][0]
        self.assertEqual(e.target_class, TargetClass.INTERNAL_DIRECT)
        self.assertEqual(e.abi, ReturnABI.REL_REG)
        self.assertEqual(e.return_reg, RegSpec("R", 6))
        self.assertEqual(e.return_token, (RegSpec("R", 6), 0xb0))

    def test_edge_return_tokens_are_continuation_offsets(self):
        toks = {}
        for e in self.mt.edges:
            toks[(e.src.function, e.callee_name)] = e.return_token
        # k -> leaf: token = MOV R6, 0xb0 (continuation after CALL at 0xa0)
        self.assertEqual(toks[("_Z1kPKiPii", "$_Z1kPKiPii$_Z4leafii")],
                         (RegSpec("R", 6), 0xb0))
        # k -> fib: token = MOV R20, 0xf0 (continuation after CALL at 0xe0)
        self.assertEqual(toks[("_Z1kPKiPii", "$_Z1kPKiPii$_Z3fibi")],
                         (RegSpec("R", 20), 0xf0))
        # fib -> fib: token = MOV R20, 0x310 (fib's own continuation)
        self.assertEqual(toks[("$_Z1kPKiPii$_Z3fibi",
                               "$_Z1kPKiPii$_Z3fibi")],
                         (RegSpec("R", 20), 0x310))

    def test_edges_placement_and_stepping(self):
        for e in self.mt.edges:
            self.assertEqual(e.placement, Placement.PRIVATE_LAZY)
            self.assertEqual(e.stepping, Stepping.STEP_INTO)

    def test_code_loc(self):
        isl = self.mt.islands[0]
        # leaf's entry is island instruction 0x450//16
        loc = self.mt.edges[0].src
        self.assertEqual(loc.module, "call_test.cubin")
        self.assertEqual(loc.island, ".text._Z1kPKiPii")
        self.assertEqual(loc.function, "_Z1kPKiPii")
        # link VA <-> instruction mapping
        self.assertEqual(isl.link_va(0x450 // 16), 0x450)


class TestSCC(unittest.TestCase):
    def setUp(self):
        _ensure_cubin()
        self.mt = ModuleTemplate.from_cubin(CUBIN, root="_Z1kPKiPii")

    def test_fib_recursive_scc(self):
        comps = self.mt.scc()
        self.assertEqual(len(comps), 3)
        fib = self.mt.function("$_Z1kPKiPii$_Z3fibi").fid
        comp = next(c for c in comps if fib in c)
        self.assertEqual(comp, {fib})
        # the self-call makes the single-node SCC recursive
        self.assertTrue(recursive_scc(comp, self.mt.edges))

    def test_leaf_and_kernel_singleton(self):
        comps = self.mt.scc()
        names = {frozenset(c) for c in comps}
        leaf = self.mt.function("$_Z1kPKiPii$_Z4leafii").fid
        kern = self.mt.function("_Z1kPKiPii").fid
        self.assertIn(frozenset({leaf}), names)
        self.assertIn(frozenset({kern}), names)

    def test_mutual_recursion_one_unit(self):
        edges = [("a", "b"), ("b", "a"), ("a", "c")]
        comps = sccs(edges)
        unit = next(c for c in comps if "a" in c)
        self.assertEqual(unit, {"a", "b"})
        self.assertTrue(recursive_scc(unit, edges))

    def test_dag_no_cycles(self):
        edges = [("a", "b"), ("b", "c"), ("a", "d")]
        comps = sccs(edges)
        self.assertTrue(all(len(c) == 1 for c in comps))


class TestOwnershipPolicy(unittest.TestCase):
    def test_root_is_private_eager(self):
        p = OwnershipPolicy(root_functions=frozenset({"k"}))
        self.assertEqual(p.classify("k", TargetClass.INTERNAL_DIRECT),
                         Placement.PRIVATE_EAGER)

    def test_internal_default_private_lazy(self):
        p = OwnershipPolicy()
        self.assertEqual(p.classify("leaf", TargetClass.INTERNAL_DIRECT),
                         Placement.PRIVATE_LAZY)

    def test_external_runtime_opaque(self):
        p = OwnershipPolicy()
        place = p.classify("", TargetClass.EXTERNAL_RUNTIME, in_module=False)
        self.assertEqual(place, Placement.SHARED_OPAQUE)
        self.assertEqual(p.stepping_for(place), Stepping.STEP_OVER)

    def test_indirect_unknown(self):
        p = OwnershipPolicy()
        self.assertEqual(p.classify("", TargetClass.INDIRECT_UNKNOWN,
                                    in_module=False),
                         Placement.INDIRECT_UNKNOWN)
        self.assertEqual(p.classify("f", TargetClass.INDIRECT_UNKNOWN),
                         Placement.INDIRECT_UNKNOWN)

    def test_include_exclude_regexes(self):
        p = OwnershipPolicy(include=r"(^|\.)(leaf|fib)$",
                            exclude=r"^syscall_")
        self.assertTrue(p.included("leaf"))
        self.assertFalse(p.included("syscall_trampoline_vprintf"))
        self.assertFalse(p.included("vfprintf_internal"))
        # include does not override exclude
        p2 = OwnershipPolicy(include=r"vprintf", exclude=r"trampoline")
        self.assertFalse(p2.included("syscall_trampoline_vprintf"))

    def test_step_into_private_over_opaque(self):
        p = OwnershipPolicy()
        self.assertEqual(p.stepping_for(Placement.PRIVATE_LAZY),
                         Stepping.STEP_INTO)
        self.assertEqual(p.stepping_for(Placement.PRIVATE_EAGER),
                         Stepping.STEP_INTO)
        self.assertEqual(p.stepping_for(Placement.SHARED_OPAQUE),
                         Stepping.STEP_OVER)


class TestSingleFunctionCubin(unittest.TestCase):
    def test_m2_smoke_no_edges(self):
        path = os.path.join(TESTS_DIR, "m2_smoke.cubin")
        if not os.path.exists(path):
            self.skipTest("m2_smoke.cubin absent")
        mt = ModuleTemplate.from_cubin(path)
        self.assertEqual(len(mt.islands), 1)
        self.assertEqual(len(mt.functions()), 1)
        self.assertEqual(mt.edges, [])


# ---------------------------------------------------------------------------
# M12a acceptance fixtures (synthetic ELF cubins; CPU-only)
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from elf_fixture import build_elf  # noqa: E402
from assembler import assemble_flat  # noqa: E402
from sassdbg.cubin import (native_relocations, native_symbols,  # noqa: E402
                           capsule_relocations, text_reloc_offsets,
                           _sections)


def _w(sass):
    return assemble_flat(sass)[0]


def _call_rel(target_off, call_off):
    """CALL.REL.NOINC word at island offset `call_off` targeting `target_off`.

    The dialect's numeric CALL.REL operand is the byte offset relative to
    PC+0x10 (not the resolved target), so encode that offset."""
    return _w(f"CALL.REL.NOINC 0x{target_off - call_off - 0x10:x};"
              f"[7:7:{{}}:6:0]")


def _gpr_reg_call(sass, reg):
    lo, hi = assemble_flat(sass)[0]
    return (lo & ~0x800) | 0x200 | (reg << 24), hi


def _ur_call(sass, ura):
    lo, hi = assemble_flat(sass)[0]
    return (lo & ~0xFF000000) | (ura << 24), hi | (1 << 27)


def _tmp_cubin(data):
    d = tempfile.mkdtemp(prefix="m12a_")
    path = os.path.join(d, "m.cubin")
    with open(path, "wb") as f:
        f.write(data)
    return path


class TestRelocAssociation(unittest.TestCase):
    """Acceptance item 1: non-empty native .rela.text.* attaches through
    sh_info, not name concatenation."""

    def test_island_relocs_via_sh_info(self):
        words = [_w("MOV32I R0, 0x1;[7:7:{}:5:1]"),
                 _w("NOP;[7:7:{}:5:1]")]
        data = build_elf(
            texts=[(".text.k", 0, words, [("k", 0, 32, 1)])],
            rela=[(".rela.text.k", 0, [(0x10, 1, 1, 0x40),
                                       (0x00, 2, 1, 0x08)])])
        path = _tmp_cubin(data)
        mt = ModuleTemplate.from_cubin(path)
        isl = mt.islands[0]
        self.assertEqual(len(isl.native_relocs), 2)
        self.assertEqual([r.offset for r in isl.native_relocs], [0x10, 0])
        # a function's relocation set is the records in its range
        fn = isl.functions[0]
        self.assertEqual([r.offset for r in fn.relocations],
                         [0x10, 0])
        self.assertTrue(all(r.section == ".rela.text.k"
                            for r in isl.native_relocs))

    def test_name_concatenation_bug_absent(self):
        # the old f".rela.{sec.name}" produced .rela..text.k and matched none
        data = build_elf(
            texts=[(".text.k", 0, [_w("NOP;[7:7:{}:5:1]")],
                    [("k", 0, 16, 1)])],
            rela=[(".rela.text.k", 0, [(0x0, 1, 1, 0)])])
        path = _tmp_cubin(data)
        self.assertEqual(len(ModuleTemplate.from_cubin(path)
                             .islands[0].native_relocs), 1)


class TestSHT_REL(unittest.TestCase):
    """Acceptance item 2: one- and multi-entry SHT_REL parse to exactly one
    record each, with the implicit addend recovered from the target word."""

    def test_single_rel_entry(self):
        words = [0x0123456789ABCDEF, 0xFEDCBA9876543210]
        data = build_elf(
            texts=[(".text.k", 0, [words], [("k", 0, 16, 1)])],
            rel=[(".rel.text.k", 0, [(0x0, 1, 1)])])
        secs = _sections(data)
        rel = native_relocations(data, secs)
        self.assertEqual(len(rel), 1)
        self.assertTrue(rel[0].addend_implicit)
        # implicit addend = the 64-bit word at the target offset
        self.assertEqual(rel[0].addend, 0x0123456789ABCDEF)
        self.assertEqual(rel[0].target_section, 4)

    def test_multi_rel_entries(self):
        words = [(0xAAAAAAAAAAAAAAAA, 0), (0xBBBBBBBBBBBBBBBB, 0)]
        data = build_elf(
            texts=[(".text.k", 0, words, [("k", 0, 32, 1)])],
            rel=[(".rel.text.k", 0, [(0x0, 1, 1), (0x10, 1, 1)])])
        secs = _sections(data)
        rel = native_relocations(data, secs)
        self.assertEqual(len(rel), 2)
        self.assertEqual([r.offset for r in rel], [0x0, 0x10])
        self.assertEqual(rel[0].addend, 0xAAAAAAAAAAAAAAAA)
        self.assertEqual(rel[1].addend, 0xBBBBBBBBBBBBBBBB)


class TestMultiIsland(unittest.TestCase):
    """Acceptance item 3: overlapping zero sh_addr and non-zero link bases."""

    def test_cross_island_unique_base(self):
        # island B at a distinct link base; A's CALL.REL jumps to B
        fb = [_w("NOP;[7:7:{}:5:1]") for _ in range(4)]
        fa = [_call_rel(0x100020, 0x0)]
        data = build_elf(
            texts=[(".text.a", 0, fa, [("fa", 0, 16, 0)]),
                   (".text.b", 0x100000, fb, [("fb", 0x20, 16, 0)])])
        path = _tmp_cubin(data)
        mt = ModuleTemplate.from_cubin(path)
        self.assertEqual(len(mt.islands), 2)
        edges = [e for e in mt.edges if e.src.function == "fa"]
        self.assertEqual(len(edges), 1)
        e = edges[0]
        self.assertEqual(e.target_class, TargetClass.INTERNAL_DIRECT)
        self.assertEqual(e.callee_name, "fb")
        # destination instruction index is island-relative (not 65605)
        self.assertEqual(e.dst.instruction, 2)

    def test_same_island_first(self):
        # a CALL inside island B must resolve within B even though the VA
        # also falls inside island A's range (both sh_addr == 0)
        a = [_w("NOP;[7:7:{}:5:1]") for _ in range(3)]   # [0, 0x30)
        b = [_call_rel(0x20, 0x0)] + [_w("NOP;[7:7:{}:5:1]")
                                      for _ in range(2)]  # [0, 0x30)
        data = build_elf(
            texts=[(".text.a", 0, a, [("fa", 0, 48, 0)]),
                   (".text.b", 0, b, [("fb", 0, 48, 0)])])
        path = _tmp_cubin(data)
        mt = ModuleTemplate.from_cubin(path)
        e = [x for x in mt.edges if x.src.function == "fb"][0]
        self.assertEqual(e.target_class, TargetClass.INTERNAL_DIRECT)
        self.assertEqual(e.callee_name, "fb")      # resolved in B, not fa

    def test_ambiguous_cross_island_fails_closed(self):
        # three islands all at sh_addr==0 with overlapping ranges: a target
        # outside the source island is ambiguous -> EXTERNAL_RUNTIME
        a = [_w("NOP;[7:7:{}:5:1]")]
        b = [_w("NOP;[7:7:{}:5:1]") for _ in range(8)]    # [0, 0x80)
        c = [_w("NOP;[7:7:{}:5:1]") for _ in range(6)]    # [0, 0x60)
        src = [_call_rel(0x50, 0x0)]   # 0x50 lies in B[0,0x80) AND C[0,0x60)
        data = build_elf(
            texts=[(".text.a", 0, a, [("fa", 0, 16, 0)]),
                   (".text.b", 0, b, [("fb", 0, 128, 0)]),
                   (".text.c", 0, c, [("fc", 0, 96, 0)]),
                   (".text.src", 0, src, [("fsrc", 0, 16, 0)])])
        path = _tmp_cubin(data)
        mt = ModuleTemplate.from_cubin(path)
        e = [x for x in mt.edges if x.src.function == "fsrc"][0]
        self.assertEqual(e.target_class, TargetClass.EXTERNAL_RUNTIME)
        self.assertIsNone(e.dst)
        self.assertEqual(e.placement, Placement.SHARED_OPAQUE)


class TestCallRetVariants(unittest.TestCase):
    """Acceptance item 4: ABS/REL, GPR and UR CALL/RET variants decode with
    the opcode-specific layout; unsupported forms fail closed."""

    def test_abs_imm_and_register_targets(self):
        body = [_w("NOP;[7:7:{}:5:1]")]
        # caller: CALL.ABS imm -> callee, CALL.REL R4, CALL.ABS UR4
        abs_imm = _w("CALL.ABS.NOINC 0x30;[7:7:{}:6:0]")  # -> callee at 0x30
        rel_reg = _gpr_reg_call("CALL.REL.NOINC 0x0;[7:7:{}:6:0]", 4)
        abs_ur = _ur_call("CALL.ABS.NOINC 0x0;[7:7:{}:6:0]", 4)
        caller = [abs_imm, rel_reg, abs_ur]
        data = build_elf(
            texts=[(".text.k", 0, caller + body,
                    [("k", 0, len(caller) * 16, 1),
                     ("callee", 0x30, 16, 0)])])
        path = _tmp_cubin(data)
        mt = ModuleTemplate.from_cubin(path)
        by_inst = {e.src.instruction: e for e in mt.edges}
        self.assertEqual(by_inst[0].target_class, TargetClass.INTERNAL_DIRECT)
        self.assertEqual(by_inst[0].callee_name, "callee")
        self.assertEqual(by_inst[1].target_class, TargetClass.INDIRECT_UNKNOWN)
        self.assertEqual(by_inst[1].return_reg, None)  # caller not callee
        self.assertEqual(by_inst[2].target_class, TargetClass.INDIRECT_UNKNOWN)

    def test_reg_and_ur_return_abis(self):
        # a callee with RET.REL UR4 reports a uniform-register pair, not a GPR
        gpr_ret = _w("RET.REL.NODEC {R10,R11}, 0x0;[7:7:{}:6:0]")
        ur_ret = _w("RET.REL.NODEC {UR4,UR5}, 0x0;[7:7:{}:6:0]")
        data = build_elf(
            texts=[(".text.k", 0, [gpr_ret, ur_ret],
                    [("gprf", 0, 16, 0), ("urf", 0x10, 16, 0)])])
        path = _tmp_cubin(data)
        mt = ModuleTemplate.from_cubin(path)
        by = {f.name: f for f in mt.functions()}
        self.assertEqual(by["gprf"].return_abi, ReturnABI.REL_REG)
        self.assertEqual(by["gprf"].return_reg, RegSpec("R", 10))
        self.assertEqual(by["urf"].return_abi, ReturnABI.REL_REG)
        self.assertEqual(by["urf"].return_reg, RegSpec("UR", 4))

    def test_abs_return_abi(self):
        w = _w("RET.ABS.NODEC {R6,R7}, 0x0;[7:7:{}:6:0]")
        data = build_elf(
            texts=[(".text.k", 0, [w], [("f", 0, 16, 0)])])
        path = _tmp_cubin(data)
        fn = ModuleTemplate.from_cubin(path).functions()[0]
        self.assertEqual(fn.return_abi, ReturnABI.ABS_REG)
        self.assertEqual(fn.return_reg, RegSpec("R", 6))

    def test_unknown_call_opcode_fails_closed(self):
        w = _w("NOP;[7:7:{}:5:1]")
        # corrupt the opcode into an unrecognized CALL-like value
        bad = (w[0] | 0x400, w[1])
        data = build_elf(
            texts=[(".text.k", 0, [bad], [("k", 0, 16, 1)])])
        path = _tmp_cubin(data)
        mt = ModuleTemplate.from_cubin(path)
        self.assertEqual(mt.edges, [])


class TestMultiReturn(unittest.TestCase):
    """Acceptance item 6: multiple returns and conflicting protocols."""

    def _build(self, words, name):
        data = build_elf(
            texts=[(".text.k", 0, words,
                    [(name, 0, len(words) * 16, 0)])])
        return ModuleTemplate.from_cubin(_tmp_cubin(data)).functions()[0]

    def test_conflicting_returns_unknown(self):
        rel = _w("RET.REL.NODEC {R20,R21}, 0x0;[7:7:{}:6:0]")
        abs_ = _w("RET.ABS.NODEC {R10,R11}, 0x0;[7:7:{}:6:0]")
        fn = self._build([rel, abs_], "f")
        self.assertEqual(fn.return_abi, ReturnABI.UNKNOWN)
        self.assertIsNone(fn.return_reg)

    def test_consistent_returns_kept(self):
        rel1 = _w("RET.REL.NODEC {R20,R21}, 0x0;[7:7:{}:6:0]")
        rel2 = _w("RET.REL.NODEC {R20,R21}, 0x0;[7:7:{}:6:0]")
        fn = self._build([rel1, rel2], "f")
        self.assertEqual(fn.return_abi, ReturnABI.REL_REG)
        self.assertEqual(fn.return_reg, RegSpec("R", 20))


class TestReturnTokenSafety(unittest.TestCase):
    """Acceptance item 7: token discovery must fail closed on stale,
    predicated, branched, clobbered, and missing-high materializations."""

    LEAF = [_w("NOP;[7:7:{}:5:1]"),
            _w("RET.REL.NODEC {R20,R21}, 0x0;[7:7:{}:6:0]")]

    def _build(self, caller_words, caller_name):
        # caller then leaf; each caller is its own function symbol
        caller_words = list(caller_words)
        leaf_off = len(caller_words) * 16
        words = caller_words + self.LEAF
        data = build_elf(
            texts=[(".text.k", 0, words,
                    [(caller_name, 0, len(caller_words) * 16, 0),
                     ("leaf", leaf_off, len(self.LEAF) * 16, 0)])])
        mt = ModuleTemplate.from_cubin(_tmp_cubin(data))
        return [e for e in mt.edges if e.src.function == caller_name][0]

    def _call(self, caller_words):
        return _call_rel(len(caller_words) * 16, len(caller_words) * 16 - 16)

    def test_ok_split_pair(self):
        e = self._build([
            _w("MOV32I R20, 0x30;[7:7:{}:5:1]"),
            _w("MOV32I R21, 0x0;[7:7:{}:5:1]"),
            self._call([0, 0, 0]),
        ], "ok")
        self.assertEqual(e.return_token, (RegSpec("R", 20), 0x30))

    def test_predicated_token_fails_closed(self):
        e = self._build([
            _w("@P0 MOV32I R20, 0x30;[7:7:{}:5:1]"),
            _w("MOV32I R21, 0x0;[7:7:{}:5:1]"),
            self._call([0, 0, 0]),
        ], "pred")
        self.assertIsNone(e.return_token)

    def test_branched_token_fails_closed(self):
        # a BRA between the token def and the call: the linear path is not
        # the only path, so the MOV cannot be proven to reach the call
        e = self._build([
            _w("MOV32I R20, 0x30;[7:7:{}:5:1]"),
            _w("MOV32I R21, 0x0;[7:7:{}:5:1]"),
            _w("BRA 0x10;[7:7:{}:6:0]"),          # -> next instruction
            self._call([0, 0, 0, 0]),
        ], "branch")
        self.assertIsNone(e.return_token)

    def test_clobbered_token_fails_closed(self):
        e = self._build([
            _w("MOV32I R20, 0x30;[7:7:{}:5:1]"),
            _w("MOV32I R21, 0x0;[7:7:{}:5:1]"),
            _w("IADD3 R20, R20, 0x1, RZ;[7:7:{}:5:1]"),
            self._call([0, 0, 0, 0]),
        ], "clobber")
        self.assertIsNone(e.return_token)

    def test_missing_high_half_fails_closed(self):
        e = self._build([
            _w("MOV32I R20, 0x30;[7:7:{}:5:1]"),
            self._call([0, 0]),
        ], "nohigh")
        self.assertIsNone(e.return_token)


class TestSccIsolationAndNames(unittest.TestCase):
    """Acceptance item 8: isolated functions appear in SCC; duplicate local
    names collide only for name lookup, not for fids."""

    def test_isolated_functions_in_scc(self):
        nop = [_w("NOP;[7:7:{}:5:1]")]
        data = build_elf(
            texts=[(".text.a", 0, nop, [("fa", 0, 16, 0)]),
                   (".text.b", 0, nop, [("fb", 0, 16, 0)])])
        mt = ModuleTemplate.from_cubin(_tmp_cubin(data))
        self.assertEqual(mt.edges, [])
        comps = mt.scc()
        self.assertEqual(len(comps), 2)
        names = {next(iter(c)) for c in comps}
        self.assertIn(".text.a:0x0", names)
        self.assertIn(".text.b:0x0", names)

    def test_duplicate_local_names(self):
        nop = [_w("NOP;[7:7:{}:5:1]")]
        data = build_elf(
            texts=[(".text.a", 0, nop, [("helper", 0, 16, 0)]),
                   (".text.b", 0, nop, [("helper", 0, 16, 0)])])
        mt = ModuleTemplate.from_cubin(_tmp_cubin(data))
        # name lookup is ambiguous -> None, but fids are distinct
        self.assertIsNone(mt.function("helper"))
        fids = {f.fid for f in mt.functions()}
        self.assertEqual(len(fids), 2)
        self.assertEqual(len(mt.function_by_fid(".text.a:0x0").words), 1)


class TestZeroSizeSymbol(unittest.TestCase):
    """Acceptance item 9: zero-sized FUNC symbols infer their extent from the
    next symbol rather than consuming the rest of the section."""

    def test_extent_inferred(self):
        nop = _w("NOP;[7:7:{}:5:1]")
        words = [nop] * 4
        data = build_elf(
            texts=[(".text.k", 0, words,
                    [("z", 0x0, 0, 0),        # zero size at offset 0
                     ("r", 0x10, 0x30, 0)])])  # real function follows
        path = _tmp_cubin(data)
        mt = ModuleTemplate.from_cubin(path)
        z = mt.function("z")
        self.assertEqual(z.size, 0x10)       # inferred to next symbol
        self.assertEqual(z.n_insts, 1)
        r = mt.function("r")
        self.assertEqual(r.size, 0x30)


class TestJustMyCode(unittest.TestCase):
    """Acceptance item 10: observable just_my_code=True/False behavior."""

    def test_jmc_filters_internal_functions(self):
        p = OwnershipPolicy(just_my_code=True, exclude=r"^helper$")
        self.assertEqual(p.classify("helper", TargetClass.INTERNAL_DIRECT),
                         Placement.SHARED_OPAQUE)
        self.assertEqual(p.stepping_for(Placement.SHARED_OPAQUE),
                         Stepping.STEP_OVER)

    def test_jmc_off_ignores_filter(self):
        p = OwnershipPolicy(just_my_code=False, exclude=r"^helper$")
        self.assertEqual(p.classify("helper", TargetClass.INTERNAL_DIRECT),
                         Placement.PRIVATE_LAZY)
        self.assertEqual(p.stepping_for(Placement.PRIVATE_LAZY),
                         Stepping.STEP_INTO)

    def test_external_stays_opaque_regardless(self):
        for jmc in (True, False):
            p = OwnershipPolicy(just_my_code=jmc)
            self.assertEqual(
                p.classify("", TargetClass.EXTERNAL_RUNTIME,
                           in_module=False), Placement.SHARED_OPAQUE)


if __name__ == "__main__":
    unittest.main()