# STG — Store to Global Memory

**Opcode mnemonic:** `STG`  
**Pipe:** `mio_pipe` (MIO — memory I/O pipe, MIO_SLOW_OPS subset)  
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD` (decoupled read-only scoreboard)  
**VIRTUAL_QUEUE:** `$VQ_AGU`

## Semantics

Stores source register `Rb` into global device memory. Same 64-bit policy
descriptor model as LDG: `desc[URc]` consumes the URc:UR(c+1) uniform register
pair as an L2 cache policy word. URc=0 is the default (no special policy).

- **Memdesc:** `*global(Ra + offset) = Rb` with cache policy from URc:UR(c+1)
- **Plain:** `*global(Ra + offset) = Rb`

### 64-bit cache policy descriptor — see `ldg.md`

`desc[UR4]` uses UR4:UR5 as a 64-bit L2 eviction policy word (introduced at
sm_80, same time as `createpolicy`). UR4 = 0 is the default (no special
policy). UR5 encodes priority + fraction/window fields. See `ldg.md`
§ "64-bit cache policy descriptor" for full encoding details.

- **`desc[URZ]` works:** `STG.E desc[URZ]` → UR5=URZ=0 (no policy), same as default.
- **R2.64 is the byte address:** `STG.E desc[URZ][R2.64+off]` shifts stores by
  exactly `off` bytes.
- **hi64[71:64] encodes which UR register** provides the low 32 bits of the
  policy word; the adjacent register provides the upper 32 bits.

On sm_89 the compiler emitted an explicit `IMAD.WIDE` to add base+offset. On
sm_90+ this is folded into the AGU — the descriptor provides translation
parameters and the register(s) provide the byte address.

STG is the store counterpart to LDG. Like LDG, it has 6 encoding variants
across 2 opcodes (`0x386` / `0x1986`). Unlike LDG, STG omits the read-specific
modifiers. The scoreboard is read-only with hardwired `dst_wr_sb=7`.

## STG vs LDG — encoding differences

| Feature | LDG | STG |
|---------|-----|-----|
| Semantics | `Rd = *global(...)` | `*global(...) = Rb` |
| Opcodes | `0x381` / `0x1981` | `0x386` / `0x1986` |
| Data register | Rd @ [23:16] | Rb @ [39:32] |
| Pu (write pred) | @ [83:81] | — (absent, bits unused) |
| Pnz (NZ pred) | @ [67:64] | — (absent) |
| SP2 (prefetch) | @ [69:68] | — (absent) |
| UR desc register | URb @ hi64[7:2] | URc @ hi64[7:0] |
| mem table | `TABLES_mem_1` | `TABLES_mem_0` |
| Scoreboard | RD+WR decoupled | RD-only decoupled |
| VQ | `VQ_AGU_UNORDERED_WR` | `VQ_AGU` |
| dst_wr_sb | VarLatOperandEnc | Hardwired 7 |
| IDEST_SIZE | 32/64/128 | 0 |

## Modifiers

### E — bit [72]
0=32-bit address (noe), 1=64-bit address (`.E`). Default noe.

### COP — bits [86:84]
Cache operator: EF(0), EN(1,default), EL(2), LU(3), EU(4), NA(5).

### SEM / SCO / PRIVATE — bits [80:77]
Encoded via `TABLES_mem_0` (different table from LDG's `TABLES_mem_1`). No
`.CONSTANT` hint for STG — only WEAK/STRONG/MMIO variants apply.

### Size — bits [75:73]
U8=0, S8=1, U16=2, S16=3, 32=4, 64=5, 128=6, INVAL=7.

## Bit layout (stg_memdesc__Ra64, 128-bit)

```
Bit  127                                                                          0
      ...###.####........#..#.######.####.###......##..###.........
      ........###########..##################.................................

Field:
  [124:122],[109:105]  8b  opex        <= TABLES_opex_0
  [121:116]            6b  req_bit_set
  [115:113]            3b  src_rel_sb   <= VarLatOperandEnc
  [112:110]            3b  dst_wr_sb    <= 7 (hardwired)
  [103:102]            2b  pm_pred
  [91],[11:0]         13b  opcode       (0x1986 for memdesc/uniform)
  [90]                 1b  input_reg_sz_32_dist  <= *reserved
  [86:84]              3b  cop (COP)
  [80:77]              4b  mem          <= TABLES_mem_0(sem,sco,private)
  [76]                 1b  memdesc      <= 1 (desc form)
  [75:73]              3b  sz
  [72]                 1b  e (E)
  [69:64]              6b  Ra_URc       (descriptor uniform register)
  [63:40]             24b  Ra_offset
  [39:32]              8b  Rb           (source data)
  [31:24]              8b  Ra           (address register)
  [15]                 1b  Pg_not
  [14:12]              3b  Pg
```

Note the URc at [69:64] vs LDG's URb at [37:32] — the uniform register and
data register positions swap between the two opcodes due to LDG's extra
modifier fields (Pu/Pnz/SP2) occupying bits 83:64.

## Verified encodings

All verified against `cuobjdump -arch sm_90 -sass` from `libcublas.so`:

| Lo64 | Hi64 | Disassembly |
|------|------|-------------|
| `0x0000001c10000986` | — | `@P0 STG.E desc[UR8][R16.64], R28` |
| `0x0001001b10001986` | — | `@P1 STG.E desc[UR8][R16.64+0x100], R27` |
| `0x0000801910000986` | — | `@P0 STG.E desc[UR8][R16.64+0x80], R25` |
| `0x0000000d02005986` | — | `@P5 STG.E desc[UR8][R2.64], R13` |
| `0x0000801102006986` | — | `@P6 STG.E desc[UR8][R2.64+0x80], R17` |
| `0x0001001502000986` | — | `@P0 STG.E desc[UR8][R2.64+0x100], R21` |
| `0x0000000304007986` | — | `STG.E desc[UR4][R4.64], R3` |

### PTX to SASS mapping

| PTX | SASS (sm_90) |
|-----|-------------|
| `st.global.u32 [%rd], %rb` | `STG.E desc[URc][Ra.64], Rb` |
| `st.global.cs.u32 [%rd], %rb` | `STG.E.CONSTANT` via mem qualifier |
| `st.volatile.global.u32 [%rd], %rb` | `STG.E` via mem qualifier |
| `st.global.u64 [%rd], %rb` | `STG.E.64 desc[URc][Ra.64], Rb` |

Same as LDG: all global stores on sm_90 go through memory descriptors. The
plain `0x386` form is not observed in user code or cublas.

## STG vs STS comparison

| Property | STS | STG |
|----------|-----|-----|
| Memory space | Shared (on-chip) | Global (device) |
| Address | `[Ra + offset]` | `desc[URc][Ra.64 + offset]` |
| Modifiers | Stride (X1/X4/X8/X16) | E, COP, SEM/SCO/PRIVATE |
| Memory descriptor | No | Yes (URc pair) |
| CS only | Yes | No |

## Open questions

- **URc at [69:64] vs LDG's URb at [37:32]:** The uniform register for the
  memory descriptor sits at different bit positions in LDG vs STG. This
  reflects LDG's extra Pu/Pnz/SP2 fields which occupy the [69:64] space in
  LDG, pushing URb down to [37:32].
- **Plain 0x386 forms:** Same as LDG — what triggers them?
