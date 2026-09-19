# sass-dec

Reverse-engineering the NVIDIA **SASS** instruction set and GPU microarchitecture
across nine architectures — Volta (**sm_70**), Turing (**sm_75**), Ampere
(**sm_80**), Ada (**sm_89**), Hopper (**sm_90**), Blackwell
(**sm_100 / sm_103 / sm_120**), and Rubin (**sm_107**) — starting from
`nvdisasm`-dumped ISA description files.

The project has four layers:

1. **Decode** the ISA: parse the dumps into queryable DBs, reconstruct encoding
   bit layouts, functional-unit grouping, and scoreboard/latency behavior, and
   write per-instruction reference docs for every compute instruction.
2. **Measure** the microarchitecture: hand-built SASS kernels + `CS2R` clock
   windows (and NCU where available) to pin down pipeline structure, register-file
   organization, scheduler/yield behavior, and memory topology per chip.
3. **Build** on top of it: a full SASS → cubin assembler with a CTypes GPU
   runner (`assembler/`), and a runtime SASS debugger (`sassdbg/`) with
   breakpoints, single-stepping, reverse execution, and per-warp private code.
4. **Simulate**: `semu/`, a C++20 behavioral simulator that executes sm_120
   cubins on the CPU.
5. **Drive the GPU directly**: `launchprobe/` reverse-engineers the CUDA kernel
   launch protocol (driver/libcuda ↔ GPU command traffic) to the point of
   launching a cubin from a fully userspace-constructed command segment.

There is no build system for the research itself: this is a *reading,
interpreting, and measuring* project on top of raw ISA dumps.

## Layout

| Path | What it is |
| --- | --- |
| `sm_*_instructions.txt`, `sm_*_latencies.txt` | Raw nvdisasm ISA/encoding specs + pipe/latency dumps for sm_70/75/80/89/90, Blackwell sm100/103/120, and Rubin sm_107. Grep-first; never read whole. |
| `tools/` | stdlib-only parsers → queryable JSON DBs, query CLIs, 113 per-instruction decoders, bit-accurate tensor-core model (`hmma_model.py`), test runner. |
| `assembler/` | Hand-written SASS → cubin toolchain (sm70/80/89/90/100/103/120) + `CudaModule` GPU runner + scoreboard dependency checker. See `ASSEMBLER_MANUAL.md`. |
| `sassdbg/` | Runtime SASS debugger: instruction tracing, cuobjdump→dialect lifting, breakpoints via device-side patching, multi-warp/multi-CTA stepping, reverse execution, CLI, on-demand command injection, per-warp private heap code. |
| `semu/` | C++20 sm_120 SASS behavioral simulator (cubin loader + CPU interpreter). See `semu/AGENTS.md`. |
| `launchprobe/` | CUDA kernel-launch protocol RE: intercepts driver↔GPU traffic (`libnvtrace.so`) and hand-builds QMD/command segments to launch cubins entirely from userspace. See `launchprobe/CONTEXT.md` + `NOTES.md`. |
| `notes/sm90/` | Hopper: 171 per-instruction docs (`instr/`) + 34 cross-cutting arch notes (`arch/`). |
| `notes/sm100/`, `notes/sm103/` | Blackwell datacenter: instruction notes, tcgen05/wgmma successor analysis, RF bank probe, `sm100/OVERVIEW.md` change summary. |
| `notes/sm120/` | GB202 (RTX 5090) microarchitecture campaign: pipeline topology, per-pipe latencies, RF banks/writeback, scheduler yield cost, L2 slices, icache, LSU/MIO/XU topology. |
| `notes/sm89/`, `notes/sm80/`, `notes/sm70/` | Ada/Ampere scalar-math pipeline characterization + register banks; Volta register banks. |
| `notes/ARCH_DIFF.md`, `notes/CUBIN_STRUCTURE.md`, `notes/DEVICE_PRINT.md` | Cross-arch encoding diffs, cubin ELF format spec, device printf notes. |
| `tests/` | 218 CUDA (`.cu`) kernels that force specific SASS encodings + 286 assembler round-trip / GPU probes (`tests/asm_construct/`). |
| `ASSEMBLER_MANUAL.md` | Full assembler syntax, scheduling brackets, and usage. |

## Tooling

The specs are parsed into queryable JSON DBs (gitignored, regenerable) — prefer
them over ad-hoc `grep`.

