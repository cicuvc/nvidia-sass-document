# SM120 (Blackwell / RTX 5090) — encoding & addressing findings

Empirical investigation on `sm_120` (RTX 5090, GB202), CUDA 12.8, driver 590.x.

## 1. Encoding substrate: identical to sm_90 / sm_100

| Property | sm_90 | sm_100 | sm_120 |
|----------|:-----:|:------:|:------:|
| Instruction word width | 128-bit | 128-bit | 128-bit |
| Opcode field | `{bit[91], bits[11:0]}` 13-bit | same | same |
| Control word (FUNIT) | ~565 fields | same positions | same positions |
| Register widths | 8-bit GPR, 6-bit UR | same | same |
| Predicate encoding | 3-bit + not bit | same | same |
| Pipe sets | 10 (no ttu) | 11 (+ ttu) | 11 (+ ttu) |
| ELF_ID / ABI | 190 / 0x33 | same | same |

All shared instructions (IADD3, FFMA, FMUL, LDC, STG, EXIT, BRA) use identical opcode values
across all three architectures. Verified by compiling & disassembling on SM120 hardware.

## 2. Control word / stall count encoding

From `notes/sm90/arch/control_codes.md` — confirmed working on SM120:

| Field | Bits | Width | Semantics |
|-------|------|------:|-----------|
| `opex` | [124:122]∥[109:105] | 8 | `(batch_t << 5) \| usched_info` |
| `req_bit_set` | [121:116] | 6 | wait barrier mask (SB0..SB5) |
| `src_rel_sb` | [115:113] | 3 | read scoreboard release (7=none) |
| `dst_wr_sb` | [112:110] | 3 | write scoreboard release (7=none) |
| `pm_pred` | [103:102] | 2 | perf-monitor predicate |

**Translation stall (transN):**
- `usched_info` = 17+N-1 (trans1=17, trans2=18, …, trans7=23, …, trans11=27)
- Occupies hi64 bits [45:41] (lower 5 bits of opex)
- `batch_t=0` (NOP) for almost all instructions
- `WAITn_END_GROUP`: usched_info = 1..15 (opex[4]=0)

**Verified control word for UMOV with trans7:**
```
opex = 23 → hi64 bits [60:58]=0b000, [45:41]=0b10111
hi64 |= (7 << 49) | (7 << 46)  // src=7, dst=7, no barriers
→ 0x000fee0000000000  (cuobjdump shows "?trans7")
```

**MOV32I with trans7 + wmsk=0xf:**
```
0x000fee0000000f00  (cuobjdump shows "MOV R5, 0xcafebabe ?trans7")
```

## 3. `desc[UR]` addressing: 64-bit cache policy descriptor (not a table index)

**Corrected interpretation (empirically proven on SM120):**

`desc[UR4]` consumes the UR4:UR5 uniform register pair as a **64-bit L2 cache
eviction policy word**, introduced at sm_80 alongside `createpolicy`.
- UR4 (low 32 bits): base policy, typically 0 = default/no special policy.
- UR5 (high 32 bits): encodes cache priority, fraction/window fields.

The "table index" interpretation was disproven:
1. All UR4 values produce identical behavior — there is no table of base addresses.
2. UR5 bytes of 0xFF cause hardware faults — the word is validated as a policy.
3. `ULDC.64` loads the full 64-bit pair; both registers are consumed.
4. sm_80 SASS shows `UMOV UR5, 0x14f00000` directly — the same policy encoding.

**Corrections to `notes/sm90/instr/ldg.md` and `stg.md`:**
- `desc[URx]` is NOT a descriptor table index — it's a 64-bit cache policy word.
- `c[0x0][0x358]` provides the default policy (0), which means "no special
  eviction policy." The driver fills it with 0.

## 4. UTMALDG / TMA: direct GPU pointer, address-space-agnostic

**`UTMALDG.2D [UR8], [UR4]`**: UR4 is a **direct 64-bit GPU pointer** to a 128-byte TMA descriptor.
The TMA hardware accepts the descriptor in **any address space** — grid-constant or generic global.

