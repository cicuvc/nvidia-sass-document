# ARCH_DIFF — opcode-space comparison across sm_75 / sm_80 / sm_90 / sm_100 / sm_120

Cross-architecture comparison of the nvdisasm ISA dumps: how the 13-bit opcode
space (`bit[91] ∥ bits[11:0]`) maps to encoding classes, and how that mapping
drifts generation to generation.

## Method

1. **Parse** each dump into a variant DB with the `parse_sm*.py` extractors:
   - sm_90/sm_100/sm_120: `tools/parse_sm90.py`, `parse_sm100.py`,
     `parse_sm120.py` (validation gates OK).
   - sm_75/sm_80: no dedicated parser existed; a driver (reproduced below)
     reuses `parse_sm90.py`'s machinery verbatim. Both parse cleanly —
     1229 / 1217 variants, **0 structural errors, 0 warnings** — confirming the
     dump format is identical across all five files. There are no
     `sm_75/sm_80_latencies.txt` dumps, so the `pipes` section is derived from
     the pipe suffixes in each variant's `OPCODES` names instead of an
     `OPERATION SETS` block (informational only; does not affect opcode maps).
   - All five headers say `ARCHITECTURE "Volta"` / `WORD_SIZE 64` — stale, do
     not trust. The presence of `BITS_13_91_91_11_0_opcode` (bit 91) proves the
     128-bit encoding in every file.
2. **Dedup**: one line per unique opcode, keeping the variant whose CLASS name
   is shortest; ties resolved by file order (primary CLASS before
   `ALTERNATE CLASS`).

Dedup artifacts to keep in mind when reading the tables below:

- The shortest-name rule can report a *different* variant of the same opcode on
  two archs without any semantic change. E.g. 0x221 is `fadd__RRR_RR` on
  sm_75/sm_80/sm_90 but `fhadd__RR` on sm_100/sm_120 — because sm_100 *added*
  fused-halves FADD variants at the same opcode and the shorter class name wins
  the dedup. Both instructions still exist.
- sm_80's HFMA2.MMA class names all carry a `_relu` suffix
  (`hfma2_mma__RRR_relu`); sm_75/sm_90 spell the same opcode without it. Naming
  difference only.

## Inventory

| arch | dump file | variants | unique opcodes | shortest-name ties |
|---|---|---:|---:|---:|
| sm_75 (Turing)   | `sm_75_instructions.txt` | 1229 | 580 | 76 |
| sm_80 (Ampere)   | `sm_80_instructions.txt` | 1217 | 616 | 77 |
| sm_90 (Hopper)   | `sm_90_instructions.txt` | 1589 | 728 | 84 |
| sm_100 (Blackwell DC) | `sm100_instructions.txt` | 1380 | 564 | 78 |
| sm_120 (Blackwell consumer) | `sm120_instructions.txt` | 1414 | 578 | 77 |

sm_90 has by far the largest opcode space; sm_100 shrinks it by 164 opcodes
(video ops, packaged-FP16, part of IMAD/texture), sm_120 re-grows slightly
(uniform `u*` family, tcgen05 MMA leftovers, TTU).

## Pairwise matrix

Deduped opcode sets: common / identical class name / differing class name /
only-A / only-B.

| pair | common | identical | differ | only-A | only-B |
|---|---:|---:|---:|---:|---:|
| sm75 vs sm80  | 573 | 558 | 15 | 7   | 43  |
| sm80 vs sm90  | 612 | 588 | 24 | 4   | 116 |
| sm90 vs sm100 | 491 | 477 | 14 | 237 | 73  |
| sm100 vs sm120| 495 | 490 | 5  | 69  | 83  |
| sm75 vs sm90  | 570 | 539 | 31 | 10  | 158 |
| sm90 vs sm120 | 471 | 452 | 19 | 257 | 107 |
| sm80 vs sm120 | 400 | 373 | 27 | 216 | 178 |
| sm75 vs sm120 | 382 | 344 | 38 | 198 | 196 |

Read: adjacent generations agree on ~96–99% of shared opcodes (the encoding
layer is stable across ~2 generations); across three+ generations the shared
fraction drops (sm75→sm120: 382/580 = 66%), so opcode value is **not** a
stable cross-generation key — always key on mnemonic + shape instead.

## Adjacent-pair class diffs (complete)

### sm75 → sm80 (15 differing)