```bash
# Parse a dump pair -> JSON DB (each parser has a built-in validation gate)
python3 tools/parse_sm90.py                                    # sm90.json
python3 tools/parse_sm100.py                                   # sm100.json
python3 tools/parse_sm100.py --instructions sm_103_instructions.txt \
  --latencies sm_103_latencies.txt -o sm103.json
python3 tools/parse_sm75_80.py                                 # sm70/75/80/89 -> sm*.json

# Query (same subcommands for query_sm90.py / query_sm100.py)
python3 tools/query_sm90.py mnem <NAME>       # variants, opcodes, format, pipe
python3 tools/query_sm90.py class <name> -v   # full CLASS block
python3 tools/query_sm90.py layout <class>    # 128-bit field map
python3 tools/query_sm90.py opcode <hex|0b|int>
python3 tools/query_sm90.py enum <Name>       # modifier value map
python3 tools/query_sm90.py pipe <MNEMONIC>   # functional-unit membership
```

`tools/decode_<mnem>.py` are minimal per-instruction decoders: extract fields
from a 128-bit encoding (lo64 + hi64) and reconstruct the SASS assembly,
validated against real cuobjdump vectors.

### Assembler and GPU tests

SASS-by-hand kernels are assembled to cubin and run on a GPU without nvcc:

```python
from assembler import assemble, CudaModule
mod = CudaModule(assemble("#fn k(out<8>) { ... }", arch="sm120"))
d = mod.devmem_alloc(2048 * 4)
mod.launch("k", grid=(1,), block=(32,), args=[d])
mod.synchronize()
out = mod.device_read(d, 128)
```

- `assemble(source, arch=...)` / `assemble_kernel` / `assemble_flat`;
  scoreboard dependency checking on by default.
- Full syntax + gotchas: **`ASSEMBLER_MANUAL.md`** (explicit register groups,
  scheduling brackets `[wr:rd:{req}:stall:yield:batch_t]`, `#fn`/`#param`,
  cross-barrier waits must go in `{req}`, MMA result-wait rules).

```bash
python3 tools/run_tests.py [-j N]   # parallel; timing-sensitive tests serial
```

### sassdbg (runtime debugger)

```bash
python3 -m sassdbg.cli --cubin x.cubin [--func F] [--grid G] [--block B]
```

Lift any cubin kernel to the assembler dialect, patch in breakpoints
(CALL/JMP-based, per-warp private code images — zero register reservation),
single-step divergent groups through BSSY/BSYNC/WARPSYNC/BAR, dump/set
registers of parked warps, and replay execution backwards from a warp-level
write-set trace (`sassdbg/wtrace.py` + `sassdbg/reverse.py`).

## Key facts about the ISA

- Each SASS instruction is **128 bits / 16 bytes** = hi64 `[127:64]` + lo64
  `[63:0]` (the file header's `WORD_SIZE 64` is a lie; Volta/Turing dumps are
  64-bit pairs of the same layout).
- Opcode is a **13-bit** field: `{bit[91], bits[11:0]}`.
- Registers: 8-bit GPR (`0xFF` = `RZ`), 6-bit uniform (`UR0`–`UR63`).
- Predicates: 3-bit (`PT` = 7) plus a 1-bit negate flag.
- Field names encode bit position: `BITS_<width>_<hi>_<lo>_<name>` (MSB:LSB).
- The **control/scheduling word** (`FUNIT uC` bit map) is stable across
  sm_90 → sm_120 — same control fields at the same bit positions.
- The scheduling bracket's `yield` bit is a warp-switch hint and the switch
  itself costs one dead issue cycle (verified on GA100, AD102, GB202);
  `yield` + reuse-cache bits is an illegal combination.

## Status

| Arch | Coverage |
| --- | --- |
| sm_90 (Hopper) | 197/207 compute instructions documented; 171 instr + 34 arch notes; 113 decoders validated on cuobjdump vectors |
| sm100/sm_103 (Blackwell DC) | 21 instr + 10 arch notes; sm_90→sm100 change analysis (`OVERVIEW.md`); B300 assembler target + RF probe |
| sm_120 (GB202) | Microarchitecture campaign: pipe topology/latency map, RF banks, scheduler/yield, memory hierarchy; 3 instr + 2 arch notes + 20 topic notes |
| sm_80 / sm_89 | Scalar-math pipeline structure measured end-to-end (per-pipe rates, conflict matrices, scheduler quirks, FP64 placement) |
| sm_70 / sm_75 | Encoding DBs + register-bank notes; Volta assembly probes |
| sassdbg | Milestones M1–M11 complete (trace, lift, breakpoints, multi-warp, stepper, reverse, CLI, command injection, warp-private code) |
| semu | sm_120 behavioral simulator, in progress (`semu/GAP.md`) |

Major microarchitecture topics in `notes/`: control codes and scoreboards,
memory model (incl. L2 NUMA on H800), tensor cores (HMMA pipeline, wgmma,
tcgen05, bit-accurate FDA model), TMA/mbarrier pipeline, CBU convergence state,
shared-memory bank conflicts, cubin/ELF structure, per-chip pipeline topology
and register-file organization, and scheduler/yield semantics.

See `AGENTS.md` for the spec-layout guide and the per-instruction
documentation recipe.
