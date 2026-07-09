# LDC — Load from Constant Memory

**Opcode mnemonic:** `LDC`  
**Pipe:** `mio_pipe` (MIO — memory I/O pipe)  
**INSTRUCTION_TYPE:** `INST_TYPE_DECOUPLED_RD_WR_SCBD` (decoupled read/write scoreboard)  
**VIRTUAL_QUEUE:** `$VQ_UNORDERED`

## Semantics

Loads data from the constant memory bank space `c[bank][offset]` into a destination
register `Rd`. The constant memory is a read-only, cache-optimized (uniform-access)
memory space used for kernel parameters and `__constant__` variables.

> Bank roles (see `../arch/cubin_elf.md`): **bank 0** = per-launch preset region +
> kernel params (`.nv.constant0`); **bank 3** = user `__constant__` bytes
> (`.nv.constant3`); **bank 4** = relocated 64-bit addresses of globals/extern
> functions/string literals (`.nv.constant4`).

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

The `.IL`/`.IS`/`.ISL` addressing modes are absent from all empirical traces and
are likely driver/runtime-internal only.

> **Update:** a *true* register-indexed `LDC Rd, c[0x0][R+imm]` (`ldc__RaNonRZ`)
> **is** emitted when a `__grid_constant__` parameter is indexed with a runtime
> value (dynamic subscript into an in-cbank param array). See the preset-region
> probe below — this is what enables reading arbitrary bank-0 offsets.

## Constant bank 0 (`c[0x0]`) preset-region layout — empirical

`c[0x0]` is split into a **driver-preset region** (`0x000`–`0x20f`) and the
**kernel-parameter region** (from `0x210`). The three fixed preset slots the SASS
prologue references are stable across kernel signatures (verified on 3 differently-
typed kernels, sm_90, CUDA 13.1):

**Verified slots** (each proven by a targeted H800 experiment — the value was made
to change with a known launch input, or matched against a `cvta`/`EIATTR` ground
truth). These supersede the "hypothesis map" further below where they overlap:

| Offset | Width | Meaning | Proof (repro) |
|--------|-------|---------|---------------|
| `0x00` | 32b | `blockDim.x` (ntid.x) | launch `block(2,4,6)` → `2` (`ldc_dims_probe.cu`) |
| `0x04` | 32b | `blockDim.y` | → `4` |
| `0x08` | 32b | `blockDim.z` | → `6` |
| `0x0c` | 32b | `gridDim.x` (nctaid.x) | launch `grid(3,5,7)` → `3` |
| `0x10` | 32b | `gridDim.y` | → `5` |
| `0x14` | 32b | `gridDim.z` | → `7` |
| `0x18` | 64b | **shared** memory window base (generic) = `{SR_SWINHI, SWINLO}` | `== __cvta_shared_to_generic(0)` (`ldc_winbase_verify.cu`) |
| `0x20` | 64b | **local** memory window base (generic), i.e. `cvta.local` base | `== &loc − __cvta_generic_to_local(&loc)` (`ldc_winbase_verify.cu`) |
| `0x28` | 32b | per-thread local/stack frame base → `R1` | `LDC R1, c[0x0][0x28]`; `DW_CFA_def_cfa R1,+frame` |
| `0x2c` | 32b | dynamic shared-memory size | launch `…,3072` → `0xc00` (`ldc_midregion_probe.cu`) |
| `0x30` | 32b | per-context **launch serial counter** | increments +1 every launch in the sweep (1,2,…,c) |
| `0x44`:`0x48` | 64b | **cooperative-grid sync barrier ptr** (hi@`0x44`, lo@`0x48`) | nonzero *only* under `cudaLaunchCooperativeKernel`; else `0` |
| `0x110` | 32b | **cooperative-launch flag** | `1` only for coop launch, else `0` |
| `0x13c` | 32b | shared allocation top = `0x400` + dyn-smem size | `0x400` base; `→0xc00` with 2048-byte dyn smem |
| `0x144`/`0x148`/`0x14c` | 32b×3 | **cluster dims** {x,y,z} | `cluster(4,1,1)` → `0x144=4` |
| `0x150`/`0x154`/`0x158` | f32×3 | **`1.0f / clusterDim.{x,y,z}`** (reciprocals for rank decode) | `clusterDim.x=4` → `0x150=0x3e800000`=0.25f |
| `0x15c`/`0x160`/`0x164` | 32b×3 | **grid size in cluster units** = gridDim/clusterDim | `grid(8),cluster(4)` → `0x15c=2`; else = gridDim |
| `0x16c` | 32b | `0x0100_0000` = `1<<24`, DSMEM per-CTA slice width | constant across all configs |
| `0x208` | 64b | **global** memory descriptor (`= 0`) | `ULDC.64 URn,c[0x0][0x208]` → `STG.E desc[URn]` |
| `0x210` | var | kernel parameter block base | `EIATTR_PARAM_CBANK` low16 = `0x210` |

