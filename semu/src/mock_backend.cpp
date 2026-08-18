// Mock backend implementation (SIM_PLAN Phase 10) — see mock_backend.hpp.

#include <semu/mock_backend.hpp>

#include <algorithm>
#include <cstring>
#include <utility>

#include <semu/capability.hpp>

namespace semu {

namespace {

// Look up the capability-manifest state for a decoded variant.  The exact
// variant class wins; falling back to the mnemonic scope when the class is
// not in the manifest (permissive: functional if ANY variant of that mnemonic
// is functional).
CapabilityState manifest_state(const DecodedInstruction& inst) {
    const auto& manifest = CapabilityManifest::current();
    for (const auto* e : manifest.by_mnemonic(inst.mnemonic)) {
        if (e->variant_class == inst.variant_class) return e->state;
    }
    for (const auto* e : manifest.by_mnemonic(inst.mnemonic)) {
        if (e->state != CapabilityState::kDecodeOnly &&
            e->state != CapabilityState::kUnsupported) {
            return e->state;
        }
    }
    return CapabilityState::kDecodeOnly;
}

// The FROZEN decode-only boundary (SIM_PLAN Phase 10 waiver): these families
// have functional-looking interpreter handlers, but their semantics are NOT
// frozen as capability (decode-only, must not be described as GPU validated).
//   - TMA (UTMALDG / UTMASTG / UTMAREDG): decode-only (manifest marks every
//     variant kDecodeOnly).
//   - non-dense tensor alternatives (sparse / rowcol / scale HMMA/QMMA/OMMA,
//     F16 accumulator): decode-only (manifest per-variant).
// The dense F32-accumulator HMMA/QMMA/OMMA shapes ARE functional (OMMA carries
// the documented gpu_waiver: CPU-only differential evidence).
bool frozen_decode_only(const DecodedInstruction& inst) {
    const std::string& m = inst.mnemonic;
    if (m == "UTMALDG" || m == "UTMASTG" || m == "UTMAREDG") {
        return true;  // TMA family: decode-only, not frozen
    }
    if (m == "HMMA" || m == "QMMA" || m == "OMMA") {
        const CapabilityState st = manifest_state(inst);
        return !(st == CapabilityState::kFunctional ||
                 st == CapabilityState::kProfiled);
    }
    return false;
}

constexpr std::uint64_t kProbeMagic = 0x4D4F434B5B5B4247ULL;  // "MOCK[BG"

}  // namespace

MockBackend::MockBackend() : MockBackend(Policy{}) {}

MockBackend::MockBackend(Policy policy) : policy_(std::move(policy)) {}

void MockBackend::bind_runtime(IRuntimeServices* services) {
    services_ = services;
}

Status MockBackend::launch(const BackendLaunchRequest& request) {
    if (!services_) {
        return Status::failure(Error::illegal_state(
            "mock backend launched before bind_runtime"));
    }
    stats_.decode_only_fault.reset();
    stats_.decode_only_mnemonics.clear();
    stats_.interpreter_ran = false;
    stats_.interpreter_result.reset();
    stats_.interpreter_fault.reset();
    stats_.lowered = 0;
    stats_.interpreter_fallback = 0;
    stats_.words_seen = 0;
    stats_.kernel = request.kernel_name;

    // ---- (1) receive the decoded IR and classify every unique word --------
    const auto is_lowered = [&](const std::string& m) {
        return std::find(policy_.lowered.begin(), policy_.lowered.end(), m) !=
               policy_.lowered.end();
    };
    const auto is_forced_decode_only = [&](const std::string& m) {
        return std::find(policy_.forced_decode_only.begin(),
                         policy_.forced_decode_only.end(), m) !=
               policy_.forced_decode_only.end();
    };
    const auto report_decode_only = [&](const PredecodedWord& w) {
        Fault f(FaultKind::kUnsupportedInstruction,
                "mock backend cannot lower '" + w.inst.mnemonic +
                    "' (decode-only variant " + w.inst.variant_class +
                    "); not lowered, not functional -> decode-only fault");
        f.set_kernel(request.kernel_name)
            .set_pc(w.pc)
            .set_instruction({w.lo, w.hi})
            .set_mnemonic(w.inst.mnemonic)
            .set_variant(w.inst.variant_class);
        stats_.decode_only_mnemonics.push_back(w.inst.mnemonic);
        if (!stats_.decode_only_fault) stats_.decode_only_fault = std::move(f);
        return f;
    };

    for (const auto& w : request.kernel->predecoded) {
        ++stats_.words_seen;
        if (!w.unique) {
            // Illegal / ambiguous words are never lowerable.
            const FaultKind k = w.reason.rfind("ambiguous", 0) == 0
                                    ? FaultKind::kAmbiguousInstruction
                                    : FaultKind::kInvalidInstruction;
            stats_.decode_only_mnemonics.push_back(w.reason);
            if (!stats_.decode_only_fault) {
                stats_.decode_only_fault =
                    Fault(k, "mock backend: " + w.reason)
                        .set_kernel(request.kernel_name)
                        .set_pc(w.pc)
                        .set_instruction({w.lo, w.hi});
            }
            return Status::failure(*stats_.decode_only_fault);
        }
        const std::string& m = w.inst.mnemonic;
        if (is_forced_decode_only(m) || frozen_decode_only(w.inst)) {
            stats_.decode_only_mnemonics.push_back(m);
            const Fault f = report_decode_only(w);
            return Status::failure(f);
        }
        // Runtime authority: the reference interpreter must be able to execute
        // the instruction family; otherwise it cannot be lowered anywhere and
        // the decode-only fault fires.
        if (!interpreter_handles(w.inst)) {
            const Fault f = report_decode_only(w);
            return Status::failure(f);
        }
        if (is_lowered(m)) {
            ++stats_.lowered;
        } else {
            ++stats_.interpreter_fallback;
        }
    }

    // ---- (2) access the runtime services ------------------------------
    // Constant bank: slice the launch's param region (KPARAM params live at
    // c[0x0][0x380] in the full bank image) and keep it for the interpreter
    // fallback (which places the SAME bytes at 0x380).  Cross-check the
    // service view against the request view.
    std::span<const std::uint8_t> svc_bank =
        services_->constant_bank(request.kernel_name);
    ++stats_.service_constant_bank_reads;
    const std::uint64_t cbank =
        request.kernel->meta.cbank_param_size > 0
            ? static_cast<std::uint64_t>(request.kernel->meta.cbank_param_size)
            : 0;
    constexpr std::uint64_t kParamBase = 0x380;
    params_slice_.clear();
    if (svc_bank.size() > kParamBase) {
        const std::uint64_t n = std::min<std::uint64_t>(
            cbank, svc_bank.size() - kParamBase);
        params_slice_.assign(svc_bank.begin() + static_cast<std::ptrdiff_t>(kParamBase),
                             svc_bank.begin() +
                                 static_cast<std::ptrdiff_t>(kParamBase + n));
    }
    // Consistency: the service constant bank and the request bank must agree
    // on the param bytes (both materialize the same launch bank).
    const std::uint64_t req_n = request.constant_bank.size() > kParamBase
        ? std::min<std::uint64_t>(cbank, request.constant_bank.size() - kParamBase)
        : 0;
    if (params_slice_.size() != req_n ||
        !std::equal(params_slice_.begin(), params_slice_.end(),
                    request.constant_bank.begin() +
                        static_cast<std::ptrdiff_t>(kParamBase))) {
        return Status::failure(Error::internal(
            "mock backend: service constant bank does not match the launch "
            "request constant bank"));
    }

    // Optional service memory probe: write + read back a magic value.
    if (!probe_ptr_.is_null()) {
        const std::uint64_t magic = kProbeMagic;
        Status wr = services_->write(probe_ptr_, &magic, sizeof(magic));
        ++stats_.service_probe_writes;
        if (wr.failed()) return wr;
        std::uint64_t back = 0;
        Status rd = services_->read(probe_ptr_, &back, sizeof(back));
        ++stats_.service_probe_reads;
        if (rd.failed()) return rd;
        if (back != kProbeMagic) {
            return Status::failure(Error::internal(
                "mock backend: runtime service memory probe round-trip "
                "mismatch"));
        }
    }

    // ---- (3) interpreter fallback for the un-lowered functional set ------
    // A real hybrid backend would hand the un-lowered blocks to the
    // interpreter; the minimal mock runs the WHOLE launch through the
    // reference interpreter to prove that path executes successfully.
    if (stats_.interpreter_fallback > 0) {
        LaunchEnv env;
        env.grid = {request.config.grid_x, request.config.grid_y,
                    request.config.grid_z};
        env.block = {request.config.block_x, request.config.block_y,
                     request.config.block_z};
        if (request.cluster && request.cluster->enabled()) {
            env.cluster = request.cluster->dims();
        }
        RunOptions opts;
        opts.mode = ExecutionMode::kPrecise;      // bit-exact reference path
        opts.worker_count = policy_.worker_count;
        opts.memory.params = &params_slice_;
        opts.memory.global = policy_.global_buffer;
        Interpreter::Result r =
            Interpreter::run_result(*request.kernel, env, opts);
        stats_.interpreter_ran = true;
        stats_.interpreter_dynamic_instructions = r.dynamic_instructions;
        stats_.interpreter_fault = r.fault;
        stats_.interpreter_result = std::move(r);
        if (stats_.interpreter_fault) {
            return Status::failure(*stats_.interpreter_fault);
        }
    }
    return Status::success();
}

}  // namespace semu