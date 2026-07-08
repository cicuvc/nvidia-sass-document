# UTMACCTL — Uniform TMA cache control (tensor-map descriptor coherence)

**Opcode mnemonics:** `UTMACCTL` = `0b1100110111001` = **0x19b9** (`_URa_`: `.IV`/`.PF` + operand) / `0b100110111001` = **0x9b9** (`_`: `.IVALL`, no operand) | **Pipe:** `udp_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` (URa form) / `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD` (IVALL form) | **VIRTUAL_QUEUE:** `VQ_TMA_UNORDERED_WR` (35) | compute-only (`SHADER_TYPE==CS`)

## Semantics
UTMACCTL manages the coherence of **tensor-map descriptors** in the TMA
descriptor cache. A `CUtensorMap` may be mutated in global memory (via
`tensormap.replace`) and then re-consumed by TMA copies; because the TMA engine
caches descriptors, software must **invalidate/prefetch** the cached copy across
the tensormap *proxy*. UTMACCTL is the SASS lowering of PTX
**`fence.proxy.tensormap`** (acquire → `.IV`) and **`prefetch.tensormap`**
(→ `.PF`).

Two encodings:
- **0x19b9 (`utmacctl_URa_`)** — takes a uniform-register **descriptor address**
  `[URa]` (64-bit, `ISRC_A_SIZE=64`) and a `cop` modifier:
  - `.IV` — **invalidate** the cached descriptor at `[URa]` (acquire-proxy fence)
  - `.PF` — **prefetch** the descriptor at `[URa]` into the TMA cache
- **0x9b9 (`utmacctl_`)** — operandless, `.IVALL` modifier — **invalidate all**
  cached descriptors (no address). `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD`
  suggests it also participates in the DEPBAR/branch-unit dependency machinery.

## Variant overview
| variant | opcode | operand | modifier | INST_TYPE |
|---|---|---|---|---|
| `utmacctl_URa_` | 0x19b9 | `[URa]` | `.IV` / `.PF` (`cop`) | DECOUPLED_RD_SCBD |
| `utmacctl_` | 0x9b9 | — | `.IVALL` (`ivall`) | DECOUPLED_BRU_DEPBAR_RD_SCBD |

## Modifiers
| modifier | field | bits | enum | values |
|---|---|---|---|---|
| `cop` (0x19b9) | fc | [82] | COP_utmacctl | IV=0, PF=1 |
| `ivall` (0x9b9) | clear | [83] | IVALLONLY_utmacctl | IVALL=1 |
| `batch_t`,`usched_info` | opex | [124:122],[109:105] | `TABLES_opex_0` | scheduling |
| `pm_pred` | pm_pred | [103:102] | PM_PRED | perfmon predicate |

## Bit layout (128-bit map)
### 0x19b9 (URa form)
| bits | field | source |
|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_0(batch_t,usched_info)` |
| [121:116] | req_bit_set | scoreboard wait mask |
| [115:113] | src_rel_sb | `VarLatOperandEnc(rd)` — READ scoreboard for `[URa]` |
| [112:110] | dst_wr_sb | `*7` |
| [103:102] | pm_pred | perfmon predicate |
| [91]∥[11:0] | opcode | 0x19b9 |
| [82] | fc | cop (IV/PF) |
| [29:24] | Sa | URa (descriptor addr, 64-bit) |
| [15] / [14:12] | Pg_not / Pg | predicate |

### 0x9b9 (IVALL form)
| bits | field | source |
|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_0(batch_t,usched_info)` |
| [121:116] | req_bit_set | scoreboard wait mask |
| [115:113] | src_rel_sb | `*7` (no source) |
| [112:110] | dst_wr_sb | `*7` |
| [91]∥[11:0] | opcode | 0x9b9 |
| [83] | clear | ivall (IVALL) |
| [15] / [14:12] | Pg_not / Pg | predicate |

Note both are among the **shortest** opcodes in the TMA family — 0x9b9 is a
12-bit value (bit [91]=0), unlike the 13-bit 0x13xx copy opcodes.

