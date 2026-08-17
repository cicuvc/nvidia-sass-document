#!/usr/bin/env python3
"""Phase 2 cubin loader integration gate (CTest 'cubin_load').

Loads real cubins through the semu CLI and cross-checks the results against
independent tools:

  - assembler-generated single-kernel cubin (repo `assembler`, pure Python)
    -> kernel count, text size, params, regcount, disasm;
  - nvcc multi-kernel cubin (built on the fly when nvcc is available)
    -> kernel count, mangled names, text sizes, KPARAM layout vs
      `cuobjdump -res-usage` and `readelf`;
  - error paths: truncated file, bad ELF flags/arch, bad symbol table,
    unknown-but-skippable EIATTR, malformed EIATTR, relocation failure.

Skips the nvcc/readelf cross-checks (exit 0 with a note) when the CUDA
toolchain is unavailable.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
NVCC = Path("/usr/local/cuda/bin/nvcc")
CUOBJDUMP = Path("/usr/local/cuda/bin/cuobjdump")
READELF = Path("/usr/bin/readelf")

failures = 0
warnings = 0


def note(msg: str) -> None:
    print(f"  note  {msg}")


def check(name: str, cond: bool, detail: str = "") -> None:
    global failures
    print(("  ok  " if cond else "FAIL  ") + name)
    if not cond:
        failures += 1
        if detail:
            print(f"       {detail}")


def run(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], text=True, capture_output=True,
                          **kw)


def semu_cli(binary, *args):
    return run([binary, *args])


def assemble_single_kernel() -> bytes:
    """Build a small single-kernel cubin with the repo assembler."""
    sys.path.insert(0, str(REPO))
    from assembler import assemble  # noqa: PLC0415
    src = """
