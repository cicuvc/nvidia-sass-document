// Interpreter throughput benchmark + hotspot profile (SIM_PLAN Phase 10).
//
// Measures Interpreter::run_result() at worker_count = {1,2,4,...}: dynamic
// instruction THROUGHPUT per worker count plus the scaling ratio
// throughput[N] / throughput[1].  No hard performance SLA is enforced (Phase
// 10 explicitly does not set one); the tool RECORDS results to a JSON file for
// comparison across machines/toolchains.
//
// Determinism gate: every worker count must reproduce the single-worker
// control-flow fingerprint (dynamic count + per-thread PC/exited/predicate
// state) — a multi-worker speedup that silently did less work is rejected.
//
// Hotspots: one extra, UNTIMED precise run with options.collect_hotspots
// produces the per-static-PC dynamic counts; the tool aggregates them into a
// top-N mnemonic profile.  Hotspot collection is deliberately NOT part of the
// timed runs (the per-dispatch map increment would distort them).
//
// Usage:
//   semu_bench_interp_throughput <grid.x> <block.x>
//       [--workers=1,2,4] [--runs=N] [--record=path] [--body=N]
//
// The benchmark kernel is built in-process from a straight-line FFMA/IADD3
// body (`--body` instructions), avoiding any dependency on nvcc / fixtures.
//
// Output: JSON object on stdout; when --record is given the object is appended
// to an array stored in that file.

#include <semu/cubin.hpp>
#include <semu/interpreter.hpp>
#include <semu/version.hpp>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>
#include <map>
#include <optional>
#include <string>
#include <unistd.h>
#include <vector>

