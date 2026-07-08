# LDC — Load from Constant Memory

**Opcode mnemonic:** `LDC`  
**Pipe:** `mio_pipe` (MIO — memory I/O pipe)  
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD` (decoupled read/write scoreboard)  
**VIRTUAL_QUEUE:** `$VQ_UNORDERED`

## Semantics

Loads data from the constant memory bank space `c[bank][offset]` into a destination
register `Rd`. The constant memory is a read-only, cache-optimized (uniform-access)
memory space used for kernel parameters and `__constant__` variables.

- **Plain (non-bindless):** `Rd = c[bank][Ra + offset]`
- **Bindless (uniform):** `Rd = c[URa][Rb + offset]` — bank resolved from a
  uniform register pair (64-bit bindless handle `CX`)

The 32-bit load is the default (no size suffix); `.64`, `.U8`, `.S8`, `.U16`,
`.S16` select narrower or wider loads. Smaller loads zero/sign-extend to 32 bits;
`.64` writes a register pair `(Rd+1):Rd`.

## Variant overview

LDC has **4 encoding variants** across **2 opcodes**:

| Class | Opcode | Ra/Rb | Format |
|-------|--------|:---:|--------|
| `ldc__RaRZ` | `0b101110000010` (`0xb82`) | `Ra == RZ` | `LDC Rd, c[bank][offset]` |
| `ldc__RaNonRZ` | `0b101110000010` (`0xb82`) | `Ra != RZ` | `LDC Rd, c[bank][Ra+offset]` |
| `ldc_ur__URRzI` | `0b1010110000010` (`0x1582`) | `Rb == RZ` (bindless) | `LDC Rd, c[URa][offset]` |
| `ldc_ur__URnonRzI` | `0b1010110000010` (`0x1582`) | `Rb != RZ` (bindless) | `LDC Rd, c[URa][Rb+offset]` |

The first two share opcode `0xb82` — distinguished by whether `Ra == RZ` (0xFF).
The bindless variants share opcode `0x1582` — require `ad == IA` (enforced by
CONDITION: "LDC with bindless requires .IA").

## Modifiers

### Size (`sz`) — bits [75:73]

| Value | Mnemonic | Load width |
|:-----:|----------|------------|
| 0     | `.U8`    | Unsigned 8-bit, zero-extend to 32 |
| 1     | `.S8`    | Signed 8-bit, sign-extend to 32 |
| 2     | `.U16`   | Unsigned 16-bit, zero-extend to 32 |
| 3     | `.S16`   | Signed 16-bit, sign-extend to 32 |
| 4     | (default) | 32-bit |
| 5     | `.64`    | 64-bit (register pair `(Rd+1):Rd`) |
| 6–7   | —        | `ILLEGAL_INSTR_ENCODING_ERROR` |

### Addressing mode (`ad`) — bits [79:78]

| Value | Mnemonic | Meaning |
|:-----:|----------|---------|
| 0     | `.IA` (default, omitted in disasm) | Immediate-absolute: `c[bank][offset]` |
| 1     | `.IL`   | Immediate-literal (unified constant space) |
| 2     | `.IS`   | Indexed: bank/offset from register |
| 3     | `.ISL`  | Indexed-literal (both `IS` + `IL`) |

**Bank constraints by mode:**
- `.IA`: banks 0–17 and 24–31 valid (18–23 forbidden; 24–31 = RTV/driver banks)
- `.IL` / `.IS` / `.ISL`: banks 0–17 only
- `.ISL`: banks 0–14 only
- **CS shader** (any mode): banks 0–7 only

**Empirical note:** Only `.IA` appears in `libcublas.so` and user-compiled kernels;
`.IL`/`.IS`/`.ISL` are driver/runtime-internal.

### Signed-offset encoding for non-RZ variants

For `ldc__RaNonRZ`, the offset is signed 17-bit: `SImm(17/0)`. The 17-bit immediate
occupies the upper 17 bits of the 21-bit ConstBankAddress0 field, making the
lower 4 bits of offset overlap with sign extension in the bit field. The
`Ra_offset` is encoded sign-extended alongside the bank.

## ISRC_A_SIZE difference

| Variant | ISRC_A_SIZE | Meaning |
|---------|:-----------:|---------|
| Plain (RaRZ / RaNonRZ) | 32 | Address is 32-bit (bank + Ra + offset) |
| Bindless (UR) | 64 | Address is 64-bit (URa register pair) |

This drives the connector register-range formulas in the latency table.

## Bit layout (non-bindless, 128-bit)

```
Bit  127                                                                          0
      ...###.####..........#...........##..###.........
      .....######...............########################