| opcode | sm75 | sm80 | note |
|---|---|---|---|
| 0x20c / 0x80c / 0xa0c / 0x1a0c / 0x1c0c | `isetp__*` | `isetp__*_EX` | EX modifier made explicit in the class name |
| 0x237 | `imma_8816_8_8_` | `imma_` | IMMA shape suffix dropped |
| 0x23d | `bmma_88128_` | `bmma_` | BMMA shape suffix dropped |
| 0x95c | `bpt__WAIT` | `bpt__noDRAIN` | BPT variant renamed |
| 0x183b | `ldsm__URsIR` | `ldsm__UR_sI_R` | LDSM form respelled |
| 0x1980 | `ld_uniform__Ra32`  | `ld_memdesc__Ra64`  | **LD/ST addressing rewrite** |
| 0x1981 | `ldg_uniform__Ra32` | `ldg_memdesc__Ra64` | " |
| 0x1983 | `ldl_uniform_`      | `ldl_memdesc_`      | " |
| 0x1985 | `st_uniform__Ra32`  | `st_memdesc__Ra64`  | " |
| 0x1986 | `stg_uniform__Ra32` | `stg_memdesc__Ra64` | " |
| 0x1987 | `stl_uniform_`      | `stl_memdesc_`      | " |

Only-sm75: the six **TTU** (ray-tracing tree-traversal unit) opcodes
`ttuopen/ttust/ttuld/ttugo/ttumacrofuse/ttucctl` + one HMMA shape. Turing
introduced RT cores; Ampere's dump drops the TTU instructions, Blackwell
re-adds them (`sm100`/`sm120` have `ttu_pipe`). Note 0x3d2 flips from
`ttuld_` (sm75) to `ttuclose_` (sm120) — the TTU opcode assignment itself
moved.
Only-sm80: `hfma2`(9) `clmad`(7) `hmnmx2`(5) `mov`(4) `jmp`(4) `ldgsts`(2)
`bra`(2) + `atom/atoms/spmetadata/ldgdepbar/arrives/dmma/gather/genmetadata/
redux` and an HMMA shape.

### sm80 → sm90 (24 differing, mostly renames)

| opcode | sm80 | sm90 | note |
|---|---|---|---|
| 0x38a / 0x198a | `atom(_uniform)__Ra*` | `atom_int(_uniform)__Ra*` | INT/F32 ATOM variants explicitly split in naming |
| 0x3a8 / 0x19a8 | `atomg(_uniform)__Ra*` | `atomg_int(_uniform)__Ra*` | " |
| 0x98e / 0x198e | `red(_uniform)__Ra*` | `red_int(_uniform)__Ra*` | " |
| 0x43e / 0x63e / 0x163e / 0x1e3e | `f2fp_rs__R*` | `f2fp_merge_c__R*` | F2FP variant respelled |
| 0x817 | `imnmx__RsIR_RIR` | `imnmx__RIR_RsIR` | IMNMX operand order swapped |
| 0x947 / 0x94a / 0xb4a | `bra_` / `jmp_imm_` / `jmp_const_` | `bra__U` / `jmp_imm__U` / `jmp_const__U` | uniform-target variants added |
| 0x34e | `lepc_` | `lepc__RRR` | LEPC gains a register form |
| 0x235 / 0x435 / 0x635 / 0x835 / 0xa35 / 0x1635 / 0x1a35 / 0x1c35 / 0x1e35 | `hfma2_mma__*_relu` | `hfma2_mma__*` | dedup naming artifact (see Method) |

Only-sm80: `warpsync`(3), `r2ur`(1) — present in the Ampere dump, gone from
the Hopper dump (yet sm_90's latencies file still lists WARPSYNC in cbu_pipe;
worth a separate probe). Only-sm90: video ops (`f2ip`9, `viaddmnmx`9,
`syncs`8, `vimnmx3`5, `i2fp`5, `viadd`5, `vhmnmx`5, `vimnmx`5, `suquery`4),
WGMM (`hgmma/igmma/bgmma/qgmma` 3 each), `uf2fp`3, `stsm/elect/utmaldg`2,
`atom`2.

### sm90 → sm100 (14 differing)

| opcode | sm90 | sm100 | note |
|---|---|---|---|
| 0x221 / 0x1e21 | `fadd__RR*_R*` | `fhadd__R*` | sm100 adds FADD fused-halves at same opcode; dedup artifact |
| 0x223 / 0x1c23 / 0x1e23 | `ffma__RR*_RR*` | `fhfma__R*` | same for FFMA |
| 0x38d | `atoms_cas__RaRZ_CAS` | `atoms_cas__RaRZ` | `_CAS` suffix dropped |
| 0x43e / 0x1e3e | `f2fp_merge_c__RR*` | `f2fp_rs_16b__RR*` | F2FP variant reassignment |
| 0x63e / 0xa3e | `f2fp_merge_c__RRC` / `f2fp__RCR` | `f2fp_4b_upconvert_scale__R*R` | " |
| 0x98e / 0x9a6 / 0x198e / 0x19a6 | `red_int/fp(_uniform)` | `redg_int/fp(_uniform)` | RED → REDG rename |

