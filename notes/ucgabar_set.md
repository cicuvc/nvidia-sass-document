# UCGABAR_SET — CGA cluster-barrier set

**Opcode:** `0b1001111000111` = **0x13c7** | **Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD` | compute-only (`SHADER_TYPE==CS`)

Set/initialize the thread-block-cluster (CGA) barrier from a uniform register. Part of the CGA-barrier family (see `notes/ucgabar_arv.md` for `ARV`/`WAIT`).

## Semantics
`@UPg UCGABAR_SET URb` — set/initialize the cluster barrier from `URb` [37:32]. A **`CGABAR_WRITERS`** member.

## Fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | opcode | 0x13c7 (b91=1) |
| [14:12]/[15] | `UPg`/`UPg_not` | uniform guard |
| [37:32] | `URb` | source uniform reg |

## Latency
`udp_pipe`, `CGABARRIER` resource. Writes the barrier state; subsequent `CGABAR_READERS` see a 6-cycle true-dependency. `DECOUPLED_BRU`, `VQ_UNORDERED`.

## Not emitted / not rendered (CUDA 13.1)
Not produced by the sampled toolchain: cooperative-groups arrive/wait lower to `UCGABAR_ARV`/`_WAIT`. nvdisasm does not render these opcodes — hand-patching produces raw bytes only.

## Verified encodings (decoder: `tools/decode_ucgabar.py`)
Field-level (spec-inferred):
| Lo64 | Hi64 | Decoder output |
|------|------|----------------|
| `0x00000007000073c7` | `0x000fe20008000000` | `UCGABAR_SET UR7` |

## Open questions
- Actual mnemonic rendering nvdisasm *would* use is unknown (unrendered).
- Which host construct emits SET — possibly driver/runtime cluster-launch setup.
