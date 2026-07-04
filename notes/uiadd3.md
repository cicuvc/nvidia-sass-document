# UIADD3 — Uniform Integer Add

**Opcode mnemonic:** `UIADD3` / `UIADD3.64` / `UIADD3.X`
**Pipe:** `udp_pipe` (uniform datapath)  
**INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

---

## Variant overview

UIADD3 is the uniform-register counterpart to IADD3. All operands are
`UniformRegister` (6-bit encoding, vs 8-bit for GPRs) and the guard predicate
is `UniformPredicate(UPT)` instead of `Predicate(PT)`.

| Mode   | Mnemonic | Width | Operands | opcode LSB |
|--------|----------|:---:|------|:---:|
| **32b plain** | `UIADD3` | 32 | `URd, UPu, UPv, [-]URa, [-]URb, [-]URc` | `000` |
| **32b X**     | `UIADD3.X` | 32 | `..., [!]UPp, [!]UPq` | `000` |
| **64b plain** | `UIADD3.64` | 64 | same as 32b (UR pairs) | `111` |
| **64b X**     | `UIADD3.64.X` | 64 | `..., [!]UPp, [!]UPq` | `111` |

> **Note:** Despite the `.64` suffix, the 64-bit variant was not triggered by
> compiler-generated SASS in the test kernels. The compiler prefers chaining
> 32-bit UIADD3 for 64/128-bit uniform arithmetic (see empirical section).
> The `.64` class exists in the spec and may appear in driver paths or
> hand-written ptxas output.

### Pu and Pv: 2-bit carry output (confirmed)

Same convention as IADD3: `UPu` and `UPv` are carry outputs, modeled as
`UniformPredicate("UPT")` with PT=7 meaning "discard". Explicit non-default
values (UP0, UP1, etc.) capture the two carry bits from the 3-input addition.
For .64 mode, carries propagate the 64-bit sum.

### X-mode carry chain

