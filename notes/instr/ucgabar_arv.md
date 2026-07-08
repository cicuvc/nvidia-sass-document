# UCGABAR_ARV — CGA (thread-block cluster) barrier arrive

**Opcode mnemonic:** `UCGABAR_ARV` = `0b1100111000111` = **0x19c7** | **Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD` | **VIRTUAL_QUEUE:** `VQ_UNORDERED` | compute-only (`SHADER_TYPE==CS`)

Signals **arrival at the thread-block-cluster (CGA) barrier** on Hopper — the uniform-
datapath primitive behind `cooperative_groups::cluster_group::barrier_arrive()`. Part of the
CGA-barrier family `UCGABAR_ARV`/`_WAIT`/`_GET`/`_SET` (all `udp_pipe`), which coordinate a
cluster of CTAs via the on-chip `CGABARRIER` resource.

## Semantics
`@UPg UCGABAR_ARV[.SYNCALL]` marks this participant as arrived at the cluster barrier
(updating the barrier's arrival count). It is a **uniform** op (one action per uniform
datapath, guarded by a **uniform predicate** `UPg`), takes no register operands, and does
not itself block — the matching `UCGABAR_WAIT` blocks until all participants arrive.
`.SYNCALL` requests an all-participant sync variant.

## Family (all `udp_pipe`, uniform-predicate guarded)
| mnem | opcode | role |
|------|--------|------|
| **UCGABAR_ARV** | 0x19c7 | arrive (update arrival count) |
| UCGABAR_WAIT | 0x1dc7 | wait until the barrier is satisfied |
| UCGABAR_GET | 0x15c7 | read the barrier token/state into `URd`[21:16] |
| UCGABAR_SET | (udp) | set/initialize the barrier |

(`UCGABARARV`/`UCGABARWAIT`/… are alias spellings of the same opcodes.)

## Operands / fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | opcode | 0x19c7 (b91=1) |
| [14:12]/[15] | `UPg`/`UPg_not` | **uniform**-predicate guard (7=UPT hidden → `@UP<n>`) |
| [72] | `syncall` | → `.SYNCALL` |

No `Sb`/`Rd`/register operands (all `ISRC_*`/`IDEST_*` = 0). `UCGABAR_GET` adds `URd`[21:16].

## Latency — the CGABARRIER resource
There is a dedicated **`CGABARRIER`** hard resource (`sm_90_latencies.txt:365`):
- **`CGABAR_WRITERS`** = {`UCGABAR_ARV`, `UCGABAR_SET`} — arrive/set **update** the barrier,
- **`CGABAR_READERS`** = {`UCGABAR_ARV`, `UCGABAR_WAIT`, `UCGABAR_GET`, **`EXIT`**} — read it,
- `TABLE_TRUE(CGABARRIER)`: a writer→reader true-dependency of **6 cycles** (line 373).

So `UCGABAR_ARV` is **both a reader and a writer** (arrive reads the current state and posts
its arrival), and — notably — **`EXIT` is a reader**: a thread cannot retire while its CGA
barrier participation is outstanding (matches the EXIT note's GMMA/CGA wait). `udp_pipe`,
`DECOUPLED_BRU`, `VQ_UNORDERED`, `MIN_WAIT_NEEDED=1`.

## Verified encodings (decoder: `tools/decode_ucgabar.py`)
Self-test 4/4; `tests/ucgabar_test.cu` (`cluster.barrier_arrive()`/`barrier_wait()`) 3/3
(2×ARV + WAIT). `@UP` guards via cubin-patch.

| Lo64 | Hi64 | Disassembly | src |
|------|------|-------------|-----|
| 0x00000000000079c7 | 0x000fe20008000000 | `UCGABAR_ARV` | `cluster.barrier_arrive()` |
| 0x0000000000007dc7 | 0x000fe20008000000 | `UCGABAR_WAIT` | `cluster.barrier_wait()` |
| 0x00000000000019c7 | 0x000fe20008000000 | `@UP1 UCGABAR_ARV` | patch |
| 0x00000000000099c7 | 0x000fe20008000000 | `@!UP1 UCGABAR_ARV` | patch |

Hand-check `UCGABAR_ARV`: opcode [11:0]=0x9c7, bit91=1 (hi bit27) → 0x19c7; `UPg`[14:12]=7 →
UPT (no guard); `syncall`[72]=0.

### PTX→SASS mapping
`cluster_group::barrier_arrive()` → `UCGABAR_ARV`; `barrier_wait(token)` → `UCGABAR_WAIT`.
Emitted for `__cluster_dims__` kernels using cluster-scope synchronization. Real cluster
`.sync()` also emits `BAR.*`/`MEMBAR` (see `bar.md`); the UCGABAR ops are the CGA-barrier-
specific piece.

## Open questions
- `.SYNCALL` and the `UCGABAR_GET`/`_SET` operand encodings did not render under cubin-patch
  (nvdisasm printed raw bytes), so they are documented from the spec only; the `_GET` `URd`
  and `_SET` semantics are unverified against real output.
- Exact `CGABARRIER` state layout (arrival count / phase) is not spec-exposed.