### Launch-config sweep (definitive slot identification)

`tests/cbank0_sweep.cu` dumps the whole preset region under 12 launch configs
(baseline; each `blockDim`/`gridDim` axis; large grid; dyn-smem; cluster dims;
cooperative) and reports which slots move with which input. This is how the
launch-shape slots above were pinned — each changes iff its corresponding launch
parameter changes. Highlights:

- **`0x44:0x48` resolves the cusparse mystery**: it is the cross-grid (cooperative)
  barrier object pointer. `sell_find_colors_*` are cooperative kernels — their
  `ISETP.NE.EX …UR12/UR13; @P0 BRA … else BPT.TRAP` prologue is the "you must launch
  me cooperatively" guard (traps when the barrier ptr is null). Word order is
  hi@`0x44`, lo@`0x48` (matching the `ULDC UR12,[0x48]; ULDC UR13,[0x44]` pairing).
- **Cluster block** (`0x140`–`0x188`): dims at `0x144/48/4c` (dup at `0x188`),
  reciprocals at `0x150/54/58`, grid-in-clusters at `0x15c/60/64`, `0x140`=cluster-present
  flag. `cluster(2,2,1)` failed to launch (misconfig on this GPU) so y/z dims are
  inferred from the x-axis behavior.
- Several **driver ring pointers** advance by a fixed stride per launch (`0x38` by
  `0x800`, `0xc0:0xc4` by `0x10000`) — internal launch/desc ring buffers, not kernel-visible.

### No SM-frequency or power values in the preset region

Checked explicitly (`tests/cbank0_hwprops.cu`, `tests/cbank0_loadtest.cu`): the region
carries **no clock or power telemetry**.
- The SM clock (1,755,000 kHz) and memory clock (1,593,000 kHz) do **not** appear in
  any unit (kHz `0x1ac778`, MHz `0x6db`, or Hz `0x689b2cc0`) at any offset.
- Under a sustained FMA burn the GPU swung **power 49→144 W** and **clock 345↔1755 MHz**,
  yet the only slots that changed were the launch counter (`0x30`) and the driver ring
  pointers (`0x38`, `0xc0`, and the `0xc0`-derived `0x198`/`0x1a0`) — launch-sequencing
  artifacts, unrelated to power/clock. Every capability/shape slot was byte-identical
  idle vs. under load.
- This is expected: the preset region is populated once at launch setup, so a live
  frequency/power reading has no place there. Runtime timing instead comes from special
  registers — `clock64()` → `S2R …, SR_CLOCKLO/HI`; wall-clock → `SR_GLOBALTIMERLO/HI`.

The **only** hardware-capability constant found is `0x10c = multiProcessorCount`
(SM count, `114` on H800 PCIe). Other stable constants (`0x40`, `0x68`, `0x1a8`,
`0x3c`) are size/quota-like driver values, none clock- or power-derived.

### Shared-memory layout is present; L1/shared *carveout* is not

`tests/cbank0_smem_carveout.cu` sweeps dynamic-smem size (0…200 KB) and the
L1/shared **carveout** preference (`MaxL1`, `MaxShared`, `50%`, default). Results:

- **Size/layout slots (present):**
  - `0x2c` = dynamic shared-memory size (0→`0x8000` at 32 KB, `0x32000` at 200 KB)
  - `0x13c` = `0x400` + dynamic size (top of the shared allocation)
  - `0x114` = `0x400` (shared-window base offset — the reserved first 1 KB, same value
    the prologue materializes as the `UMOV UR4,0x400` immediate)
  - `0x16c` = `1<<24` (DSMEM per-CTA slice width)
- **Carveout (NOT present):** switching `cudaFuncAttributePreferredSharedMemoryCarveout`
  between MaxL1 / MaxShared / 50% changed **no** preset slot (the `dyn=0` columns and
  the `dyn=8K` columns are byte-identical apart from the launch counter/ring pointers).

