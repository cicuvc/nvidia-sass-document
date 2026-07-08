# UCGABAR_GET — CGA cluster-barrier query

**Opcode:** `0b1010111000111` = **0x15c7** | **Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_BRU_DEPBAR_RD_SCBD` | **VIRTUAL_QUEUE:** `VQ_UNORDERED` | compute-only (`SHADER_TYPE==CS`)

Read the thread-block-cluster (CGA) barrier state/token into a uniform register. Part of the CGA-barrier family (see `ucgabar_arv.md` for `ARV`/`WAIT`).

## Semantics
`@UPg UCGABAR_GET URd` — read the cluster barrier's current token/phase into uniform register `URd` [21:16]. A **`CGABAR_READERS`** member.

## Fields (128-bit)
| bits | field | notes |
|------|-------|-------|
| [91]∥[11:0] | opcode | 0x15c7 (b91=1) |
| [14:12]/[15] | `UPg`/`UPg_not` | uniform guard (7=UPT hidden) |
| [21:16] | `URd` | barrier token dest |

## Latency
`udp_pipe`, `CGABARRIER` resource. Writer→reader true-dependency of **6 cycles** from `ARV`/`SET`. `DECOUPLED_BRU`, `VQ_UNORDERED`.

## Not rendered (CUDA 13.1 nvdisasm gap)
nvdisasm does not render this opcode: hand-patching produces raw bytes only. The mnemonic exists in the sm_90 ISA DB but the shipped disassembler omits it. `URd` placement is spec-inferred.

## Verified encodings (decoder: `tools/decode_ucgabar.py`)
Field-level (spec-inferred, nvdisasm does not render):
| Lo64 | Hi64 | Decoder output |
|------|------|----------------|
| `0x00000000000575c7` | `0x000fe20008000000` | `UCGABAR_GET UR5` |

## Open questions
- Actual mnemonic rendering nvdisasm *would* use is unknown (unrendered).
- Which host construct emits GET — possibly driver/runtime cluster-launch setup.
- Exact `CGABARRIER` token layout is not spec-exposed.
