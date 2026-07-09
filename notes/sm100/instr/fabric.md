# Fabric instructions — `UBLKCP` / `UBLKRED` / `UBLKPF`  → PTX `fabric.try_*`

**PTX:** `fabric.try_put`, `fabric.try_get`, `fabric.try_red`, `fabric.try_pullred`,
`fabric.submit`, `fabric.wait` (§9.7.10.5, PTX ISA 9.3)
**SASS core ops:** `UBLKCP` (copy, 0x13ba), `UBLKRED` (reduce, 0x13bb),
`UBLKPF` (prefetch, 0x13bc) — all `udp_pipe` | **VIRTUAL_QUEUE:** `$VQ_TMA_UNORDERED_WR`
**Status:** spec-grounded + confirmed on `sm_100a` with CUDA 13.3 ptxas
(`tests/fabric_test.cu` assembled via hand-crafted PTX + new ptxas 13.3.73).

New in PTX ISA 9.3 (sm_100+). The **fabric** instructions are the device-side
API for direct NVLink-fabric access — copying data to/from remote GPU fabric
handles (logical endpoints), with mbarrier completion tracking and optional
in-flight reduction. The SASS backend is a small family of **uniform block
transfer ops** (`UBLKCP` / `UBLKRED` / `UBLKPF`) issued via the TMA unordered-
write path, wrapping a `SYNCS.ARRIVE` for mbarrier byte-count completion.

## The fabric family at a glance

| PTX | SASS | opcode | direction |
|-----|------|:------:|-----------|
| `fabric.try_put` | `UBLKCP` + `SYNCS.ARRIVE.TRANS64.RED` | 0x13ba | shared→fabric (write) |
| `fabric.try_get` | `UBLKCP` + `SYNCS.ARRIVE.TRANS64.RED` | 0x13ba | fabric→shared (read) |
| `fabric.try_red` | `UBLKRED` + `SYNCS.ARRIVE` | 0x13bb | shared→fabric with reduction |
| `fabric.try_pullred` | (likely UBLKRED + direction swap) | 0x13bb | (TODO: assemble) |
| `fabric.submit` | `UTMACMDFLUSH` | 0x79b7 | flush pending fabric/TMA cmds |
| `fabric.wait` | (mbarrier wait, no unique opcode) | — | — |

All three UBLK* ops share a nearly identical encoding: `udp_pipe`, three
uniform-register operands `[URa]`, `[URb]`, `URc` (address/descriptor pairs and
a size operand), and a common modifier set for space selection, memory-ordering
semantics, scope, and byte-mask/counting/multicast variants.

## The full try_put lowering (confirmed on sm_100a)
```
// preamble: load LE-id, data-offset, src shmem addr, size, mbar from params
ULEA UR5, ...                    // compute mbarrier state handle
USHF.R.U32.HI UR8, URZ, 0x4, UR8  // pack size >> 4 for 16B completion
UIADD3.64 UR4, UPT, UPT, UR4, UR6, URZ  // assemble fabric handle descriptor
MOV R0, UR8                      // move size to GPR for RED return
SYNCS.ARRIVE.TRANS64.RED.A0TX RZ, [UR9], R0  // mbarrier arrive (trigger)
UBLKCP.G.S.STRONG.SYS [UR4], [UR10], UR8     // the copy: src=G(handle), dst=S(smem)
```
`SYNCS.ARRIVE.TRANS64.RED.A0TX` (`syncs_arrive_`, opcode 0x19a7) is the
mbarrier arrive that sets up the 16B-counted completion tracking —
`.mbarrier::complete_tx::16B` — the completion counter advances by 1 per 16
bytes transferred. The `UBLKCP` then executes the actual async copy; both
together the instruction is the fabric op; the surrounding `ELECT` wrap provides
the "try" (single-lane) semantics — identical to the `UTCATOMSWS` / `UTCBAR`
leader-lane pattern.

---

## `UBLKCP` — uniform block copy (0x13ba)

`UBLKCP.dst.src.sem.scope [URa], [URb], URc`
where `.dst` / `.src` are the space qualifiers (G=global/fabric, S=shared),
and `URa`/`URb` carry the fabric handle descriptor and local address.