Conclusion: the kernel is told *how much* dynamic shared memory it has (`0x2c`,`0x13c`)
and the shared-window geometry (`0x114`,`0x16c`), but the **L1↔shared split** is a
physical SM configuration the driver programs into the SM's config registers at launch;
it is never surfaced to kernel code through the constant bank. (Bank-width config, the
old `cudaSharedMemConfig`, is likewise fixed at 4-byte on sm_90 and absent here;
`SR_SMEMBANKS`/`SR_SMEMSZ` special registers exist if a kernel needs those at runtime.)

### Register count / local / static-shared footprint is NOT in the preset region

The per-function code attributes reported by `cudaFuncGetAttributes` live in the ELF
`EIATTR_*` metadata (and drive SM hardware config), **not** in `c[0x0]`. Verified with
`tests/cbank0_funcattr.cu` + `tests/cbank0_localbacking.cu`:

| `cudaFuncAttributes` field | varied | preset slot? | actually stored in |
|----------------------------|--------|:---:|--------------------|
| `numRegs` | 8 → 14 | none changed | `EIATTR_REGCOUNT` (ELF) |
| `localSizeBytes` | 0 → 1 KB → 32 KB → 64 KB | none changed | `EIATTR_FRAME_SIZE`/`MIN_STACK_SIZE`; the frame is the `VIADD R1,-N` immediate, base at `0x28` |
| `sharedSizeBytes` (static) | — | none | ELF EIATTR + computed offsets |
| `maxThreadsPerBlock` | 1024 → 128 | none (`0x80` never appeared) | `EIATTR_MAX_THREADS` |
| `constSizeBytes` | — | — | `EIATTR_PARAM_CBANK` size |

Notably, launching 64 KB/thread of local at full occupancy (228×1024 threads)
allocated a **~14 GB local backing store** (free mem 80→66 GB) yet moved **no** preset
slot — so `0x40`/`0x1a8` are *not* the local backing-store size either; they remain
unidentified stable driver constants (definitively **not** register/local/freq/power/
memory-size derived). A kernel never needs to read its own register/local/shared counts
at runtime: they are fixed at compile time and baked into the SASS/ELF.

The cluster-related `cudaFuncAttributes` (`requiredClusterWidth`,
`clusterSchedulingPolicyPreference`, …) *do* have launch-time analogues in the preset
region — the cluster block at `0x140`–`0x188` (dims, reciprocals, grid-in-clusters).

Key relationships confirmed:
- All three memory *windows* have a generic base in this region: **shared** `0x18:0x1c`,
  **local** `0x20:0x24`, plus the stack offset `0x28` and the global descriptor `0x208`.
- The **shared-space** (STS/LDS) *offset* base `0x400` is **not** read from here — it
  is an immediate (`UMOV UR4,0x400`) added to `SR_CgaCtaId<<24`; see `sts.md`
  "Shared-memory address model". `c[0x0][0x18:0x1c]` is the *generic* (cvta) base,
  a different quantity.
- `EIATTR_PARAM_CBANK` / `EIATTR_CBANK_PARAM_SIZE` / `EIATTR_FRAME_SIZE` in
  `.nv.info.<kernel>` corroborate the `0x210` base, param size, and the `R1 -=` frame.

### Library mining — which preset slots real code reads

`cuobjdump -arch sm_90 -sass` over the CUDA 13 math libs, counting `LDC/ULDC c[0x0][off]`
with `off < 0x210` (`/tmp` scan; per-lib counts):

| Lib | preset offsets read |
|-----|---------------------|
| libcublas | `0x00,04,08,0c,10,14` (dims), `0x28` (4137×), `0x208` (3801×) — nothing else |
| libcurand | `0x00,04,08,0c`, `0x28`, `0x208` |
| libcusolver | dims, `0x28`, `0x208`, + `0x6c` (20×) |
| libcusparse | dims, `0x28`, `0x208`, + `0x20/0x24` (26× — `cvta.local`), + `0x44/0x48` (11×) |
| libcufft | (no sm_90 SASS in this build) |

