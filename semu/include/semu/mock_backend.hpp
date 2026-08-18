#pragma once

// Minimal mock backend (SIM_PLAN Phase 10).
//
// Validates the frozen backend contract for a FUTURE JIT backend without
// implementing one: it proves that an IBackend can
//
//   1. receive the pre-decoded IR (BackendLaunchRequest::kernel->predecoded),
//   2. access the runtime services (IRuntimeServices memory / constant bank),
//   3. classify every instruction into
//        - "lowered"            (the mock's hypothetical JIT codegen set),
//        - "interpreter fallback" (functional but not lowered: delegating the
//          whole launch to the reference Interpreter succeeds), or
//        - "decode-only fault"  (cannot lower, cannot execute: reported
//          through the fault ABI as FaultKind::kUnsupportedInstruction).
//
// Classification authority (the game a real JIT would follow):
//   - the FROZEN decode-only boundary decides first: the TMA family
//     (UTMALDG / UTMASTG / UTMAREDG) is decode-only by Phase 10 waiver, and
//     the non-dense tensor alternatives (sparse / rowcol / scale HMMA/QMMA/
//     OMMA, F16 accumulator) are decode-only per the capability manifest —
//     both fault even though the interpreter has functional-looking handlers;
//   - the reference interpreter (`interpreter_handles()`) is the runtime
//     authority for everything else: an instruction family it cannot execute
//     is not lowerable anywhere -> decode-only fault;
//   - remaining functional instructions split into the mock's "lowered" set
//     and the interpreter fallback set.
//
// This is a minimal scaffold, not a JIT: it never codesigns anything.  For a
// launch with zero decode-only faults it optionally runs the ENTIRE launch
// through Interpreter::run_result with the service constant bank sliced into
// the interpreter's MemoryConfig.params (the params land at c[0x0][0x380] on
// both sides), proving the un-lowered instructions execute successfully
// end-to-end.  Lowered-only launches need no interpreter run.

#include <optional>
#include <string>
#include <vector>

#include <semu/context.hpp>
#include <semu/cubin.hpp>
#include <semu/fault.hpp>
#include <semu/interpreter.hpp>
#include <semu/status.hpp>

namespace semu {

class MockBackend : public IBackend {
public:
    struct Policy {
        // Mnemonics the mock has "lowered" (a future JIT would codegen them).
        // Everything functional outside this set is handed to the interpreter
        // fallback.  Empty = every functional instruction falls back.
        std::vector<std::string> lowered{"MOV", "EXIT", "NOP"};

        // Mnemonics forced down the decode-only fault path even when the
        // capability manifest marks them functional — the mock's explicit
        // "cannot lower this" view.  The TMA family default is not strictly
        // needed (the manifest already marks it kDecodeOnly) but keeps the
        // distinguishability against future manifest changes explicit.
        std::vector<std::string> forced_decode_only{
            "UTMALDG", "UTMASTG", "UTMAREDG",
        };

        // Optional global buffer for the fallback interpreter run (owned by
        // the caller; the interpreter's setup_global wraps it).  Null = the
        // fallback runs compute-only.  The interpreter's global addressing is
        // self-contained (a global VA of 0 = buffer start), so the caller
        // supplies the bytes it expects the kernel to see.
        std::vector<std::uint8_t>* global_buffer = nullptr;

        // Worker count for the fallback interpreter run.
        int worker_count = 1;
    };

    explicit MockBackend();
    explicit MockBackend(Policy policy);

    // --- IBackend -------------------------------------------------------
    void bind_runtime(IRuntimeServices* services) override;
    // Classifies every unique pre-decoded word; on the first decode-only /
    // illegal / ambiguous word it returns that word's Fault (through the fault
    // ABI) WITHOUT running anything.  Otherwise (optionally) runs the
    // interpreter over the whole launch and returns its fault on failure.
    Status launch(const BackendLaunchRequest& request) override;
    const char* name() const override { return "mock"; }

    // --- diagnostics ----------------------------------------------------
    struct Stats {
        std::string kernel;                    // last launched kernel
        std::uint64_t words_seen = 0;          // unique pre-decoded words
        std::uint64_t lowered = 0;             // classified as "lowered"
        std::uint64_t interpreter_fallback = 0;  // classified "fallback"
        // First decode-only / illegal / ambiguous fault (when any).
        std::optional<Fault> decode_only_fault;
        std::vector<std::string> decode_only_mnemonics;  // all faulted mnemonics
        // Fallback run observability.
        bool interpreter_ran = false;
        std::uint64_t interpreter_dynamic_instructions = 0;
        std::optional<Fault> interpreter_fault;
        // The full fallback interpreter result (tests inspect GPRs).
        std::optional<Interpreter::Result> interpreter_result;
        // Runtime-service accesses.
        std::uint64_t service_constant_bank_reads = 0;
        std::uint64_t service_probe_writes = 0;
        std::uint64_t service_probe_reads = 0;
    };
    const Stats& stats() const { return stats_; }

    // Runtime-service access probe: when set_service_probe() was called with a
    // live device pointer, launch() writes a magic 8-byte value through
    // services_->write and reads it back through services_->read, counting the
    // accesses.  The test observes the magic byte in the Context's allocator.
    void set_service_probe(DevicePtr ptr) { probe_ptr_ = ptr; }

private:
    Policy policy_;
    IRuntimeServices* services_ = nullptr;
    DevicePtr probe_ptr_{};  // is_null() == no probe
    Stats stats_;
    std::vector<std::uint8_t> params_slice_;  // constant-bank param region for
                                              // the fallback interpreter run
};

}  // namespace semu