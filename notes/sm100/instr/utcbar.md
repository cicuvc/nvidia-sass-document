# UTCBAR — tcgen05 tensor-core barrier  → PTX `tcgen05.commit`

**Opcode mnemonic:** `UTCBAR` — two opcodes:
commit/arrive = `0b1001111101001` (0x13e9), flush = `0b100111101001` (0x9e9)
**Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` (commit) / `DECOUPLED_WR_SCBD` (flush)
**Virtual queue:** `$VQ_TC_1CTA` (=41) / `$VQ_TC_2CTA` (=42) commit; `$VQ_UNORDERED` flush

New on sm100 (Blackwell). `UTCBAR` = **U**niform **T**ensor-**C**ore **BAR**rier.
The mbarrier-arrive form is the SASS realization of PTX **`tcgen05.commit`**: it
makes an mbarrier object track completion of all prior async `tcgen05` ops issued
by the thread, signalling an arrive-on when they finish.

## Semantics (commit form, 0x13e9)
`UTCBAR[.2CTA][.MULTICAST] [URa], URb [, URc]`
- **`[URa]`** — the mbarrier shared-memory address (a `.b64` mbarrier object).
- **`URb`** — parameter/count operand (observed `URZ`; the arrive count is fixed
  at 1 by `.mbarrier::arrive::one`, so ptxas passes `URZ`).
- **`URc`** — `ctaMask` for `.MULTICAST` (which cluster CTAs to signal); `URZ`
  otherwise. A CONDITION enforces `multicast==nomulticast -> URc==URZ`.

On execution the instruction is async (`DECOUPLED_RD_SCBD`, `src_rel_sb` active);
upon completion of the tracked tcgen05 ops the hardware performs the arrive-on the
mbarrier. Consumers then `mbarrier.try_wait` on it (a normal MBAR wait, not a
tcgen05 op).

## Variant overview
| Class | Kind | Opcode | Form |
|-------|------|--------|------|
| `utcbar__1CTA` | CLASS | 0x13e9 | commit, `1CTA` (`$VQ_TC_1CTA`) |
| `utcbar__2CTA` | CLASS | 0x13e9 | commit, `2CTA` (`$VQ_TC_2CTA`) |
| `utcbar_one__1CTA` | ALT | 0x13e9 | + `.ONE` |
| `utcbar_one__2CTA` | ALT | 0x13e9 | + `.ONE` |
| `utcbar_flush_` | CLASS | 0x9e9 | flush (`$VQ_UNORDERED`) |
| `utcbar_flush_one_` | ALT | 0x9e9 | flush + `.ONE` |

The flush form (`UTCBAR.FLUSH`, 0x9e9) is a separate opcode with no address
operands — a plain drain/flush of the tensor-core pipe. Not emitted by
`tcgen05.commit`; not observed in these tests. The `_one_` alternates are
encoding-identical (`.ONE` display-only).

## Modifiers (commit form)
| Slot | Enum | Bits | Meaning |
|------|------|------|---------|
| `cluster_sz` | `ONLY1CTA`/`ONLY2CTA` | [85] (`ignoreKill`) | `1CTA` / `2CTA` (PTX `.cta_group`) |
| `multicast` | `MULTICAST` | [75] | `.MULTICAST` (signal cluster CTAs via `URc` mask) |
| `wakeup` | `WAKEUP` | [76] | `WAKEUP` |
| `paramtype` | `BAR_TYPE` | [77] | `A1T0`(0, default) / `A0TX`(1) |

`BAR_TYPE` (arrive/track parameterization): `A1T0`=0, `A0TX`=1. `WAKEUP`,
`MULTICAST` are 0/1. `cluster_sz` selects the virtual queue and sets bit[85].

## Bit layout (128-bit, commit form)
```
[124:122]∥[109:105] opex        = TABLES_opex_0(batch_t, usched_info)
[121:116]           req_bit_set  = wait barrier mask
[115:113]           src_rel_sb   = read-scoreboard release
[112:110]           dst_wr_sb    = *7 (pinned)
[103:102]           pm_pred
[91]∥[11:0]         opcode       = 0x13e9
[85]                ignoreKill   = cluster_sz (2CTA)
[77]                NaN          = paramtype (BAR_TYPE)
[76]                memdesc      = wakeup
[75]                input_reg_sz_32_bit75_dist = multicast
[71:64]             Ra_URc       = URc (ctaMask, MULTICAST)
[39:32]             Rb           = URb (param/count)
[31:24]             Ra           = URa (mbarrier address)
[15]                Pg_not ; [14:12] Pg = @UPg (UniformPredicate)
```
(Internal field names `NaN`/`memdesc`/`ignoreKill` are legacy reuse; their values
here encode BAR_TYPE / wakeup / cluster size.)

## Verified encodings (cuobjdump, `nvcc -arch=sm_100a`, CUDA 13.1)
Source: `tests/tcgen05_commit_test.cu` → `tests/tcgen05_commit_test.cubin`.
Decoder: `tools/decode_utcbar.py` — all round-trip (**ALL PASS**).

| Disassembly | Lo64 / Hi64 | 2CTA | mcast | URa | URc |
|-------------|-------------|:----:|:-----:|:---:|:---:|
| `UTCBAR [UR4], URZ` | `…73e9` / `…080000ff` | 0 | 0 | UR4 | URZ |
| `UTCBAR.2CTA [UR4], URZ` | `…73e9` / `…082000ff` | 1 | 0 | UR4 | URZ |
| `UTCBAR.MULTICAST [UR4], URZ, UR10` | `…73e9` / `…0800080a` | 0 | 1 | UR4 | UR10 |

Confirmed facts:
- `tcgen05.commit.cta_group::1.mbarrier::arrive::one.b64 [mbar]` → `UTCBAR [URa], URZ`
  (URa = mbarrier shmem address; count operand passed as URZ).
- `.cta_group::2` → `.2CTA` (bit[85]); requires a cluster launch
  (`__cluster_dims__`).
- `.multicast::cluster [mbar], ctaMask` → `.MULTICAST` (bit[75]) with the 16-bit
  `ctaMask` in `URc` (UR10).
- Like the allocator sequence, `UTCBAR` is issued under `ELECT` (single leader
  lane), consistent with warp-collective tcgen05 semantics.

## Where UTCBAR fits (the tcgen05 sync taxonomy)
| PTX | SASS | role |
|-----|------|------|
| `tcgen05.commit` | **`UTCBAR`** (0x13e9) | mbarrier tracks async-op completion |
| `tcgen05.wait::st` | `FENCE.VIEW.ASYNC.T` | blocking completion wait (store) |
| `tcgen05.wait::ld` | (scoreboard) | blocking completion wait (load) |
| `tcgen05.fence::*_thread_sync` | (none) | compile-time code-motion fence |

`commit` is the **non-blocking / mbarrier-based** completion mechanism (the thread
continues; the mbarrier fires later), whereas `wait::*` are **blocking** waits.
The two are alternatives from the PTX "mbarrier based completion mechanism".

## Cross-references
- `notes/sm100/instr/tcgen05_wait.md` — the blocking completion waits.
- `notes/sm100/instr/tcgen05_fence.md` — the no-op code-motion fences.
- `notes/sm100/instr/utccp.md` — a typical async producer whose completion
  `UTCBAR` commits to an mbarrier.
- `notes/sm90/arch/tma_mbarrier.md` — mbarrier model (TMA on Hopper); the same
  mbarrier objects `tcgen05.commit` arrives on.
- `notes/sm100/instr/utcatomsws.md` — sibling `UTC*` uniform tensor-core op.

## Latency (sm100_latencies.txt)
`UTCBAR` is part of `OP_TMA_TC` (line 214) — the tensor-core/TMA async op group;
subtracted from `UDP_subset`, handled as a scoreboard-gated async op. The
mbarrier arrive fires on tracked-op completion, not a fixed latency-table cycle.

## Open questions
- Exact meaning of `URb` (the param/count operand) beyond `URZ` — does any PTX
  form pass a non-zero count/handle here?
- `BAR_TYPE` `A1T0` vs `A0TX` semantics (arrive-count/thread-count parameterization?) —
  only `A1T0` (default) observed.
- When is the flush form (`UTCBAR.FLUSH`, 0x9e9) emitted? Not from
  `tcgen05.commit`; likely an internal pipe-drain (maybe around dealloc or
  kernel exit) — needs a workload that surfaces it.
- Runtime effect of `WAKEUP`.
