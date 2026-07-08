# LD — Load from generic address space

**Opcode mnemonics:** `LD` = `0b1100110000000` = **0x1980** (memdesc/uniform, 64-bit addr) / `0b100110000000` = **0x980** (plain imm-offset) | **Pipe:** `mio_pipe` | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD` | **VIRTUAL_QUEUE:** `VQ_AGU_UNORDERED_WR`

## Semantics
LD is the **generic-address-space** load: the target state space (global /
shared / local) is **resolved at runtime** from the pointer, rather than being
fixed at compile time as with `LDG` (global), `LDS` (shared), `LDL` (local). PTX
`ld.u32 [genericptr]` (no state-space qualifier) lowers to `LD`; the hardware AGU
inspects the address window and routes the access to the right memory. Otherwise
LD is structurally **identical to LDG** — same fields, modifiers, descriptor
addressing, and `mio_pipe` / decoupled-scoreboard behavior.

Address forms (same as LDG): `desc[URb][Ra.64+off]` (descriptor, sm_90 default),
`[Ra+URb+off]` (uniform), `[Ra+off]` (plain). On sm_90 ptxas always emits the
**memdesc** form `LD.E … desc[URb][Ra.64]`.

## Variant overview
| variant | opcode | memdesc | E | address |
|---|---|---|---|---|
| `ld__sImmOffset` | 0x980 | 0* | 0 | `[Ra+off]` (Ra≠RZ) |
| `ld__uImmOffset` | 0x980 | 0* | 0 | `[RZ+off]` |
| `ld_uniform__Ra32` | 0x1980 | 0 | 0 | `[Ra+URb+off]` |
| `ld_uniform__RaRZ` [ALT] | 0x1980 | 0 | 0 | `[URb+off]` |
| `ld_uniform__Ra64` | 0x1980 | 0 | 1 | `[Ra.64+URb+off]` |
| `ld_memdesc__Ra64` | 0x1980 | 1 | 1 | `desc[URb][Ra.64+off]` |

*Plain 0x980 hardwires memdesc=0 (bit [76] is `*0`). All observed sm_90 LD use
`ld_memdesc__Ra64` — same as LDG.

## Modifiers (identical set to LDG)
| modifier | field | bits | enum | values |
|---|---|---|---|---|
| `e` | e | [72] | E | noe=0 / `.E`=1 (64-bit extended addr; the norm) |
| `cop` | cop | [86:84] | COP | EF=0(`.EF`),EN=1(default),EL=2,LU=3,EU=4,NA=5 (6,7 illegal) |
| `sp2` | sp2 | [69:68] | SP2 | nosp2=0, LTC64B=1, LTC128B=2, LTC256B=3 |
| `sz` | sz | [75:73] | SZ_U8_S8_U16_S16_32_64_128 | U8=0,S8=1,U16=2,S16=3,32=4(default),64=5,128=6 (7 illegal) |
| `sem`/`sco`/`private` | mem | [80:77] | `TABLES_mem_1(...)` | WEAK/CONSTANT/STRONG/MMIO × scope × private |
| `memdesc` | memdesc | [76] | — | 0 plain / 1 desc |
| `Pnz` | Pnz | [67:64] | `TABLES_Pnz_0(Pnz@not,Pnz)` | NZ predicate (default PT, omitted) |

**Note:** LD uses `TABLES_mem_1` for the `mem` field, the **same table as LDG** —
so the sem/sco/private→code mapping is shared (0=WEAK default, 4=CONSTANT,
2=CTA, 10=STRONG.SYS, etc.). This is a slightly different table than the
`TABLES_mem_3` used by LDGSTS — the generic/global loads share one, the async
copy has its own.

Size drives `IDEST_SIZE = 32 + {64:+32,128:+96}` and Rd alignment
(`.64`→%2, `.128`→%4); `.E` drives `ISRC_A_SIZE = 32 + 32` (64-bit `Ra` pair).

## Bit layout (128-bit, ld_memdesc__Ra64)
| bits | field | source |
|---|---|---|
| [124:122],[109:105] | opex | `TABLES_opex_0(batch_t,usched_info)` |
| [121:116] | req_bit_set | scoreboard wait mask |
| [115:113] | src_rel_sb | `VarLatOperandEnc(rd)` |
| [112:110] | dst_wr_sb | `VarLatOperandEnc(wr)` |
| [103:102] | pm_pred | perfmon predicate |
| [91]∥[11:0] | opcode | 0x1980 |
| [90] | input_reg_sz | 64-bit Ra distinguisher (`*`) |
| [86:84] | cop | COP |
| [80:77] | mem | sem/sco/private (`TABLES_mem_1`) |
| [76] | memdesc | 1 (desc form) |
| [75:73] | sz | size |
| [72] | e | E |
| [69:68] | sp2 | SP2 |
| [67:64] | Pnz | `TABLES_Pnz_0` |
| [63:40] | Ra_offset | 24-bit signed offset |
| [37:32] | Ra_URb | memory descriptor UR |
| [31:24] | Ra | address register |
| [23:16] | Rd | destination register |
| [15] / [14:12] | Pg_not / Pg | predicate |

(The plain 0x980 form widens `Ra_offset` to 32 bits [63:32] and has no `Ra_URb`.)

## Cross-comparison (load family)
| op | opcode | space | note |
|---|---|---|---|
| **LD** | 0x1980/0x980 | **generic** (runtime-resolved) | this note |
| `LDG` | 0x1981/0x381 | global | `ldg.md` — same fields, `TABLES_mem_1` |
| `LDS` | — | shared | `lds.md` |
| `LDL` | — | local | `ldl.md` |
| `LDC` | — | constant | `ldc.md` |

LD and LDG differ by **only one opcode bit** (0x1980 vs 0x1981) and are otherwise
field-identical — LDG is the space-specialized fast path, LD the generic fallback
when the pointer's space is statically unknown (e.g. a `void*` that may address
global or shared). ptxas prefers the specialized ops when it can prove the space.

## Latency (from `sm_90_latencies.txt`)
`LD` ∈ `mio_pipe` (MIO_SLOW_OPS), `VQ_AGU_UNORDERED_WR`, decoupled read/write
scoreboard — the load result is tracked by a `dst_wr_sb` (unlike the async ops).
Same latency class as LDG/LDS/STS.

## Verified encodings (`tests/ld_test.cu`, sm_90a, CUDA 13.1)
| Lo64 | Hi64 | Disassembly | PTX |
|---|---|---|---|
| `0x0000000402037980` | `0x001eaa000c101900` | `LD.E R3, desc[UR4][R2.64]` | `ld.u32` |
| `0x0000000402037980` | `0x001eaa000c101100` | `LD.E.U8 R3, desc[UR4][R2.64]` | `ld.u8` |
| `0x0000000402037980` | `0x001eaa000c101500` | `LD.E.U16 R3, desc[UR4][R2.64]` | `ld.u16` |
| `0x0000000402027980` | `0x001eaa000c101b00` | `LD.E.64 R2, desc[UR4][R2.64]` | `ld.u64` |
| `0x0000000402087980` | `0x001eaa000c101d00` | `LD.E.128 R8, desc[UR4][R2.64]` | `ld.v4.u32` |
| `0x0000100404057980` | `0x001eaa000c115900` | `LD.E.STRONG.SYS R5, desc[UR4][R4.64+0x10]` | `ld.volatile.u32 [+16]` |

Decoder `tools/decode_ld.py`: **6/6 PASS**. `sz` is Hi64 low nibble
(`...19`=32, `...11`=U8, `...15`=U16, `...1b`=64, `...1d`=128); `.volatile` →
`mem=10` (`STRONG.SYS`, `...59`); the 24-bit offset (`+0x10`) sits in [63:40].

### PTX→SASS mapping
| PTX | SASS (sm_90) |
|---|---|
| `ld.u32 [genericptr]` | `LD.E R, desc[URb][Ra.64]` |
| `ld.u8/u16/u64` | `LD.E.U8 / .U16 / .64` |
| `ld.v4.u32` | `LD.E.128` |
| `ld.volatile.u32 [p+16]` | `LD.E.STRONG.SYS R, desc[URb][Ra.64+0x10]` |
| `ld.global.*` | `LDG.E …` (space-specialized, not LD) |

**Key finding:** `ld.volatile` (generic) → `LD.E.STRONG.SYS` — the volatile
qualifier maps to the strongest memory ordering (`STRONG` semantics, `SYS`
scope, `TABLES_mem_1` code 10), forcing the access to bypass caching/coalescing
and observe system-wide ordering.

## Open questions
- Non-memdesc / plain 0x980 forms — same open question as LDG; not emitted by
  ptxas on sm_90 (all use the descriptor form).
- SP2 sector-cache prefetch on generic LD — not triggered here.
- Whether a truly space-ambiguous pointer that resolves to *shared*/*local* at
  runtime still uses this `desc[URb]` global-style descriptor, or if the AGU
  reinterprets it per resolved space.
