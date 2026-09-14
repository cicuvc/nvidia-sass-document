# LDCU — Uniform Load Constant (sm_120)

**Opcode mnemonic:** LDCU  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:**
`INST_TYPE_DECOUPLED_WR_SCBD` (`DECOUPLED_RD_WR_SCBD` for the CX forms)  |
**VIRTUAL_QUEUE:** `$VQ_LDCU`

> sm_120 rename of Hopper `ULDC` (`notes/sm90/instr/uldc.md`).  This note
> documents the **8 sm_120 encoding variants** (6 base classes + 2
> `optional_upx` alternates) and the silicon-verified semantics.
> Probe: `tests/asm_construct/probe_ldcu_variants.py`.

## Semantics

`LDCU` loads data from the **constant memory** hierarchy into the **uniform
register file** (`UR0`–`UR79`).  The source is a constant address and the
destination is one or two uniform-register groups; the loaded value is meant
for the scalar/uniform datapath (`UIADD3`, `UMOV`, `ULEA`, …).  All forms are
`udp_pipe` and write a **real `wr` scoreboard** (`dst_wr_sb`, encoded through
`VarLatOperandEnc`), so consumers must wait it with `req={n}` — unlike most
`udp_pipe` ops whose write scoreboard is pinned `*7`.

Three orthogonal selectors define the 8 variants:

1. **Source/address family**
   * `C` **bound** — `c[bank][URa + off]`: a fixed constant bank (5-bit bank,
     immediate offset, optional uniform-register byte index).
   * `CX` **bindless** — `c[URa][URb + off]`: a 64-bit bindless-constant
     *handle* in a uniform-register pair plus a uniform-register index.
   * **VA** — `[URa + off32]`: a 64-bit **generic/global virtual address**
     plus a 32-bit signed offset, with a `[!]UPp` predicate that selects a
     zero-fill (measured, see below).
2. **Scalar vs `.256`** — the `.256` classes add a second destination base
   (`URd2`) and an 8-bit `word_mask` (a masked, compacting 32-byte load).
3. **Optional uniform predicate** — the `_optional_upx_` alternates pin
   `Pp=7`/`memdesc=1`; the base classes expose `UPp`.

## Variant overview

| # | class | opcode | SIDL name | source | ISRC_A | IT |
|---|-------|--------|-----------|--------|-------:|----|
| 1 | `ldcu_const_RCR_` | `0x17ac` | `LDCU_CbURaOffs` | `c[bank][URa+off18]` | 32 | DECOUPLED_WR_SCBD |
| 2 | `ldcu_const_RCxR_` | `0x1bac` | `LDCU_CXb` | `c[URa64][URb+off17]` | 64 | DECOUPLED_RD_WR_SCBD |
| 3 | `ldcu_ur_offs_` | `0x19ac` | `LDCU_CXbVA` | `[URa64+off32]`, `UPp` | 64 | DECOUPLED_WR_SCBD |
| 4 | `ldcu_ur_offs_optional_upx_` (ALT) | `0x19ac` | `LDCU_CXbVA` | `[URa64+off32]` | 64 | DECOUPLED_WR_SCBD |
| 5 | `ldcu_256_const_RCR_` | `0x1dac` | `LDCU_256_CbURaOffs` | `.256 URd2,URd,c[bank][URa+off18],mask` | 32 | DECOUPLED_WR_SCBD |
| 6 | `ldcu_256_const_RCxR_` | `0x15ac` | `LDCU_256_CXb` | `.256 …,c[URa64][URb+off17],mask` | 64 | DECOUPLED_RD_WR_SCBD |
| 7 | `ldcu_256_ur_offs_` | `0x13ac` | `LDCU_256_CXbVA` | `.256 …,[URa64+off32],mask,UPp` | 64 | DECOUPLED_WR_SCBD |
| 8 | `ldcu_256_ur_offs_optional_upx_` (ALT) | `0x13ac` | `LDCU_256_CXbVA` | `.256 …,[URa64+off32],mask` | 64 | DECOUPLED_WR_SCBD |