Takeaway: real kernels overwhelmingly touch only **dims + stack base (`0x28`) + global
descriptor (`0x208`)**. The window-base slots (`0x18`,`0x20`) appear only when a kernel
forms a generic pointer to shared/local (cusparse `cvta.local`). `0x44/0x48` (cusparse
`sell_find_colors_*`) is now **resolved** as the cooperative-grid barrier pointer (see
sweep below). `0x6c` (cusolver `sort_diag_of_T`) reads `0` under every tested config
(block/grid/dyn-smem/cluster/coop) — still unidentified; its cusolver use sits in a
`assert(gridDim==1)`-style path, so it may be a slot only populated by an internal
launch route.

### Reading the preset region (methodology)

PTX forbids immediate `.const` addresses (`ld.const.u32 %r,[0x208]` →
*"Immediate addresses allowed only for .local state space"*). Instead, dynamically
index a `__grid_constant__` param, which ptxas lowers to register-indexed
`LDC Rd, c[0x0][R + 0x210]`; a **negative** index reaches the preset region below
the param base. Repro: `tests/ldc_dump_const.cu`.

Offset math validated by planting sentinels in the grid-constant payload
(`0xdeadbeef/0xcafebabe/0x12345678` read back exactly at `0x210/0x214/0x218`).

### Global memory descriptor value (H800 PCIe, driver 580.82.07, CUDA 12.8)

```
c[0x0][0x208..0x20f] = 0x0000000000000000
```

The default global memory descriptor is **all-zero**. Confirmation is self-consistent:
the probe kernel's own `out[i] = …` compiles to `STG.E desc[UR][…]` with `UR` loaded
from `c[0x0][0x208]` (= 0), and the store returns correct data — so `desc[UR=0]`
**is** the functional "generic global" descriptor. The value is stable across launches,
whereas the adjacent slot `0x200/0x204` is a per-launch cookie (changes every run).

### Full preset-region layout (hypothesis map — partially verified)

> **Status:** this map was seeded by a broad single-run dump before the targeted
> experiments above. Rows that the "Verified slots" table now confirms/corrects are
> marked inline; the rest are **retained as unverified hypotheses**. Where the two
> disagree, the verified table wins.

Dumped on H800 PCIe, driver 580.82.07, CUDA 12.8, `<<<1,1>>>` kernel.
Values are from a single run; per-launch cookies and ASLR-dependent pointers
will vary across invocations. Structural quantities (sizes, offsets, constants)
are expected stable. Repro: `tests/cbank0_dump.cu`.

#### Confirmed fixed slots
| Offset | Width | Value (this run) | Meaning | Proof |
|--------|-------|----------|---------|-------|
| `0x28` | 64b | `0x00fffdc0_00000000` | per-thread local/stack base | SASS `LDC R1, c[0x0][0x28]`; `DW_CFA_def_cfa R1,+frame` |
| `0x114` | 32b | `0x00000400` | shared-window **base offset** (reserved first 1 KB) — constant `0x400`; the prologue uses the same value as an immediate (`UMOV UR4,0x400`) rather than reading it. Paired with `0x13c` = `0x400`+dyn-smem (allocation top). |
| `0x134` | 32b | `0x00000400` | duplicate `0x400` slot (unverified) |
| `0x208` | 64b | `0x00000000_00000000` | global memory descriptor | SASS `ULDC.64 URn, c[0x0][0x208]` → `STG.E desc[URn]` |
| `0x200` | 64b | varies | per-launch cookie / CGA ID | changes every run; zero in first run, non-zero in others |

#### Size / quota hypothesis (scope: per CTA, SM, or kernel)
| Offset | Value | Decimal | Hypothesis |
|--------|-------|---------|------------|
| `0x38` | `0x04c0_c000` | 79,691,776 (~76 MiB) | ~~local/stack window size~~ **CORRECTED:** advances by `0x800` every launch (ring buffer ptr low half), not a size |
| `0x40` | `0x0384_32c8` | 58,995,400 | constant across all configs *and* under load; another driver value (unverified; **not** clock/power) |
| `0x68` | `0x0120` | 288 | constant; unknown (unverified; not clock/power) |
| `0x16c` | `0x0100_0000` | 16,777,216 | **RESOLVED:** `1<<24` = DSMEM per-CTA slice width; constant across all configs |
| `0x10c` | `0x72` | 114 | **RESOLVED:** `multiProcessorCount` (SM count) — H800 PCIe = 114 SMs |
| `0x1a8` | `0x04e0_0000` | 81,788,928 (78 MiB) | constant; likely local-memory backing-store size (unverified; not clock/power) |
| `0x3c` | `0x2` | 2 | constant; unknown (unverified) |
| `0x1ac` | `0x2` | 2 | constant; unknown (unverified) |

