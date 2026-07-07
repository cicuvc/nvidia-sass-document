# DADD — FP64 add

**Opcode mnemonic:** `DADD` = `0b1000101001` = **0x229** (RRR) + 4 operand-form variants | **Pipe:** `fma64lite_pipe` (FP64 datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_EMULATABLE`, `VIRTUAL_QUEUE=$VQ_REDIRECTABLE` | since sm_70

Double-precision add: `Rd = (±|Ra|) + (±|Rc|)`. Two 64-bit register-pair addends, each with
optional negate/absolute; IEEE rounding mode. No FTZ modifier — FP64 always keeps denormals.

## Semantics (verified)
`a + b` / `a - b` (via negate) / `__dadd_r{n,z,u,d}` → `DADD[.rnd] Rd, [-][|]Ra[|], [-][|]Rc[|]`.
Both operands are 64-bit pairs `Ra:Ra+1`, `Rc:Rc+1` (even-aligned, ≠R254). `Rd` likewise.

## Variant overview (5 CLASS variants — 2nd operand shape)
| opcode | form | 2nd source (`Rc`) |
|--------|------|-------------------|
| 0x229  | RRR  | register `Rc` [71:64] |
| 0x429  | RRsI | FP64 immediate (high 32b) [63:32] |
| 0x629  | RRC  | const bank c[bank][off] |
| 0x1629 | RRCx | const bank, extended |
| 0x1e29 | RRU  | uniform register `URb` [37:32] |

## Modifiers / fields (128-bit)
| bits | field | source | notes |
|------|-------|--------|-------|
| [91]∥[11:0] | `opcode` | 0x229… | selects operand form |
| [14:12]/[15] | `Pg`/`Pg_not` | guard | guard predicate (7=PT hidden) |
| [23:16] | `Rd` | Register | result pair |
| [31:24] | `Ra` | Register | addend A pair |
| [71:64] | `Rc` | Register | addend B pair (RRR) |
| [63:32] | imm | FP64 imm high-32b | RRsI (low 32b implied 0) |
| [37:32] | `Ra_URb` | uniform | RRU |
| [79:78] | `stride`=`rnd` | `Round1` | RN=0(hidden), RM=1, RP=2, RZ=3 |
| [72] | `Ra@negate` | `-Ra` | |
| [73] | `Ra@absolute` | `|Ra|` | |
| [75] | `Rc@negate` | `-Rc` | (subtraction) |
| [74] | `Rc@absolute` | `|Rc|` | |

**FP64 immediate**: only the high 32 bits of the double are encoded ([63:32]); the low 32 bits
are implicitly 0 (so only doubles representable in the top 32 bits, e.g. `2.5`=0x40040000…).

## Cross-comparison (FP64 family, all `fma64lite_pipe`)
| op | operation |
|----|-----------|
| **DADD** | `±|a| ± |b|` |
| **DMUL** | `a * b` |
| **DFMA** | `a*b + c` |
| **DSETP** | FP64 compare → predicate |
| **DMMA** | FP64 tensor MMA |

## Latency (from sm_90_latencies.txt)
`fma64lite_pipe`, in `FMALITE_OPS` (= fma64lite_pipe − DMMA − CLMAD − HFMA2MMA). Fixed-latency
FP64 op (slower than FP32 FMA; the FP64 unit is throughput-limited on most SKUs).
`COUPLED_EMULATABLE`/`VQ_REDIRECTABLE`: may be emulated / redirected to the FP64 unit.

## Verified encodings (sm_90, CUDA 13.1)
| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000000002067229` | `0x008fce0000000004` | `DADD R6, R2, R4` |
| `0x0000000002067229` | `0x008fce0000004004` | `DADD.RM R6, R2, R4` |
| `0x0000000002067229` | `0x008fce0000008004` | `DADD.RP R6, R2, R4` |
| `0x0000000002067229` | `0x008fce000000c004` | `DADD.RZ R6, R2, R4` |
| `0x0000000002067229` | `0x008fce0000000204` | `DADD R6, |R2|, R4` |
| `0x0000000002067229` | `0x008fce0000000804` | `DADD R6, R2, -R4` |
| `0x0000000602047e29` | `0x004fce0008000000` | `DADD R4, R2, UR6` |
| `0x4004000002047429` | `0x004fce0000000000` | `DADD R4, R2, 2.5` |

Decoder: `tools/decode_dadd.py` (all 8 vectors pass). Test: `tests/dadd_test.cu`.

### PTX→SASS mapping
- `a + b` (double) → `DADD Rd, Ra, Rc`; `a - b` → `DADD Rd, Ra, -Rc`
- `fabs(a) + b` → `DADD Rd, |Ra|, Rc`
- `__dadd_rn/rz/ru/rd` → `DADD` / `.RZ` / `.RP` / `.RM`
- `a + const` → RRsI (imm, if the double fits in high-32b) or RRC (const bank).

## Open questions
- Const-bank (RRC/RRCx) text form unverified (ptxas used RRU for the runtime const-param here).