Only-sm100 (73): **tcgen05** family `utc{bar,cp,hmma,qmma,shift,stsws,ldsws,
atomsws}` (~13), QFMA4/QMUL4/QADD4 (11), packaged FP `ffma2/fmul2/fadd2/
fmnmx3` (14), `cctl`8, `ldcu`3, `uvirtcount/credux/ustgr/uredgr/syncs/
acqshminit/ugetnextworkid/umemsets/ldg/stg/stt/ldt` + texture leftovers.
Only-sm90 (237): `hfma2`13, `imad`12, `plop3`6, video (`vabsdiff/vabsdiff4/
viaddmnmx/vimnmx3/vhmnmx`), texture (`tex/tld4/tld/txd/tmml/txq`), surface
(`suatom/suld/sust`), `prmt/shf/ffma/dfma/clmad/f2ip/f2f/f2i/i2f/frnd/rpcmov/
bmov/uldc` —
mostly *opcode-count* shrink (packed-FP16 & video removed, IMAD trimmed) rather
than reassignment.

### sm100 → sm120 (5 differing — most stable pair)

| opcode | sm100 | sm120 | note |
|---|---|---|---|
| 0x210 / 0x810 / 0x1c10 | `iadd(_imm)__*` | `iadd3(_imm)__*` | 32-bit IADD folded into IADD3 |
| 0x43e / 0x1e3e | `f2fp_rs_16b__RR*` | `f2fp_merge_c__RR*` | F2FP variant flip vs sm90 |

Only-sm120 (83): the **uniform `u*` expansion** (~45: `u{iadd,imad,fmul,f2f,
i2i,i2ip,f2ip,mnmx,sel,fset/fsetp,fhadd,fhfma,fadd,ffma,frnd,fmnmx,iabs,viadd,
vimnmx,virtcount,mov,mov64iur,cs2ur}`), `cctl`8, `ldcu`3, `sel`3, tcgen05
`qmma`(2)/`omma`/`mxqmma`, TTU 6, `uf2ip`3, texture/surface leftovers.
Only-sm100 (69): video ops (`vabsdiff`5, `vabsdiff4`5, `viaddmnmx`5,
`vimnmx3`3, `vhmnmx`3), `ffma2/qfma4/fmul2/fadd2/fmnmx3/qmul4/qadd4` (28),
tcgen05 `utc*` (13), `i2fp`2, `scatter/gather/genmetadata/credux/ustgr/uredgr/
stt/ldt`.

## Stable vs recycled opcodes

Recycled / reassigned opcodes (deduped class on both sides, semantically
unrelated):

- **0x236**: `hmma__884_f32` (sm75) → `viadd__RRR_RRR` (sm90+) — the HMMA
  8x8x4-F32 shape opcode was freed and handed to VIADD.
- **0x235 / 0x835 / 0x1c35**: `hfma2_mma__*` (sm75–sm100) →
  `iadd*(no)imm__*` (sm120) — HFMA2.MMA removed on Blackwell consumer, opcode
  reused by IADD.
- **0x3d2**: `ttuld_` (sm75) → `ttuclose_` (sm120) — TTU opcode reassignment.
- 0x1980–0x1987 LD/ST block: same mnemonics, but the *addressing model* changed
  under them (uniform → memdesc) in sm80.

Everything else that persists does so with the same class name — the basic
ALU/control-flow opcode assignments have been frozen since Turing.

## Open questions

- WARPSYNC: in the sm_80 dump as its own opcode(s), absent from sm_90's, yet
  listed in sm_90's `cbu_pipe` OPERATION SETS. Re-check against real sm_90
  cubins (`cuobjdump -sass` + `tools/query_sm90.py opcode`).
- The sm_75/sm_80 `pipes` sections here are suffix-derived and include digits
  in mnemonic bases (e.g. `XMAD3`); they are informational only.

## Repro

```bash
python3 tools/parse_sm90.py       # -> sm90.json (validation gate)
python3 tools/parse_sm100.py      # -> sm100.json
python3 tools/parse_sm120.py      # -> sm120.json
python3 tools/parse_sm75_80.py    # -> sm75.json + sm80.json
# then, per arch: group variants by opcode, keep shortest class name
# (ties -> file order), sort ascending, emit "0x<hex>-><class>".
```