**Grid-constant descriptor:**
```
LDCU.64 UR4, c[0x0][0x348]   ← load grid-constant param address
UTMALDG.2D [UR8], [UR4]       ← UR4 = grid-constant address of CUtensorMap
```

**Global-memory descriptor (verified working on SM120):**
```
LDCU.64 UR4, c[0x0][0x380]   ← load regular param (pointer to global memory)
UTMALDG.2D [UR8], [UR4]       ← UR4 = generic global address of CUtensorMap
```

The SASS is identical — only the constant bank offset differs. The TMA engine
treats UR4 as a generic address; it is host's responsibility to place the
descriptor in valid GPU memory (via `cudaMemcpy` for global, or
`__grid_constant__` for grid-constant).

**Verified on SM120 (via `cvta.to.global.u64` + `ld.b32`):**

```
UR4 value from c[0x0][0x348] = 0x00007f9f7a280380  (GPU virtual address in grid-constant space)
cvta.to.global.u64 → converts to generic address
ld.b32 from this address → reads TMA descriptor bytes
Descriptor byte 0-7 = d_src pointer (verified against host-side CUtensorMap)
```

**Key difference: STG/LDG `desc[]` vs UTMALDG `[UR]`:**

| | STG/LDG `desc[UR4]` | UTMALDG `[UR4]` |
|---|---|---|
| URx semantics | 64-bit **cache policy word** (UR4:UR5 pair) | Direct **64-bit GPU pointer** |
| c[0x0] offset | 0x358 (driver fills with 0 = default policy) | 0x348 (grid-const) / 0x380 (global ptr) |
| Hard-coded alt | `desc[URZ]` works (zero policy) | N/A |
| Introduced | sm_80 (with `createpolicy`) | sm_90 (with TMA) |

## 5. Memory policy descriptor vs TMA

The 64-bit `desc[UR4:UR5]` cache policy mechanism (introduced at sm_80 alongside
`createpolicy`) and TMA's direct-pointer model coexist on SM120. `desc[UR4:UR5]`
encodes L2 eviction policy — UR4 = base (typically 0), UR5 = priority + fraction/window.

TMA uses direct pointers to 128-byte descriptors instead because TMA descriptors
are far too large (128 bytes) to fit in two 32-bit registers. TMA descriptors are
stored as grid-constant or global-memory parameters and referenced by direct pointer.

## 6. Constant bank 0 on SM120 vs SM90

**SM90:** `__grid_constant__` parameters placed adjacent to preset region; negative-offset
trick (`base = -0x210/4; b.a[base+i]`) reads preset values.

**SM120:**
- `__grid_constant__` negative-offset trick does NOT work (reads zeros)
- Regular parameter negative-offset also fails
- Large struct parameters (> some threshold) passed by pointer, not by value
- `#pragma unroll 0` is IGNORED by SM120 compiler
- Unrolled loop with negative base still works (compiler emits correct LDC offsets)
- Grid-constant memory accessible via `cvta.to.global.u64` + generic load

**Working probe method on SM120:**
```c
const int base = -40;
for (int i = 0; i < 64; i++) {
    uint32_t v = probe_param.pad[base + i];  // compiler emits LDC
    out[i] = v;
}
```

## 7. Minimal hand-built cubin

**Structure** (from `tools/build_sm120_cubin.py`):
- ELF skeleton reused from compiled template
- `.text` section patched with custom SASS
- Mercury/capmerc sections stripped (not required for loading)
- `cuModuleLoadData` → `cuModuleGetFunction` → `cuLaunchKernel` confirmed working

**Minimum instruction set for writing a value to global memory:**
```
MOV R5, 0xcafebabe              ?trans7    (MOV32I with wmsk=0xf)
LDC.64 R2, c[0x0][0x380]        ?trans2    (load kernel param = out[] ptr)
STG.E desc[URZ][R2.64], R5      ?trans1    (store with URZ descriptor)
EXIT                             ?trans5
```

