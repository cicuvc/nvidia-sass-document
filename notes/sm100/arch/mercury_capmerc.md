# Mercury / capmerc sections in sm_100+ cubins

**Question:** do the cubins our toolchain produces contain Mercury (`merc` / `capmerc`)
sections? **Answer: yes — automatically, for `sm_100`+ (SM > 99), with no special
flag.** `sm_90` cubins contain none.

Verified with CUDA 13.1 (`ptxas`/`nvcc` V13.1.115) on a trivial kernel
(`tests/mk_min.cu`). Corroborates (and extends) the crucible-notes ptxas Mercury model
(`~/cs/project/crucible-notes/decoded/ptxas-mercury/`, RE of ptxas 13.0.88) — treat
that as external/unofficial; the facts below are from our own binaries.

## What Mercury is
**Mercury** is ptxas's internal SASS-container IR. The pipeline is:

```
PTX → ptxas Mercury encoder → capmerc ELF (packet stream) → FNLZR finalizer → native SASS ELF
```

ptxas output mode is chosen by the **hidden** `--binary-kind {mercury,capmerc,sass}`
option (not shown in `--help`, and rejected as "Unknown option" if passed by name in
13.1). **SM > 99 auto-selects the capmerc path**; SM ≤ 99 uses plain `sass`.

## What actually lands in an `sm_100` cubin
Both raw `ptxas -arch=sm_100 x.ptx -o x.cubin` and full `nvcc -arch=sm_100 -cubin`
produce a **finalized** cubin that additionally **retains the Mercury capsule**:

- `EF_CUDA_MERCURY` (ELF header flag bit31 `0x80000000`) is **clear** — the file is
  native SASS, not a raw Mercury binary. (`e_flags` = `0x6006402`; `0x9006402` with
  `-lineinfo`.)
- Native `.text._Z…` (PROGBITS AX) disassembles to real SASS (`cuobjdump -sass` works).
- Alongside it, a retained capsule:

| Section | cuobjdump type | notes |
|---------|----------------|-------|
| `.nv.capmerc.text._Z…` | `CUDA_CAPMERC` (LOPROC+0x16) | Mercury packet stream for the kernel (align 16) |
| `.nv.merc.nv.info` / `.nv.merc.nv.info._Z…` | `CUDA_INFO` (LOPROC+0x83) | cloned per-function/kernel EIATTR |
| `.nv.merc.symtab` | `SYMTAB` (LOPROC+0x85) | cloned symbol table |
| `.nv.merc.debug_frame` | PROGBITS | cloned DWARF frame |
| `.nv.merc.rela.debug_frame` | `RELA` (LOPROC+0x82) | cloned relocations |
| `.nv.merc.nv.shared.reserved.0` | `CUDA_RESERVED_SHARED` (LOPROC+0x15) | cloned reserved-smem |

All Mercury sections carry the section flag **`0x10000000`** (readelf shows `p`,
processor-specific). With `-lineinfo`, more clones appear:
`.nv.merc.debug_line`, `.nv.merc.nv_debug_line_sass`, `.nv.merc.nv_debug_ptx_txt`,
`.nv.merc.rela.debug_line`, `.nv.merc.rela.nv_debug_line_sass`.

The retained capsule enables **opportunistic (re)finalization** to a different SM by a
downstream tool, without re-running the front end.

## Mercury metadata in `.nv.info`
- `EIATTR_MERCURY_ISA_VERSION` = **1.1** (`EIFMT_HVAL`).
- `.nv.compat`: `EICOMPAT_ATTR_MERCURY_ISA_MAJOR_MINOR_VERSION` = **1.1**.

(These two also appear in `sm_90` cubins as version tags — see
`../../sm90/arch/cubin_elf.md` — but the `sm_90` cubin has **no** `.nv.merc.*` /
`.nv.capmerc.*` sections. The Mercury *capsule* is `sm_100+`-only.)

## Not observed here
- No `.mercury_to_sass_map` (`SHT_CUDA_MERCURY_SASS_MAP`) in the retained-capsule form.
  Per crucible-notes that section belongs to a *pure* capmerc-mode output; our
  finalized-with-retention form instead keeps the `.nv.merc.*` DWARF/symtab clones.
- `R_MERCURY_*` relocations live inside the retained `.nv.merc.rela.*` clones; the
  primary (finalized) relocations are ordinary `R_CUDA_*`.

## Repro
```
nvcc -arch=compute_100 -ptx -o mk100.ptx mk_min.cu
ptxas -arch=sm_100 mk100.ptx -o mk100.cubin      # or: nvcc -arch=sm_100 -cubin
readelf -SW mk100.cubin | grep -iE 'merc|capmerc'
cuobjdump -elf  mk100.cubin | grep -iE 'CAPMERC|MERCURY'
cuobjdump -sass mk100.cubin                       # native SASS still present
# control: sm_90 has zero merc sections
readelf -SW <sm90.cubin> | grep -ic merc          # -> 0
```

## Cross-references
- General cubin ELF layout / sections / relocations: `../../sm90/arch/cubin_elf.md`.
- External Mercury RE model (unofficial): `crucible-notes/decoded/ptxas-mercury/`.