Field (ldc__RaRZ / ldc__RaNonRZ):
  [124:122],[109:105]  8b  opex        <= TABLES_opex_0(batch_t, usched_info)
  [121:116]            6b  req_bit_set         
  [115:113]            3b  src_rel_sb   <= VarLatOperandEnc(src_rel_sb)
  [112:110]            3b  dst_wr_sb    <= VarLatOperandEnc(dst_wr_sb)
  [103:102]            2b  pm_pred             
  [91],[11:0]         13b  opcode       (0xb82 for non-bindless)
  [79:78]              2b  stride (ad)  (AdMode: IA=0, IL=1, IS=2, ISL=3)
  [75:73]              3b  sz           (size: U8=0..64=5)
  [58:54]              5b  Sb_bank      <= ConstBankAddress0(Sa_bank, Ra_offset)
  [53:38]             16b  Ra_offset    <= ConstBankAddress0(Sa_bank, Ra_offset)
  [31:24]              8b  Ra           (*Ra, RZ=0xFF for RaRZ)
  [23:16]              8b  Rd           
  [15]                 1b  Pg_not       
  [14:12]              3b  Pg           
```

### ConstBankAddress0 encoding

The bank (5-bit) and offset (16-bit) are packed into a 21-bit field spanning bits
[58:38]. The bank occupies the upper 5 bits [58:54]; the offset occupies [53:38].
For decoding, the offset is the raw unsigned 16-bit value.

## Bindless variant differences

Opcode `0x1582`. Key encoding differences:

| Field | Plain (0xb82) | Bindless (0x1582) |
|-------|--------------|-------------------|
| Source operand | `C:Sa` (constant bank) | `CX:Sa` (bindless constant handle) |
| Bank source | 5-bit immediate `Sa_bank` | 6-bit `URa` uniform register |
| Base register | 8-bit `Ra` @ [31:24] | 8-bit `Rb` @ [71:64] (starred) |
| Offset source | ConstBankAddress0(Sa_bank, Ra_offset) | Raw `Sa_offset` @ [53:38] |
| ad constraint | Any valid mode | Forced IA only |

Bindless encoding layout:
```
  [71:64]  8b  Rc (*Rb)      <- Rb (base register, starred)
  [53:38] 16b  Ra_offset     <- Sa_offset (direct)
  [29:24]  6b  Sa            <- URa (uniform register)
