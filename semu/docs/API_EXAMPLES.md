# semu API examples (Phase 10 frozen surface)

Every snippet below compiles and runs against `semu_core` (see
`semu/tests/compile_api_test.cpp` for the enforced equivalent).  Headers are
self-contained; `#include <semu/...>` is all you need.

## 1. Decode a 128-bit instruction (decoded IR)

```cpp
#include <semu/decoder.hpp>

const auto& dec = semu::Decoder::instance();
auto r = dec.decode(lo64, hi64);          // or decode(Word128{lo, hi})
if (r.is_unique()) {
    const auto& inst = r.instruction();
    std::string s = inst.disasm_full;     // cuobjdump-style text + schedule
    int stall = inst.schedule.stall;      // scoreboard bracket fields
    // inst.mnemonic / variant_class / operands / modifiers / slot_values
    // are the stable IR a JIT lowers.
}
```

## 2. Load a cubin and launch through a backend

```cpp
#include <semu/context.hpp>
#include <semu/mock_backend.hpp>

auto ctx = semu::Context::create(std::make_shared<semu::MockBackend>());
auto mod = ctx->load_module(bytes);            // strict executable load
auto fn  = ctx->function(mod.value(), mangled_kernel);
semu::LaunchConfig cfg; cfg.grid_x = 16; cfg.block_x = 128;
auto ptr = ctx->memory().allocate(semu::AddressSpace::kGlobal, 4096);
auto res = ctx->launch(fn.value(), cfg,
                       { semu::KernelArg::pointer(ptr.value(), "out") });
if (res.failed()) { /* res.take_error().describe() */ }
std::uint32_t v; ctx->memory().read(ptr.value(), &v, sizeof v);
```

## 3. Reference interpreter (CPU-only, bit-exact)

```cpp
#include <semu/cubin.hpp>
#include <semu/interpreter.hpp>

semu::LaunchEnv env; env.grid = {1,1,1}; env.block = {32,1,1};
semu::RunOptions opts;                       // precise by default
std::vector<std::uint8_t> global(4096, 0);   // device global backing
opts.memory.global = &global;
auto r = semu::Interpreter::run_result(kernel, env, opts);
if (r.fault) { /* FaultKind + locality */ }
else { /* r.ctas[i].warps[w].threads[l].gpr[...] */ }
```

`interpreter_handles(decoded_inst)` answers "can the reference interpreter
execute this instruction family?" without constructing an interpreter.

## 4. Fault ABI

```cpp
#include <semu/fault.hpp>
semu::Fault f(semu::FaultKind::kUnsupportedInstruction, "decode-only");
f.set_kernel("k").set_pc(0x40).set_mnemonic("UTMALDG")
 .set_variant("utmaldg__UUU").set_instruction({lo, hi});
if (f.kind() == semu::FaultKind::kUnsupportedInstruction) { /* ... */ }
std::string report = f.to_report();
```

`Fault` is an `Error`: `f.code() == ErrorCode::kFault`, and any backend can
return it through `Status::failure(f)`.

## 5. Event stream + profiler (trace-only, never affects execution)

```cpp
#include <semu/profiler.hpp>
#include <semu/execution.hpp>

semu::RunOptions opts;
opts.model.l1tex = semu::L1TexMode::kTraceOnly;   // emit memory events
opts.model.race  = semu::RaceMode::kReport;       // race detection
auto r = semu::Interpreter::run_result(kernel, env, opts);
semu::profiler::MemoryProfiler prof(kernel.symbol_name, 1);
prof.add_events(r.memory_events);
auto report = prof.report();                 // fixed schema v1.0
std::string json = report.to_json();
std::string races = /* r.race_reports */ /* to_json not on vector: iterate */
```

## 6. Runtime services (the backend-facing contract)

`IRuntimeServices` is what a backend (interpreter, mock, future JIT) may use:
device memory (`write/read/memset/copy`, `read_typed/write_typed`), the
kernel's constant bank (`constant_bank(name)`), the event channel
(`emit_event` / `set_event_sink`), and cluster DSMEM (`translate_shared`,
`read_shared`, `write_shared`, `atomic_shared`, `shared_topology`).  Backends
never reach into private simulator state.

```cpp
class MyBackend : public semu::IBackend {
    semu::IRuntimeServices* rt = nullptr;
    void bind_runtime(semu::IRuntimeServices* s) override { rt = s; }
    semu::Status launch(const semu::BackendLaunchRequest& req) override {
        // req.kernel->predecoded  -> decoded IR per 16-byte word
        // rt->constant_bank(req.kernel_name) / rt->write(...)
        return semu::Status::success();
    }
    const char* name() const override { return "my-backend"; }
};
```

The Phase 10 freeze guarantees: `IBackend`/`IRuntimeServices`/`IBackend`-side
additions for async/TMA must come through the **versioned extension points**
reserved in `context.hpp` (completion/commit callbacks, mbarrier state query),
never by editing the frozen virtual surfaces.

## 7. Mock backend (validates the JIT-facing contract)

```cpp
#include <semu/mock_backend.hpp>

semu::MockBackend::Policy pol;
pol.lowered = {"MOV", "EXIT", "NOP"};        // the hypothetical JIT set
pol.forced_decode_only = {"UTMALDG", "UTMASTG", "UTMAREDG"};  // TMA
auto bk = std::make_shared<semu::MockBackend>(std::move(pol));
auto ctx = semu::Context::create(bk);
// after a launch:
const auto& st = bk->stats();                // words/lowered/fallback
if (st.decode_only_fault) { /* FaultKind::kUnsupportedInstruction */ }
if (st.interpreter_result) { /* fallback interpreter result */ }
```

The mock demonstrates the two fallback paths a future JIT must honor:
functional-but-un-lowered instructions execute via the reference interpreter
(launch succeeds); decode-only instructions (TMA family, non-dense tensor)
fault through the fault ABI and nothing runs.