The sm_90 `ULDC` had no `.128`/`.256` and an extra `imm_` class; sm_120 drops
`imm_`, adds `.128` to the `sz` enum and the two `.256` families.  The sm_90
`uldc_ur_offset_` (`c[bank][URa+off]`) is folded into variant 1 here.

## Modifiers

| Modifier | Field | Bits | Values |
|----------|-------|------|--------|
| `sz` (scalar forms) | `sz` | [75:73] | `SZ_U8_S8_U16_S16_32_64_128`: 0=U8, 1=S8, 2=U16, 3=S16, 4=32, 5=64, 6=128, 7=invalid |
| `texunpack` | `texunpack` | [81:80] | 0=notexunpack, 1=TEXUNPACK, 2=HDRUNPACK, 3=invalid |
| `.256` | `sz` (`ONLY256_ldcu`) | (`sz` is the type-`ONLY256` discriminator, not a width) | `.256` |
| `word_mask` | `word_mask` | [83:80]∥[35:32] | low nibble → `URd`, high nibble → `URd2` |
| `UPp` | `Pp` / `memdesc` | [89:87] / [90] | uniform-predicate zero-fill enable; `memdesc = !UPp`; ALT pins `Pp=7, memdesc=1` (= `!UPT`, always load) |

`IDEST_SIZE = popcount(word_mask & 0xF)·32`, `IDEST2_SIZE =
popcount(word_mask >> 4)·32` for the `.256` forms.  For the scalar forms:
`.64` needs an even-aligned pair, `.128` a 4-aligned quad; `.64`/`.128`
consume `URd`/`URd+1`/… in low-word-first order (same as sm_90).

## Bit layout

Common fields (all variants):

```
[14:12]        Pg          guard uniform predicate
[15:15]        Pg_not
[91],[11:0]    opcode      13-bit {bit[91], bits[11:0]}
[23:16]        Rd          URd  (scalar dest / low 128-bit group)
[79:72]        imm8        URd2 (high 128-bit group; .256 only)
[35:32],[83:80] word_mask  (.256 only; low nibble bits [35:32], high [83:80])
[121:116]      req_bit_set
[115:113]      src_rel_sb  `*7` for RCR/VA; encodable (RD) for the CX forms
[112:110]      dst_wr_sb   VarLatOperandEnc(wr)
[103:102]      pm_pred
[124:122],[109:105] opex    TABLES_opex_0(batch_t, usched_info)
```

Source fields:

```
RCR (bound)                       RCxR (bindless CX)            VA
  [58:54],[53:37] ConstBankAddress0   [31:24] Ra  (= URa64)     [31:24] Ra  (= URa64)
    -> Sa_bank / Ra_offset            [71:64] Ra_URc (= URb)    [69:38] Sa_offset (32-bit)
  [31:24] Ra (URa byte index)         [53:37] Ra_offset (17-bit) [89:87] Pp, [90] memdesc
  sz[75:73] texunpack[81:80]          sz[75:73] texunpack[81:80] sz[75:73] texunpack[81:80]
```

**Verified encodings** (RTX 5090, `probe_ldcu_variants.py`; `.64` dest shown):

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `00c02000040677ac` | `000e220008000a00` | `LDCU.64 {UR6,UR7}, c[0x3][UR4+0x100]` (RCR) |
| `0000200004067bac` | `000e220008000a05` | `LDCU.64 {UR6,UR7}, c[UR4][UR5+0x100]` (CX) |
| `00004000040679ac` | `000e22000f800a00` | `LDCU.64 {UR6,UR7}, [{UR4,UR5}+0x100], !UPT` (always load) |
| `00004000040679ac` | `000e220008000a00` | `LDCU.64 {UR6,UR7}, [{UR4,UR5}+0x100], UP0` (zero-fill if UP0) |
| `00c0200304047dac` | `000e220008030800` | `LDCU {UR8,UR9}, {UR4,UR5}, c[0x3][UR4+0x100], 0x33` (.256 bound) |
| `000020030e0475ac` | `000e220008030805` | `LDCU {UR8,UR9}, {UR4,UR5}, c[UR14][UR5+0x100], 0x33` (.256 CX) |
| `00004003060473ac` | `000e22000f830800` | `LDCU {UR8,UR9}, {UR4,UR5}, [{UR6,UR7}+0x100], 0x33, !UPT` (.256 VA) |