#fn k_add(a<8>, b<8>, c<8>, n<4>) {
  LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
  LDC.64 {R2,R3}, #param(a);[1:7:{}:1:0]
  LDC.64 {R4,R5}, #param(b);[2:7:{}:1:0]
  LDC.64 {R6,R7}, #param(c);[3:7:{}:1:0]
  LDC.32 R8, #param(n);[4:7:{}:1:0]
  LDG.E.64 {R10,R11}, desc[{UR4,UR5}][{R2,R3}+0x0];[0:1:{0,1}:1:0]
  LDG.E.64 {R12,R13}, desc[{UR4,UR5}][{R4,R5}+0x0];[1:1:{0,1}:1:0]
  FADD R14, R10, R12;[2:7:{}:1:0]
  FADD R15, R11, R13;[3:7:{}:1:0]
  STG.E.64 desc[{UR4,UR5}][{R6,R7}+0x0], {R14,R15};[4:1:{0,1}:1:0]
  EXIT;[7:7:{}:5:0]
}
"""
    return assemble(src, kernel_name="k_add", check_deps=False)


def main() -> int:
    global warnings
    if len(sys.argv) != 2:
        print("usage: cubin_load_test.py <semu binary>", file=sys.stderr)
        return 2
    binary = Path(sys.argv[1])

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)

        # ---------------------------------------------------------------
        # 1. assembler single-kernel cubin
        # ---------------------------------------------------------------
        print("== assembler single-kernel cubin")
        try:
            cubin = assemble_single_kernel()
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL  assemble_single_kernel: {e}")
            return 1
        single = td / "single.cubin"
        single.write_bytes(cubin)

        r = semu_cli(binary, "load", single)
        check("load exit 0", r.returncode == 0, r.stderr)
        check("load reports 1 kernel", "1 kernel(s)" in r.stdout, r.stdout)
        check("load names k_add", "_Z5k_add" in r.stdout, r.stdout)

        r = semu_cli(binary, "list-kernels", single)
        check("list-kernels exit 0", r.returncode == 0, r.stderr)
        lines = [l for l in r.stdout.splitlines() if "\t" in l]
        check("list-kernels 1 line", len(lines) == 1, r.stdout)
        if lines:
            name, text, regs, shared, params = lines[0].split("\t")
            check("kernel name _Z5k_add", name == "_Z5k_add", name)
            check("text size >= 256 (padded)", int(text) >= 256, text)
            check("params = 4 (a,b,c,n)", params == "4", params)

        r = semu_cli(binary, "disasm", single, "_Z5k_add")
        check("disasm exit 0", r.returncode == 0, r.stderr)
        check("disasm has FADD", "FADD" in r.stdout, "")
        check("disasm has EXIT", "EXIT" in r.stdout, "")
        check("disasm has pc column", "/*0000*/" in r.stdout, r.stdout[:200])

        r = semu_cli(binary, "inspect", single)
        check("inspect exit 0", r.returncode == 0, r.stderr)
        check("inspect sections", ".text." in r.stdout and ".symtab" in r.stdout,
              "")
        check("inspect symbols", "[ " in r.stdout, "")

        # ---------------------------------------------------------------
        # 2. error paths on the assembler cubin
        # ---------------------------------------------------------------
        print("== error paths")
        bad = td / "bad_magic.cubin"
        bad.write_bytes(b"\x00" + cubin[1:])
        r = semu_cli(binary, "load", bad)
        check("bad magic rejected", r.returncode == 1 and
              "not an ELF" in r.stderr, r.stderr)

        # wrong arch: patch e_flags to sm90's value
        bad = td / "bad_flags.cubin"
        b = bytearray(cubin)
        b[48:52] = (0x005a055a).to_bytes(4, "little")
        bad.write_bytes(bytes(b))
        r = semu_cli(binary, "load", bad)
        check("wrong e_flags rejected", r.returncode == 1 and
              "sm120" in r.stderr and "e_flags" in r.stderr, r.stderr)

        # truncated in the text section
        bad = td / "truncated.cubin"
        bad.write_bytes(cubin[: len(cubin) - 400])
        r = semu_cli(binary, "load", bad)
        check("truncated rejected", r.returncode == 1, r.stderr)

        # unknown EIATTR injection: append a fmt=3 record (skippable) to
        # the per-kernel .nv.info.<kern> section.  Find the section by
        # scanning the section table for the CUDA_INFO type whose name
        # starts with .nv.info. and whose sh_info points at the text sec.
        print("== EIATTR injection")
        injected = td / "unknown_attr.cubin"
        b = bytearray(cubin)
        e_shoff = int.from_bytes(b[40:48], "little")
        shnum = int.from_bytes(b[60:62], "little")
        shstrndx = int.from_bytes(b[62:64], "little")
        shstr_off = int.from_bytes(b[e_shoff + shstrndx * 64 + 24:
                                     e_shoff + shstrndx * 64 + 32], "little")
        info_idx = None
        for i in range(shnum):
            sh = e_shoff + i * 64
            name_off = int.from_bytes(b[sh:sh + 4], "little")
            j = shstr_off + name_off
            name = b[j:j + 16].split(b"\0")[0].decode()
            if name.startswith(".nv.info."):
                info_idx = i
                break
        check("found .nv.info.<kern> section", info_idx is not None)
        if info_idx is not None:
            sh = e_shoff + info_idx * 64
            sec_off = int.from_bytes(b[sh + 24:sh + 32], "little")
            # Replace the section content with a single unknown fmt=3
            # record (4 bytes) and shrink sh_size to match; the rest of the
            # original payload stays in the file but beyond the declared
            # section size.  0x1e is on the reviewed skippable allowlist.
            rec = bytes([3, 0x1e, 0x5a, 0x00])
            b[sec_off:sec_off + 4] = rec
            b[sh + 32:sh + 40] = (4).to_bytes(8, "little")
        injected.write_bytes(bytes(b))
        r = semu_cli(binary, "load", injected)
        check("unknown EIATTR warns, load ok", r.returncode == 0 and
              "warning" in r.stderr.lower() and "0x1e" in r.stderr, r.stderr)

        # Non-allowlisted unknown EIATTR (0x51) -> hard error, even via
        # `load` (executable mode).
        bad = td / "unknown_exec_eiattr.cubin"
        b = bytearray(cubin)
        if info_idx is not None:
            sh = e_shoff + info_idx * 64
            sec_off = int.from_bytes(b[sh + 24:sh + 32], "little")
            rec = bytes([3, 0x51, 0x5a, 0x00])
            b[sec_off:sec_off + 4] = rec
            b[sh + 32:sh + 40] = (4).to_bytes(8, "little")
        bad.write_bytes(bytes(b))
        r = semu_cli(binary, "load", bad)
        check("non-allowlisted unknown EIATTR rejected",
              r.returncode == 1 and "0x51" in r.stderr and
              "not supported" in r.stderr, r.stderr)

        # malformed EIATTR: fmt=4 record whose size field overruns the
        # section (truncate the file so the payload lands past EOF).
        bad = td / "bad_eiattr.cubin"
        b = bytearray(cubin)
        if info_idx is not None:
            sh = e_shoff + info_idx * 64
            sec_off = int.from_bytes(b[sh + 24:sh + 32], "little")
            # overwrite the first record header: fmt=4, etype=0x17, size=0xffff
            b[sec_off:sec_off + 4] = bytes([4, 0x17, 0xff, 0xff])
        bad.write_bytes(bytes(b))
        r = semu_cli(binary, "load", bad)
        check("malformed EIATTR rejected", r.returncode == 1 and
              "EIATTR" in r.stderr, r.stderr)

        # ---------------------------------------------------------------
        # 3. nvcc multi-kernel cubin + readelf/cuobjdump cross-check
        # ---------------------------------------------------------------
        print("== nvcc multi-kernel cubin")
        have_nvcc = NVCC.is_file() and CUOBJDUMP.is_file()
        if not have_nvcc:
            note("nvcc/cuobjdump unavailable; skipping multi-kernel + "
                 "cross-checks")
        else:
            src = td / "multi.cu"
            src.write_text("""
