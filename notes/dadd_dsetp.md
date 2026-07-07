# DADD — FP64 Add

**Opcode:** `0x229` (RRR), `0x429` (RRsI), `0x629` (RRC), `0x1629` (RRCx), `0x1e29` (RRU)  
**Pipe:** `fma64lite_pipe`, `$VQ_REDIRECTABLE`  
**TYPE:** `INST_TYPE_COUPLED_EMULATABLE`

## Semantics

`Rd = Ra + Rb` in double-precision (FP64). Mirrors FADD (F32) but with 64-bit
register pairs.

## Format

`@Pg DADD{.rnd} Rd, [-]|[||]Ra{.reuse}, [-]|[||]Rb{.reuse}`

## Verified encodings

| Disassembly | PTX |
|-------------|-----|
| `DADD R2, R6, UR4` | `add.rn.f64` |
| `DADD.RM R6, R6, UR4` | `add.rm.f64` |

## PTX to SASS

| PTX | SASS |
|-----|------|
| `add.rn.f64 %rd, %ra, %rb` | `DADD Rd, Ra, URb` |
| `add.rm.f64` | `DADD.RM` |
| `add.rp.f64` | `DADD.RP` |
| `add.rz.f64` | `DADD.RZ` |
| `sub.f64` | `DADD Rd, Ra, -URb` (negate Rb) |

## DSETP — FP64 Compare-Set-Predicate

**Opcode:** `0x22a` (RRR), `0x42a` (RRsI), `0x62a` (RRC), `0x162a` (RRCx), `0x1e2a` (RRU)  
**Pipe:** `fma64lite_pipe`, `$VQ_REDIRECTABLE`

### Semantics

Compares two FP64 values and writes the result to predicate registers.

`Pu, Pv = Ra DSETP_FCMP Rb`

### Format

`DSETP.{test}{.bop} Pu, Pv, [-]|[||]Ra, [-]|[||]Rb, [!]Pp`

- `DSETP_FCMP`: 16 values (MIN=0, LT=1, EQ=2, LE=3, GT=4, NE=5, GE=6, NUM=7, NAN=8, LTU=9, EQU=10, LEU=11, GTU=12, NEU=13, GEU=14, MAX=15)
- `Bop`: AND, OR, XOR — boolean operation combining Pu/Pv results

### Verified encodings

| Disassembly | PTX |
|-------------|-----|
| `DSETP.LEU.AND P0, PT, R6, UR4, PT` | `setp.leu.f64` |
