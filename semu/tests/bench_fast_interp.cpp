// Phase 5.5 fast-interpreter benchmark (SIM_PLAN section 6).
//
// Measures Interpreter::run_result() only (load/decode/JSON excluded).  Same
// loaded Kernel + LaunchEnv run in precise and fast mode, warmup >= 3 runs,
// >= 15 timed runs in alternating AB/BA order, reporting median / p10 / p90,
// ns per dynamic instruction, and the fast/precise speedup.  Also validates
// that every timed run produced the same dynamic instruction count
// (no "did less work" false speedup).
//
// Usage:
//   semu_bench_fast_interp <cubin> <kernel> <grid.x> <block.x> [runs]
//
// Output: a JSON object on stdout.  Performance is only meaningful on a
// Release build; debug/sanitizer runs are reported but not gated.

#include <semu/context.hpp>
#include <semu/interpreter.hpp>

#include <algorithm>
#include <cfenv>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <optional>
#include <string>
#include <vector>

namespace {

std::optional<std::vector<std::uint8_t>> read_file(const char* path) {
    FILE* f = std::fopen(path, "rb");
    if (!f) return std::nullopt;
    std::fseek(f, 0, SEEK_END);
    const long n = std::ftell(f);
    std::fseek(f, 0, SEEK_SET);
    std::vector<std::uint8_t> buf(static_cast<std::size_t>(n));
    if (n > 0 &&
        std::fread(buf.data(), 1, buf.size(), f) != buf.size()) {
        std::fclose(f);
        return std::nullopt;
    }
    std::fclose(f);
    return buf;
}

// Basic steady-clock timer.  (std::chrono is overkill for a micro-bench.)
double now_ms() {
    struct timespec ts;
    ::clock_gettime(CLOCK_MONOTONIC, &ts);
    return static_cast<double>(ts.tv_sec) * 1e3 +
           static_cast<double>(ts.tv_nsec) * 1e-6;
}

// Control-flow fingerprint: a deterministic hash over every thread's PC /
// exited / predicate state plus the dynamic instruction count.  Used to
// detect "did less work" false speedups — a run that skipped instructions or
// took a different path changes the hash.  FP GPRs are deliberately excluded
// (fast mode legitimately differs there).
std::uint64_t fingerprint(const semu::Interpreter::Result& r) {
    std::uint64_t h = 1469598103934665603ULL;  // FNV-1a offset basis
    auto mix = [&h](std::uint64_t v) {
        h ^= v;
        h *= 1099511628211ULL;
    };
    mix(r.dynamic_instructions);
    for (const auto& cta : r.ctas) {
        for (const auto& ws : cta.warps) {
            for (int lane = 0; lane < 32; ++lane) {
                const auto& t = ws.threads[lane];
                mix(t.pc);
                mix(t.exited ? 1u : 0u);
                for (int p = 0; p < 7; ++p) mix(t.pred[p] ? 1u : 0u);
            }
        }
    }
    return h;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 5) {
        std::fprintf(stderr,
                     "usage: %s <cubin> <kernel> <grid.x> <block.x> [runs]\n",
                     argv[0]);
        return 2;
    }
    const char* cubin_path = argv[1];
    const std::string kernel_name = argv[2];
    const std::uint32_t grid_x =
        static_cast<std::uint32_t>(std::strtoul(argv[3], nullptr, 10));
    const std::uint32_t block_x =
        static_cast<std::uint32_t>(std::strtoul(argv[4], nullptr, 10));
    const int runs = argc >= 6 ? std::atoi(argv[5]) : 15;

    auto buf = read_file(cubin_path);
    if (!buf) {
        std::fprintf(stderr, "bench: cannot read '%s'\n", cubin_path);
        return 1;
    }
    auto mod = semu::Module::load(std::move(*buf));
    if (mod.failed()) {
        std::fprintf(stderr, "bench: %s\n",
                     mod.take_error().describe().c_str());
        return 1;
    }
    const semu::Kernel* k = mod.value().find_kernel(kernel_name);
    if (!k) {
        std::fprintf(stderr, "bench: kernel '%s' not found\n",
                     kernel_name.c_str());
        return 1;
    }

    semu::LaunchEnv env;
    env.block = {block_x, 1, 1};
    env.grid = {grid_x, 1, 1};

    semu::RunOptions precise;
    precise.mode = semu::ExecutionMode::kPrecise;
    semu::RunOptions fast;
    fast.mode = semu::ExecutionMode::kFast;
    fast.fast_fp_fallback = semu::FastFpFallback::kNone;

