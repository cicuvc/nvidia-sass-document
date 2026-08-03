# LDGSTS — asynchronous global→shared copy (cp.async)

**Opcode mnemonic:** LDGSTS  |  **Pipe:** mio_pipe (VQ_AGU_UNORDERED_WR)  |  **INSTRUCTION_TYPE:** INST_TYPE_DECOUPLED_RD_WR_SCBD

Asynchronously copies bytes from global memory into shared memory, per
thread.  This is the SASS encoding of PTX `cp.async.cg.shared.global`.
Verified SM120 (test_ldgsts.py) against nvcc-generated code.

## The working sequence (mirrors nvcc)

```
LDGSTS.E.BYPASS.128 [Rshared], desc[UR4][Rsrc.64]   ; async 16B/lane
LDGDEPBAR[wr=SB0]     ; bind ALL prior LDGSTS completions to SB0
DEPBAR.LE SB0, 0x0    ; drain: every LDGSTS has landed in shared
BAR.SYNC 0            ; warp-wide visibility
LDS.128 ..., [Rshared]; read the copied data
```

* **dest `[Rb]`** is a SHARED-window byte offset (0x400 with a 16 KB
  `#pragma SHARED(0x4000)` window).  It is NOT an absolute address.
* **source `desc[UR4][Ra.64+off]`** is a 64-bit global address (the same
  `desc`/address form as LDG).
* **`.BYPASS` requires `.128`** (spec condition); `.128` copies 16 bytes per
  lane.  `.32`/`.64` copy 4/8 bytes (verified single-lane).

## Completion / scoreboard semantics

LDGSTS writes shared memory and has IDEST_SIZE = 0 — it sets **no result SB
itself**.  Completion is tracked via LDGDEPBAR:

* **LDGDEPBAR** (`0x79af`, also DECOUPLED_RD_WR_SCBD) binds the completion of
  **every prior LDGSTS** to the SB named by its `wr` (`&wr=0x0` → SB0).
* **DEPBAR.LE SB0, 0x0** then waits until the tally drains (all LDGSTS have
  landed in shared).
* LDGSTS's own `rd_sb` (nvcc uses `&rd=0x2` = SB2) is an anti-dependency on
  the *source* registers (a later writer must not clobber the addresses
  while the async read is in flight).

In the verified hand-built pattern the LDGSTS carries no `req` on the
descriptor (`[7:2:{}:5:1]`); the LDCU.64 UR4/LDC.64 R6,R7 producers use SB3
and the in-place address bump `IADD3 R6, R6, R1` waits on SB3.  The
LDGDEPBAR `wr=SB0` + `DEPBAR.LE SB0,0x0` is what guarantees the shared data
is ready for LDS.

## Variants (sm120.json)

| variant | opcode | form |
|---------|--------|------|
| `ldgsts__RR32U` / `RR64U` | 0x1fae | dest [Rb(+URc+off)], src desc/Ra64 |
| `ldgsts__RUR` / `ldgsts__desc_RRU` / `memdesc_` | 0x1dae | uniform/desc forms |
| (2 more ALT) | | |

Modifiers: `e` (EONLY), `loc` (LOC: ACCESS/BYPASS), `cop` (COP), `sp2`,
`sz` (32/64/128), `fc` (FILLCTRL: nofillctrl/ZFILL), `sem`/`sco`/`private`
(TABLES_mem_3).  Encoding bits on the desc_RRU form: `cop`[86:84],
`sp2`[72:71], `sz`[75:73], `fc`[82], `loc`[81], `mem`[80:77]
(TABLES_mem_3), `Ra_URc`(desc UR)[71:64], `Ra`[31:24], `Rb`[23:16].

## Cross-comparison

* PTX `cp.async.cg.shared.global [smem], [gmem], 16` → `LDGSTS.E.BYPASS.128`.
* The `.BYPASS` loc (L2-bypass, 16B-aligned) is the standard bulk-copy form.
* `LDGDEPBAR` + `DEPBAR.LE SB0,0x0` + `BAR.SYNC` is the canonical wait;
  `cp.async.wait_all` lowers to the DEPBAR pair.
* Related: LDS/STS (shared window), LDG (global reads), LDGSTS.32/.64 for
  smaller async copies (e.g. strided gather into shared).

## Verified encodings (test_ldgsts.py, SM120)

* Warp round-trip: 32 lanes × 16 B = 512 B copied global→shared→global,
  every word matches.
* Single-lane `.128`, `.32`, `.64`.
* Encoding data bits (sz/cop/loc/mem, bits 64..104 and lo 0..15) match
  nvcc `-arch=sm_120` byte-for-byte.

## Open questions

* FILLCTRL.ZFILL (zero-fill on fault) not exercised.
* Multi-warp / LDGSTS pipelining (`DEPBAR.LE SB0, N` partial drains across a
  loop) not yet benchmarked — the pattern is the same as DEPBAR counting.