## Cross-comparison (TMA family)
| op | PTX | opcode | role |
|---|---|---|---|
| `UTMALDG` | `cp.async.bulk.tensor` load | 0x15b4/0x13b4 | data copy g→s |
| `UTMASTG` | `cp.async.bulk.tensor` store | 0x13b5 | data copy s→g |
| `UTMAREDG` | `cp.reduce.async.bulk.tensor` | 0x13b6 | reduce s→g |
| `UBLKCP` | `cp.async.bulk` | 0x13ba | non-tensor copy |
| **UTMACCTL** | `fence.proxy.tensormap` / `prefetch.tensormap` | **0x19b9 / 0x9b9** | descriptor cache control |

All `udp_pipe` / `VQ_TMA_UNORDERED_WR`. UTMACCTL is the odd one out — it moves no
tile data, only manages descriptor-cache coherence.

## Latency (from `sm_90_latencies.txt`)
`UTMACCTL` ∈ `OP_TMA` (`sm_90_latencies.txt:166`) ⊂ `udp_pipe`. Decoupled
read-scoreboard op, all `*_SIZE=0` except `ISRC_A_SIZE=64` (URa form). The IVALL
form's `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD` ties it into the DEPBAR path.

## Verified encodings (`tests/utmacctl_test.cu`, sm_90a, CUDA 13.1)
| Lo64 | Hi64 | Disassembly | source PTX |
|---|---|---|---|
| `0x00000000040079b9` | `0x0003e20008000000` | `UTMACCTL.IV [UR4]` | `fence.proxy.tensormap::generic.acquire.<scope> [p],128` |
| `0x00000000040079b9` | `0x0001e40008040000` | `UTMACCTL.PF [UR4]` | `prefetch.tensormap [p]` |

Decoder `tools/decode_utmacctl.py`: **2/2 empirical PASS** + 1 spec-derived
(`UTMACCTL.IVALL`, 0x9b9, not emitted by stock PTX here).

### PTX→SASS mapping
| PTX | SASS |
|---|---|
| `fence.proxy.tensormap::generic.acquire.{cta,cluster,gpu,sys} [p], 128` | **`UTMACCTL.IV [URa]`** (preceded by `DEPBAR {5..0}`) |
| `prefetch.tensormap [p]` | **`UTMACCTL.PF [URa]`** |
| `fence.proxy.tensormap::generic.release.<scope>` | **`MEMBAR.ALL.GPU` + `ERRBAR` + `CGAERRBAR`** (not UTMACCTL — the *release* side is a memory barrier, not a cache-control op) |
| `tensormap.cp_fenceproxy…` | fused `ATOMG.E.EXCH.STRONG.GPU` (copy) + fence (no UTMACCTL in the tested form) |

**Key finding:** only the **acquire** side of `fence.proxy.tensormap` lowers to
`UTMACCTL.IV` (invalidate the stale cached descriptor before re-reading); the
**release** side becomes a plain `MEMBAR.ALL.GPU`+`ERRBAR`/`CGAERRBAR` sequence.
The `.IV` acquire is emitted **after** a `DEPBAR {5,4,3,2,1,0}` (drain all
scoreboards) — coherence point ordering.

Corroborates `../arch/memory_model.md` ("fence.proxy.tensormap → UTMACCTL.IV"),
now confirmed with the exact 0x19b9 encoding and the `.PF`/`.IVALL` siblings.

## Open questions
- What triggers the operandless **`UTMACCTL.IVALL`** (0x9b9) from PTX — likely a
  bulk-invalidate on kernel entry/exit or a driver-level descriptor flush; not
  reproduced from user PTX here.
- The `.acquire` scope (`.cta/.cluster/.gpu/.sys`) does **not** change the SASS
  (`UTMACCTL.IV` identical for gpu/cta/sys) — scope has no instruction-level
  field; ordering is enforced by the preceding `DEPBAR`.