#### Driver pointer table (hypothesis: function descriptor table / CBU page table)
All share same high-32b base in this run (`0x00007f6f_…`), which is ASLR-dependent.

| Offset | 64-bit value | Hypothesis |
|--------|-------------|------------|
| `0x20` | `0x00007f6f_f5000000` | **RESOLVED — not a driver pointer:** this is the **local-memory window generic base** (`0x20:0x24`, 64-bit); `== cvta.local` base. See Verified slots. |
| `0x24` | (hi32 of `0x20`) | high 32b of the local window base |
| `0xc0` | `0x00007f6f_ea280000` | function descriptor table base? (unverified) |
| `0xc8` | `0x00007f6f_ea010000` | offset table (deltas: `0xea280000 − 0xea010000 = 0x270000`) |
| `0x118` | `0x00007f6f_eb7ac200` | another table pointer |
| `0x170` | `0x00007f70_00000000` (hi32 @ 0x174) | hi32 of a different pointer region |
| `0x198` | `0x00007f6f_ea280210` | = `0xc0` + `0x210` → constant-bank parameter area alias |
| `0x1a0` | `0x00007f6f_ea280318` | = `0xc0` + `0x318` → another offset into same table |

The derived offsets `0xc0 + 0x210` and `0xc0 + 0x318` suggest a base table
whose entries are at fixed displacements, with `0x210` mirroring the parameter
base. Likely the driver's internal CBU page table or kernel descriptor vector.

#### FP32 pool → cluster-dim reciprocals (RESOLVED)
| Offset | Value | Meaning |
|--------|-------|---------|
| `0x150` | `0x3f800000` (1.0f) | **`1.0f / clusterDim.x`** — `cluster(4,1,1)` → `0x3e800000` (0.25f) |
| `0x154` | `0x3f800000` (1.0f) | `1.0f / clusterDim.y` |
| `0x158` | `0x3f800000` (1.0f) | `1.0f / clusterDim.z` |
| `0x15c` | `0x00000001` | **grid size in cluster units .x** = gridDim.x / clusterDim.x |

Not a generic FP constant pool: the three `1.0f` are per-axis **reciprocals of the
cluster dimensions**, used to decode a linear cluster rank into 3-D by
multiply-by-reciprocal. They only stay `1.0f` because a non-clustered launch has
`clusterDim = (1,1,1)`. `0x15c/0x160/0x164` continue as grid-in-cluster-units.

#### Launch-config / grid shape (mostly RESOLVED via sweep)
| Offset | Value | Meaning |
|--------|-------|------------|
| `0x00–0x14` | six `0x00000001` | **RESOLVED:** `0x00-0x08` = `blockDim.{x,y,z}`, `0x0c-0x14` = `gridDim.{x,y,z}` |
| `0x140` | `0x00000000` | **RESOLVED:** cluster-present flag (`1` when clustered) |
| `0x144–0x14c` | `1, 1, 1` | **RESOLVED:** `clusterDim.{x,y,z}` (`cluster(4,1,1)`→`0x144=4`) |
| `0x15c–0x164` | grid/cluster | **RESOLVED:** grid size in cluster units (gridDim/clusterDim) |
| `0x188` | `0x00000001` | **RESOLVED:** duplicate of `clusterDim.x` |

(Also resolved elsewhere: `0x18:0x1c` = shared window generic base; `0x2c` = dynamic
shared-memory size; `0x30` = launch serial counter; `0x44:0x48` = cooperative barrier
ptr; `0x110` = cooperative flag; `0x13c` = `0x400`+dyn-smem — see Verified slots + sweep.)

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
- **`ldc__RaNonRZ` (indexed LDC):** ~~Under what circumstances does a true
  `ldc__RaNonRZ` get emitted?~~ **Resolved:** a runtime-indexed `__grid_constant__`
  param array emits `LDC Rd, c[0x0][R+0x210]` (see preset-region section). Generic
  `ld.const` register loads still lower to ULDC; the difference is per-thread
  (divergent) vs uniform index.
- **LDCU resolution:** If `LDCU` is truly a separate instruction (not just LDC),
  what is its sm_90 opcode?
