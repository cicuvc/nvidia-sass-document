# semu User Guide (Phase 10)

`semu/` is the CPU-only sm120 SASS behavior simulator built in SIM_PLAN.md.
This guide covers everything needed to build, load, run, debug, profile and
benchmark kernels **without a GPU** (CPU-only is a first-class environment),
plus the Phase 10 frozen public API, the capability matrix and the documented
limitations / waivers.

API reference and copy-paste examples live in `docs/API_EXAMPLES.md`.

## 1. Build

Requires Linux x86-64, a C++20 compiler (GCC/Clang), CMake >= 3.20 and ninja.
No CUDA toolchain is required for the core library, CLI or CPU tests.

```bash
cmake -S semu -B semu/build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build semu/build
```

Useful options:

| Option | Default | Meaning |
|---|---|---|
| `SEMU_BUILD_CLI` | ON | build `semu` command-line tool |
| `SEMU_BUILD_TESTS` | ON | build + register CTest |
| `SEMU_ENABLE_SANITIZERS` | OFF | ASan+UBSan (`-fsanitize=address,undefined`) |
| `SEMU_ENABLE_TSAN` | OFF | ThreadSanitizer (host race checks only) |
| `SEMU_WERROR` | ON | compile warnings are errors |

Sanitizer builds are separate trees (`semu/build-asan`, `semu/build-tsan`) so
the ordinary `semu/build` stays clean.

The generated ISA/capability tables in `semu/generated/` are committed; a
plain build never needs Python.  Regeneration is byte-identical and gated:
`ctest -R 'isa_regen|manifest_regen'`.

## 2. CLI

```
semu <command> [options]
```

| Command | Purpose |
|---|---|
| `--version` | version + build + **frozen interface versions** (backend / decoded-IR / runtime-services / event-stream / fault ABI) |
| `capability [--full]` | capability manifest: per-variant decode-only / functional / profiled / unsupported state |
| `disasm <lo> <hi>` / `disasm <cubin> [kernel]` | decode one word / dump pre-decoded kernel text |
| `load <cubin>` | strict executable load; lists kernels + resource metadata |
| `inspect <cubin>` | full ELF / section / symbol / kernel dump (permissive) |
| `list-kernels <cubin>` | one machine-readable line per kernel |
| `run <cubin> <kernel> <gx> <bx> [gy by gz bz] [options]` | execute a kernel; per-lane GPR JSON + optional memory/race/profiler payloads |
| `debug <cubin> <kernel> ...` | single-step debug REPL (breakpoints, watchpoints, memory view/modify, trace) |
| `decode-json <lo> <hi>` | structured decode (for tooling) |

`run` options: `--precise` (default, bit-exact) / `--fast` (host-float),
`--fast-fallback=`, `--instruction-limit=`, `--workers=N` (CPU worker pool),
`--l1tex` / `--l2` / `--race` (trace-only memory-model events),
`--profile` (profiler report JSON), `--global=HEX`, `--param-hex=HEX`,
`--shared-size=N`, `--local-size=N`.

Example — run a kernel with one 8-byte param (little-endian) and a profiler
report:

```bash
semu run tests/tma_min.cubin _Z... 1 1 \
  --param-hex=7856341200000000 --profile
```

`--version` reports the Phase 10 freeze contract:

```
frozen API (Phase 10): backend=1 decoded_ir=1 runtime_services=1 event_stream=1 fault=1
```

## 3. C++ API

The public surface is `semu/include/semu/*.hpp` (30 headers, each
self-contained — verified by the `api_compile` gate).  Highlights:

- `semu/status.hpp` — `Error` / `Status` / `Result<T>` / `ErrorCode`.
- `semu/decoder.hpp` — `Decoder` → `DecodedInstruction` (the **decoded IR**).
- `semu/cubin.hpp` — `Module` / `Kernel` / `PredecodedWord` (the **stable IR** a
  backend consumes).
- `semu/context.hpp` — `Context` / `RuntimeModule` / `Function` /
  `LaunchConfig` / `LaunchResult` / `KernelArg`, plus the backend contracts:
  `IBackend`, `BackendLaunchRequest`, `IRuntimeServices`, `IEventSink`,
  `BasicMemoryEvent`.
- `semu/interpreter.hpp` — the reference backend (`Interpreter`) and
  `interpreter_handles()`.
- `semu/mock_backend.hpp` — minimal IBackend implementation used to validate
  the frozen contract (and a template for a future JIT).
- `semu/fault.hpp` — `Fault` / `FaultKind` (the **fault ABI**).
- `semu/profiler.hpp` — `MemoryProfiler` → `ProfilerReport` (stable schema).
- `semu/race_detector.hpp`, `semu/memory_service.hpp`, `semu/debugger.hpp` —
  trace-only analyzers and the debug session.

The public API is compile-tested: `ctest -R api_compile` compiles every header
standalone (`-Werror`) and runs smoke checks over the frozen surface.

## 4. Phase 10 frozen interface contract

`semu/include/semu/api.hpp` defines the freeze markers:

