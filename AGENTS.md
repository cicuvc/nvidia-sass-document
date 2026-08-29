# AGENTS.md

## What this repo is
Reverse-engineering repo built around two nvdisasm-dumped ISA description files for the **Hopper (sm_90)** SASS instruction set. There is no build/test/lint — do not look for a package manager, CI, or entrypoints. The work is *reading and interpreting* these files to reconstruct how to decode SASS instructions (encoding, functional-unit grouping, latencies) and writing per-instruction reference docs. Tooling (`tools/`) + research notes (`notes/`) + a doc checklist (`TODO.md`) sit on top of the raw dumps.

- `sm_90_instructions.txt` (~159k lines) — full instruction/encoding spec.
- `sm_90_latencies.txt` (~441 lines) — pipe grouping, scoreboard/latency tables.

Both are grep-first: never `Read` them whole. Use `grep -n` to locate a section, then read a bounded window.

### Current state
- **197/207** compute instructions documented (notes + decoder + test kernel). Only `F2FP` and `RTT` remain unchecked.
- **194 notes** (`notes/`) — 168 per-instruction + 26 cross-cutting / infrastructure notes (pipes, scoreboards, memory model, CBU state, tensor-core microarch, FDA/bit-accurate MMA model, etc.).
- **109 decoders** (`tools/decode_*.py`) — one per documented instruction, each validated against real cuobjdump vectors.
- **177 CUDA kernels** (`tests/*.cu`) + **87 assembler/round-trip tests** (`tests/asm_construct/test_*.py`) that build SASS by hand, load it through `assembler/`, and run it on a GPU.
- **124 tool scripts** total in `tools/` (incl. `parse_sm90.py`, `query_sm90.py`, decoders, `hmma_model.py`, shared libs).

### Current work
The repo now also ships a **working SASS assembler + GPU runner** (`assembler/`,
see `ASSEMBLER_MANUAL.md`) and a bit-accurate tensor-core fp16/bf16/fp8
reference model (`tools/hmma_model.py`).  Tests build kernels as SASS text,
assemble to cubin, and run them (HMMA/QMMA tensor-core, LDG/STG, cp.async,
memory model probes).  Doc-writing continues against `TODO.md`.

## Tooling (`tools/`)
A stdlib-only extractor turns the spec into a queryable JSON DB — prefer it over ad-hoc `grep`/manual parsing for structured lookups.
- `python3 tools/parse_sm90.py` — parses both `.txt` files -> `sm90.json` (~21 MB, gitignore-worthy/regenerable). Has a built-in validation gate; a clean run prints `validation OK` with counts: **1589 variants** (1168 `CLASS` + 421 `ALTERNATE CLASS`), **238 mnemonics**, 414 enums, 84 tables, 2309 FUNIT fields, 277 pipe entries.
- `python3 tools/query_sm90.py <cmd>` — query `sm90.json`. Commands: `mnem <NAME>`, `class <name> [-v]`, `opcode <hex|0b|int>`, `layout <class>` (128-bit field map), `fields <regex>`, `enum <Name>`, `table <Name>`, `pipe <MNEMONIC>`, `stats`.
- Regenerate `sm90.json` after any parser change; trust the validation gate (asserts opcode presence + bit ranges ⊆[0,127] + width==Σ span per field).

