# Work-stealing — `clusterlaunchcontrol.try_cancel` / `query_cancel`  → `UGETNEXTWORKID` + `SYNCS`

**PTX:** `clusterlaunchcontrol.try_cancel` / `clusterlaunchcontrol.query_cancel`
(§9.7.14.18–19, PTX ISA 9.3)
**SASS core op:** `UGETNEXTWORKID` (opcode 0x13ca, `udp_pipe`, `$VQ_WORKID`=43)
**Status:** resolved empirically on `sm_100a` (CUDA 13.1).

New on sm100 (Blackwell). `clusterlaunchcontrol` is the PTX API for cooperative
work-stealing across CTAs in a cluster: one CTA asks the hardware work
distributor to cancel a not-yet-launched cluster and gain ownership of its work
items. At the SASS level the *try_cancel* atomic request is a single
**`UGETNEXTWORKID.SELFCAST`** instruction; the response is a 16-byte opaque blob
written to shared memory, decoded by normal arithmetic + `ISETP`/`LOP3`.

## The full lowering chain
```
PTX                                     SASS

mbarrier.init.shared::cta.b64[mbar],N  SYNCS.EXCH.64 [mbar], stateVal
barrier.cluster.arrive/wait             BARRIER.CLUSTER ...
ELECT (leader thread)                   ELECT P1, URZ, PT
clusterlaunchcontrol.try_cancel.async   UGETNEXTWORKID.SELFCAST [addr], [mbar]
  .mbarrier::complete_tx::bytes           (async write of 16B opaque handle)
  .multicast::cluster::all
mbarrier.try_wait                       MBARRIER.TRY_WAIT ...
LDS.128 handle←[addr]                  LDS.128 R{lo..hi}, [addr]
query_cancel.is_canceled handle→p      ISETP / LOP3 (bitfield decode)
query_cancel.get_first_ctaid handle→{x,y,z}  SHF / LOP3 (extract ctaid fields)
fence.proxy.async::generic             FENCE.VIEW.ASYNC...
```

Two pieces are special opcodes; the rest is standard arithmetic + mbarrier ops.
`UGETNEXTWORKID` is the only hardware work-stealing primitive; `SYNCS.EXCH.64`
is also used in other mbarrier/bookkeeping contexts.

---

## `UGETNEXTWORKID` — the work-stealing atomic request

**Opcode:** 0x13ca, `udp_pipe`, `INST_TYPE_DECOUPLED_RD_SCBD`, `$VQ_WORKID`=43.
Two operands — both non-zero uniform registers carrying shared-memory addresses:

### Format
`UGETNEXTWORKID.SELFCAST [URa], [URb]`

| operand | role |
|---------|------|
| `[URa]` | 16-byte aligned shared-memory address for the opaque **response handle** |
| `[URb]` | shared-memory mbarrier address (completion signalling via `.mbarrier::complete_tx::bytes`) |

`URa` and `URb` are a **register pair**: `URb = URa + 1`, fused by
`TABLES_URa_0(URa, URb)` into the 8-bit Ra field [31:24] — exactly the same
adjacent-pair encoding as `URe`/`URh` in the MMA `idesc` fusion.

### Modifiers
| Slot | Enum | Bits | Meaning |
|------|------|------|---------|
| `cast` | `UGETNEXTWORKID_CAST` | [72] | `SELFCAST`(0) = response to one CTA / `BROADCAST`(1) = response to all cluster CTAs |

`SELFCAST` matches PTX `.multicast::cluster::all` — the response handle is
written (via async proxy) to the local shared memory `[URa]` of each CTA in the
cluster, and completion is signalled through the mbarrier at each CTA's `[URb]`.
`BROADCAST` (cast=1) presumably writes only to the issuing CTA.

### Bit layout (128-bit)
```
[124:122]∥[109:105] opex       = TABLES_opex_0(batch_t, usched_info)
[121:116]           req_bit_set
[115:113]           src_rel_sb
[112:110]           dst_wr_sb  = *7
[103:102]           pm_pred
[91]∥[11:0]         opcode     = 0x13ca
[72]                cast       = SELFCAST(0)/BROADCAST(1)
[31:24]             TABLES_URa_0(URa, URb)  (= URa; URb=URa+1)
[15]                Pg_not ; [14:12] Pg = @UPg
```