    // ---- functional validation before timing -----------------------------
    auto rp = semu::Interpreter::run_result(*k, env, precise);
    auto rf = semu::Interpreter::run_result(*k, env, fast);
    if (rp.fault || rf.fault) {
        std::fprintf(stderr, "bench: run faulted (precise=%d fast=%d)\n",
                     rp.fault.has_value(), rf.fault.has_value());
        return 1;
    }
    const std::uint64_t dyn = rp.dynamic_instructions;
    if (rf.dynamic_instructions != dyn) {
        std::fprintf(stderr,
                     "bench: dynamic instr mismatch precise=%llu fast=%llu\n",
                     static_cast<unsigned long long>(dyn),
                     static_cast<unsigned long long>(
                         rf.dynamic_instructions));
        return 1;
    }
    const std::uint64_t fast_ops = rf.fast_stats.fast_fp_ops +
                                   rf.fast_stats.precise_fallback_ops;
    const std::uint64_t fallback = rf.fast_stats.precise_fallback_ops;
    // Control-flow fingerprint of the validated runs; every timed run must
    // reproduce it exactly (no fault, same dynamic count, same path), so a
    // mode that silently did less work is rejected (Medium-5).
    const std::uint64_t fp_precise = fingerprint(rp);
    const std::uint64_t fp_fast = fingerprint(rf);
    if (fp_precise != fp_fast) {
        std::fprintf(stderr,
                     "bench: control-flow fingerprint mismatch precise=%llu "
                     "fast=%llu\n",
                     static_cast<unsigned long long>(fp_precise),
                     static_cast<unsigned long long>(fp_fast));
        return 1;
    }

    // ---- warmup ----------------------------------------------------------
    for (int i = 0; i < 3; ++i) {
        auto wp = semu::Interpreter::run_result(*k, env, precise);
        auto wf = semu::Interpreter::run_result(*k, env, fast);
        if (wp.fault || wf.fault ||
            wp.dynamic_instructions != dyn ||
            fingerprint(wp) != fp_precise || fingerprint(wf) != fp_fast) {
            std::fprintf(stderr, "bench: warmup validation failed\n");
            return 1;
        }
    }

    // ---- timed runs, alternating AB/BA order -----------------------------
    std::vector<double> tp, tf;
    tp.reserve(runs);
    tf.reserve(runs);
    for (int i = 0; i < runs; ++i) {
        const bool ab = (i % 2) == 0;
        // Validate a timed result against the expected fingerprint / count /
        // fault-free contract before trusting its time.
        auto check = [&](const semu::Interpreter::Result& r,
                         std::uint64_t expect_fp, const char* which) -> bool {
            if (r.fault) {
                std::fprintf(stderr, "bench: %s timed run faulted\n", which);
                return false;
            }
            if (r.dynamic_instructions != dyn ||
                fingerprint(r) != expect_fp) {
                std::fprintf(stderr,
                             "bench: %s timed run fingerprint mismatch "
                             "(dyn=%llu vs %llu)\n",
                             which,
                             static_cast<unsigned long long>(
                                 r.dynamic_instructions),
                             static_cast<unsigned long long>(dyn));
                return false;
            }
            return true;
        };
        const double t0 = now_ms();
        if (ab) {
            auto rp_run = semu::Interpreter::run_result(*k, env, precise);
            const double t1 = now_ms();
            auto rf_run = semu::Interpreter::run_result(*k, env, fast);
            const double t2 = now_ms();
            if (!check(rp_run, fp_precise, "precise")) return 1;
            if (!check(rf_run, fp_fast, "fast")) return 1;
            tp.push_back(t1 - t0);
            tf.push_back(t2 - t1);
        } else {
            auto rf_run = semu::Interpreter::run_result(*k, env, fast);
            const double t1 = now_ms();
            auto rp_run = semu::Interpreter::run_result(*k, env, precise);
            const double t2 = now_ms();
            if (!check(rf_run, fp_fast, "fast")) return 1;
            if (!check(rp_run, fp_precise, "precise")) return 1;
            tf.push_back(t1 - t0);
            tp.push_back(t2 - t1);
        }
    }
    std::sort(tp.begin(), tp.end());
    std::sort(tf.begin(), tf.end());
    auto pct = [](const std::vector<double>& v, double q) {
        const int idx = static_cast<int>(q * static_cast<double>(v.size() - 1));
        return v[std::max(0, std::min<int>(idx, static_cast<int>(v.size()) - 1))];
    };
    const double mp = pct(tp, 0.5), mf = pct(tf, 0.5);
    const double p10p = pct(tp, 0.1), p90p = pct(tp, 0.9);
    const double p10f = pct(tf, 0.1), p90f = pct(tf, 0.9);

    std::printf(
        "{\"kernel\":\"%s\",\"cubin\":\"%s\",\"grid\":[%u,1,1],"
        "\"block\":[%u,1,1],\"runs\":%d,\"dynamic_instructions\":%llu,"
        "\"fast_fp_ops\":%llu,\"precise_fallback_ops\":%llu,"
        "\"precise_ms_median\":%.4f,\"precise_ms_p10\":%.4f,"
        "\"precise_ms_p90\":%.4f,\"fast_ms_median\":%.4f,"
        "\"fast_ms_p10\":%.4f,\"fast_ms_p90\":%.4f,"
        "\"speedup\":%.3f,\"precise_ns_per_instr\":%.3f,"
        "\"fast_ns_per_instr\":%.3f,"
        "\"fallback_ratio\":%.6f}\n",
        kernel_name.c_str(), cubin_path, grid_x, block_x, runs,
        static_cast<unsigned long long>(dyn),
        static_cast<unsigned long long>(fast_ops),
        static_cast<unsigned long long>(fallback),
        mp, p10p, p90p, mf, p10f, p90f,
        mp / mf,
        mp * 1e6 / static_cast<double>(dyn),
        mf * 1e6 / static_cast<double>(dyn),
        dyn ? static_cast<double>(fallback) /
                  static_cast<double>(fast_ops ? fast_ops : 1)
            : 0.0);
    return 0;
}
