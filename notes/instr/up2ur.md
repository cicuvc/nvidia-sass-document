# UP2UR — Uniform Predicate to Uniform Register

**Opcode mnemonic:** UP2UR  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Copies the hardware uniform predicate register (`UPR`) into a uniform register (`URd`), optionally combined with a source register and an immediate/register offset.

The `UPR` is a special single-bit uniform predicate that represents the result of warp-wide voting or predicate reduction. UP2UR expands this single bit into a full 32-bit URd value (0 or 1).

The `insert` modifier (B3B0) selects which byte lane of URd receives the UPR value:
- `B0` (0) — insert into byte 0 (bits [7:0])
- `B1` (1) — insert into byte 1
- `B2` (2) — insert into byte 2
- `B3` (3) — insert into byte 3

Three forms exist:
- **Simple:** `UP2UR.B0 URd, UPR` — just predicate-to-register
- **Imm:** `UP2UR.B0 URd, UPR, URa, imm32` — predicate + register + immediate
- **URb:** `UP2UR.B0 URd, UPR, URa, URb` — predicate + two registers

## Variant overview

| Variant | Opcode | Pattern | Notes |
|---------|--------|---------|-------|
| `up2ur__URb` | `0x1c83` | `UP2UR.Bx URd, UPR, URa, URb` | Two-register form |
| `up2ur_simple_` (ALT) | `0x1883` | `UP2UR.Bx URd, UPR` | Simple form (Ra_offset=255, URa=URZ) |
| `up2ur__Imm` | `0x1883` | `UP2UR.Bx URd, UPR, URa, imm32` | Immediate form |

No empirical examples of any variant found in libcublas or ptxas-generated code on sm_90, CUDA 13.1.

## Modifiers

| Modifier | Field | Bits | Values |
|----------|-------|------|--------|
| `insert` | insert | [77:76] | 0=B0, 1=B1, 2=B2, 3=B3 |

## Bit layout

### up2ur_simple_ (ALT) / up2ur__Imm — opcode 0x1883

The simple form is distinguished by `Sa=URZ(63)` and `Ra_offset=255`; the imm form uses a live URa and a 32-bit immediate.

```
[124:122],[109:105]  opex                <= TABLES_opex_1
[121:116]            req_bit_set
[115:113]            src_rel_sb           <= *7
[112:110]            dst_wr_sb            <= *7
[103:102]            pm_pred
[91:91],[11:0]       opcode               <= 0b1100010000011
[77:76]              insert               <= insert (B3B0)
[63:32]              Ra_offset            <= *255 (simple) / Sb (imm)
[29:24]              Sa                   <= *63 (simple) / URa (imm)
[21:16]              URd                  <= URd
[15:15]              Pg_not               <= UPg@not
[14:12]              Pg                   <= UPg
```

### up2ur__URb — opcode 0x1c83

```
[124:122],[109:105]  opex                <= TABLES_opex_1
[121:116]            req_bit_set
[115:113]            src_rel_sb           <= *7
[112:110]            dst_wr_sb            <= *7
[103:102]            pm_pred
[91:91],[11:0]       opcode               <= 0b1110010000011
[77:76]              insert               <= insert (B3B0)
[37:32]              Ra_URb               <= URb
[29:24]              Sa                   <= URa
[21:16]              URd                  <= URd
[15:15]              Pg_not               <= UPg@not
[14:12]              Pg                   <= UPg
```

## Latency

UP2UR is in `udp_pipe` and belongs to the `OP_UP2UR` latency group. The latency file groups it with `WHOLE_UPRED_OPS` using the `UPR_UPRED` connector, indicating UP2UR reads from a special `UPR` register file (distinct from the GPR/UGPR uniform register file).

In the UGPR latency tables, UP2UR falls under the `UDP_subset` group (it is not in ULDC_VOTEU_UMOV_ULEPC or R2UR_S2UR). Latency characteristics match standard udp_pipe ops:

```
TABLE_TRUE(UGPR): UDP_subset → {URd} : 4 12 12 8 12 7 9 12 12 10 9
TABLE_OUTPUT(UGPR): {URd} : 1 4 7 7
TABLE_ANTI(UGPR): {URa} : 1 1 1 3
```

Output latency: **1–7 cycles**. True-dependency: **4–12 cycles** (heavily role-dependent).

## Cross-comparison

### UP2UR vs UR2UP

| Property | UP2UR | UR2UP |
|----------|-------|-------|
| Direction | Predicate → Register | Register → Predicate |
| Source | `UPR` (special uniform predicate) | Uniform Register (`URa`) |
| Dest | `URd` (uniform register) | `UPP` (uniform predicate destination) |
| Pipe | `udp_pipe` | `udp_pipe` |
| Latency set | `OP_UP2UR` / `WHOLE_UPRED_OPS` | `OP_UR2UP` |

Both instructions use the `UPR_UPRED` connector in the latency file and are grouped together in `WHOLE_UPRED_OPS`.

## Open questions

- **No empirical examples:** Neither `UP2UR` nor `UR2UP` appear in libcublas or ptxas-generated code. These instructions likely serve internal purposes (e.g., reading hardware predicate state for TMA completion tracking, or warp-level voting that needs to spill to a register).
- **UPR register semantics:** What hardware conditions set the `UPR` bit? Is it written by `VOTEU` (uniform vote), `USETP`/`UPSETP`, or a separate hardware mechanism?
- **B3B0 byte insert:** Why insert a single-bit predicate into a byte? This suggests `UPR` may pack multiple 1-bit predicates into a 32-bit word, and `B3B0` selects which one to expand.