`$VQ_WORKID` = 43 — a dedicated virtual queue for the work-distributor
interface (separate from `$VQ_TMEM`, `$VQ_SW_STATE`, `$VQ_TC_*`, etc.).

### Verified encoding
From the `clusterlaunchcontrol.try_cancel` lowering:
```
UGETNEXTWORKID.SELFCAST [UR6], [UR7]
  Lo64 0x00000000060073ca  Hi64 0x000fd80008000000
  opcode=0x13ca  Ra[31:24]=6 (UR6/UR7 pair)  cast=0 (SELFCAST)
```
Issue pattern: `ELECT` selects a leader thread; leader issues
`UGETNEXTWORKID.SELFCAST` (async, decoupled — `src_rel_sb` active, consumer waits
on the mbarrier completed by the work distributor).

---

## The rest of the chain (non-UGETNEXTWORKID pieces)

### `mbarrier.init` → `SYNCS.EXCH.64`
`mbarrier.init.shared::cta.b64 [mbar], count` lowers to `SYNCS.EXCH.64 URZ,
[URa], URb` — the `SYNCS` family (10 variants, `mio_pipe`) includes mbarrier
arrival/exchange/TCNT/PHASECHK/FLUSH operations (`SYNCS_EXCH` = exchange/write a
64-bit mbarrier state). The `SYNCS` family is separate from the UTC tcgen05 ops;
it is the cluster-wide mbarrier management API. (TODO: dedicated SYNCS analysis.)

### `query_cancel` → standard register ops, no unique SASS
`clusterlaunchcontrol.query_cancel.is_canceled` loads the 16-byte opaque handle
from shared memory (`LDS.128`) and decodes a predicate bit with `ISETP`/`LOP3`.
`get_first_ctaid` extracts the x/y/z CTA-id fields with `SHF`/`LOP3` bitfield
extracts. These are **not** distinct SASS opcodes — the handle is just a 128-bit
packed struct that software parses. (Confirmed: the query syntaxes generated no
unrecognized instructions in the probe.)

### `fence.proxy.async::generic` → `FENCE` variants
The proxy acquire/release fences between iterations of the work-stealing loop are
standard `FENCE` opcodes (already documented in `tcgen05_wait.md` and the
underlying `fence_`/`fence_g_`/`fence_t_` classes); no new opcode here.

---

## Where UGETNEXTWORKID fits in the broader picture
This is the **only hardware work-item API**. All work-stealing / cooperative
scheduling sits on:
1. **`UGETNEXTWORKID`** — atomic cancel+steal request (0x13ca).
2. **`SYNCS`** — mbarrier management (init/arrive/exchange/phasecheck).
3. **Standard mbarrier waits + cluster barriers** — ordering the stolen work.

The `clusterlaunchcontrol.query_cancel` response is a software-parsed 128-bit
blob; NVIDIA could change its format without a new opcode. This mirrors how
`idesc` carries MMA types rather than distinct opcodes — the API surface is PTX;
the hardware primitive is a narrow, stable async command.

## Cross-references
- `notes/sm100/instr/utcatomsws.md` — same `ELECT` + leader-lane async dispatch
  pattern, used by the TMEM allocator.
- `notes/sm100/instr/tcgen05_wait.md` — `FENCE.VIEW.ASYNC.*` used for proxy
  ordering between iterations.
- `notes/sm100/instr/utcbar.md` — `UTCBAR` for tcgen05 MMA completion; same
  mbarrier objects used for work-stealing completion.
- `notes/sm100/arch/control_codes.md` — `$VQ_WORKID` is part of the virtual
  queue namespace first seen here; the scheduling model is the same.

## Open questions
- Exact format of the 128-bit opaque response handle — what bits encode
  `is_canceled`, `ctaid.x/y/z`, and what the remaining fields are (the dump
  doesn't expose the WD-side microcode, so this is a pure SBI).
- `BROADCAST` (cast=1) — when does ptxas emit it (non-multicast try_cancel,
  or another use)?
- SYNCS.EXCH semantics — the `SYNCS` mbarrier family is a fertile separate topic.