The X overlay adds two explicit carry predicates (`UPp, UPq`) which encode
carry-in from a previous operation. The sources use `[~]` (ones-complement
invert) instead of `[-]` (two's complement negate).

---

## Operand forms

| Form   | Ra  | Sb             | Rc  | 32b opcode (13-bit) | 64b opcode |
|--------|-----|----------------|-----|:---:|:---:|
| URURUR | URa | URb            | URc | `0b1001010010000` (0x1290) | `0b1001010010111` (0x1297) |
| URsIUR | URa | SImm(32)       | URc | `0b1100010010000` (0x1890) | `0b1100010010111` (0x1897) |

X forms share the same opcodes, distinguished by `/XONLY:X`. No C/CX or multi-immediate
operand forms (uniform paths don't have a constant memory bank that maps to C/CX).

---

## ENCODING layout (128-bit, MSB-left)

Shown for `uiadd3__URURUR_URURUR` (32-bit); `.64` is identical except opcode
and the `_SIZE` properties (all 64). Uniform registers use 6-bit slots.

| Bits                | Width | Field            | Source | Notes |
|---------------------|:-----:|------------------|--------|-------|
| [124:122],[109:105] | 8     | `opex`           | `TABLES_opex_1(...)` | no per-operand reuse |
| [121:116]           | 6     | `req_bit_set`    | `req_bit_set` | |
| [115:113]           | 3     | `src_rel_sb`     | `*7` | fixed |
| [112:110]           | 3     | `dst_wr_sb`      | `*7` | fixed |
| [103:102]           | 2     | `pm_pred`        | `pm_pred` | |
| **[91],[11:0]**     | **13**| **`opcode`**     | **Opcode** | |
| [90]                | 1     | `input_reg_sz_32_dist` | `*1` (plain) / `UPp@not` (X) | |
| [89:87]             | 3     | `Pnz`            | `*7` (plain) / `UPp` (X) | |
| [86:84]             | 3     | `cop`            | `UPv` | **carry₂ output** |
| [83:81]             | 3     | `Pu`             | `UPu` | **carry₁ output** |
| [80]                | 1     | `UPq_not`        | `*1` (plain) / `UPq@not` (X) | |
| [79:77]             | 3     | `UPq`            | `*7` (plain) / `UPq` (X) | |
| [75]                | 1     | `sz`             | `URc@negate` (plain) / `URc@invert` (X) | |
| [74]                | 1     | `sh`             | `0` (plain) / `*X` (X) | |
| [72]                | 1     | `e`              | `URa@negate` (plain) / `URa@invert` (X) | |
| [69:64]             | 6     | `Ra_URc`         | `URc` | |
| [63]                | 1     | `Sb_invert`      | `URb@negate` (plain) / `URb@invert` (X) | |
| [37:32]             | 6     | `Ra_URb`         | `URb` | |
| [29:24]             | 6     | `Sa`             | `URa` | |
| [21:16]             | 6     | `URd`            | `URd` | |
| [15]                | 1     | `Pg_not`         | `UPg@not` | |
| [14:12]             | 3     | `Pg`             | `UPg` | uniform guard predicate |

### 64-bit variant differences

- All `_SIZE` properties = 64 (vs 32)
- All uniform register operands must be even-aligned (`(URx+(URx==URZ))%2==0`)
- Register upper bound: `%MAX_UNIFORM_REG_COUNT-2` (consumes a register pair)
- Same bit layout, same `TABLES_opex_1`

---

## Key differences from IADD3

| Feature | IADD3 | UIADD3 |
|---------|-------|--------|
| Pipe | `int_pipe` | `udp_pipe` |
| Register type | GPR (8-bit, `R0..R254`) | UR (6-bit, `UR0..UR63`) |
| Guard predicate | `Predicate(PT)` | `UniformPredicate(UPT)` |
| Operand forms | 5 (RRR, RsIR, RCR, RCxR, RUR) | 2 (URURUR, URsIUR) |
| C/CX support | Yes (constant bank) | No |
| .reuse support | Yes (`TABLES_opex_4`) | No (`TABLES_opex_1`) |
| 64-bit width mode | No (always 32-bit) | Yes (`UIADD3.64` with paired URs) |
| Multi-register ops | No (always single-reg) | Yes (`.64` uses UR pairs) |

---

## Conditions

### Register bounds
- 32-bit: `URd ≤ %MAX_UNIFORM_REG_COUNT-1`
- 64-bit: `URd ≤ %MAX_UNIFORM_REG_COUNT-2` with even-alignment check

### Simultaneous negate/invert ban
```
(URa@negate == 1) -> (URb@negate == 0)
(URb@negate == 1) -> (URa@negate == 0)
```
Same for X-mode: `(URa@invert) -> ¬(URb@invert)`.

### opex
`TABLES_opex_1(batch_t, usched_info)` — only batch/drain scheduling, no per-operand
reuse since uniform register ports don't support `.reuse`.

---

## Pipe and latency

| Property | Value |
|----------|-------|
| Pipe | `udp_pipe` |
| OPERATION SET | `{UIADD3, UIADD3udp_pipe, UIADD3.64, UIADD3.64udp_pipe}` |
| INST_TYPE | `INST_TYPE_COUPLED_MATH` |

UIADD3 is in the uniform datapath pipe alongside `UIMAD`, `ULEA`, `ULOP3`,
`USHF`, `UMOV`, and TMA operations.

---

## Empirical confirmation (sm_90, CUDA 13.1)

### 32-bit UIADD3 (confirmed)

**64-bit add via uniform path** (`a + b` where both are u64):
```
UIADD3    UR4, UP0, UR4, UR6, URZ      ; UR4.lo = UR4.lo + UR6.lo
UIADD3.X  UR5, UR5, UR7, URZ, UP0, !UPT  ; UR5.hi = UR5.hi + UR7.hi + carry
```

**64+64+64 addition** (three u64 values):
```
UIADD3    UR4, UP0, UR4, UR6, URZ       ; lo = a.lo + b.lo
UIADD3    UR4, UP1, UR4, UR8, URZ       ; lo = lo + c.lo
UIADD3.X  UR5, UR9, UR5, UR7, UP1, UP0  ; hi = a.hi + b.hi + c.hi + carries
```

The third instruction is an X-mode add that consumes carry outputs (UP1, UP0)
from the two plain UIADD3 ops as carry-in predicates.

### 3-way carry capture with explicit Pu/Pv

```
UIADD3    UR4, UP0, UP1, UR4, UR8, UR10    ; UP0=carry₁, UP1=carry₂
UIADD3.X  UR5, URZ, UR9, UR11, UP0, UP1    ; consume both carries
```

The compiler emits `UP0, UP1` as explicit (non-default) carry outputs when
the 3-way sum can produce two carry bits. Confirms the Pu/Pv theory.

### 128-bit add chain

```
UIADD3   UR6, UP0, UR4, UR6, URZ          ; bits[63:0]
UIADD3.X UR7, UR5, UR7, URZ, UP0, !UPT    ; bits[127:64] with carry
```

### UIADD3.64 (not triggered)

Despite `.64` being in the spec with a full CLASS definition, the compiler
prefers chaining 32-bit UIADD3 ops for all tested cases. The `.64` variant
might be used in driver-internal paths or hand-encoded ptxas output.

---

## Common patterns

### URa=Rd overwrite (accumulator)
```
UIADD3 UR4, UP0, UR4, UR6, URZ      ; UR4 += UR6  (add to self)
```

### Immediate operand
```
UIADD3 UR4, UP0, UR4, 0x40, URZ     ; UR4 += 64
```

### Carry propagate to GPR
```
UIADD3   UR4, UP0, UR4, UR6, URZ    ; UR4.lo = ..., carry→UP0
IADD3    R5, RZ, UP0, RZ, RZ, RZ    ; R5 = zero_extend(UP0)  (carry→GPR)
```
In practice seen as `IMAD.U32 R5, RZ, RZ, URcarry` — same degenerate pattern.