namespace {

// Minimal ELF64 sm120 cubin with a single kernel (same shape as the loader
// tests).  `words` is the kernel text as (lo, hi) halves.
std::vector<std::uint8_t> make_bench_cubin(
    const std::vector<std::pair<std::uint64_t, std::uint64_t>>& words) {
    struct S {
        std::string name;
        std::uint32_t type = 0;
        std::uint64_t flags = 0;
        std::vector<std::uint8_t> data;
        std::uint32_t link = 0;
        std::uint32_t info = 0;
        std::uint64_t align = 4;
        std::uint64_t entsize = 0;
    };
    const std::string mangled = "_Z5benchv";
    std::vector<S> secs(7);
    secs[0].name = "";
    secs[1].name = ".shstrtab"; secs[1].type = 3;
    secs[2].name = ".strtab"; secs[2].type = 3;
    secs[3].name = ".symtab"; secs[3].type = 2; secs[3].link = 2;
    secs[3].entsize = 24; secs[3].align = 8;
    secs[4].name = ".text." + mangled; secs[4].type = 1;
    secs[4].flags = 2 | 4; secs[4].align = 128;
    secs[5].name = ".nv.info"; secs[5].type = 0x70000000;
    secs[6].name = ".nv.info." + mangled; secs[6].type = 0x70000000;
    secs[6].info = 4;

    auto push32 = [](std::vector<std::uint8_t>* v, std::uint32_t x) {
        for (int i = 0; i < 4; ++i) v->push_back((x >> (8 * i)) & 0xff);
    };
    auto push64 = [](std::vector<std::uint8_t>* v, std::uint64_t x) {
        for (int i = 0; i < 8; ++i) v->push_back((x >> (8 * i)) & 0xff);
    };
    std::vector<std::uint8_t> kern_info;  // CBANK 0: no params

    std::vector<std::uint8_t> text;
    for (const auto& [lo, hi] : words) {
        push64(&text, lo);
        push64(&text, hi);
    }

    std::vector<std::uint8_t> symtab(24, 0);
    auto sym = [&](std::uint32_t name_off, std::uint8_t info,
                   std::uint8_t other, std::uint16_t shndx,
                   std::uint64_t value, std::uint64_t size) {
        std::vector<std::uint8_t> e;
        push32(&e, name_off); e.push_back(info); e.push_back(other);
        e.push_back(shndx & 0xff); e.push_back(shndx >> 8);
        push64(&e, value); push64(&e, size);
        symtab.insert(symtab.end(), e.begin(), e.end());
    };
    const std::string textsec = ".text." + mangled;
    const std::string constant0 = ".nv.constant0." + mangled;
    std::string strtab = std::string(1, '\0') + textsec + '\0' + mangled +
                         '\0' + constant0 + '\0';
    const std::uint32_t m_off =
        static_cast<std::uint32_t>(1 + textsec.size() + 1);
    const std::uint32_t c_off =
        m_off + static_cast<std::uint32_t>(mangled.size() + 1);
    sym(1, 0x03, 0x00, 4, 0, 0);
    sym(m_off, 0x12, 0x10, 4, 0,
        static_cast<std::uint64_t>(words.size() * 16));  // func
    sym(c_off, 0x03, 0x00, 4, 0, 0);

    secs[4].data = text;
    secs[6].data = kern_info;
    secs[3].data = symtab;
    secs[2].data.assign(strtab.begin(), strtab.end());

    std::string shstr(1, '\0');
    for (std::size_t i = 1; i < secs.size(); ++i) shstr += secs[i].name + '\0';
    secs[1].data.assign(shstr.begin(), shstr.end());

    std::vector<std::uint64_t> offs(secs.size(), 0);
    std::uint64_t cur = 64;
    for (std::size_t i = 0; i < secs.size(); ++i) {
        if (i == 0) continue;
        const std::uint64_t al = std::max<std::uint64_t>(secs[i].align, 1);
        cur = (cur + al - 1) & ~(al - 1);
        offs[i] = cur;
        cur += secs[i].data.size();
    }
    const std::uint64_t shoff = cur;

    std::vector<std::uint8_t> out;
    const std::uint8_t ident[16] = {0x7f, 'E', 'L', 'F', 2, 1, 1, 0x41,
                                    0x08, 0, 0, 0, 0, 0, 0, 0};
    out.insert(out.end(), ident, ident + 16);
    auto p16 = [&](std::uint16_t v) {
        out.push_back(v & 0xff);
        out.push_back((v >> 8) & 0xff);
    };
    p16(2);       // ET_EXEC
    p16(190);     // EM_CUDA
    push32(&out, 1);
    push64(&out, 0);
    push64(&out, 0);
    push64(&out, shoff);
    push32(&out, 0x06007802);
    p16(64); p16(56); p16(0);
    p16(64); p16(static_cast<std::uint16_t>(secs.size())); p16(1);
    for (std::size_t i = 1; i < secs.size(); ++i) {
        while (out.size() % std::max<std::uint64_t>(secs[i].align, 1))
            out.push_back(0);
        out.insert(out.end(), secs[i].data.begin(), secs[i].data.end());
    }
    std::uint32_t name_pos = 1;
    for (std::size_t i = 0; i < secs.size(); ++i) {
        std::uint32_t no = 0;
        if (i > 0) { no = name_pos; name_pos += secs[i].name.size() + 1; }
        push32(&out, no);
        push32(&out, secs[i].type);
        push64(&out, secs[i].flags);
        push64(&out, 0);
        push64(&out, i == 0 ? 0 : offs[i]);
        push64(&out, secs[i].data.size());
        push32(&out, secs[i].link);
        push32(&out, secs[i].info);
        push64(&out, secs[i].align);
        push64(&out, secs[i].entsize);
    }
    return out;
}

// Control-flow fingerprint (same idea as bench_fast_interp): dynamic count +
// per-thread PC / exited / predicate state.  A timed run that deviates (did
// less work, different path) is rejected.
std::uint64_t fingerprint(const semu::Interpreter::Result& r) {
    std::uint64_t h = 1469598103934665603ULL;
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

double now_ms() {
    return std::chrono::duration<double, std::milli>(
               std::chrono::steady_clock::now().time_since_epoch())
        .count();
}

std::string git_head() {
    std::FILE* f = popen("git rev-parse HEAD 2>/dev/null", "r");
    if (!f) return "unknown";
    char buf[64] = {0};
    std::size_t n = std::fread(buf, 1, 63, f);
    pclose(f);
    if (n == 0) return "unknown";
    while (n > 0 && buf[n - 1] == '\n') buf[--n] = 0;
    return std::string(buf);
}

std::string iso8601_now() {
    std::time_t t = std::time(nullptr);
    struct tm tmv;
    localtime_r(&t, &tmv);
    char buf[32];
    std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S%z", &tmv);
    return buf;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 3) {
        std::fprintf(stderr,
                     "usage: %s <grid.x> <block.x> "
                     "[--workers=1,2,4] [--runs=N] [--record=path] "
                     "[--body=N]\n",
                     argv[0]);
        return 2;
    }
    const std::uint32_t grid_x =
        static_cast<std::uint32_t>(std::strtoul(argv[1], nullptr, 10));
    const std::uint32_t block_x =
        static_cast<std::uint32_t>(std::strtoul(argv[2], nullptr, 10));
    if (grid_x == 0 || block_x == 0) {
        std::fputs("bench: grid/block must be non-zero\n", stderr);
        return 2;
    }
    std::vector<int> workers = {1, 2, 4};
    int runs = 7;
    int body = 256;
    std::string record_path;
    for (int i = 3; i < argc; ++i) {
        const std::string a = argv[i];
        if (a.rfind("--workers=", 0) == 0) {
            workers.clear();
            const std::string v = a.substr(10);
            std::size_t pos = 0;
            while (pos < v.size()) {
                std::size_t comma = v.find(',', pos);
                const std::string tok = v.substr(pos, comma == std::string::npos
                                                      ? std::string::npos
                                                      : comma - pos);
                const int w = std::atoi(tok.c_str());
                if (w < 1 || w > 256) {
                    std::fprintf(stderr, "bench: bad worker '%s'\n",
                                 tok.c_str());
                    return 2;
                }
                workers.push_back(w);
                if (comma == std::string::npos) break;
                pos = comma + 1;
            }
        } else if (a.rfind("--runs=", 0) == 0) {
            runs = std::atoi(a.c_str() + 7);
        } else if (a.rfind("--body=", 0) == 0) {
            body = std::atoi(a.c_str() + 7);
        } else if (a.rfind("--record=", 0) == 0) {
            record_path = a.substr(9);
        } else {
            std::fprintf(stderr, "bench: unknown option '%s'\n", a.c_str());
            return 2;
        }
    }
    if (runs < 3) runs = 3;

    // Build the benchmark kernel: a straight-line compute body followed by
    // EXIT.  FFMA chain (R2 = R0*R1 + R2) keeps the body dense; the IADD3
    // counter makes the chain data-dependent and prevents trivial dead-code
    // elision in any future optimizer.
    constexpr std::pair<std::uint64_t, std::uint64_t> kMovZero = {
        0x0000000000007802ULL, 0x000fc00000000f00ULL};  // MOV32I R0, 0
    constexpr std::pair<std::uint64_t, std::uint64_t> kMovOne = {
        0x0000000100007802ULL, 0x000fc00000000f00ULL};  // MOV32I R0, 1
    constexpr std::pair<std::uint64_t, std::uint64_t> kMovTwo = {
        0x0000000200017802ULL, 0x000fc00000000f00ULL};  // MOV32I R1, 2
    constexpr std::pair<std::uint64_t, std::uint64_t> kAddOne = {
        0x0000000100007810ULL, 0x000fc00007ffe0ffULL};  // IADD3 R0, R0, 1, RZ
    constexpr std::pair<std::uint64_t, std::uint64_t> kFfma = {
        0x0000000100027223ULL, 0x000fc00000000002ULL};  // FFMA R2, R0, R1, R2
    constexpr std::pair<std::uint64_t, std::uint64_t> kExit = {
        0x000000000000794dULL, 0x000fc00003800000ULL};  // EXIT
    std::vector<std::pair<std::uint64_t, std::uint64_t>> words;
    words.push_back(kMovZero);
    words.push_back(kMovOne);
    words.push_back(kMovTwo);
    if (body < 4) body = 4;
    for (int i = 0; i < body; ++i) {
        words.push_back(kFfma);
        if ((i % 8) == 0) words.push_back(kAddOne);
    }
    words.push_back(kExit);

    const auto cubin = make_bench_cubin(words);
    auto mod = semu::Module::load(cubin);
    if (mod.failed()) {
        std::fprintf(stderr, "bench: %s\n",
                     mod.take_error().describe().c_str());
        return 1;
    }
    const semu::Kernel* k = mod.value().find_kernel("_Z5benchv");
    if (!k) {
        std::fprintf(stderr, "bench: kernel not found\n");
        return 1;
    }

    semu::LaunchEnv env;
    env.grid = {grid_x, 1, 1};
    env.block = {block_x, 1, 1};

    // ---- baseline single-worker reference (worker set head) ---------------
    const int ref_workers = workers.front();
    semu::RunOptions ref_opts;
    ref_opts.worker_count = ref_workers;
    ref_opts.instruction_limit = 100000000u;
    auto ref_run = semu::Interpreter::run_result(*k, env, ref_opts);
    if (ref_run.fault) {
        std::fprintf(stderr, "bench: reference run faulted: %s\n",
                     ref_run.fault->message().c_str());
        return 1;
    }
    const std::uint64_t dyn = ref_run.dynamic_instructions;
    const std::uint64_t ref_fp = fingerprint(ref_run);
    std::fprintf(stderr,
                 "bench: grid=%ux1 block=%ux1 body=%d dyn=%llu "
                 "ref_workers=%d\n",
                 grid_x, block_x, body,
                 static_cast<unsigned long long>(dyn), ref_workers);

    // ---- per-worker-count timing ------------------------------------------
    struct WcResult {
        int workers = 0;
        double median_ms = 0, p10_ms = 0, p90_ms = 0;
        std::uint64_t dyn = 0;
        double ns_per_instr = 0, instr_per_ms = 0, scaling = 1;
    };
    std::vector<WcResult> wc;
    for (const int w : workers) {
        auto check = [&](const semu::Interpreter::Result& r,
                         const char* which) -> bool {
            if (r.fault) {
                std::fprintf(stderr,
                             "bench: workers=%d %s run faulted: %s\n", w,
                             which, r.fault->message().c_str());
                return false;
            }
            if (r.dynamic_instructions != dyn || fingerprint(r) != ref_fp) {
                std::fprintf(stderr,
                             "bench: workers=%d %s run diverged from the "
                             "reference (dyn=%llu vs %llu)\n",
                             w, which,
                             static_cast<unsigned long long>(
                                 r.dynamic_instructions),
                             static_cast<unsigned long long>(dyn));
                return false;
            }
            return true;
        };
        semu::RunOptions opts;
        opts.worker_count = w;
        opts.instruction_limit = 100000000u;
        // warmup
        for (int i = 0; i < 2; ++i) {
            auto wu = semu::Interpreter::run_result(*k, env, opts);
            if (!check(wu, "warmup")) return 1;
        }
        std::vector<double> times;
        times.reserve(static_cast<std::size_t>(runs));
        for (int i = 0; i < runs; ++i) {
            const double t0 = now_ms();
            auto r = semu::Interpreter::run_result(*k, env, opts);
            const double t1 = now_ms();
            if (!check(r, "timed")) return 1;
            times.push_back(t1 - t0);
        }
        std::sort(times.begin(), times.end());
        auto pct = [&](double q) {
            const int idx =
                static_cast<int>(q * static_cast<double>(times.size() - 1));
            return times[std::max(0, std::min<int>(
                idx, static_cast<int>(times.size()) - 1))];
        };
        WcResult r;
        r.workers = w;
        r.dyn = dyn;
        r.median_ms = pct(0.5);
        r.p10_ms = pct(0.1);
        r.p90_ms = pct(0.9);
        r.ns_per_instr = r.median_ms * 1e6 / static_cast<double>(dyn);
        r.instr_per_ms = static_cast<double>(dyn) / r.median_ms;
        wc.push_back(r);
    }
    const double ref_instr_per_ms = wc.front().instr_per_ms;
    for (auto& r : wc) r.scaling = r.instr_per_ms / ref_instr_per_ms;

    // ---- hotspot profile (untimed, single worker, opt-in) -----------------
    struct Hot {
        std::uint64_t pc = 0;
        std::string mnemonic;
        std::uint64_t count = 0;
    };
    std::vector<Hot> hotspots;
    {
        semu::RunOptions hopts;
        hopts.worker_count = 1;
        hopts.instruction_limit = 100000000u;
        hopts.collect_hotspots = true;
        auto hr = semu::Interpreter::run_result(*k, env, hopts);
        if (hr.fault) {
            std::fprintf(stderr, "bench: hotspot probe faulted\n");
            return 1;
        }
        std::map<std::uint64_t, std::uint64_t> total = hr.pc_hotspots;
        std::vector<std::pair<std::uint64_t, std::uint64_t>> entries;
        for (const auto& [pc, n] : total) entries.emplace_back(pc, n);
        std::sort(entries.begin(), entries.end(),
                  [](const auto& a, const auto& b) {
                      if (a.second != b.second) return a.second > b.second;
                      return a.first < b.first;
                  });
        for (const auto& [pc, n] : entries) {
            const std::size_t idx = static_cast<std::size_t>(pc / 16);
            std::string mnem =
                (idx < k->predecoded.size() && k->predecoded[idx].unique)
                    ? semu::isa::mnemonic_name(k->predecoded[idx].inst->mnemonic)
                    : "?";
            hotspots.push_back({pc, std::move(mnem), n});
        }
    }

    // ---- report ------------------------------------------------------------
    std::printf("{");
    std::printf("\"benchmark\":\"interp_throughput\",\"grid\":[%u,1,1],"
                "\"block\":[%u,1,1],\"body\":%d,\"runs\":%d,"
                "\"dynamic_instructions\":%llu,\"recorded_at\":\"%s\","
                "\"git_commit\":\"%s\",\"build\":\"%s\",\"cxx\":\"%s\","
                "\"host_cpus\":%ld,",
                grid_x, block_x, body, runs,
                static_cast<unsigned long long>(dyn), iso8601_now().c_str(),
                git_head().c_str(), semu::build_mode().c_str(),
                semu::build_cxx_compiler().c_str(),
                std::max<long>(1L, sysconf(_SC_NPROCESSORS_ONLN)));
    std::printf("\"workers\":[");
    for (std::size_t i = 0; i < wc.size(); ++i) {
        if (i) std::printf(",");
        printf("{\"n\":%d,\"median_ms\":%.4f,\"p10_ms\":%.4f,"
               "\"p90_ms\":%.4f,\"ns_per_instr\":%.3f,"
               "\"instr_per_ms\":%.3f,\"scaling\":%.3f}",
               wc[i].workers, wc[i].median_ms, wc[i].p10_ms, wc[i].p90_ms,
               wc[i].ns_per_instr, wc[i].instr_per_ms, wc[i].scaling);
    }
    std::printf("],\"hotspots\":[");
    const std::size_t top = std::min<std::size_t>(10, hotspots.size());
    std::map<std::string, std::uint64_t> mnem_total;
    for (const auto& h : hotspots) mnem_total[h.mnemonic] += h.count;
    for (std::size_t i = 0; i < top; ++i) {
        if (i) std::printf(",");
        printf("{\"pc\":%llu,\"mnemonic\":\"%s\",\"count\":%llu,"
               "\"pct\":%.2f}",
               static_cast<unsigned long long>(hotspots[i].pc),
               hotspots[i].mnemonic.c_str(),
               static_cast<unsigned long long>(hotspots[i].count),
               static_cast<double>(hotspots[i].count) * 100.0 /
                   static_cast<double>(dyn));
    }
    std::printf("],\"mnemonic_totals\":{");
    bool first = true;
    for (const auto& [m, n] : mnem_total) {
        if (!first) std::printf(",");
        first = false;
        printf("\"%s\":%llu", m.c_str(),
               static_cast<unsigned long long>(n));
    }
    std::printf("}}");

    // ---- optional record (append a JSON line to an array file) ------------
    // Each invocation appends one object; a reader treats the file as a JSON
    // array of newline-delimited objects (or reads line by line).
    if (!record_path.empty()) {
        std::string rec;
        rec += "{\"recorded_at\":\"" + iso8601_now() + "\",\"git\":\"" +
               git_head() + "\",\"build\":\"" + semu::build_mode() +
               "\",\"grid_x\":" + std::to_string(grid_x) +
               ",\"block_x\":" + std::to_string(block_x) +
               ",\"body\":" + std::to_string(body) +
               ",\"dynamic_instructions\":" + std::to_string(dyn) +
               ",\"note\":\"scaling is super-linear (parallel worker "
               "cache/warmth effect); NOT evidence of linear scaling\"" +
               ",\"workers\":[";
        for (std::size_t i = 0; i < wc.size(); ++i) {
            if (i) rec += ",";
            char b[160];
            std::snprintf(b, sizeof(b),
                          "{\"n\":%d,\"median_ms\":%.4f,"
                          "\"ns_per_instr\":%.3f,\"instr_per_ms\":%.3f,"
                          "\"scaling\":%.3f}",
                          wc[i].workers, wc[i].median_ms, wc[i].ns_per_instr,
                          wc[i].instr_per_ms, wc[i].scaling);
            rec += b;
        }
        rec += "],\"hotspots\":[";
        for (std::size_t i = 0; i < top; ++i) {
            if (i) rec += ",";
            char b[80];
            std::snprintf(b, sizeof(b),
                          "{\"pc\":%llu,\"mnemonic\":\"%s\",\"count\":%llu}",
                          static_cast<unsigned long long>(hotspots[i].pc),
                          hotspots[i].mnemonic.c_str(),
                          static_cast<unsigned long long>(hotspots[i].count));
            rec += b;
        }
        rec += "]}";
        std::ofstream out(record_path, std::ios::app);
        out << rec << "\n";
    }
    return 0;
}