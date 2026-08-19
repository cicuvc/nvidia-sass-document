// Frozen public API compile + smoke test (SIM_PLAN Phase 10).
//
// Two purposes:
//   1. COMPILE: every public header in include/semu/ is compiled standalone
//      (see CMake: per-header object compile checks) and together in this TU
//      with -Wall -Wextra -Wpedantic -Werror.  A header that is not
//      self-contained (missing #include) or that breaks the frozen surface
//      fails the build.
//   2. RUN: exercises the frozen API surface described by api.hpp —
//      IBackend / IRuntimeServices / decoded IR / event stream / fault ABI /
//      profiler schema / mock backend — so a consumer that links only against
//      the public headers compiles and runs.
//
// This test intentionally uses ONLY public headers (no internal include/).
// It must keep compiling for the FROZEN interfaces; adding a JIT backend must
// not require changing anything here.

#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

#include <semu/api.hpp>
#include <semu/capability.hpp>
#include <semu/cluster.hpp>
#include <semu/context.hpp>
#include <semu/cubin.hpp>
#include <semu/debugger.hpp>
#include <semu/decoder.hpp>
#include <semu/execution.hpp>
#include <semu/fault.hpp>
#include <semu/fp.hpp>
#include <semu/global_model.hpp>
#include <semu/hb_clock.hpp>
#include <semu/interpreter.hpp>
#include <semu/l1tex_model.hpp>
#include <semu/l2_events.hpp>
#include <semu/mbarrier.hpp>
#include <semu/memory.hpp>
#include <semu/memory_events.hpp>
#include <semu/memory_service.hpp>
#include <semu/mock_backend.hpp>
#include <semu/profiler.hpp>
#include <semu/race_detector.hpp>
#include <semu/shared_bank.hpp>
#include <semu/status.hpp>
#include <semu/subcore_scheduler.hpp>
#include <semu/tensor.hpp>
#include <semu/tensor_map.hpp>
#include <semu/version.hpp>
#include <semu/word.hpp>

#include "test_framework.hpp"

namespace {

// A minimal third-party-style IBackend implementation — exactly the shape a
// future JIT backend takes.  It compiles against the frozen interface and
// exercises IRuntimeServices + the decoded IR at runtime.
class ExternalBackend : public semu::IBackend {
public:
    semu::IRuntimeServices* services = nullptr;
    bool received_ir = false;
    std::string last_kernel;
    std::size_t words_parsed = 0;

    void bind_runtime(semu::IRuntimeServices* s) override { services = s; }

    semu::Status launch(const semu::BackendLaunchRequest& request) override {
        last_kernel = request.kernel_name;
        received_ir = request.kernel != nullptr;
        CHECK(received_ir);
        for (const auto& w : request.kernel->predecoded) {
            if (w.unique) {
                ++words_parsed;
                // The decoded IR surface a JIT would lower.
                const auto& inst = *w.inst;
                (void)inst.mnemonic;
                (void)inst.variant_class;
                (void)inst.guard_pred;
                (void)inst.guard_not;
                (void)inst.operands.size();
                (void)inst.modifiers.size();
                (void)inst.slot_values.size();
                (void)inst.schedule.stall;
                (void)semu::Decoder::instance()
                    .disassemble(inst.word, /*full=*/true)
                    .size();
            }
        }
        // Runtime services access: constant bank + event channel + memory.
        (void)services->constant_bank(request.kernel_name);
        semu::BasicMemoryEvent ev;
        ev.kind = semu::EventKind::kLaunch;
        ev.pc = 0;
        ev.domain = "external-backend";
        (void)services->emit_event(ev);
        (void)services->shared_topology();
        return semu::Status::success();
    }
    const char* name() const override { return "external-compile-test"; }
};

// A sink implementing the frozen event channel ABI.
class CountingSink : public semu::IEventSink {
public:
    std::size_t events = 0;
    bool emit(const semu::BasicMemoryEvent&) override {
        ++events;
        return true;  // keep delivering
    }
};

}  // namespace

TEST(api_compile_freeze_markers) {
    CHECK(semu::kBackendApiVersion == 1);
    CHECK(semu::kDecodedIrVersion == 3);
    CHECK(semu::kRuntimeServicesVersion == 1);
    CHECK(semu::kEventStreamVersion == 1);
    CHECK(semu::kFaultAbiVersion == 1);
    CHECK(semu::kErrorModelVersion == std::string("1"));
    CHECK(semu::profiler::kReportSchemaVersion == std::string("1.0"));
}