## Bound form: `URa` is a byte offset

Silicon-verified (`in = 0x1122334455667788` at `c[0x0][0x380]`):

| `LDCU UR20, c[0x0][UR12+0x380]` | UR12 | result |
|---|---|---|
| 0 | `0x55667788` | low word of `in` |
| 4 | `0x11223344` | high word of `in` |
| 8 | pointer at `c[0x0][0x388]` | next 8-byte slot |
| 1 | CUDA 716 | constant loads need ≥4-byte alignment |

So the effective address is `bank base + Sa_offset + URa` (URa in **bytes**),
not a word index.  The constant offset itself is a 17-bit field (the FORMAT
declares `SImm(18)`; the on-wire `Ra_offset` is 17 bits alongside a 5-bit
bank via the `ConstBankAddress0` relocator).

## `.256` `word_mask` is a masked, compacting 32-byte gather

Silicon-verified with four contiguous 8-byte params
(`a,b,c,d` → source words 0..7 = `A,A,B,B,C,C,D,D`):

* bit *i* of `word_mask` selects 32-bit source word *i* of the 32-byte block;
* selected words 0–3 are written **compacted** (in increasing word order) to
  `URd, URd+1, …`; selected words 4–7 to `URd2, URd2+1, …`;
* a nibble with no bits set means the corresponding destination base is
  `URZ` and no registers are written.

Verified masks (read back as `[URd2 group ‖ URd group]`):

| mask | selected | result |
|---|---|---|
| `0x01` | word 0 | `UR4=A` |
| `0x05` | words 0,2 | `UR4=A, UR5=B` (compaction) |
| `0x0A` | words 1,3 | `UR4=A, UR5=B` |
| `0x10` | word 4 | `UR8=C` |
| `0x55` | words 0,2,4,6 | `UR8=C, UR9=D, UR4=A, UR5=B` |
| `0xAA` | words 1,3,5,7 | `UR8=C, UR9=D, UR4=A, UR5=B` |
| `0xFF` | words 0–7 | `UR8..11=C,C,D,D; UR4..7=A,A,B,B` |

This is the same `word_mask` mechanism as Blackwell `LDG.256`
(`BITS_8_72_72_63_57_word_mask` there; `BITS_8_83_80_35_32` on LDCU).

## Bindless (CX) and VA source forms

* **CX bindless** (`c[URa][URb+off]`): `URa` is a **64-bit bindless-constant
  handle** (a uniform pair, even-aligned), `URb` a 32-bit uniform index, and
  the immediate offset is 17 bits.  ptxas exposes a `DisableLDCUWithURb` knob,
  confirming the URb-indexed form.  Reaching it at runtime needs a
  driver-provided constant handle, which the hand-built-cubin runner cannot
  fabricate, so only the encoding is verified (round-trip + opcode).
