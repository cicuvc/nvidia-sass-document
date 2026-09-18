# UTCATOMSWS — uniform tensor-core atomic on software state (TMEM allocator)

**Opcode mnemonic:** `UTCATOMSWS` — three opcodes by sub-op:
`CAS`=`0b1001111100011` (0x13e3), `FAS`=`0b1010111100011` (0x15e3),
`OP`(AND/OR)=`0b1100111100011` (0x19e3)
**Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD`
**Virtual queue:** `$VQ_SW_STATE` (=44, Blackwell-new) | **MEM_SCBD_TYPE:** `BARRIER_INST`

New on sm100 (Blackwell). `UTCATOMSWS` = **U**niform **T**ensor-**C**ore
**ATOM**ic on **S**oft**W**are **S**tate. It performs a warp-uniform atomic
read-modify-write on a hardware-maintained "software state" resource — the
key primitive behind the **tcgen05 Tensor Memory (TMEM) allocator**. There is
no `alloc`/`dealloc` hardware opcode; instead ptxas builds those PTX primitives
out of `UTCATOMSWS` + an `ELECT`/`NANOSLEEP` spin loop (see below).

## Why it exists
PTX `tcgen05.alloc` / `dealloc` / `relinquish_alloc_permit` manage a pool of
TMEM columns. On Blackwell that pool is tracked by an on-chip software-state
register (virtual queue `$VQ_SW_STATE`, distinct from `$VQ_TMEM`). `UTCATOMSWS`
is the only instruction that atomically mutates it:
- **`FIND_AND_SET`** — atomically find a free slot in the state bitmap, mark it
  used, and return its index (+ a success predicate). This is the allocation
  primitive.
- **`AND` / `OR`** — clear / set bits of the state word (deallocation, permit
  bookkeeping).
- **`CAS`** — general compare-and-swap on the state word.

## Semantics (per sub-op)
| Sub-op | opcode | operands (cuobjdump order) | action |
|--------|--------|----------------------------|--------|
| `FIND_AND_SET` | 0x15e3 | `UPu, URd, URb` | find+set free slot; `URd`=result index, `UPu`=success, `URb`=state handle |
| `AND` | 0x19e3 | `URd, URb` | `state &= URb` (op bit[87]=0) |
| `OR` | 0x19e3 | `URd, URb` | `state \|= URb` (op bit[87]=1) |
| `CAS` | 0x13e3 | `UPu, URd, URb, URc` | compare-and-swap; `UPu`=success |

All operands are **uniform registers** (`UR*`) / **uniform predicates** (`UP*`) —
this is a warp-uniform op issued from the UDP, consistent with `tcgen05`'s
"one warp does the allocation collectively" model.

## Variant overview
| Class | Kind | Opcode | Sub-op modifier |
|-------|------|--------|-----------------|
| `utcatomsws_cas_` | CLASS | 0x13e3 | `/CAS` (enum: only `CAS`) |
| `utcatomsws_cas_one_` | ALT | 0x13e3 | + `/ONEONLY` (`.ONE`) |
| `utcatomsws_fas_` | CLASS | 0x15e3 | `/FIND_AND_SETONLY` + `/ALIGN` |
| `utcatomsws_fas_one_` | ALT | 0x15e3 | + `/ONEONLY` |
| `utcatomsws_op_` | CLASS | 0x19e3 | `/ATOMICOP` = {AND, OR} via bit[87] |
| `utcatomsws_op_one_` | ALT | 0x19e3 | + `/ONEONLY` |

The `_one_` alternates are **encoding-identical** to their base class (same
`BITS_` map) — `.ONE` is a display-only modifier with no dedicated encode bit in
this dump. Not observed in emitted code.

## Modifiers
| Slot | Enum | Bits | Meaning |
|------|------|------|---------|
| `cluster_sz` | `CLUSTER_SIZE` | [85] (`ignoreKill`) | `1CTA`(0) / `2CTA`(1) — cluster-collective allocation |
| `op` (OP class) | `ATOMICOP` | [87] (`cas`) | `AND`(0) / `OR`(1) |
| `align` (FAS) | `ALIGN` | [75] | `noalign`(0) / `ALIGN`(1) — aligned slot search |

`CLUSTER_SIZE.2CTA` maps PTX `.cta_group::2` (collective alloc across the two
peer CTAs of a cluster); it also widens the operands to 64-bit
(`IDEST/ISRC_*_SIZE = 32 + (2CTA)*32`). Note the spec's internal field name for
[85] is `ignoreKill` and for [87] is `cas` — legacy names; their *values* here
encode cluster size and AND/OR respectively.

`CLUSTER_SIZE` "1CTA"=0/"2CTA"=1; `ATOMICOP` AND=0/OR=1; `ALIGN` noalign=0/ALIGN=1;
`FIND_AND_SETONLY`={FIND_AND_SET}; `CAS`={CAS}; `ONEONLY`={ONE}=1.

## Bit layout (128-bit, common)
```
[124:122]∥[109:105] opex        = TABLES_opex_0(batch_t, usched_info)
[121:116]           req_bit_set  = wait barrier mask
[115:113]           src_rel_sb   = read scoreboard release (RD/WR both active)
[112:110]           dst_wr_sb    = write scoreboard release
[103:102]           pm_pred
[91]∥[11:0]         opcode       = 0x13e3 / 0x15e3 / 0x19e3
[87]                cas          = op (AND/OR)          — OP class only
[85]                ignoreKill   = cluster_sz (2CTA)
[83:81]             Pu           = UPu                  — FAS / CAS only
[75]                input_reg_sz_32_bit75_dist = align  — FAS only
[71:64]             Ra_URc       = URc                  — CAS only
[39:32]             Rb           = URb (state handle)
[23:16]             Rd           = URd (result / operand)
[15]                Pg_not ; [14:12] Pg = @UPg (UniformPredicate)
```
`INST_TYPE_DECOUPLED_RD_WR_SCBD` + both scoreboard fields active: the atomic is
decoupled/async and releases **both** a read and a write scoreboard when it
completes (unlike LDTM which is WR-only, or STTM which is RD-only).

## Verified encodings (cuobjdump, `nvcc -arch=sm_100a`, CUDA 13.1)
Mined from the `tcgen05.alloc`/`dealloc` lowering in `tests/ldtm_test.cubin`,
`tests/sttm_test.cubin`, and `tests/utcatomsws_test.cubin` (1CTA + 2CTA paths).
Decoder: `tools/decode_utcatomsws.py` — all round-trip (**ALL PASS**).

| Disassembly | Lo64 / Hi64 | opcode | cluster2 | align | URd | URb | UPu |
|-------------|-------------|:------:|:--------:|:-----:|:---:|:---:|:---:|
| `UTCATOMSWS.FIND_AND_SET.ALIGN UP0, UR6, UR6` | `…75e3` / `…08000800` | 0x15e3 | 0 | 1 | UR6 | UR6 | UP0 |
| `UTCATOMSWS.2CTA.FIND_AND_SET.ALIGN UP0, UR4, UR4` | `…75e3` / `…08200800` | 0x15e3 | 1 | 1 | UR4 | UR4 | UP0 |
| `UTCATOMSWS.AND URZ, UR6` | `…79e3` / `…08000000` | 0x19e3 | 0 | – | URZ | UR6 | – |
| `UTCATOMSWS.AND URZ, UR4` | `…79e3` / `…08000000` | 0x19e3 | 0 | – | URZ | UR4 | – |

Confirmed facts:
- `.2CTA` prints **before** the sub-op suffix (`UTCATOMSWS.2CTA.FIND_AND_SET`),
  and sets bit[85].
- `FIND_AND_SET` returns its result in `URd` (the alloc code then `SHF.L`/`×0x20`
  converts the slot index to a column address).
- Dealloc uses `.AND URZ, URb` (result discarded to `URZ`=UR63/0xff in the field).
- Only `FIND_AND_SET`(+.ALIGN[/.2CTA]) and `AND` are emitted by ptxas for
  alloc/dealloc; `CAS`, `OR`, and the `.ONE` alternates were **not** observed.

### The alloc spin-loop context (from `tests/ldtm_test.cubin`)
```
ELECT P0, URZ, PT                            ; pick a leader lane (.sync)
loop:
  DEPBAR.LE SB0, 0x36
  UTCATOMSWS.FIND_AND_SET.ALIGN UP0, UR6, UR6 ; try to grab a free TMEM slot
  BRA.U   UP0, done                          ; UP0 set => success
  NANOSLEEP 0x64                             ; back off
  BRA.U  !UP0, loop                          ; retry (alloc is blocking)