**Key encoding formulas:**
```
MOV32I Rd, imm:  lo = (imm << 32) | (Rd << 16) | (7 << 12) | 0x802
                  hi = (usched << 41) | (7 << 49) | (7 << 46) | (0xF << 8)

UMOV URd, imm:   lo = (imm << 32) | (URd << 16) | (7 << 12) | 0x882
                  hi = (usched << 41) | (7 << 49) | (7 << 46)

STG.E desc[URZ][R2.64+off], Rb:
                  lo = (off << 40) | (Rb << 32) | (2 << 24) | 0x7986
                  hi = CTL_STG | 0xFF  // URZ=0xFF in hi64[7:0]

LDC R1, c[0x0][0x37c] — can be OMITTED (not required for basic kernels)
MOV64I — sets R2.64 atomically, but STG requires c[0x0][0x380] provenance for address
```

## 8. TMA load SASS mapping (2D, mbarrier)

```
mbarrier.init            → SYNCS.EXCH.64
mbarrier.arrive.expect_tx → SYNCS.ARRIVE.TRANS64
mbarrier.try_wait        → SYNCS.PHASECHK.TRANS64.TRYWAIT + spin loop
cp.async.bulk.tensor.2d  → UTMALDG.2D
fence.proxy.async        → FENCE.VIEW.ASYNC.S
__syncthreads()          → BAR.SYNC.DEFER_BLOCKING

ELECT P1                 → single-lane election for TMA dispatch
BSSY.RECONVERGENT + BSYNC → thread-0 / others divergence pattern
```

**Constant bank layout for the TMA kernel (2-param + grid_constant):**
```
c[0x0][0x348]  = tma_desc (__grid_constant__, 128 bytes)  → loaded via LDCU.64
c[0x0][0x358]  = STG desc[UR] default policy slot. With no stream policy: 0.
                  With cudaStreamSetAttribute(AccessPolicyWindow): non-zero 64-bit
                  CVT-format descriptor (UR4 and UR5 both populated).
                  This is the default L2 cache policy applied to all global memory
                  ops on the stream, picked up via `LDCU.64 UR4, c[0x0][0x358]`.
c[0x0][0x37c]  = global mem descriptor (LDC R1 target)    → ABI, can be omitted
c[0x0][0x400]  = gmem_out pointer (regular param)
```

## 9. Open questions

- Exact TMA descriptor binary format (word-level decoding)
- Whether other descriptor table indices (1, 2, …) map to different address spaces
- Why `#pragma unroll 0` is ignored on SM120 PTXAS
- SM120 constant bank 0 preset region layout (differs from SM90)
- `MOV64I` vs `LDC.64` provenance requirement for STG addresses

## 10. ILLEGAL_INSTRUCTION on high registers = regcount undercount (resolved)

**Old theory (WRONG):** R14–R16 were thought to be "reserved by the launch
path" because `MOV R14, RZ` etc. faulted with `CUDA_ERROR_ILLEGAL_INSTRUCTION`
while R0–R13/R17+ worked.

**Actual cause — the EIATTR_REGCOUNT undercount.** The GPU reserves the
**top 2 registers of each 8-register allocation window**: a kernel declaring
`regcount = N` may only use registers `[0, N-2)`. The assembler computed
`regcount = roundup8(max_reg + 1)` with a floor at multiples of 8, which
undercounted at window boundaries:

| max_reg | old regcount | usable [0,N-2) | register usable? |
|--------:|-------------:|---------------:|:----------------:|
| 16 (R16) | 16 | [0,14) | **no** (R14–16 fault) |
| 22 (R22) | 24 | [0,22) | **no** (R22–23 fault) |
| 24 (R24) | 24 | [0,22) | **no** (also the roundup bug) |
| 30 (R30) | 32 | [0,30) | **no** (R30–31 fault) |
| 38 (R38) | 40 | [0,38) | **no** (R38–39 fault) |

Fixed formula in `assembler/sass_elf.py::_compute_regcount`:
`regcount = max(8, ((max_reg + 10) // 8) * 8)`  (= `ceil((max_reg+3)/8)*8`,
the +3 = one register count + two reserved). After the fix **every register
0..255 is usable**; the same cubin that faulted before runs correctly, and
`compute-sanitizer` (which adjusts the launch config) had masked the bug.

ptxas's own allocation naturally leaves this headroom (a regcount-40 kernel
uses at most R37, never R38/39), which is why real cublas SASS never trips it.
