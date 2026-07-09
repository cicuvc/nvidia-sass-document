# STTM / STT — tensor-memory (TMEM) store  → PTX `tcgen05.st`

**Opcode mnemonic:** `STTM` (and alt `STT`) = `0b1100111101101` (0x19ed, 6637)
**Pipe:** `udp_pipe` (uniform datapath) | **INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_SCBD`
**Virtual queue:** `$VQ_TMEM` (=40) | **MEM_SCBD_TYPE:** `BARRIER_INST`

New on sm100 (Blackwell). The store mirror of `LDTM` — the SASS realization of
PTX **`tcgen05.st`**, an asynchronous warp-collective store from registers into
5th-gen TensorCore **Tensor Memory (TMEM)**. See `ldtm.md` for TMEM background;
this note focuses on the store-specific differences.

## Semantics
`STTM tmem[URc + Sc_offset], Rb` asynchronously copies a register vector starting
at `Rb` into the TMEM block based at `URc + Sc_offset`, collectively across the
warp. The register-vector width = f(`layout`, `num`) per PTX Table 53 (identical
to the LDTM load table).

`INST_TYPE_DECOUPLED_RD_SCBD` + `dst_wr_sb` pinned to `7` (none): the store has
**no write scoreboard** (it writes TMEM, not registers) and its only dependency
handle is the **read scoreboard** `src_rel_sb` it releases when the source
registers have been consumed. This is the exact **inverse** of LDTM, which pins
`src_rel_sb=7` and uses `dst_wr_sb`. Async completion (TMEM write visibility) is
ordered separately — PTX `tcgen05.wait::st`, which lowers to `FENCE.VIEW.ASYNC.T`
(see below), not a scoreboard on this instruction.

## Variant overview
| Class | Kind | Opcode | Distinguisher |
|-------|------|--------|---------------|
| `sttm_` | CLASS | 0x19ed | full `layout`×`num` matrix, optional `.unpack::16b` |
| `stt_` | ALT of `stsm_…` | 0x19ed | `layout` pinned `32dp32bit`; `size`∈{32,64,128} |

Like `LDT`, the `STT`/`SIZE_ldt` ALTERNATE is **never emitted** by ptxas (every
`tcgen05.st` shape → `STTM`); it is an assembler-only spelling parented under the
Hopper `STSM` (shared-memory matrix store) class tree.

## Modifiers (STTM)
| Slot | Enum | Bits | Meaning |
|------|------|------|---------|
| `layout` | `LAYOUT` | [87]∥[82:81] | TMEM access shape (same map as LDTM) |
| `num` | `NUM` | [85:83] | repeat factor `x1..x128` → sets `ISRC_B_SIZE` |
| `expand` | `EXPAND16BIT` | [80] | `noexpand16bit`(0) / `EXPAND16BIT`(1) = PTX `.unpack::16b` |

`LAYOUT` / `NUM` value-maps are identical to LDTM (see `ldtm.md`).
`.32x32b`(=2) and `.x1`(=0) are the defaults and are elided by cuobjdump.

The one modifier difference vs LDTM: bit [80] carries **`EXPAND16BIT`**
(`.unpack::16b`, split a 32-bit reg into two 16-bit columns) instead of `PACK`.
Both ride the same legacy `texunpack` control bit.

## Bit layout (128-bit, STTM)
```
[124:122]∥[109:105] opex        = TABLES_opex_0(batch_t, usched_info)
[121:116]           req_bit_set  = wait barrier mask
[115:113]           src_rel_sb   = VarLatOperandEnc(src_rel_sb)  ← read-reg release barrier
[112:110]           dst_wr_sb    = 7  (pinned: no write scoreboard — store)
[103:102]           pm_pred
[91]∥[11:0]         opcode       = 0x19ed
[87]∥[82:81]        layout       (3b, MSB at 87, interleaved with num)
[85:83]             vecidx       = num
[80]                texunpack    = expand   (.unpack::16b)
[79:72]∥[63:40]     Sb_offset    = 32-bit signed TMEM offset (= Sc_offset; split field)
[71:64]             Ra_URc       = URc  (uniform TMEM base address register)
[39:32]             Rb           = data source base register
[15]                Pg_not ; [14:12] Pg = @UPg predicate (UniformPredicate)
```
Difference from LDTM in operand placement:
- **Data** register `Rb` sits in [39:32] (LDTM's `Rd` was [23:16]; STTM leaves
  [23:16] unused since it has no register *dest*).
- **TMEM address** register `URc` is in [71:64] (`Ra_URc` slot). LDTM put its
  base `URb` in [39:32]; STTM needs [39:32] for the data reg, so the address reg
  moves up to [71:64].
- Scoreboard roles swap: `src_rel_sb` active / `dst_wr_sb` pinned (LDTM inverse).

## ISRC_B_SIZE (register-vector width)
`ISRC_B_SIZE` (bits) = 32 × (register count), following PTX Table 53 — the same
(num, layout) sum-of-products used by LDTM's `IDEST_SIZE`. CONDITIONS enforce the
NA cells, N-register alignment on `Rb`, and range checks (all keyed on `Rb`
instead of `Rd`).

## Cross-comparison: STTM vs LDTM
| aspect | LDTM (`tcgen05.ld`) | STTM (`tcgen05.st`) |
|--------|--------------------|--------------------|
| opcode | 0x19ee | 0x19ed |
| direction | TMEM → registers | registers → TMEM |
| INST_TYPE | `DECOUPLED_WR_SCBD` | `DECOUPLED_RD_SCBD` |
| active scoreboard | `dst_wr_sb` [112:110] | `src_rel_sb` [115:113] |
| pinned scoreboard | `src_rel_sb`=7 | `dst_wr_sb`=7 |
| GPR operand | dest `Rd` [23:16] | source `Rb` [39:32] |
| TMEM addr reg | `URb` [39:32] | `URc` [71:64] |
| pack modifier [80] | `PACK` (`.pack::16b`) | `EXPAND16BIT` (`.unpack::16b`) |
| completion wait | `tcgen05.wait::ld` (scoreboard) | `tcgen05.wait::st` → `FENCE.VIEW.ASYNC.T` |

## Latency (sm100_latencies.txt)
`STTM`/`STT` are members of `LDTM_STTM_OP` (line 81) together with `LDTM`/`LDT`.
Its GPR dependency row is a uniform **`1`** cycle (issue handoff, not TMEM access
latency); the op is excluded from `UDP_subset` fixed-latency timing (line 218)
and handled as a scoreboard-gated async op. See `ldtm.md` for the full table.

## Verified encodings (cuobjdump, `nvcc -arch=sm_100a`, CUDA 13.1)
Source: `tests/sttm_test.cu` → `tests/sttm_test.cubin`. Decoder:
`tools/decode_sttm.py` — all 8 round-trip (**ALL PASS**).

| Disassembly | Lo64 / Hi64 | layout | num | exp | Rb | URc | Soff | src_sb |
|-------------|-------------|:------:|:---:|:---:|:--:|:---:|:----:|:------:|
| `STTM tmem[UR6], R4` | `…79ed` / `0041e20008040006` | 2 `32dp32bit` | 0 `x1` | 0 | R4 | UR6 | 0 | 0 |
| `STTM.x2 tmem[UR6], R4` | `…79ed` / `0081…080c0006` | 2 | 1 `x2` | 0 | R4 | UR6 | 0 | 0 |
| `STTM.16dp64bit.x2 tmem[UR6], R4` | `…79ed` / `080e0006` | 3 | 1 | 0 | R4 | UR6 | 0 | 0 |
| `STTM.16dp128bit.x4 tmem[UR6], R4` | `…79ed` / `08100006` | 0 | 2 `x4` | 0 | R4 | UR6 | 0 | 0 |
| `STTM.16dp256bit tmem[UR6], R4` | `…79ed` / `08020006` | 1 | 0 | 0 | R4 | UR6 | 0 | 0 |
| `STTM.16dp128bit.EXPAND16BIT tmem[UR6], R4` | `…79ed` / `08010006` | 0 | 0 | 1 | R4 | UR6 | 0 | 0 |
| `STTM.16dp32bit_t0_t15.x2 tmem[UR6], R4` | `…79ed` / `08880006` | 4 | 1 | 0 | R4 | UR6 | 0 | 0 |
| `STTM.16dp32bit_t16_t31.x2 tmem[UR6+0x10], R4` | `…79ed`(lo bit set) / `088a0006` | 5 | 1 | 0 | R4 | UR6 | 16 | 0 |

Confirmed facts:
- Operand order in the disassembly is `tmem[...], Rb` (dest TMEM first, then data
  register) — the natural store spelling.
- Address reg encodes in [71:64] (`Ra_URc`), data reg in [39:32] (`Rb`) — the
  swap vs LDTM verified.
- `req_bit_set` (wait mask) carries the RAW dependency on the producer that wrote
  the source regs (e.g. `req=0x4`/`0x8` on the first two — waiting on SB2/SB3
  set by the input loads); `src_rel_sb=0` releases scoreboard SB0 on reg read.
- `EXPAND16BIT` (bit[80]=1) verified from `.unpack::16b`.

### tcgen05 store-side lowering (same kernel)
| PTX | SASS |
|-----|------|
| `tcgen05.st.sync.aligned.32x32b.x1.b32 [ta], {r0}` | `STTM tmem[URc], Rb` |
| `tcgen05.st.sync.aligned.16x128b.x4.b32 [ta], {r0..r7}` | `STTM.16dp128bit.x4 tmem[URc], Rb` |
| `…16x128b.x1.unpack::16b… [ta], {r0,r1}` | `STTM.16dp128bit.EXPAND16BIT tmem[URc], Rb` |
| `…16x32bx2.x2… [ta], 16, {r0,r1}` | `STTM.16dp32bit_t0_t15/_t16_t31.x2 tmem[URc+0x10], Rb` (`immHalfSplitoff`→`Sc_offset`) |
| `tcgen05.wait::st.sync.aligned` | `FENCE.VIEW.ASYNC.T` |

## Open questions
- Same as LDTM re: TMEM addressing units (column vs byte) and the `STT`/`SIZE_ldt`
  ALTERNATE never being emitted.
- Exact ordering guarantees of `FENCE.VIEW.ASYNC.T` for `tcgen05.wait::st` vs the
  `src_rel_sb` read barrier — the fence orders the async TMEM write visibility,
  the scoreboard only orders source-register reuse.
