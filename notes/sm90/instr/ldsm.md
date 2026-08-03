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

Lane `t` supplies the address of the row named by `t`:

```
.x1:      addr_t = base + t*16                 (matrix 0, row t, stride 16)
.x2/.x4:  addr_t = base + (t//8)*128 + (t%8)*32
             matrix t//8 at +m*128, row t%8, row-stride 32
```

* `.x1` stores a matrix contiguously (row-stride 16, 8 rows = 128 bytes).
* `.x2`/`.x4` store each matrix with **row-stride 32** (16 bytes of data +
  16-byte gap per row).  Matrices sit at `m*128` offsets.  nvcc's optimizer
  turns the `.x2` address into `(t%8)*32` when the matrices are adjacent —
  this is the same formula, since `(t//8)*128 + (t%8)*32` is what the layout
  needs (a 32-byte row stride, NOT 16 — my first guesses of a 16-byte stride
  or interleaved `[mat0|mat1]` rows were wrong).
* Rows are 16 bytes of data; the 16 bytes at `+16..+31` of each 32-byte row
  are not part of the matrix.

**Fragment distribution** (row-major `.M88`): lane `t`'s register for matrix
`m` holds row `(t//4)` of that matrix, bytes `[4*(t%4) .. +4)` of the 16-byte
row.  The row's data is fetched from the address supplied by lane `t//4`
(`addr_{t//4}`).  `lo16` = element at `+4*(t%4)`, `hi16` = `+4*(t%4)+2`.

For `.x2`/`.x4`, register `k` (`k*32+...` slot) holds matrix `k`'s fragment;
the per-matrix fragment layout inside each matrix is identical to `.x1`.

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