| Marker | Covers |
|---|---|
| `kBackendApiVersion` | `IBackend` / `BackendLaunchRequest` / `Context::launch` |
| `kDecodedIrVersion` | `DecodedInstruction` / `DecodeResult` / `PredecodedWord` / `Kernel` |
| `kRuntimeServicesVersion` | `IRuntimeServices` (memory / constant bank / event channel / cluster DSMEM) |
| `kEventStreamVersion` | `BasicMemoryEvent` / `IEventSink` / `MemoryEvent` |
| `kFaultAbiVersion` | `Fault` / `FaultKind` / `Error` / `Status` / `ErrorCode` |

Guarantees:

- Adding a JIT backend requires **no change** to the cubin loader, the public
  launch API, the memory model, the debugger or the profiler schema (Phase 10
  exit criterion).
- Extensions to the async/TMA semantics use **versioned extension points**
  reserved in `context.hpp` (completion/commit callbacks + mbarrier state
  query) — they may not alter the frozen `IRuntimeServices` virtual surface.
- Everything that is NOT frozen is the *instruction semantics* of decode-only
  variants: closing them never requires an ABI break.

## 5. Capability matrix & waivers

`semu capability` prints the per-encoding-variant state.  States:
`decode-only` (decoded, not executable), `functional` (implemented + tested),
`profiled` (functional and emitting profiler events), `unsupported`.

Two families carry explicit Phase 10 waivers — **they must never be written up
as "GPU validated"**:

| Instruction family | Frozen state | Evidence | Waiver |
|---|---|---|---|
| TMA — `UTMALDG` / `UTMASTG` / `UTMAREDG` | **decode-only** (semantics NOT frozen) | decodable; interpreter has a synchronous tile-expansion handler for testing only; GPU observable non-blocking completion semantics unclosed | `decode_only` — capability matrix lists them; closing semantics later does not break the frozen ABI |
| Tensor — dense HMMA/QMMA/OMMA (F32 accumulator) | **functional** | CPU-only bit-exact differential semu==model (per accumulator word); GPU three-way differential is thin (see SIM_PLAN Phase 9 table) for HMMA/QMMA | OMMA specifically: **gpu_waiver** (user instructed skip; never "GPU validated") |
| Tensor — sparse / rowcol / scale alternatives, F16 accumulator | **decode-only** | none | runtime fault (`kUnsupportedInstruction`) |
| FP8 `e3m2` / `e2m3` / OMMA on GPU | **user-skip** | CPU-only bit-exact; **not executed on GPU** (user instructed) | any docs must distinguish "semu==model (CPU)" from "GPU verified" |
| LDGSTS `.cg` bypass wavefront/conflict counts | **unsupported** (profiler model only) | functional path implemented; perf model has no confidence | profiler `unsupported` |

The mock backend enforces the tensor/TMA boundary for a future JIT: TMA and
non-dense tensor variants are reported through the fault ABI
(`FaultKind::kUnsupportedInstruction`) instead of executing; dense tensor
falls back to the interpreter.

## 6. Benchmarking (no SLA)

`semu_bench_interp_throughput` measures single- and multi-worker dynamic
instruction throughput + scaling and a hotspot profile.  It records results to
`semu/benchmarks/record.json`.  Phase 10 explicitly sets **no hard
performance SLA**; the record is for trend tracking only.

```bash
cmake --build semu/build --target semu_bench_interp_throughput -j
semu/build/tests/semu_bench_interp_throughput 64 256 \
  --workers=1,2,4,8 --runs=9 --body=512 --record=semu/benchmarks/record.json
```

Each run validates the determinism gate (every worker count reproduces the
single-worker control-flow fingerprint, so a "speedup" is never the result of
doing less work).  Hotspots are collected in a separate untimed probe
(`--collect_hotspots` equivalent inside the tool) so timed numbers are not
distorted.

## 7. Testing a CPU-only machine

`tools/run_semu_cpu_gate.sh` runs the full CPU gate (35 CTest-equivalents plus
the fuzz / l1tex / LDGSTS / tensor oracles):

```bash
tools/run_semu_cpu_gate.sh semu/build
```

GPU differentials (`tools/diff_phase5.py --gpu`, `tools/fuzz_phase5.py --gpu`,
`tools/tensor_gpu_differential.py`) require an sm_120 device (e.g. RTX 5090,
CUDA 13.x) and are optional.

## 8. Limitations

- **CPU-only execution is the model**: the interpreter is synchronous; async
  completion, memory latency and scoreboard timing are logical (orders are
  preserved, cycles are not modeled).
- **TMA decode-only**: `UTMALDG` / `UTMASTG` / `UTMAREDG` semantics are not
  frozen; a kernel that needs their non-blocking completion behavior cannot be
  trusted to match hardware beyond the CPU unit-test scope.
- **Decode-only instructions fault at runtime** with
  `FaultKind::kUnsupportedInstruction` (localized: kernel / PC / warp / active
  mask / instruction word / variant).
- **Fast mode** (`--fast`) may differ from sm_120 bit-exact FP results (NaN
  payloads, signed zero, subnormals, directed rounding, FTZ/FMZ, double
  rounding); precise mode is the only bit-exact mode.
- **Multi-worker parallelism** is throughput-oriented; data-race-free kernels
  are deterministic across worker counts, but racy kernels produce
  scheduling-dependent results (the race detector reports them).
- **Profiler precision tiers** are reported per metric
  (`exact-architectural` / `exact-empirical` / `approximate` / `unsupported`),
  never silently merged.
- The 2 GiB `semu/core` file in old builds was a crash dump, not a source file;
  avoid committing it.