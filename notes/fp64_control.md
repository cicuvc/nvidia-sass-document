# FP64 Math — DFMA / DADD / DMUL / DSETP

**Pipe:** `fma64lite_pipe`  
**TYPE:** `INST_TYPE_COUPLED_EMULATABLE`, `$VQ_REDIRECTABLE`

## Overview

FP64 mirror of the FADD/FMUL/FFMA/FSETP family. All operands are 64-bit
(`ISRC_A_SIZE=64`), requiring register pairs (R2n:R2n+1).

| Instruction | Opcode (RRR) | Variants | Operands | PTX |
|-------------|:---:|:---:|:---:|------|
| DFMA | `0x22b` | 9 | Rd, Ra, Rc | `fma.rn.f64` |
| DADD | `0x229` | 5 | Rd, Ra | `add.f64` |
| DMUL | `0x228` | 5 | Rd, Ra | `mul.f64` |
| DSETP | `0x22a` | 10 | Pu, Pv, Ra, Rc | `setp.*.f64` |

## Verified encodings

| Disassembly | PTX |
|-------------|-----|
| `DADD R2, R6, UR4` | `add.f64` (RUR) |
| `DMUL R6, R6, UR4` | `mul.f64` (RUR) |
| `DFMA R8, R6.reuse, UR4, R8` | `fma.rn.f64` (RUR_RUR) |
| `DSETP.LEU.AND P0, PT, R6.reuse, UR4, PT` | `setp.leu.f64` (RRU_RU) |

## Notes

- `fma64lite_pipe` — "lite" indicates this is the lower-throughput FP64 pipe
  (a separate `fma64heavy_pipe` exists for higher-throughput FP64 on H100).
- `$VQ_REDIRECTABLE` — the instruction can be redirected between pipes.
- DSETP uses the same 16-value `DSETP_FCMP` enum (MIN=0..MAX=15) and bop modifier
  (AND/OR/XOR), exactly mirroring FSETP.

## CS2R — Control/Status Register to GPR

**Opcode:** `0x805`, **Pipe:** `int_pipe`, **1 variant**

Reads a hardware special register into a regular register. Format: `CS2R Rd, SR_XXX`.

Generated from PTX `mov.u32 %r, %special_reg` where the special register names
map to the hardware register indices.

Notable for 32-bit vs 64-bit distinction: CS2R always produces a 32-bit value
(by default). The 64-bit variant reads a register pair.

## RTT — Return to Trap Handler

**Opcode:** `0x94f`, **Pipe:** `cbu_pipe`, **1 variant**

Returns control to the trap handler after a trap/exception has been processed.
No register operands.

## CSMTEST — Compute Shader Model Test

**Opcode:** `0x80d`, **Pipe:** `fe_pipe`, **3 variants**

Tests compute shader model conditions (e.g. warp voting, predicate combining)
and writes results to predicates. Format variations include bop-based
predicate combining and simple comparison forms.

## NANOTRAP — Nanosecond Trap

**Opcode:** `0x35a`/`0x95a`/`0xb5a`/`0x1b5a`/`0x1d5a`, **Pipe:** `cbu_pipe`, **5 variants**

Hardware exception injection with optional randomization (.RAND). The register
operand carries the trap vector/PC. Not emitted by ptxas — used by driver/runtime.

## QSPC — Query Address Space

**Opcode:** `0x3aa`/`0x19aa`, **Pipe:** `mio_pipe`, **15 variants**

Queries the address space type of a memory address: shared, global, local,
generic, or constant. Produces a predicate result (Pu/r) and optionally a
register result (Rd). Used by the compiler to resolve generic-pointer dispatch
at runtime.