### Operands
| pos | SASS | bits | role |
|-----|------|------|------|
| dst | `[URb]` | [39:32] | destination address (64-bit descriptor pair when dst=G) |
| src | `[URa]` | [31:24] | source address (64-bit descriptor pair when src=G) |
| size | `URc` | [71:64] | transfer size in bytes (must be multiple of 16) |

### Modifiers
| Slot | Enum | Bits | Meaning |
|------|------|------|---------|
| `dst` | `DST` (G=0, S=1) | [73] | destination space |
| `src` | `DST` (G=0, S=1) | [74] | source space |
| `sem`+`sco` | `TABLES_mem_5(sem,sco,0)` | [80:77] | memory-ordering sem (WEAK/STRONG) + scope (CTA/SM/GPU/SYS) |
| `multicast` | `MULTICAST` | [75] | `.MULTICAST` — fabric multicast |
| `byte_mask` | `BYTE_MASK` | [84] | `.cp_mask` / per-16B byte select |
| `sp2` | `SP2` | [82:81] | 2-bit SP2 modifier |
| `seq` | `SEQ` | [83] | `.SEQUENCED` |
| `counted` | `COUNTED` | [85] | `.counted::bytes` |

Key CONSTRAINTS from the spec:
- `{src=G, dst=G}` is illegal (can't have both global).
- `.multicast` requires `src=G`.
- `sp2` only allowed with `src=S`.
- `.counted` requires `src=S, dst=G`.
- `.counted` is mutual exclusive with `.byte_mask`/`.DST_G_BYTE_MASK`.

These constraints make UBLKCP a directed copy between **one local** (S) and
**one remote/fabric** (G) space — the two typical cases being
`.G.S` (fabric→shared, try_get) and `.S.G` (shared→fabric, try_put).

### Verified encodings (cuobjdump, CUDA 13.3 ptxas, sm_100a)

| PTX | SASS | src | dst | URa | URb |
|-----|------|:---:|:---:|:---:|:---:|
| `fabric.try_put` (shared→fabric) | `UBLKCP.S.G.STRONG.SYS [UR4], [UR10], UR8` | S(1) | G(0) | UR4 | UR10 |
| `fabric.try_get` (fabric→shared) | `UBLKCP.G.S.STRONG.SYS [UR4], [UR10], UR8` | G(0) | S(1) | UR4 | UR10 |

(For try_put, the operand roles are: `[UR10]` = shared src, `[UR4]` = fabric-handle dst descriptor; cuobjdump prints the 3-operand syntax as `[URa], [URb], URc` regardless of direction.)

Both are wrapped in `ELECT` for the "try" semantics — only the elected leader
lane issues the UBLKCP; all other lanes skip.

## `SYNCS.ARRIVE.TRANS64.RED.A0TX` — the mbarrier byte-count arrive

The `SYNCS.ARRIVE.TRANS64.RED.A0TX` (opcode 0x19a7, `syncs_arrive_` class)
precedes every fabric UBLKCP: it performs an arrive on the mbarrier with 64-bit
transfer size and a RED (reduction) return value in the `A0TX` parameterisation,
setting up the `.mbarrier::complete_tx::bytes` (or `::16B`) tracking. The `UR9`
operand encodes the mbarrier address; `R0` carries the size-encoded byte count.
The `SYNCS` family is the cluster-wide mbarrier management API (init/arrive/
exchange/phasecheck/TCNT); see `ugetnextworkid.md` for the exchange variant used
by work-stealing.

## `fabric.submit` → `UTMACMDFLUSH` (0x79b7) + `CCTL.IVALL`

`fabric.submit` guarantees all previously issued fabric operations are visible to
fabric consumers. It lowers to a single **`UTMACMDFLUSH`** (flush pending
TMA/fabric commands) followed by `CCTL.IVALL` (cache-invalidate-all, ensuring the
local view is coherent with the fabric) and a `DEPBAR.LE SB0, 0x0` (ordering
barrier). `UTMACMDFLUSH` = `0b111100110110111` (0x79b7), `udp_pipe`,
`$VQ_UNORDERED`. The `UTMACMDFLUSH` class was already in the dump as a TMA
management op; `fabric.submit` simply targets it.

## Bit layout (128-bit, UBLKCP)
```
[124:122]∥[109:105] opex       = TABLES_opex_0(batch_t, usched_info)
[121:116]           req_bit_set
[115:113]           src_rel_sb
[112:110]           dst_wr_sb  = *7
[103:102]           pm_pred
[91]∥[11:0]         opcode     = 0x13ba
[85]                counted ; [84] byte_mask ; [83] seq ; [82:81] sp2
[80:77]             TABLES_mem_5(sem,sco,0) — combined sem+sco display
[76]                = 0
[75]                multicast ; [74] src(G/S) ; [73] dst(G/S)
[71:64]             URc (size)
[39:32]             URb (dst/desc addr)
[31:24]             URa (src/desc addr)
[15]                Pg_not ; [14:12] Pg = @UPg
```

`$VQ_TMA_UNORDERED_WR` — the same virtual queue as TMA unordered stores
(UTMASTG/UTMAREDG). This is a strong architectural clue: fabric copies share the
TMA engine's async write-dispatch path.

## The MODIFIER SYSTEM (what ptxas couldn't assemble)

### DST (G=0, S=1)
Space selector: G = global fabric handle (the LE-id + offset descriptor),
S = shared memory. CONDITIONS enforce the cross-space constraints (at least one
operand must be S; `.counted` requires src=S/dst=G; `.multicast` requires src=G).

### TABLES_mem_5 (sem, sco, ctx)
A 3-input lookup (`sem`, `sco`, `ctx`) producing a 4-bit display tag for
cuobjdump:
| row | sem | sco | ctx | display encoding |
|-----|-----|-----|-----|------------------|
| 1,0,0→0 | WEAK(1) | nosco(0) | 0 | `.WEAK.` |
| 2,2,0→5 | STRONG(2) | SM(2) | 0 | `.STRONG.SM` |
| 2,5,0→10 | STRONG(2) | SYS(5) | 0 | `.STRONG.SYS` |
| 0,0,1→1… | ACQUIRE(0) | nosco(0) | 1 | `.ACQUIRE.` |

(The full table has 18 rows covering all sem/sco/context triplets;
`SEM_ublkcp` WEAK=1/STRONG=2 and the DSTFMT-like sem enum may map through this
same table from the FREQ/shader-side TMA context.)

## Cross-references
- `notes/sm100/instr/ugetnextworkid.md` — same `ELECT` + `SYNCS` + TMA dispatch
  pattern; `SYNCS.EXCH.64` for mbarrier init.
- `notes/sm100/instr/utcatomsws.md` — leader-lane async dispatch via `ELECT`.
- `notes/sm100/instr/tcgen05_wait.md` — `FENCE.VIEW.ASYNC.*` for proxy ordering.
- `notes/sm90/arch/memory_model.md` — TMA unordered write model; `$VQ_TMA_UNORDERED_WR`
  is the TMA storage queue these fabric ops also use.
- `~/cs/project/documented-ptx/09.7.10-fabric-instructions.md` — the host-side
  Logical Endpoint API that creates the fabric handles these device ops operate on.

## Open questions
- `fabric.try_red` (= `UBLKRED`, opcode 0x13bb) and `fabric.try_pullred` — 
  ptxas 13.3.73 could not assemble them (syntax error); need a newer build or
  the full MODIFIER system for RED operations (`.redOp` / `.type`).
- Exact format of the 64-bit `URb` fabric-handle descriptor (the
  `[dstLeId, dstDataOff]` b128 encoding — presumably the LE-id (32-bit) and
  offset (64-bit) packed as a register pair, similar to the `UMMAB`/`gdesc`
  descriptor encoding in MMA).
- `TABLES_mem_5` 3-input lookup's full semantics — what `ctx` (third input, 0/1)
  selects (shader context? acquire vs release? internal only).
- `UTMACMDFLUSH` vs `DEPBAR` semantics — why `fabric.submit` needs both a TMA
  command flush AND a CCTL invalidate + barrier, versus a single fence.