* **VA** (`[URa64 + off32]`): `URa` is a 64-bit **generic/global virtual
  address** with a 32-bit signed byte offset.  Silicon-verified with a real
  `cuMemAlloc` device pointer: `LDCU.64 {UR20,UR21}, [UR6+0x4], !UPT` returns
  the buffer's words 1/2 (low word first), `LDCU.U8/S8` sign/zero-extend a
  byte.  So the VA class is the **uniform-datapath scalar global load** (a
  "uniform LDG"): it reads ordinary global memory through the generic VA,
  with the usual `.64`/`.128` group alignment rules.  The
  `CCTL.E.C.LDCU.IV.{DEEP,SHALLOW}` sibling (`cctl_c_ldcu_va_`, opcode
  `0x1540`) invalidates the corresponding uniform-load cache for a VA.

  **What `UPp` means (measured):** it is an **active-low enable with a
  zero-fill else-branch**.  The instruction *always writes* the destination;
  when the printed `[!]UPp` predicate evaluates to **FALSE** the load is
  performed, and when it evaluates to **TRUE** the whole destination group is
  written **0** (the source address is not accessed — a `.64` zero-fill does
  not fault even on a misaligned address).

  | written guard | runtime value | result (UR20/UR21 pre-set to 0x11111111/0x22222222) |
  |---|---|---|
  | `UP0`  | 0 | loads `0xA1B2C3D4, 0x55667788` |
  | `UP0`  | 1 | `0x00000000, 0x00000000` |
  | `!UP0` | 1 | loads |
  | `!UP0` | 0 | `0, 0` |
  | `UPT`  | 1 | `0, 0` |
  | `!UPT` / omitted (ALT) | – | loads (the no-predicate encoding) |

  Verified identically for `UP0`, `UP1`, `UP2`, `UP5` (with the target
  predicate set by `UISETP.EQ/NE.AND UPn, UPT, URZ, URZ, UPT` and read back
  via `UP2UR URd, UPR`).  Hence the rule is `Rd = printed_pred ? 0 :
  mem[URa+off]`, and the `optional_upx` alternate pins `Pp=7, memdesc=1` =
  `!UPT`, i.e. the always-load spelling.  This invert-on-`memdesc` convention
  is shared with the sm_90 `ULDC` `ur_offs`/`imm` classes (there the same
  `[90]` bit is named `input_reg_sz_32_dist`), so it is an ISA-wide uniform-
  datapath idiom, not a mis-decode.

## Scoreboards and latency

* Scalar bound/VA: `INST_TYPE_DECOUPLED_WR_SCBD`, `src_rel_sb` pinned `*7`.
* CX forms: `INST_TYPE_DECOUPLED_RD_WR_SCBD`, `src_rel_sb` is a real `RD`.
* All: `dst_wr_sb` is `VarLatOperandEnc(wr)` → consumers wait via `req={n}`
  (verified; the same pattern is what breaks the sm_90 ULDC port, where
  `dst_wr_sb` is pinned `*7`).
* `udp_pipe` → the `ULDC_VOTEU_UMOV_ULEPC` rows of the UGPR latency tables
  (see `notes/sm90/instr/uldc.md` §Latency).

## Tooling

`assembler/` now accepts all three source families (added for this probe):
`c[bank][URa+off]`, `c[URa][URb+off]` (and `c[{URa,URb}][…]`), `[URa+off]`,
plus the `.256` second destination group and `word_mask`.  Two latent bugs
were fixed along the way:

* the matcher sized `URd2` with `IDEST_SIZE` instead of `IDEST2_SIZE`, which
  rejected every `.256` mask whose low nibble was empty and high nibble set;
* `_parse_mem_addr` dropped a register-group's own `+imm` offset when
  normalizing `[URa+off]` to `[RZ+URb+off]`, losing e.g. `[{UR4,UR5}+0x100]`.

`tools/sass_disasm.py` renders all 8 forms and byte-round-trips them.

## Open questions

* **Why the `UPp` enable is active-low** — measured behaviour is `Rd =
  printed_pred ? 0 : load`; whether cuobjdump's printed polarity or the
  hardware bit polarity is the odd one out is a naming question.  (The
  `.256` VA form should be re-checked the same way; only the scalar form was
  measured.)
* **Bindless handle format** — the `c[URa]` handle is 64-bit; whether it is a
  raw const-space VA or a tagged {base,size} descriptor is unknown.
* **`.256` write-back of unselected registers** — unselected destination
  registers read back 0, but it is not distinguished whether the hardware
  writes 0 or simply leaves them untouched (kernels should not rely on it).
* **`texunpack`** (`.TEXUNPACK`/`.HDRUNPACK`) — sm_90-era texture unpack
  modifiers carried into sm_120; not emitted by ptxas for LDCU and untested.
* **17-bit vs 18-bit immediate offset** — the FORMAT declares `SImm(18)` but
  the encoded `Ra_offset` field is 17 bits; the exact wrap/sign behaviour at
  the boundary is unverified.
* **VA `off32` sign/range** — the offset is declared `SImm(32)`; only small
  positive offsets were exercised.
