# Memory model / cache-control claims — verification vs sm_90 spec

Verifying a pasted description of the Hopper cache/ordering model against the
instruction dump. Buckets: **CONFIRMED**, **CORRECTION**, **NOT IN SPEC / needs
probe**. All enum values quoted are from `sm_90_instructions.txt`.

## CONFIRMED (exact against spec enums/fields)

- **Eviction priority `cop`** = enum `COP`, 3-bit: `EF=0, EN=1, EL=2, LU=3,
  EU=4, NA=5` (6,7 INVALID). Matches the table exactly.
- **Strength `sem`** = enum `SEM`, 2-bit: `CONSTANT=0, WEAK=1, STRONG=2,
  MMIO=3`. Exact.
- **Three orthogonal per-access fields** on `LDG`/`STG`: FORMAT carries
  `/E /COP /SP2 /SZ… /SEM /SCO /PRIVATE` — i.e. `cop`+`sem`+`sco` are the whole
  ordering/residency model, no separate legacy "cache class" bit. Confirmed.
- **`.E` extended-address flag** = enum `E` (`noe=0, E=1`), a 1-bit field.
  `LDG/STG/ATOMG` carry `/E`; `LDS/STS/LDC` have **no** `/E` slot (verified). Exact.
- **L2 sector-promotion field** = enum `SP2`: `nosp2=0, LTC64B=1, LTC128B=2,
  LTC256B=3`. Matches "NOSP / 64B / 128B / 256B" (spec name is `SP2`/`nosp2`,
  `LTC*B`).
- **CCTL sub-ops** (spread across `COP_*` enum variants, union):
  `PF1=0, PF2=1, WB=2, IV=3, RS=5, IVALL=4, IVALLP=6, WBALL=7, WBALLP=8,
  PML2=9, DML2=10, RML2=11`. All claimed ops present **except** PF1_5 and RSLB
  (see CORRECTION).
- **CCTLT (texture)**: `CCTLTOp` = `IVTH=1`, plus a separate `IVALL` modifier on
  the cctlt classes. Matches "IVTH / IVALL".
- **Cache selector** = enum `Cache` (`D=0, U=1, C=2, I=3`); texture handled by
  the separate `CCTLT` opcode. Matches D/U/C/I (+texture).
- **Integer atomic-op field**: enum `AtomsOp` = `ADD=0, MIN=1, MAX=2, INC=3,
  DEC=4, AND=5, OR=6, XOR=7, EXCH=8`. Exact.
- **CAS is a distinct opcode, not an atomic-op value**: `ATOM/ATOMG/ATOMS` each
  have separate `*_cas__*` classes with their own opcode, a `/CAS` modifier and
  an `ATOMCASSZ` size enum. Opcodes differ from the regular atomic:
  ATOMG reg `…1110101000` vs CAS `1110101001`; ATOM `1110001010` vs `1110001011`;
  ATOMS `1110001100` vs `1110001101`. Exact.
- **`MEMBAR` fields**: FORMAT = `/MEMBAR_SEM(...):sem /SCO_CTA_SM_GPU_SYS_VC_CTAPARTIAL:sco`.
  - `membar_sem` = `SC=0, ALL=1, NONE(nomembar_sem)=2, MMIO=3`. Exact.
  - `membar_sco` = `CTA=0, SM=1, GPU=2, SYS=3, VC=5` (+`CTA.PARTIAL=6`). Exact,
    **and genuinely a different numbering** from the load/store `SCO` enum.
- **Async / fence mnemonics all exist**: `LDGSTS, LDGDEPBAR, DEPBAR, ERRBAR,
  CGAERRBAR, UTMACCTL, REDG`. (Their exact PTX→SASS lowerings are probe-only,
  below.)

## CORRECTION (claim disagrees with spec)

- **Scope ladder `CTA < SM < GPU < VC < SYS` is NOT the field encoding.**
  The load/store scope enum `SCO` is: `nosco=0, CTA=1, SM=2, VC=3, GPU=4, SYS=5`.
  So in the LDG/STG `sco` field **VC (3) is encoded *below* GPU (4)** — VC sits
  between SM and GPU, not above GPU. The `MEMBAR` scope enum orders them yet
  differently (`GPU=2, SYS=3, VC=5`), so **the two scope fields use different
  numbering and neither follows the stated breadth order.** The conceptual
  breadth story may hold, but as an *encoding* claim `GPU<VC` and `VC<SYS` are
  wrong for at least one of the two fields each.
- **`PF1_5` (prefetch to L1.5) does not exist** in the sm_90 CCTL enums (no
  match anywhere in the file).
- **`RSLB` (reset line, look-aside buffer) does not exist** in sm_90 (no match).

## NOT IN SPEC / needs SASS probe (can't confirm from instruction dump)

- **L2 line = 128 B, four 32 B sectors, 4-bit tag sector mask (S0–S3, 0xf), 32 B
  transaction granularity.** These are L2/LSU **hardware** properties; there is
  **no per-instruction sector-mask enum/field** in the spec (only the `SP2`
  fill-promotion field exists). Consistent with, but not provable from, these
  files.
- **Legacy PTX→SASS projection table** (`.ca/.cg/.cs/.lu/.cv/.wt` → cop/sem/sco
  combos) and **default-scope-by-class** (ld/st weak-no-scope vs atom/red
  `STRONG.GPU`): these are ptxas lowering/rendering behaviors. Every field value
  cited is a legal enum value, so internally consistent, but the mapping itself
  needs probe SASS.
  - ⚠ Suspicious: claim says `.ca` → `sco=CTA` **printed `.SM`**. In sm_90 `SCO`,
    `CTA=1` and `SM=2` are *distinct* scopes, so printing CTA as `.SM` would be
    wrong — likely a probe on a cluster-scope build or a mislabel. Flag for
    re-probe.
- **"relaxed == acquire == acq_rel same bits", "MMIO bare addressing / bypasses
  desc[UR][Rn]", "STRONG only when ordered"** — renderer/lowering behaviors,
  plausible, not encoded as such in the spec.
- **fence.acq_rel.cluster → MEMBAR.ALL.GPU + ERRBAR;CGAERRBAR**, **fence.proxy.
  tensormap → UTMACCTL.IV**, **cp.async.* → LDGSTS(.BYPASS)** — the mnemonics
  exist; exact lowering is probe-only.

## Net
Field/enum-level claims are almost all **correct** (cop, sem, membar_sem/sco,
SP2, E, CCTL/CCTLT sub-ops, atomic-op set, CAS-as-own-opcode). The main
**substantive errors** are: (1) the scope *ordering/encoding* — load/store `SCO`
puts VC below GPU, and the two scope fields use different numbering; (2) `PF1_5`
and `RSLB` sub-ops are not in sm_90. Cache-geometry and PTX-lowering statements
are out of scope for these files and left as probe items.
