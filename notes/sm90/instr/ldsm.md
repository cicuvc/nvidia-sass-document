# LDSM — warp-cooperative shared-memory matrix load (ldmatrix)

**Opcode mnemonic:** LDSM  |  **Pipe:** mio_pipe (VQ_AGU)  |  **INSTRUCTION_TYPE:** INST_TYPE_DECOUPLED_RD_WR_SCBD

Collectively loads one or more 8x8 matrices from shared memory, distributing
fragments across the 32 lanes of a warp.  This is the SASS encoding of PTX
`ldmatrix.sync.aligned.m8n8[.trans].num[.b16]` (the `.m8n16`/`.m16n16`/
`.b8`/sub-byte shapes of PTX 8.6 map to `.M816`/`.M832`; see the sz/mode
tables).  All lanes must execute the same LDSM; each lane supplies ONE
16-byte-aligned address naming a matrix row, and every lane receives a
2-element (b16) fragment.

## Semantics

Each lane provides an address = the start of one matrix row.  The addresses
are collected warp-wide; fragment delivery is a fixed hardware mapping (see
"Address model" below).  `ldmatrix` waits for all lanes in the warp (the
`.sync.aligned` of PTX), then lanes read shared and scatter fragments into
their registers.  Results are async (scoreboarded / DECOUPLED) — consumers
must wait (req on the LDSM's dst scoreboard, or enough stall).

## Variant overview

| mnemonic          | opcode   | notes |
|-------------------|----------|-------|
| `LDSM[...][.NUM] Rd, [Ra+off]`  | 0x83b | register/immediate address (sImmOffset) |
| `LDSM[...][.NUM] Rd, [URa+off]` | 0x183b | uniform-register address |

Modifiers: `.SZ` = `.16` (b16) | `.U4TO8`/`.S4TO8` (M816) | `.U2TO4`/`.S2TO4`
(M832); `.MODE` = `.M88` (row-major 8x8 b16) | `.MT88` (transposed) |
`.M816` | `.M832`; `.NUM` = `.1`/`.2`/`.4` (one/two/four matrices).

## Address model (silicon-verified SM120, matches ldmatrix.m8n8.*)

**X4 is the base case; X1/X2 are `num`-limited subsets of it.**  The hardware
performs NO layout/stride assumption — every address is just the start of a
16-byte row that the user placed there.

1. The 32 lanes' addresses are grouped by 8: group `g` = lanes `8g..8g+7`.
2. `.x4` processes all 4 groups, `.x2` the first 2, `.x1` the first 1.
3. Each group reads the `8 × 16` bytes at its 8 addresses and splits them
   into 32 32-bit words.
4. Those 32 words are written to **one register** of the 32 lanes: word
   (row `r`, block `c`) of group `g` (row data `addr_{8g+r}[4c..+4)`) lands in
   lane `4r + c`, register `g`.  So lane `t`'s register for matrix `m` holds
   row `t//4`, bytes `[4*(t%4)..+4)` of the row, fetched from the address
   supplied by lane `t//4` (i.e. `addr_{8m + t//4}`); `lo16` = element at
   `+4*(t%4)`, `hi16` = `+4*(t%4)+2` (row-major `.M88`).

Consequently the address formula is entirely up to the caller.  Verified
equivalences:
* `.x1` reads the same matrix with contiguous (stride-16) addresses
  `addr_t = base + t*16` OR stride-32 addresses `addr_t = base + (t%8)*32`
  (the `.x4` group-0 layout) OR a scrambled per-row order
  `addr_t = base + 16*((t*3+1)%8)` — the fragment always comes from whatever
  rows the group-0 addresses name.
* `.x2`/`.x4` use `addr_t = base + (t//8)*128 + (t%8)*32` for matrices at
  `m*128` with row-stride 32.  nvcc's optimizer reduces this to `(t%8)*32`
  for adjacent matrices.  (My earlier "x1 stride 16 vs x2/x4 stride 32" was
  a property of the tested layouts, NOT a hardware rule.)

**Transposed `.MT88`**: lane `t`'s register holds `a[(t%4)*2][t//4]` (lo16)
and `a[(t%4)*2+1][t//4]` (hi16).  The two data rows come from the addresses
supplied by lanes `(t%4)*2` and `(t%4)*2+1`.  (Verified: transpose reads
16-bit elements at odd column positions, so an injection whose high b16 half
was zero made odd columns read back zero — a test-injection artifact, not a
transpose issue.)

## Encoding (from CLASS ldsm__sImmOffset)

```
[124:122],[109:105]  opex        <= TABLES_opex_0(batch_t,usched_info)
[121:116]  req_bit_set
[115:113]  src_rel_sb             VarLatOperandEnc
[112:110]  dst_wr_sb              VarLatOperandEnc
[103:102]  pm_pred
[91:91],[11:0] opcode             (0x83b / 0x183b)
[79:78]    stride   <= mode       M88=0 MT88=1 M816=2 M832=3
[77:75]    sz       <= sz         16=0 U4TO8=1 S4TO8=2 U2TO4=3 S2TO4=4
[73:72]    num      <= num        _1=0 _2=1 _4=2
[63:40]    Ra_offset (24-bit SImm)
[31:24]    Ra                    (8-bit; RZ=off)
[23:16]    Rd                    (8-bit; dest start register)
[15:15]    Pg_not
[14:12]    Pg
```

CONDITIONS: `.M88`/`.MT88` require `.16`; `.M816` requires `.U4TO8`/`.S4TO8`;
`.M832` requires `.U2TO4`/`.S2TO4`.  `num==2` needs Rd 2-aligned (and room),
`num==4` needs Rd 4-aligned.

## Latency

mio_pipe (VQ_AGU), same row as LDS/STS.  Results are DECOUPLED — a consumer
must wait for the LDSM's dst scoreboard (req) or leave enough stall.  In the
test kernels, `[1:7:{1}:8:1]` (dst sb 1, wait on addr-load sb) followed by a
consumer `req={1}` worked for .x1/.x2/.x4.  Addresses must be loaded from
global memory with their own scoreboard wait before the LDSM issues (LDSM
reads `Ra` at issue; an unready address faults 700).

## Cross-comparison

* PTX `ldmatrix.sync.aligned.m8n8.num.b16 [addr]` → `LDSM.16.M88.num Rd,[Ra]`.
* `.trans` → `.MT88`.
* The `.m8n16`/`.m16n16`/`.b8`/sub-byte (`.b6x16_p32`, `.b4x16_p64`)
  decompression forms are PTX 8.6 / sm_100+; the sm_90 SASS file still lists
  `.M816`/`.M832` with `.U4TO8`/`.S4TO8`/`.U2TO4`/`.S2TO4` sz codes (not
  exercised on SM120 here).
* Related: STS feeds the shared data; BAR.SYNC before LDSM to make stores
  visible; STG after to export fragments.

## Verified encodings (test_ldsm.py, SM120)

All four families pass: `.M88.x1`, `.M88.x2`, `.M88.x4`, `.MT88.x1` with a
b16-value injection (`value[byteoffset/2] = byteoffset/2`) through LDG+STS and
host-computed addresses passed via global memory.  Addresses must include the
shared-window base (0x400) — LDSM `Ra` is the absolute window offset.

## Open questions

* `.M816`/`.M832` (b8/sub-byte) and the sz sub-byte decompression were not
  exercised (SM120/PTX 8.x do not expose these shapes to the ISA the same
  way); their row layout is assumed to follow the same 16-byte-row model.
* nvcc's `.x2`/`.x4` row-stride-32 layout is the empirically observed one;
  the extra 16 bytes per row are unexplained by PTX docs (row padding).