```

## LDC vs ULDC

| Property | LDC | ULDC |
|----------|-----|------|
| Pipe | `mio_pipe` | `udp_pipe` |
| Dest register | Regular (`Rd`) | Uniform (`URd`) |
| Predicate | Regular (`Pg`) | Uniform (`UPg`) |
| Opcode base | `0xb82` / `0x1582` | `0xab9` / `0x1ab9` / `0x18b8` / `0x1abb` |
| Source | `c[bank][...]` | `c[bank][...]` (uniform reg output) |
| Scoreboard | `INST_TYPE_DECOUPLED_RD_WR_SCBD` | `INST_TYPE_COUPLED_MATH` |

### Empirical lowering (sm_90, CUDA 13.1)

**All** `ld.const` PTX instructions with register-indexed addresses are aggressively
lowered to **ULDC** by ptxas, regardless of the addressing mode:

| PTX | SASS |
|-----|------|
| `ld.const.u32 %r, [%addr]` (register addr) | `ULDC UR4, c[bank][UR4]` |
| `ld.const.u32 %r, [%addr+imm]` | `ULDC UR4, c[bank][UR4+imm]` |
| `ld.const[bank]` (explicit bank) | **Deprecated since PTX 2.2** |
| `ld.const ... [addr].unified` | **Not valid for `.const` state space** |

**Only** fully-immediate constant loads remain as LDC:
| Use case | Encoding |
|----------|----------|
| Stack frame pointer | `LDC R1, c[0x0][0x28]` |
| Kernel param (output buffer) | `LDC.64 R2, c[0x0][0x210]` |
| Constant var at static offset | `LDC R5, c[0x3][RZ]` (bank>0, offset=0) |

The `ldc__RaNonRZ` (indexed register) variant is **never emitted** by ptxas on
sm_75, sm_80, or sm_90. The `.IL`/`.IS`/`.ISL` addressing modes are also absent
from all empirical traces. These are likely driver/runtime-internal only.

## Latency

MIO pipe, decoupled scoreboard (INST_TYPE_DECOUPLED_RD_WR_SCBD).

### TABLE_OUTPUT (GPR) — LDC as producer

The output dependency from LDC to consumers follows MIO_OPS:
```
MIO_OPS:{Rd @RdRange, Rd2 @Rd2Range}  
```
For a dependent consumer: the output latency is 1 cycle for most consumers.

### TABLE_TRUE (GPR) — LDC as consumer of CBU data

Constant-buffer-unit true-dependency: any producer → MIO_CBU consumer has latency 2:
```
TABLE_TRUE(GPR) : ALL_OPS = { MIO_CBU_OPS : 2 }
```

The constant data flows through the CBU (constant buffer unit) with a fixed
2-cycle true-dependency latency from other producers.

### Decoupled scoreboard

The `VIRTUAL_QUEUE=$VQ_UNORDERED` and decoupled scoreboard mean LDC uses
separate read (RD) and write (WR) scoreboards with variable-latency encoding:
- `src_rel_sb` [115:113]: source release scoreboard (3-bit, default 7)
- `dst_wr_sb` [112:110]: destination write scoreboard (3-bit, default 7)
- `req_bit_set` [121:116]: request bit mask (6-bit)

## Verified encodings

All verified against `cuobjdump -arch sm_90 -sass` from compiled kernels (`ldc_test.cu` + `libcublas.so`):

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x00000a00ff017b82` | `0x000fe20000000800` | `LDC R1, c[0x0][0x28]` |
| `0x00008600ff027b82` | `0x000e620000000a00` | `LDC.64 R2, c[0x0][0x218]` |
| `0x00008800ff047b82` | `0x000e300000000a00` | `LDC.64 R4, c[0x0][0x220]` |
| `0x00008c00ff087b82` | `0x000ee20000000a00` | `LDC.64 R8, c[0x0][0x230]` |
| `0x00008400ff027b82` | `0x000e240000000a00` | `LDC.64 R2, c[0x0][0x210]` |
| `0x00000800ff007b82` | `0x000e240000000800` | `LDC R0, c[0x0][0x20]` |
| `0x00009400ff163b82` | `0x000e640000000a00` | `@P3 LDC.64 R22, c[0x0][0x250]` |
| `0x00c00000ff057b82` | `0x000e300000000800` | `LDC R5, c[0x3][RZ]` |
| `0x00009400ff102b82` | `0x000e640000000a00` | `@P2 LDC.64 R16, c[0x0][0x250]` |

### PTX to SASS mapping

| PTX | SASS (sm_90) |
|-----|-------------|
| `ld.const.u32` (immediate) → kernel param | `LDC Rd, c[0x0][imm]` |
| `ld.const.u64` (immediate) → kernel param | `LDC.64 Rd, c[0x0][imm]` |
| `ld.const.u32` (register addr) | **ULDC** (not LDC) — forced by ptxas |
| `ld.const` indexed `__constant__[idx]` | **ULDC** (not LDC) |
| `ld.const[bank]` | **Deprecated** since PTX 2.2 |
| `ld.const ... .unified` | **Rejected** by ptxas for `.const` |

## LDCU

`LDCU` (idx 222 in `ref_memo.txt`) is marked as "likely an LDC variant" in
AGENTS.md. The sm_90 spec dumps contain no separate `LDCU` instruction. Given
LDC's `INST_TYPE_DECOUPLED_RD_WR_SCBD` and separate request/release scoreboards,
LDC already supports warp-uniform (coherent) semantics in hardware. `LDCU` in
the ref_memo likely refers to a PTX concept (e.g. `ldu` opcode) that maps to the
same LDC hardware instruction with different encoding hints.

## Open questions

- **`.IL` / `.IS` / `.ISL` addressing modes:** No empirical examples found.
  What specific driver/runtime scenarios trigger them, and what is the exact
  datapath difference vs `.IA`?
- **`ldc__RaNonRZ` (indexed LDC):** On sm_90, `nvcc` converts all
  register-indexed constant loads to ULDC + uniform address computation. Under
  what circumstances does a true `ldc__RaNonRZ` get emitted?
- **LDCU resolution:** If `LDCU` is truly a separate instruction (not just LDC),
  what is its sm_90 opcode?