TEST(api_compile_fault_abi) {
    semu::Fault f(semu::FaultKind::kUnsupportedInstruction,
                  "decode-only test");
    f.set_kernel("k").set_pc(0x40).set_cta(0).set_warp(0);
    semu::Word128 w{0x1234, 0x5678};
    f.set_instruction(w).set_mnemonic("UTMALDG").set_variant("utmaldg__UUU");
    CHECK(f.kind() == semu::FaultKind::kUnsupportedInstruction);
    CHECK(std::string(semu::to_string(f.kind())) == "UnsupportedInstruction");
    CHECK(f.kernel() == std::string("k"));
    CHECK(f.pc() == 0x40);
    CHECK(f.instruction()->lo == 0x1234u);
    CHECK(!f.to_report().empty());
    // Error model interop (Fault IS an Error).
    CHECK(f.code() == semu::ErrorCode::kFault);
}

TEST(api_compile_decoded_ir_smoke) {
    // NOP word decodes; the IR fields a JIT consumes are reachable.
    const auto& dec = semu::Decoder::instance();
    auto r = dec.decode(0x0000000000007918ULL, 0x000fc00000000000ULL);
    CHECK(r.is_unique());
    if (!r.is_unique()) return;
    const auto& inst = r.instruction();
    CHECK(inst.mnemonic != semu::isa::Mnemonic::kUnknown);
    CHECK(inst.variant_class != semu::isa::VariantClass::kUnknown);
    (void)inst.guard_pred;
    (void)inst.guard_not;
    (void)inst.operands;
    (void)inst.modifiers;
    (void)inst.slot_values;
    (void)inst.raw_fields;
    (void)inst.schedule;
    (void)semu::Decoder::instance().disassemble(inst.word);
    (void)semu::Decoder::instance().disassemble(inst.word, /*full=*/true);
    // word.hpp bit helpers.
    CHECK(semu::opcode_of(0x0000000000007918ULL, 0x000fc00000000000ULL) != 0);
    (void)semu::extract_bits(0, 0, 63, 0);
}

TEST(api_compile_event_stream_smoke) {
    CountingSink sink;
    semu::MemoryEvent ev;
    ev.kind = semu::MemoryEventKind::kL1TexIssue;
    ev.sm = 0;
    ev.subcore = 1;
    ev.cta = 2;
    ev.warp = 3;
    ev.pc = 0x10;
    ev.mnemonic = "LDGSTS";
    ev.request_kind = "coupled";
    ev.lane_ranges.resize(32);
    ev.model_version = semu::kModelVersion;
    (void)ev;
    semu::BasicMemoryEvent basic;
    basic.kind = semu::EventKind::kMemoryAccess;
    basic.width = 4;
    (void)sink.emit(basic);
    CHECK(sink.events == 1);
    // Profiler schema is versioned and consumable.
    semu::profiler::MemoryProfiler prof("k", 1);
    prof.add_event(ev);
    auto rep = prof.report();
    CHECK(rep.schema_version == semu::profiler::kReportSchemaVersion);
}

TEST(api_compile_runtime_services_contract) {
    auto ctx = semu::Context::create(
        std::make_shared<ExternalBackend>());
    CHECK(ctx.ok());
    if (!ctx.ok()) return;
    // IRuntimeServices honored by Context (it IS the runtime).
    auto* rt = &ctx.value();
    (void)rt->constant_bank("nope");  // empty span for unknown kernel
    const auto& topo = rt->shared_topology();
    (void)topo;
    // KernelArg launch surface.
    auto a = semu::KernelArg::integer(0x11223344, "n");
    CHECK(a.width() == 8);
    auto p = semu::KernelArg::raw(std::vector<std::uint8_t>(4, 0xEE), "blob");
    CHECK(p.width() == 4);
    // Error model.
    auto e = semu::Error::not_found("missing");
    CHECK(e.code() == semu::ErrorCode::kNotFound);
    CHECK(!e.describe().empty());
}

TEST(api_compile_mock_backend_surface) {
    semu::MockBackend::Policy pol;
    pol.lowered = {"MOV"};
    pol.forced_decode_only = {"UTMALDG"};
    auto mb = std::make_shared<semu::MockBackend>(std::move(pol));
    CHECK(std::string(mb->name()) == "mock");
    mb->set_service_probe(semu::DevicePtr{});
    (void)mb->stats();
    auto ctx = semu::Context::create(mb);
    CHECK(ctx.ok());
}

TEST(api_compile_capability_manifest) {
    const auto& m = semu::CapabilityManifest::current();
    CHECK(m.header().arch == "sm120");
    CHECK(m.count(semu::CapabilityState::kDecodeOnly) > 0);
    auto rows = m.by_mnemonic("HMMA");
    CHECK(!rows.empty());
    (void)m.to_text();
    (void)m.to_json();
}

int main() { return semu_test::run_all("api_compile"); }