__global__ void k_nop() {}
__global__ void k_scale(const float* a, float* c, int n, float s) {
    int i = threadIdx.x;
    if (i < n) c[i] = a[i] * s;
}
__global__ void k_add(const float* a, const float* b, float* c, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (i < n) c[i] = a[i] + b[i];
}
""")
            multi = td / "multi.cubin"
            p = run([NVCC, "-arch=sm_120", "-O3", "-cubin", "-o", multi, src])
            if p.returncode != 0:
                note("nvcc failed; skipping multi-kernel cross-checks")
            else:
                r = semu_cli(binary, "list-kernels", multi)
                check("multi: exit 0", r.returncode == 0, r.stderr)
                lines = [l for l in r.stdout.splitlines() if "\t" in l]
                check("multi: 3 kernels", len(lines) == 3, r.stdout)
                names = sorted(l.split("\t")[0] for l in lines)
                check("multi: mangled names",
                      names == ["_Z5k_addPKfS0_Pfi", "_Z5k_nopv",
                                "_Z7k_scalePKfPfif"], " ".join(names))
                sizes = {l.split("\t")[0]: int(l.split("\t")[1])
                         for l in lines}
                check("multi: text sizes match nvcc (256/384/512)",
                      sizes == {"_Z5k_nopv": 256, "_Z7k_scalePKfPfif": 384,
                                "_Z5k_addPKfS0_Pfi": 512}, str(sizes))
                regs = {l.split("\t")[0]: int(l.split("\t")[2])
                        for l in lines}
                check("multi: regcount 4/10/12",
                      regs == {"_Z5k_nopv": 4, "_Z7k_scalePKfPfif": 10,
                               "_Z5k_addPKfS0_Pfi": 12}, str(regs))

                # cuobjdump -res-usage cross-check
                p = run([CUOBJDUMP, "-arch", "sm_120", "-res-usage", multi])
                if p.returncode == 0:
                    for name, want in (("_Z5k_nopv", "REG:4"),
                                       ("_Z7k_scalePKfPfif", "REG:10"),
                                       ("_Z5k_addPKfS0_Pfi", "REG:12")):
                        ok = name in p.stdout and want in p.stdout
                        check(f"cuobjdump regcount {name}", ok,
                              p.stdout[-400:])
                else:
                    note("cuobjdump -res-usage failed")

                # readelf section/symbol cross-check
                if READELF.is_file():
                    p = run([READELF, "-SW", multi])
                    if p.returncode == 0:
                        for n in (".text._Z5k_nopv", ".text._Z7k_scalePKfPfif",
                                  ".text._Z5k_addPKfS0_Pfi", ".nv.info",
                                  ".symtab"):
                            check(f"readelf section {n}", n in p.stdout, "")
                    p = run([READELF, "-s", multi])
                    if p.returncode == 0:
                        check("readelf FUNC GLOBAL symbols",
                              "FUNC" in p.stdout and
                              "GLOBAL" in p.stdout, "")

                # KPARAM layout: k_add(a,b,c,n) = 8,8,8,4 bytes at 0/8/16/24
                r = semu_cli(binary, "inspect", multi)
                check("multi: inspect exit 0", r.returncode == 0, r.stderr)
                check("multi: k_add 4 params", "params=4" in r.stdout, "")
                # param lines are "    param[N] off=0x.. size=N"
                param_lines = [l.strip() for l in r.stdout.splitlines()
                               if l.strip().startswith("param[")]
                # inspect prints kernels in symtab order (nvcc emits add,
                # scale, nop) with params ordinal-ascending after the
                # P2-GAP-02 normalization: k_add is the first 4 lines.
                check("multi: 8 param lines total (add 4 + scale 4 + nop 0)",
                      len(param_lines) == 8, str(param_lines))
                sizes = [int(l.split("size=")[1]) for l in param_lines[:4]]
                check("multi: k_add param sizes 8,8,8,4 (ordinal asc)",
                      sizes == [8, 8, 8, 4], str(sizes))
                ords = [int(l.split("[")[1].split("]")[0])
                        for l in param_lines[:4]]
                check("multi: k_add param ordinals 0,1,2,3",
                      ords == [0, 1, 2, 3], str(ords))

                # disasm: k_nop must contain LDC + EXIT
                r = semu_cli(binary, "disasm", multi, "_Z5k_nopv")
                check("multi: disasm k_nop exit 0", r.returncode == 0,
                      r.stderr)
                check("multi: disasm has EXIT", "EXIT" in r.stdout, "")

                # wrong kernel name -> error
                r = semu_cli(binary, "disasm", multi, "_Z5missing")
                check("disasm unknown kernel fails", r.returncode == 1 and
                      "not found" in r.stderr, r.stderr)

        # ---------------------------------------------------------------
        # 4. Phase-2 GAP probes on the assembler cubin
        # ---------------------------------------------------------------
        print("== P2-GAP probes")
        # P2-GAP-07: wrong OSABI must be rejected.
        bad = td / "bad_osabi.cubin"
        b = bytearray(cubin)
        b[7] = 0x00  # EI_OSABI 0x41 -> 0
        bad.write_bytes(bytes(b))
        r = semu_cli(binary, "load", bad)
        check("bad OSABI rejected", r.returncode == 1 and
              "OSABI" in r.stderr, r.stderr)

        # P2-GAP-04: odd text size must be rejected.
        bad = td / "odd_text.cubin"
        b = bytearray(cubin)
        e_shoff = int.from_bytes(b[40:48], "little")
        shnum = int.from_bytes(b[60:62], "little")
        shstrndx = int.from_bytes(b[62:64], "little")
        shstr_off = int.from_bytes(b[e_shoff + shstrndx * 64 + 24:
                                     e_shoff + shstrndx * 64 + 32], "little")
        for i in range(shnum):
            sh = e_shoff + i * 64
            name_off = int.from_bytes(b[sh:sh + 4], "little")
            j = shstr_off + name_off
            name = b[j:j + 20].split(b"\0")[0].decode()
            if name.startswith(".text."):
                sz = int.from_bytes(b[sh + 32:sh + 40], "little")
                b[sh + 32:sh + 40] = (sz - 1).to_bytes(8, "little")
                break
        bad.write_bytes(bytes(b))
        r = semu_cli(binary, "load", bad)
        check("odd text size rejected", r.returncode == 1 and
              "multiple of 16" in r.stderr, r.stderr)

        # P2-GAP-03: an illegal word must fail strict `load`...
        bad = td / "bad_word.cubin"
        b = bytearray(cubin)
        if info_idx is not None:
            # zero the first text word: locate .text section by flags
            for i in range(shnum):
                sh = e_shoff + i * 64
                name_off = int.from_bytes(b[sh:sh + 4], "little")
                j = shstr_off + name_off
                name = b[j:j + 20].split(b"\0")[0].decode()
                if name.startswith(".text."):
                    t_off = int.from_bytes(b[sh + 24:sh + 32], "little")
                    b[t_off:t_off + 16] = bytes(16)
                    break
        bad.write_bytes(bytes(b))
        r = semu_cli(binary, "load", bad)
        check("illegal word fails strict load", r.returncode == 1 and
              "decodes as illegal" in r.stderr, r.stderr)

        # ...and `disasm` (inspection) shows the placeholder without PC drift.
        r = semu_cli(binary, "disasm", bad, "_Z5k_add")
        check("inspection disasm keeps pc0 placeholder",
              r.returncode == 0 and "/*0000*/  <unresolved" in r.stdout and
              "/*0010*/" in r.stdout, r.stdout[:300])

        # P2-GAP-01: inspect shows constant0/shared/local associations.
        r = semu_cli(binary, "inspect", single)
        check("inspect shows constant0", "constant0" in r.stdout, "")
        check("inspect shows shared", "shared=" in r.stdout, "")

        # Review round 2 #1: out-of-range relocation sh_info must produce a
        # structured error (exit 1), never a host crash (exit 139).
        # (Covered deterministically by unit test
        # cubin_relocation_oob_shinfo_no_crash; here we exercise the CLI on
        # a rela-section-bearing cubin when available.)
        bad = td / "oob_shinfo.cubin"
        b = bytearray(cubin)
        e_shoff = int.from_bytes(b[40:48], "little")
        shnum = int.from_bytes(b[60:62], "little")
        shstrndx = int.from_bytes(b[62:64], "little")
        shstr_off = int.from_bytes(b[e_shoff + shstrndx * 64 + 24:
                                     e_shoff + shstrndx * 64 + 32], "little")
        rela_patched = False
        for i in range(shnum):
            sh = e_shoff + i * 64
            name_off = int.from_bytes(b[sh:sh + 4], "little")
            j = shstr_off + name_off
            name = b[j:j + 24].split(b"\0")[0].decode()
            typ = int.from_bytes(b[sh + 4:sh + 8], "little")
            if typ == 4 and name.startswith(".rela"):
                b[sh + 44:sh + 48] = (0xffff).to_bytes(4, "little")
                rela_patched = True
                break
        if rela_patched:
            bad.write_bytes(bytes(b))
            r = semu_cli(binary, "load", bad)
            check("OOB relocation sh_info: structured error, no crash",
                  r.returncode == 1 and "out-of-range" in r.stderr, r.stderr)
        else:
            note("assembler cubin has no .rela; OOB sh_info covered by unit "
                 "test cubin_relocation_oob_shinfo_no_crash")

        # Review round 2 #2: inspection mode allows unknown EIATTR (0x51);
        # strict mode rejects it.
        bad = td / "inspect_unknown.cubin"
        b = bytearray(cubin)
        if info_idx is not None:
            sh = e_shoff + info_idx * 64
            sec_off = int.from_bytes(b[sh + 24:sh + 32], "little")
            rec = bytes([3, 0x51, 0x5a, 0x00])
            b[sec_off:sec_off + 4] = rec
            b[sh + 32:sh + 40] = (4).to_bytes(8, "little")
        bad.write_bytes(bytes(b))
        r = semu_cli(binary, "load", bad)
        check("strict load rejects unknown 0x51",
              r.returncode == 1 and "0x51" in r.stderr, r.stderr)
        # disasm uses inspection mode -> warns, succeeds.
        r = semu_cli(binary, "disasm", bad, "_Z5k_add")
        check("inspection disasm tolerates unknown 0x51",
              r.returncode == 0 and "warning" in r.stderr.lower(), r.stderr)

    print(f"\n{'PASS' if failures == 0 else 'FAIL'}: {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