done:
  SHF.L.U32 / IMAD.SHL.U32 R0, R0, 0x20      ; slot index -> column addr (x32)
  ATOMS.OR [shmem], R2                       ; publish alloc bitmap
  STS [shmem], R0                            ; write TMEM addr to [dst]
```
This is why "what SASS does `tcgen05.alloc` map to" has no single answer — the
atomic primitive is `UTCATOMSWS.FIND_AND_SET`, wrapped in a software retry loop.

## Hand-assembled execution and cubin ABI (B200)

`tests/asm_construct/tcgen05_alloc_sm100.sass` is a hand-written reproduction
of the complete 1-CTA 32-column path: alloc, publish the TMEM address, dealloc,
then `UVIRTCOUNT.DEALLOC.SMPOOL` relinquish.  Its native instruction bytes match
the corresponding nvcc lowering through the allocator/guard code.  The cubin
assembled by this repository executed successfully on a Modal B200 and returned
the first allocation at TMEM column address `0x0`.

The experiment exposed a loader-visible ABI beyond the instructions themselves:

- the cubin must target **`sm_100a`**, not generic `sm_100`;
- per-kernel info contains `AT_ENTRY_FRAGMENT_TMEM_CTA1`,
  `RESERVED_SMEM_USED`, `TCGEN05_1CTA_USED`, and
  `VRC_CTA_INIT_COUNT=0x80`;
- `.nv.shared.reserved.0` is 0x54 bytes, and weak symbols name its allocator
  fields: `allocation_phase` at 0x40, `devtool_atexit_pc` at 0x48, and
  `allocation_mask` at 0x50;
- `__nv_reservedSMEM_offset_0_alias` carries the special
  `STO_RESERVED_SHARED` value, and `.nv.reservedSmem.cap` advertises 0x400;
- nvcc also records the VOTEU/REDUX offsets as `INT_WARP_WIDE` and its
  cooperative-group transition offsets.

With identical SASS and the TCGEN05 EIATTR markers but without that reserved
shared-memory symbol ABI, the kernel faults with CUDA error 719.  Adding those
symbols makes the same hand-generated cubin run successfully.  This strongly
indicates that the driver uses native ELF metadata/symbols to establish the
TMEM allocator's entry/exit state.

The `EXIT` instructions visible immediately around relinquish in this particular
kernel are **not part of `tcgen05.relinquish_alloc_permit` semantics**.  The PTX
operation was the last source-level operation, so ptxas tail-folded the control
flow: after `ELECT`, non-leader lanes exit early, while the elected lane performs
`UVIRTCOUNT.DEALLOC.SMPOOL`, updates reserved shared state, and then exits.  In a
control experiment with a global store after relinquish, ptxas emitted no early
exit: all lanes continued to the store, `UVIRTCOUNT.DEALLOC.SMPOOL` remained
unconditional at warp-group scope, and only the reserved-state `STS.U8` was
predicated by the elected-lane predicate.

The retained Mercury capsule is **not required** for this process.  Removing
every `.nv.capmerc.*` and `.nv.merc.*` section from the working nvcc cubin still
produced a correct alloc/dealloc result.  `tools/strip_cubin_sections.py`
performs that experiment while repairing section and symbol indices.

### CBU `ATEXIT_PC` observation

The entry fragment also installs a real, nonzero CBU at-exit PC.  In the
hand-assembled B200 kernel it is directly readable with:

```sass
BMOV R10, ATEXIT_PC.LO
BMOV R11, ATEXIT_PC.HI
```

Two samples in one launch—immediately before relinquish and after the elected
lane had executed `UVIRTCOUNT.DEALLOC.SMPOOL` plus the reserved-state store—were
identical.  One run returned `0x00002b6df75aa480` at both points (the absolute
VA changes between module loads).  Thus relinquish does not clear the CBU
`ATEXIT_PC`; it remains armed until the eventual `EXIT`, where the guard can
inspect allocator state and decide whether cleanup/trapping is needed.  This
hardware CBU value is distinct from merely loading the reserved shared-memory
`devtool_atexit_pc` field.

## Latency (sm100_latencies.txt)
`UTCATOMSWS` = `ATOMSWS_OP` (line 38), grouped into `OP_SWS` with
`UTCLDSWS`/`UTCSTSWS` (line 216). Like the other TMEM ops it is **subtracted from
`UDP_subset`** (line 218) — i.e. excluded from fixed UDP latency and treated as a
scoreboard-gated async op. Its uniform-predicate output latency (`UPu`) is `1`
(`ATOMSWS_OP\`{UPu,UPv} : 1 1 1 1 1 1 1 1 1 1`, line 433). The real RMW latency
is tracked via the read+write scoreboards, not a fixed table entry.

## Cross-references
- `notes/sm100/instr/ldtm.md`, `sttm.md` — TMEM load/store; consume the addresses
  this allocator produces.
- `$VQ_SW_STATE` vs `$VQ_TMEM` — separate virtual queues: the *allocator state*
  and the *tensor memory* are distinct resources.
- Sibling SWS ops (not yet documented): `UTCLDSWS` / `UTCSTSWS` — load/store of
  the software-state region (`OP_SWS`).

## Open questions
- Exact bit-width and layout of the software-state word `URb` refers to (the
  TMEM free-list bitmap): is it a single UGPR, or a handle into a wider state?
- CAS (`URc`) and `OR` operand semantics — not emitted by ptxas here; need a
  workload that forces them (e.g. contended multi-warp allocation).
- What distinguishes the `.ONE` alternate at runtime, given it is
  encoding-identical (assembler-only, or a decode disambiguation only)?
- `.ALIGN` semantics for `FIND_AND_SET` — aligned to what granularity (the 32-col
  TMEM allocation unit)?