Parser gotchas already handled (don't reintroduce): sub-section keywords and even the next `CLASS` can be **glued after `;` with no newline** (`;OPCODES`, `ENCODING!..._unused`, `;CLASS "..."`); multiple `BITS_` statements may share one physical line; field names can contain digits, so bit-pairs are consumed until their count equals the declared width; `imad_pseudo_*` classes carry a `REMAP "..."` directive instead of `BITS_` (no opcode field — expected).

## Assembler (`assembler/`)
A hand-written SASS → cubin toolchain targeting **sm_120** (regenerated `sm120.json`), plus a CTypes CUDA runner and a scoreboard dependency checker.  Full syntax and feature list: **`ASSEMBLER_MANUAL.md`** (read it before writing SASS-by-hand tests).

Key entry points (`from assembler import ...`):
- `assemble(source, kernel_name="", check_deps=True, strict_deps=False) -> bytes` (cubin)
- `assemble_kernel(source, ...) -> AssembleResult` (also `.encoded` = list of `(lo64,hi64)`, `.params`)
- `assemble_flat(source) -> list[(lo64,hi64)]` — encode only, for decoder/round-trip tests
- `CudaModule(cubin)` — `launch(func, grid, block, args)`, `devmem_alloc/free`, `device_read/write`, `synchronize`; drives the GPU without nvcc at runtime

Source dialect essentials (see §3–§4 of the manual):
- Kernel: `#fn name(p1<4>, p2<8>) { ... }`; `<size>` is the parameter's byte
  width (pointer = 8, tensor map = 128), NOT the buffer size a pointer points
  at; `#param(name)` → `c[0x0][0x380+off]`; `#spec_const(SLOT_DEFAULT_CDESC)`
  → `c[0x0][0x358]` (default global cache descriptor); `#pragma NAME(value)`
  sets `MAXREG_COUNT`/`SHARED`/`SHADER_TYPE`/`MBARRIER_*`; labels via
  `#def_label(name)` + `#label(name)`.
- Scheduling bracket `[wr:rd:{req}:stall:yield[:batch_t]]` on every line; scoreboards are SB0–SB5 (7 = none, 6 rejected).
- **Cross-barrier waits MUST go in `{req}`, not `rd`** (probe-verified the hard way, sassdbg probe3): `rd=2` on a MOV32I did NOT wait (CALL target from LDC → 718 INVALID_PC), `rd=1` on an STG.64 did NOT wait the LDC address pair (garbage → 700); the same waits via `{2}`/`{0,1}` work. LDC/LDCU/LDG are variable-latency — the first consumer of ANY result register (incl. the UR4/UR5 desc pair) must wait its barrier via req; stall cycles do NOT cover it. (Re-claiming an already-used barrier (e.g. RPCMOV `wr=0` on top of LDCU's) lets one `req={0}` cover all outstanding claims on it.
- **S2R SR_CTAID.X is a SLOW scoreboarded read** (probe: /tmp bisect, m3c bring-up): nvcc claims a barrier on it and the consumer waits via req (`S2R R7, SR_CTAID.X;[0:7:{}:7:0]` … `IMAD …;[7:7:{0}:4:1]`).  Stall cycles alone need ≥8 NOPs (~100+ cyc) to be safe; a stall-5 consumer reads PER-LANE GARBAGE (launch residue), and different consumers in adjacent instructions can disagree.  Waiting the claimed barrier via `{req}` is exact even at zero padding.  SR_TID.X is fast (stall 5 suffices).  Local memory addressing gotcha re-confirmed during the same bring-up: `STL/LDL [RZ+imm]` must target ≥ LMEMHIOFF (0xfff9c0) — address 0 faults 700; and when fixing a 64-bit address by hand, add offsets to the LOW register of the pair.
- **64/128-bit operands MUST be explicit register groups** `{Ra,Rb}`/`{Ra,Rb,Rc,Rd}` (cuobjdump prints the scalar shorthand; the assembler source requires groups — this is the #1 gotcha).
- `LDCU` is the sm_120 name of `ULDC`.
- HMMA/QMMA results are NOT scoreboarded (COUPLED_EMULATABLE): pad **≥16 NOP** before reading `Rd` (fewer can fault 0x715).
- QMMA srcFmt enum (probed): `E4M3=0, E3M4=1, E2M3=2, E5M2=4, E3M2=5, E2M1=6`.
- `CudaModule.launch` packs pointer args as 8 bytes and `bytes` args (tensor
  maps) at their full size; param sizes are read from the cubin's KPARAM.

Running tests: `python3 tools/run_tests.py [-j N]` (parallel processes; timing/descriptor-sensitive tests run serially — see `TIMING_SENSITIVE` in run_tests.py).  When adding a GPU test prefer independent buffers/streams; keep `test_cache_desc`-style per-stream state out of the parallel batch.

## Dynamic SASS instrumentation (`sassdbg/`)
Runtime SASS tracing/debugging built on the assembler. Grows out of `sassdbg/poc_code_patch.cu`
(device-side code patching) + the finding that **`CCTL.I.IVALL` invalidates the
non-coherent icache**, making re-patching of already-executed code work
(without it, stores land in memory but the SM keeps executing the stale line —
even across kernel launches).  Host `cudaMemcpy` cannot touch code VAs
("invalid argument"); patch via a device patcher kernel.  Static anchor trick:
put `asm("pmevent 0")` in a CUDA kernel → `PMTRIG` instruction → 16-byte
pattern-match in the cubin → replace with any assembled instruction.

- `sassdbg/instrument.py` — `instrument(source, undo=...)`: parses an
  assembler-dialect kernel, matches every instruction with `SassMatcher`, and
  emits a **write-set-only** trace (dest GPRs with width from `IDEST_SIZE`,
  P2R predicate snapshots, UR dests via `MOV R,UR`, MEM records with
  address+data, optional pre-store MEMOLD old-value loads for reverse
  execution).  Tracer registers R240–R253 + UR60/61 are reserved (kernel
  using them is rejected); **LDG rejects Rd ≥ R254** (window rule).
  Tracer STGs use bracket `[7:7:{0..5}:8:0]` — claiming rd=SB1 like the test
  kernels do causes anti-dep/divergent-retarget hazards with the interleaved
  record traffic.  Trace = fixed 32-byte records (STEP/REG/PRED/UREG/MEM/
  MEMOLD), per-thread 1 MiB region, running offset counter (loop-safe).
- `sassdbg/tracer.py` — runner + decoder + diff printer:
  `python3 -m sassdbg.tracer kernel.sass [--block N] [--no-undo] [--dump-source]`,
  `--demo` for a built-in kernel.  Launch is grid=(1,) 1-D only for now.
- `sassdbg/lift.py` — **M2**: cuobjdump→dialect lifter.
  `python3 -m sassdbg.lift x.cubin [--func F] [--roundtrip]` dumps dialect
  source (scheduling brackets decoded from the raw control bits); the
  `#fn` header carries the real param signature read from the cubin's
  per-function `.nv.info.<func>` KPARAM ELF records.  `--roundtrip`
  re-assembles and byte-compares against the original text section — the
  full tests/*.cu corpus (153 nvcc sm_120 cubins) round-trips exactly.
  `normalize_source()` runs the repair loop that rewrites cuobjdump
  spellings the dialect rejects (bare base reg of a 64/128-bit operand →
  explicit `{Ra,Rb}` group, integral float immediates → `0f...`).
  `python3 -m sassdbg.tracer x.cubin --func F` lifts + instruments + runs
  an arbitrary cubin kernel end-to-end (auto-args: 8-byte params get a
  64 KiB scratch buffer, scalars 0).  Smoke test:
  `tests/asm_construct/test_sassdbg_m2.py` (+ `tests/m2_smoke.{cu,cubin}`).

Roadmap: M3 (runtime breakpoints via device-side patching — DONE,
`patch.py` + probe findings below); M4 = single-step / reverse
execution from MEMOLD undo records.

M3 probe findings (`sassdbg/probe_patch.py`, all experiments pass):
- **cuModuleLoadData / first cuLaunchKernel of a module BLOCKS while
  another kernel spins on-device** (lazy-load path).  Warm up every tool
  kernel (launch once + stream_sync) BEFORE launching a spinning target.
- Host↔device control uses device memory + cuMemcpy polling (~10-20µs);
  `cuMemAllocManaged` fails with 201 under the driver API here, and
  device-side STG to cuMemAllocHost memory faults 700 via the default
  cache descriptor.  `cuCtxSynchronize` waits for ALL kernels — never
  call it while a target is parked (use `stream_query`/`stream_sync`).
- **CCTL.I.IVALL is SM-LOCAL** (no GPU scope exists in the spec: COP =
  IVALL/IVALLP/WBALL/WBALLP only).  A patcher-side invalidate reaches
  the target only if both CTAs coincidentally share an SM.  Reliable
  mechanism = TARGET-side invalidation: debugger prologue reports its
  code base via `LEPC` (= own instruction VA; kernel base = LEPC −
  index*16, verified against the assembled encoding via an LDG
  readback kernel), parks at a start gate, then runs IVALL once after
  release — any patch stored while parked is visible on first fetch.
- **IVALL races in-flight fills**: a lone `CCTL.I.IVALL; BRA target`
  can still deliver one stale execution of the target line (the fill
  is discarded from the icache, so exactly one stale iteration).
  Hardened prologue = `IVALL; NOP×32 (stall 8); IVALL; BRA` → 30/30
  reliable.  Resume paths are safe unhardened when no fill of the
  restored line can be in flight (parked warp nowhere near the line).
- **Tight loops defeat IVALL**: a loop spanning a couple of 128B lines
  replays from a loop/fetch buffer that CCTL.I/D.IVALL does NOT flush —
  a mid-run patch of an actively-executed tight loop is NEVER seen.
  A fat loop (~2KB body) refetches per iteration and the same IVALL
  makes the patch visible within one iteration.  => breakpoints must be
  armed before the loop is entered.
- **M3v2: slot-less breakpoints via CALL.ABS + RPCMOV**
  (superseded by M3v3 below; probes: `sassdbg/probe_callheap2.py` =
  user's, `probe_callheap3.py`):
  the site word is overwritten with the CONSTANT word
  `CALL.ABS.NOINC PT, {R252,R253}, 0x0` (prologue preloads R252/253 with
  the handler VA from ctrl+0x20).  The breakpoint HANDLER is
  **heap-resident** — plain devmem written by host cuMemcpy; the GPU
  fetches/executes SASS from device memory with no icache ceremony.
  Handler entry: `RPCMOV.32 R248/249, Rpc.LO/HI` → **RPC = VA of the
  CALL instruction itself** = the breakpoint identity (no slots, no hit
  ids, no per-site relocation).  It saves the kernel's PR (P2R→ctrl+0x18),
  reports the site VA (ctrl+0x10), and spins on a GENERATION counter
  (ctrl+0x08; a shared one-shot flag + self-reset races — a generation
  compare never does).  Resume = restore site word + clear hit + bump
  gen; the handler restores PR (LDG→R2P stall-13), runs the hardened
  IVALL; NOP×32; IVALL, and `RET.ABS.NODEC PT, {R248,R249}, 0x0` back to
  the SITE — re-executing the restored original instruction.  The RET
  target lives in registers and the site line is cold (warp was parked
  in the heap) → no hot-line patch race at all.
  - **CALL/RET truth** (probe3 matrix): `CALL_DEPTH.INC`/`RET_DEPTH.DEC`
    only maintain a hardware call-depth counter — the jump target is
    ALWAYS `Ra + disp` (**disp in bytes**); nested INC/DEC with correct
    register VAs works at depth 2; `RET.DEC RZ` faults 700.  `CALL.REL`
    never writes RPC (RPCMOV reads indeterminate); `CALL.ABS` does.
    `CALL.ABS` immediate form (field = VA>>2, encoding verified) faults
    jumping anywhere — use the register form.  Divergent CALL.ABS works
    (each group gets its own RPC).  See notes/sm90/instr/{call,ret,rpcmov}.md.
  - The patch word is deliberately UNCONDITIONAL (@PT): a breakpoint
    fires when execution REACHES the site, pre-predicate; the stepper's
    arm-the-successors model depends on it (a predicate-preserving patch
    silently skips a predicated-off `@P0 BRA` site and the kernel runs
    to completion instead of hitting the fall-through bp).
  - **BRX is the RELATIVE twin** of JMX (target = next_pc + Ra + off —
    Ra kernel-relative; absolute VA faults 700).  notes/{brx,jmx}.md.
- **M3v3 (current): multi-warp breakpoints via per-warp blobs**
  (probe `sassdbg/probe_mwarp.py`, E2E
  `tests/asm_construct/test_sassdbg_m3w.py`):
  - Patch word = CONSTANT `CALL.ABS.NOINC PT, {R252,R253}, 0x80000` —
    R252/253 = the PER-WARP blob base, so one word serves all sites and
    all warps.  Kernel reservation dropped to **R252/R253 only** (v2
    needed R246–R253 + UR60/61).
  - Per-warp blob (1 MiB devmem, warpid = SR_CTAID.X*ctawarps +
    SR_TID.X>>5, ctawarps passed via ctrl+0x28; multi-CTA supported,
    E2E `tests/asm_construct/test_sassdbg_m3c.py` = 2 CTAs x 2 warps;
    **HARD constraint: all CTAs must be CO-RESIDENT** — parked warps
    never exit, so a grid exceeding resident capacity deadlocks at the
    gate; LMB verified per-warp even across CTAs by
    `sassdbg/probe_lmbshare.py`):
    [0,0x20000) local backing / [0x40000,...) comms (gen + hit VA) /
    [0x80000,...) handler code.  The prologue runs **SETLMEMBASE once,
    permanently** — the blob doubles as the warp's local backing, so the
    handler spills/restores R246–R251 + PR with `STL/LDL [RZ+uImm24]`
    (zero scratch register needed — breaks the "need a register to save
    a register" bootstrap).  Comms are **desc-less**
    `STG/LDG.E.STRONG.GPU [{R252,R253}+COMMS+k]` (URs freed).
  - The handler returns through a **self-constructed
    `RET.ABS.NODEC RZ, imm`**: RPCMOV → site VA → bit-surgery compose
    (imm = va>>2, SCALE 4: field[7:0]→lo[23:16], [37:8]→lo[63:34],
    [55:38]→hi[17:0]; `compose_ret_word()` in patch.py) → STG.E.128
    over the handler's OWN last line → hardened IVALL covers the fetch.
    NOTE: CALL.ABS imm form faults 700 (probe3 P4) but RET imm form
    WORKS (probe P6b).  When validating via the assembler pass the BYTE
    address (it does the /4); self-modifying code must >>2 itself.
  - **SETLMEMBASE has a settling latency**: local accesses in the first
    ~10s of cycles after it are flaky (lane-split LMB views, 700s on
    never-device-written addrs).  The prologue's gate spin provides the
    settling window — never let the first local access be time-critical
    or a host-data read.  STL/LDL `[RZ+uImm24]` reach only the low
    0x640 dwords of the local window (LMEMHIOFF+0x640 crosses 2^24);
    deeper frames need register-based local addressing.
  - Host: `Debugger(src, max_warps=N)`; `wait_hit()` sets `bp.warp`;
    `resume(bp)` bumps the generation of exactly the warps parked at
    that site (one resume releases a multi-warp pile-up at one site).
    M2/M3/M4/M5 tests + full serial regression all pass (127/128, the
    one failure = known test_uimad self-bug).
- `sassdbg/patch.py` — M3v3 host API: `inject_debugger(source, max_bps)`
  (prologue: LEPC base report at inst 1 + per-warp blob setup + gate +
  hardened IVALL, reserves R252/R253 only; extra `dbgctrl<8>` param),
  `Patcher` (warm-up launch mandatory — host cuMemcpy cannot
  write module code space), `Debugger`: `launch(args, grid, block)`
  (parks at the gate), `arm(orig_inst_index)` / `disarm` / `wait_hit`
  (maps site VA → bp) / `resume` / `wait_done` (stream_query-based;
  never cuCtxSynchronize while parked).  Resume consumes the bp (re-arm
  to break again).  E2E: `tests/asm_construct/test_sassdbg_m3.py` (5/5),
  `test_sassdbg_m3w.py` (2-warp, 3/3).

M4 (`sassdbg/wtrace.py` + `sassdbg/reverse.py`) — warp-level trace +
forward/backward state replay.  DONE: instrumenter, decoder, reverse
engine, E2E test (`tests/asm_construct/test_sassdbg_m4.py`, divergent
if/else kernel: forward replay == device ground truth, step_back to any
point, partial-replay equivalence).

- Warp-unit records: one record = 32 lane values contiguous (one
  coalesced STG per lane); every record starts with a 32-lane TAG
  subblock (`0x5A000000|kind<<16|aux`; predicated-off lanes leave zeros).
  Four sections per warp region (MAIN/SGPR/PRED/UP, sizes in wtrace.py),
  section header word = claim counter, data from section_base+0x80.
  STEP carries BMOV MACTIVE; REG aux = `reg|nlog2<<8`; MEM/MEMOLD =
  tag + addr(8B/lane) + data(size/lane); UREG adds an idx subblock.
- **Divergence-safe allocation**: per-lane register counters CANNOT
  survive divergence (split groups' counters drift; REDUX.MAX at a
  reconvergence point only reconciles the group with itself — observed:
  both branch bodies' records lost to overlapping writes).  Instead each
  instrumented instruction CLAIMS its frame bytes per section with a
  single-lane atomic RMW + broadcast:
  `P2R save; BMOV MACTIVE; FLO.U32 (bfind = MSB set bit);
  ISETP.EQ P6 vs laneid; @P6 ATOMG.E.ADD.STRONG.GPU; SHFL.IDX broadcast;
  R2P restore`.  Claim order == issue order across groups, so the STEP
  stream is the control-flow history (reverse PC chain = stream walked
  backwards; a divergent if/else shows both bodies + the join steps once
  per group with complementary masks).
 - Claim-phase gotchas (all verified): ISETP with stall 13 REQUIRES
   yield=1 (`[7:7:{3}:13:1]`; `:13:0` trips the opex
   batch_t/usched_info illegal-encoding table — assemble_flat does NOT
   catch it, only full `assemble`); FLO.U32 = bfind (MSB index);
   SHFL.IDX form `SHFL.IDX PT, Rd, Ra, Rsrc_lane, Rbound` claims its own
   wr SB (per-section SB assignment main=4/sgpr=3/pred=2/up=1 to avoid
   double-claim); ATOMG result lands on wr=SB5; 64-bit dest pairs must be
   EVEN-aligned (MISALIGNED_REG_ERROR) — `{R233,R234}` is illegal.
   **depcheck is ON for all sassdbg-generated code** (patch.py, cli.py
   assemble with check_deps=True; default-on in assemble already); it
   caught two real wtrace bugs, now fixed: the head's per-warp region
   IMAD.WIDE now req-waits the `__trace` LDC (`{1}`), and the claim
   phase's BMOV MACTIVE claims SB2 with FLO.U32 req-waiting it (`{2}`) —
   BMOV is variable-latency, its result was previously unscoreboarded.
- Tracer registers R224-R245 + UR59/60/61 (M3v3 debugger reserves only
  R252/R253 — its handler scratch R246-R251 is spill-restored via local;
  disjoint by design).  `instrument_warp(source, undo=True)` appends the
  `__trace<8>` param; grid=(1,) only; host must zero the region (claim
  counters start at 0).
- `reverse.py`: `WarpReplay(sidecar_json, trace_bytes, warp=0)` —
  parses sections (4B-resync tag scan, tolerant of zero gaps), merges
  aux-section records into per-STEP frames by idx (stream order matches
  execution order per group), `replay(n_frames=None, state=None)`
  (resumable), `step_back(state)` (REG/PR/UR/UPR from value-history
  stacks; MEM from the paired MEMOLD old-bytes — undoing the first
  traced store restores the host-written pre-kernel image; ATOM/RED
  without MEMOLD: the restored Rd IS the old memory value, so REG undos
  run before MEM undos within a frame).

M5 (`sassdbg/stepper.py`) — source-level single-stepping + reverse
from a breakpoint.  DONE: CFG/next_pcs static analysis, Stepper,
wtrace+debugger composition, E2E test
(`tests/asm_construct/test_sassdbg_m5.py`).

- `Cfg(source)`: original-source instruction indices; `next_pcs(idx)`
  = fall-through (+ label target for predicated BRA; BSSY falls through;
  BSYNC → matching BSSY target via nested stack scan; EXIT/RET/KILL →
  none; BRX/JMX/CALL raise — dynamic targets).
- `Stepper`: park at bp → arm ALL of next_pcs (safe while parked) →
  resume → whichever slot hits is the path taken → disarm the losers.
  The hit sequence IS the executed path (verified: exact 26-step path
  through a 5-iteration loop, correct result).  Self-edge steps arm
  after resume (best effort — resume restores the site word).
- **Multi-warp (M3v3)**: `Stepper(..., max_warps=N)` +
  `run_to_entry_all()` / `step_all(state)` / `run_all(state)` drive
  every parked warp in lockstep: union-arm successors → resume all
  current bps (one resume releases a same-site pile-up) → deferred-arm
  successors that coincide with a parked site → collect each warp's
  next hit (`bp.warp`) → disarm untaken sites.  Boundary invariant:
  armed sites == parked sites.  Per-warp paths in `st.paths[w]`.
  A warp MAY re-park at its current site if another warp's successor
  re-armed it before its refetch — a harmless duplicate step (the
  original instruction still executes exactly once, one step later).
  E2E: `tests/asm_construct/test_sassdbg_m5w.py` (2-warp divergent
  if/else, exact per-warp paths, 3/3 repeat runs).
- **Two M3 latent bugs found & fixed by M5** (M3 never saw them: it
  resumed within ~1 ms and m2_smoke left P0=0):
  1. The slot spin's `ISETP` (stall 4) feeding `@!P0 BRA` hit the
     ISETP→BRA CBU predicate-forwarding floor (needs stall ≥13, and
     yield=1 — `:13:0` trips the opex table): a stale P0=1 (left by the
     gate) made the first spin iteration FALL THROUGH to a JMX to an
     unwritten return VA (=0) → error 700 within milliseconds of
     parking.  Fixed: slot+gate ISETPs now `[7:7:{5}:13:1]`.
  2. **The slot clobbered the kernel's P0**: the spin ISETP leaves
     P0=(release!=0)=1, so a resumed kernel branch on P0 took the wrong
     path (observed: loop ran one extra iteration).  Fixed: slots
     save/restore the full PR file through the ctrl buffer (P2R→STG on
     entry, LDG→R2P stall-13 before the JMX; per-slot word at
     ctrl+0x20+4*max_bps+4*slot).  The gate's ISETP still leaves P0=1 at
     kernel entry (predicates are architecturally 0 there; harmless in
     practice — documented).
  3. Hit id is now the SLOT number (slots recycle; the global bp id
     counter outgrew them → "unknown hit id" once slot 0 recycled to
     bp id 33).  `wait_hit` maps slot→armed bp.
     (All three are v1-slot history: M3v2's CALL+RPCMOV heap handler
     has no slots and no hit ids — the site VA IS the identity — but
     the PR save/restore and ISETP stall-13-yield-1 lessons carry over
     to the handler.)
 - Reverse-from-bp composition: `Debugger(instrument_warp(src).source,
   allow_cdesc_urs=True)` (accepted for API compat; v3 touches NO uniform
   registers, so wtrace's UR60/61 cdesc usage composes freely).
   wtrace R224-R245 vs debugger R252/R253 are disjoint by design (the
   v3 handler's R246-R251 scratch is spill-restored via local).  The
  bp-replaced instruction's post-records never emit, so
  `WarpReplay.replay()` lands on pc=bp step with pre-instruction state;
  step_back walks backwards (pc=N semantics: frames 0..N applied).
- Hand-scheduled kernel gotcha (test kernels, not the tools): ALU→ALU
  chains need the house-style `[7:7:{}:5:1]` brackets — stall 4 lets the
  consumer read launch residue (0x3F800000 high bits observed).

M6 (`sassdbg/cli.py`) — interactive CLI frontend (cmd.Cmd REPL,
scriptable via stdin).  DONE: E2E smoke
`tests/asm_construct/test_sassdbg_m6.py`.

- `python3 -m sassdbg.cli --sass k.sass | --cubin x.cubin [--func F]
  [--grid G] [--block B] [--max-warps N] [--trace]` — auto-args (8-byte
  params get a zeroed 64 KiB scratch buffer, scalars zero-filled;
  `--trace` appends the wtrace region).  Launches parked at the gate.
- Commands: `b N`/`d N` (arm/disarm, ORIGINAL-source instruction
  numbering — with --trace the CLI maps through the wtrace scaffolding
  internally), `info b`, `r` (run_to_entry_all), `c` (resume all parked,
  wait next hit), `s` (step_all lockstep), `w`, `p [w]` (per-warp
  paths), `l [N]`, `back [w]` / `regs w lane Rx` (--trace reverse via
  WarpReplay; updated on warp-0 hits), `dump w [lane] Rx…` /
  `set w [lane] Rx val` / `exec w <sass line>` (M7 injection on a
  PARKED warp), `q` (resumes anything parked so the kernel can
  finish).
- Limitations: don't mix manual `b` with `s` (step_all manages its own
  armed set; arming an already-armed site raises); a bp is CONSUMED on
  resume; --trace is single-CTA (wtrace region index = tid>>5, no
  CTAID) and reverse replay is single-warp.

M7 (patch.py `exec_cmd`/`dump_regs`/`set_reg` + CLI `dump`/`set`/`exec`)
— on-demand command injection at a breakpoint: dump/set ANY register of
a PARKED warp (per-lane), probe architectural state, repeatable until
resume.  DONE: E2E `tests/asm_construct/test_sassdbg_m7.py` (E1-E5) +
CLI smoke (test_sassdbg_m6.py section D).

- Blob layout gains [0x90000=CMD_OFF,...) command buffer; comms gains
  +0x18 cmd_seq (host bump) / +0x1c ack (handler echo) / +0x100 results
  window.  Handler spin loop polls BOTH gen and cmd_seq (baselines in
  local spill slots 7/8); dispatch = update slot8 → hardened
  IVALL;NOP×32;IVALL → `CALL.ABS.NOINC PT, {R252,R253}, 0x90000` →
  command code ends with `RET.ABS.NODEC PT, {R252,R253}, cmdret_off`
  back to the spin top (anchors found by two-pass `_handler_anchors`).
- Command contract: R246-R251 + P0-P6 are free scratch (kernel's values
  live in local slots 0-6); WRITING R252/R253 is rejected (dest-parse;
  read-only use as STG address base allowed); control-flow mnemonics
  rejected; straight-line only.  Result readback via `cmd_read` /
  STG to [{R252,R253}+0x40100+k].
- Per-lane dump/set: `_LANE_PRELUDE` computes SR_TID.X&31 → lane*4
  address pair {R248,R249} (64-bit groups must be CONSECUTIVE — {R249,
  R253} is a SyntaxError); results window is reg-major ×32 lanes
  (reg i at +0x40100+4*i*32, lane at +4*lane).  set_reg predicates on
  `ISETP.EQ.AND P0, PT, R250, <lane>, PT` (imm-compare form NEEDS the
  bool-op suffix `.AND` — bare `ISETP.EQ ... imm` fails to match).
  P2R PR packing: bit i → Pi (P0 = bit 0).
- `assemble_flat` takes PLAIN SASS — wrapping the command in
  `#fn cmd(){}` silently yields ZERO instructions (the handler then
  CALLs a zeroed buffer → 715).  Assert `enc` non-empty.

Roadmap: debugger feature-complete (M1-M7: trace, lift, breakpoints,
multi-warp/multi-CTA, stepper, reverse, CLI, command injection).

Assembler fixes made for M2 (all covered by the corpus round-trip +
`tools/run_tests.py`):
- `sass_elf.py`: `total_ps` is now `max(offset+size)` — summing param
  sizes undercounted when a 4-byte param precedes an 8-byte one
  (alignment gap), and the driver rejected the launch with error 701.
- `sass_matcher.py`: address-width pins (`ONLY64`/`U32ONLY`) join their
  operand group so a 64-bit address can't match the U32 class (ATOMG bit
  63); plain `[Ra+off]` may match a UR-index slot defaulted to URZ
  (STAS/REDAS); MEM_ADDR operands never match DESC-composite groups
  (STL memdesc); `TMA` composite (UBLKPF `desc[...]`);
  `ZeroUniformRegister`/`NonZeroUniformRegister` operand types; B3B0
  byte-select suffix `.B0`–`.B3` on UREG operands (UR2UP); first-operand-
  group binding tie-break (BAR single-register IR-vs-RI); IMAD/UIMAD
  LO-vs-HI preference; HFMA2-family packed f16x2 immediates.
- Wide-operand/group-size errors carry `operand #i` + an explicit
  `{Ra,...}` suggestion — lift.py's repair loop consumes them.

## Documentation workflow (current effort)
Goal: write a per-instruction reference doc for every **compute** SASS instruction. Split across sessions.
- `TODO.md` — the master checklist (**197/207 instructions** done), grouped into 10 categories: **Integer/Vector**, **FP32**, **FP16**, **FP64**, **Convert**, **Uniform**, **Memory**, **Tensor**, **Control Flow**, **Misc**. Derived from `ref_memo.txt` (the curated sm_70..sm_90 opcode roster). Texture/surface/graphics instructions and pseudo/lowered opcodes are intentionally excluded (see its "Excluded" section). `-> MNEM` tags map ref_memo names to the canonical sm_90 mnemonic (shape/width/uniform/extended variants collapse to one instruction, so their docs may be consolidated). `LDCU` is unresolved (likely an LDC variant).
- `notes/sm90/instr/*.md` — per-instruction reference docs (164). `notes/sm90/arch/*.md` — cross-cutting topic notes (14: `scoreboards`, `memory_model`, `cbu_state`, `iswz`, `hmma_pipeline`, `div`, `fp64_control`, `tma_mbarrier`, `tensorcore_microarch_speculation`, `wgmma`, `control_codes`, `usched_latency`, `ldc_admode`, `tcgen05_vs_wgmma`, `encoding_classification`). Each records: spec-grounded facts, external-reference reconciliation, empirical corroboration (cuobjdump mining), and open questions.
- Tick the box in `TODO.md` when done.
- `sm90.json` is gitignored/regenerable; `ref_memo.txt` uses a ROT13 column that is not the mnemonic (mnemonic is the 3rd column).

### Phase 2 — Refinement workflow
With the first doc pass complete, focus shifts to **note quality and consistency**:
1. **Cross-check descriptions** against `notes/` sibling instructions — e.g. VIMNMX vs IMNMX, VSADD vs VABSDIFF, all MMA variants consistent in terminology.
2. **Resolve open questions** — many notes have `## Open questions` sections; answer or prune stale ones.
3. **Consolidate** related instructions (e.g. HADD2/HADD2_F32 into one note, DADD/DADD_F64, IMAD/IMAD_WIDE/IMAD_HI/IMAD_X).
4. **Verify encodings** — run decoder round-trips against real cuobjdump vectors (decoder scripts should all pass).
5. **Improve cross-references** — link between notes (e.g. SHF → PRMT, I2FP → I2F, RED → ATOMS).

Key conventions for notes:
- Record both spec-derived facts AND empirical observations
- If the compiler does something unexpected (lowers to different instruction, prefers uniform regs, skips a variant), document it
- When an instruction exists in spec but ptxas doesn't emit it (e.g. IMNMX on sm_90), document the relationship and the arch that does emit it
- Latency tables: map the instruction's pipe to the correct row in TABLE_TRUE/TABLE_OUTPUT/TABLE_ANTI

### Per-instruction documentation steps (the repeatable recipe)

Follow this flow for every new instruction. Each step feeds the next; skip a step = miss a detail.

**Step 1 — Spec lookup (`query_sm90.py`)**
```bash
query_sm90.py mnem <NAME>        # variant count, opcodes, format preview, pipe
query_sm90.py pipe <NAME>        # pipe membership (maps to latency section)
query_sm90.py class <name> -v    # full CLASS block: FORMAT, slots, PROPERTIES, PREDICATES, CONDITIONS, ENCODING
query_sm90.py layout <class>     # 128-bit field map (table + ASCII visual)
```
From the CLASS output, read:
- `FORMAT` — slot names & their types (Register, Predicate, UniformRegister, F32Imm, etc.)
- `ENCODING` — exact bit positions; note gaps, `*<n>` fills, TABLE-based fields (opex)
- `PROPERTIES` — INSTRUCTION_TYPE, IDEST_SIZE, ISRC_A/B/C/E_SIZE (0 = absent operand)
- `PREDICATES` — operand sizes that feed latency connector math
- `CONDITIONS` — register-range constraints and illegal-encoding guards

**Step 2 — Enum cross-check**
```bash
query_sm90.py enum <TypeName>    # modifier value maps: FCMP, MUFU_OP, REDUX_SZ, Round1, ...
```
Map each format modifier to its numeric encoding. Note any `INVALID*` values that trigger `ILLEGAL_INSTR_ENCODING_ERROR`.

**Step 3 — Disassembly hunting (cuobjdump)**
```bash
# Check cublas for real-world usage (fast grep; timeout if needed)
cuobjdump -arch sm_90 -sass /usr/local/cuda/lib64/libcublas.so | grep -A1 "<MNEMONIC>" | head -20

# Check both hex lines — sm_90 is 128-bit: lo64 (first /*...*/) + hi64 (second /*...*/)
# Decode one by hand to confirm opcode bits [91]∥[11:0] match the spec
```
Collect a few representative encodings: plain form, negated operand, all modifier combos visible.

**Step 4 — Write a test kernel (`tests/<mnem>_test.cu`)**

Cover every observable variant + modifier:
- Plain form (C++ or PTX inline asm)
- Negate/absolute on each source operand
- Each rounding mode (.RM, .RP, .RZ, .RN default)
- Saturation (.SAT)
- Flush mode (.FMZ/.FTZ if applicable)
- Immediate operand (trigger RIR/RRI variant)
- Uniform register variant (trigger RUR/RRU by loading params into uniform regs via `ULDC` — ptxas on sm_90 often does this automatically for kernel parameters)

For instructions the compiler won't emit from C/C++ (e.g. legacy IMNMX on sm_90), try:
- `nvcc -arch=sm_75` (older arch may emit different mnemonic)
- PTX inline asm with the exact PTX mnemonic
- If neither works, document the compiler's chosen mnemonic (e.g. VIMNMX vs IMNMX) and note it as a relationship

**Step 5 — Compile & disassemble**
```bash
nvcc -arch=sm_90 -O3 -cubin -o tests/<mnem>_test.cubin tests/<mnem>_test.cu
cuobjdump -arch sm_90 -sass tests/<mnem>_test.cubin
```
Verify: every case generated the expected SASS mnemonic. If some cases lowered to different instructions (e.g. `-a*b` → FFMA instead of FMUL, or compiler split into UISETP+USEL), record the pattern in the note.

**Step 6 — Write a decoder (`tools/decode_<mnem>.py`)**

Minimal Python script that:
- Extracts fields from lo64+hi64 via bit positions from ENCODING
- Reconstructs the full SASS assembly as cuobjdump would print it
- Validates against the test vectors from Steps 3 & 5
- Prints match/mismatch for each test vector

Spec essentials:
- 128-bit instruction = hi64 (bits [127:64]) + lo64 (bits [63:0])
- Opcode is 13-bit: `{bit[91], bits[11:0]}`
- Bit positions in `BITS_<width>_<hi>_<lo>` are MSB:LSB, so extract MSB-first
- Registers: 8-bit for normal (R0–R255, where 0xFF=RZ), 6-bit for uniform (UR0–UR63)
- Predicates: 3-bit (P0–P6, 7=PT), plus a 1-bit `.not` at the adjacent position
- Immediate floats: 32-bit IEEE754 at [63:32], big-endian (use `struct.unpack('>f', struct.pack('>I', val))`)

**Step 7 — Write the note (`notes/sm90/instr/<mnem>.md`)**

Structure (follow existing notes for consistency):
```
# MNEMONIC — One-line description
**Opcode mnemonic:** ...  |  **Pipe:** ...  |  **INSTRUCTION_TYPE:** ...
## Semantics
## Variant overview (table with opcodes)
## Modifiers (table with field positions)
## Bit layout (128-bit map)
## Cross-comparison (vs related instructions, if applicable)
## Latency (from sm_90_latencies.txt)
## Verified encodings (table with Lo64/Hi64 → Disassembly)
### PTX→SASS mapping
## Open questions
```

**Step 8 — Tick TODO**
```markdown
- [x] **MNEMONIC** (idx N) — description
```

Key conventions for notes:
- Record both spec-derived facts AND empirical observations
- If the compiler does something unexpected (lowers to different instruction, prefers uniform regs, skips a variant), document it
- When an instruction exists in spec but ptxas doesn't emit it (e.g. IMNMX on sm_90), document the relationship and the arch that does emit it
- Latency tables: map the instruction's pipe to the correct row in TABLE_TRUE/TABLE_OUTPUT/TABLE_ANTI

## Critical gotchas
- **Explicit register groups in hand-assembled SASS**: every 64/128-bit operand lists
  **all** its registers as `{Ra,Rb}` / `{Ra,Rb,Rc,Rd}`. The legacy implicit forms are
  rejected by the parser/matcher: `R6.64`, `LDC.64 R6`, `LDCU.64 UR4`,
  `desc[UR4]`, `MOV.64 R0` (single-reg dest) — all must be rewritten
  (`LDC.64 {R6,R7}`, `desc[{UR4,UR5}]`, `STG desc[{UR4,UR5}][{R6,R7}+0x0]`).
  This is why the UR4/UR5-descriptor and R6/R7-address reuse bugs are gone: the
  pair is explicit, and the matcher cross-checks the group width against the
  matched variant's `IDEST_SIZE`/`ISRC_*_SIZE` (a single register on a 64-bit
  slot, or a mismatched group width, is an error). Note this is the **assembler
  source dialect only** — cuobjdump still *prints* `[R6.64+0x0]`/`desc[UR4]`
  and the tools decoders keep parsing that printer syntax.
- The header says `ARCHITECTURE "Volta"` and `WORD_SIZE 64`, but this is the **sm_90** file and each SASS instruction is **16 bytes / 128 bits** (`FUNIT uC` -> `ENCODING WIDTH 128`; bit positions in `BITS_*`/`FUNIT` masks run [127:0], MSB-left). Trust the 128-bit width, not `WORD_SIZE`.
- Opcode names carry a pipe suffix in the latency file (e.g. `IADD3` and `IADD3int_pipe` are the same op; the suffixed form is the pipe-bound variant). Both appear in OPERATION SETS.
- "Illegal encoding" tables (`TABLES_*_illegal_encodings`) map input tuples to error codes; they are *rejections*, not valid decodes.

## `sm_90_instructions.txt` layout (locate via `grep -n`)
Top-level sections in order:
- `ARCHITECTURE` / `RELOCATORS` (line 1+) — ELF ids and `R_CUDA_*` relocation bitfields.
- `PARAMETERS`, `CONSTANTS` (~158+) — enums referenced everywhere: `VQ_*` (virtual queue / functional unit), `INST_TYPE_*` (scoreboard class), `IOPERAND_TYPE_*`, `IERROR_*`, `ISHADER_*`.
- `REGISTERS` (~307) — register-class and `SIDL_NAMES` definitions.
- `TABLES`, then many `TABLES_<name>` (~1771+) — reusable decode tables (e.g. `FixLatDestMap`, `DestPred`, `IntSize`) plus per-opcode `TABLES_mem_*`, `TABLES_opex_*`, `TABLES_op_*`, `TABLES_URb_*`; `*_illegal_encodings` list forbidden tuples.
- Enum definitions (~1326+) — modifier value maps like `ATOMICINTSIZES "U32"=0 ...`, `UniformRegister "UR0"=0 ...`. These decode modifier/subop fields to names.
- `OPERATION PROPERTIES` / `OPERATION PREDICATES` (~5042) — the list of per-class property/predicate keys.
- `FUNIT uC` (~5106) — control-bit bitfield layout. Each line is `Name '<128-char mask>'` where `X` marks the bits (MSB-left). This is the schedule/control-word field map (e.g. `Pred`, `PredNot`, `Dest`, `RegA/B/C`, `Imm32`, `Sync`, `NODEP`).
- `CLASS "..."` blocks (~7422 onward, **1168 primary + 421 `ALTERNATE CLASS` = 1589 encoding variants**; note one `CLASS` is glued after a `;`, so `grep "^CLASS "` undercounts by 1) — one per instruction encoding variant.

### Anatomy of a `CLASS` block (the core decode unit)
Each `CLASS` has these sub-sections:
- `FORMAT` — assembler syntax template of named **slots** written `Type("default"):slotname` (modifiers use a leading `/`, e.g. `/AIO("I"):io`; operands like `Register:Rd`, `SImm(11)*:Ra_offset`). The `slotname` after the `:` is exactly the identifier used on the RHS of `ENCODING` `BITS_...=` lines, and `Type` is the enum from the value-map section (`AIO`, `AInteger`, ...) that converts the mnemonic to the field's numeric value. See "FORMAT->ENCODING" below.
- `CONDITIONS` — legality assertions. Each is `<ERROR_TYPE>` / `<predicate>` `:` / `"message"`; the **predicate must hold, and the named error fires when it is FALSE** (e.g. `OOR_REG_ERROR` lists the *valid* register set). `ERROR_TYPE`s and their severity (`ERROR`/`WARNING`/`INFO`) are declared in the header `CONDITION TYPES` block (~line 136). Predicate language: FORMAT slot names as operands (`Rd`, `sz`, `io`, ...); `` `Type@value `` enum-literal compares (`` sz==`AInteger@"64" ``, `` Rd==`Register@RZ ``); `%NAME` = `PARAMETERS`, `$NAME` = `CONSTANTS`; `A -> B` implication (gates a requirement on a modifier/size slot); `DEFINED TABLES_x(...)` / `!DEFINED TABLES_x_illegal_encodings(...)` table-membership guards. Size-driven idiom: `(sz==`AInteger@"64") -> (Rd==RZ || Rd<=%MAX_REG_COUNT-2)` (multi-reg operands need room + N-alignment); `(Rd+(Rd==`Register@RZ))%2` adds 1 so `RZ` always passes.
- `PROPERTIES` — `INSTRUCTION_TYPE` (`INST_TYPE_*`), `MEM_SCBD*`, `VALID_IN_SHADERS`, per-operand `*_OPERAND_MAP`/`*_OPERAND_TYPE`.
- `PREDICATES` — operand sizes (`ISRC_A_SIZE`, `IDEST_SIZE`, ...) that drive register-range math (`RaRange` etc.).
- `OPCODES` — exactly two lines, `<name><pipe_suffix> = <op>;` and `<name> = <op>;`, both the same value. The opcode is a **13-bit** field but the `0b` literal drops leading zeros (e.g. `ACQBULK = 0b100000101110;` and `ALD = 0b1100100001;` both fill the same 13-bit slot).
- `ENCODING` — the bit-to-field mapping. Field names encode their bit position:
  `BITS_<width>_<hi>_<lo>[_<hi2>_<lo2>...]_<name> = <source>;`
  e.g. `BITS_3_14_12_Pg = Pg` (3 bits, [14:12]). `<hi>_<lo>` may repeat to span disjoint bitfields: the opcode is always `BITS_13_91_91_11_0_opcode` = bit [91] (MSB) concatenated with [11:0]. RHS may be a literal, a modifier field, `*<n>` (default/reserved), or a `TABLES_*(...)` lookup.

### FORMAT->ENCODING (how slots become bits)
The `ENCODING` RHS references `FORMAT` slot names. Verified RHS forms:
- `slotname` — value parsed for that slot; converted via the slot's enum `Type` (e.g. `AIO "I"=0,"O"=1` -> `BITS_1_79_79_op=io`).
- `slotname@attr` — an operand sub-attribute: `Pg@not` (predicate negate), `Sb@negate`/`Sb@absolute` (const-operand `[-]`/`[||]`).
- `TABLE(slot,...)` — one or more slots re-encoded through a `TABLES_*`/relocator fn; the LHS may list several `BITS_` targets at once, e.g. `BITS_5_58_54_Sb_bank,BITS_14_53_40_Sb_offset = ConstBankAddress2(Sb_bank,Sb_addr)`. Multiple slots can also fuse into one field: `BITS_8_..._opex=TABLES_opex_0(batch_t,usched_info)`.
- `*<n>` (`*7`,`*0`,`*255`) — fixed/reserved fill when no operand drives the field (an optional `$(...)$` scoreboard group absent -> `*7`; present -> `VarLatOperandEnc(src_rel_sb)`).
- `*<slotname>` — a slot the class pins/reserves rather than freely encoding (e.g. `*Ra` when `Ra` is constrained to `RZ`/non-`RZ`; `*dstfmt.srcfmt` mandatory discriminator with no default).

## `sm_90_latencies.txt` layout
- `OPERATION SETS` — functional-unit pipe membership: `int_pipe`, `mio_pipe`, `fe_pipe`, `fmalighter_pipe`, `fp16_pipe`, `cbu_pipe`, `fma64lite_pipe`, `fma64heavy_pipe`, `udp_pipe`, plus derived sets via set algebra (`FXU_OPS = int_pipe + fe_pipe - ...`). This is the authoritative **functional-unit grouping**.
- `HARD RESOURCE`, `CONNECTOR NAMES`, `CONNECTOR CONDITIONS`/`SETS` — register files (`GPR`, `UGPR`) and per-operand range formulas keyed on the `*_SIZE` predicates from the instruction file.
- `TABLE_TRUE` / `TABLE_OUTPUT` / `TABLE_ANTI` (GPR and UGPR) — producer×consumer **latency matrices** (true/output/anti dependency cycles). Rows/columns are pipe-group×operand-role; the trailing numbers are latencies in cycles.

The `*_SIZE`/`*Range` predicates tie the two files together: instruction `PREDICATES` set sizes, latency `CONNECTOR CONDITIONS` convert them to register spans used to index the latency tables.

## PTX→SASS quick reference (`~/cs/project/documented-ptx/`)
NVIDIA PTX ISA 9.3 documentation converted to markdown, plus empirical PTX→SASS mapping files. Use these when documenting an instruction to map user-visible PTX constructs to the SASS encodings studied here.

- `ptx2sass-int-mad.md` — `mad`/`mul`/`mad.cc`/`madc` → IMAD/IMAD.WIDE/IMAD.HI/IMAD.X/UIMAD (verified sm_90, CUDA 13.1).
- `ptx2sass-int-add.md` — `add`/`sub`/`add.cc`/`addc` → IADD3/IADD3.X/UIADD3 (verified sm_90, CUDA 13.1).
- `instructions/` — per-PTX-instruction reference files (216 files).
- `09.7.*.md` — per-instruction-family PTX spec chapters.

Workflow: when documenting a SASS instruction, first check this dir for a PTX mapping file. If none exists for that instruction family, create one by writing a small CUDA kernel → `nvcc -arch=sm_90 -O3 -cubin` → `cuobjdump -arch sm_90 -sass` → cross-reference with `tools/query_sm90.py opcode <hex>`.

## Reference (unreliable, use with care)
`~/cs/project/crucible-notes` — AI-generated RE notes on NVIDIA/other toolchains; explicitly "best-guess, not authoritative." The `ptxas/extracted/*.json` files are the most relevant cross-check (e.g. `opcode_pipeline_map.json`, `per_sm_latency_tables.json`, `encoding_*`, `opcode_master.json`). Treat these two txt dumps as the source of truth over the notes when they conflict.
