// Shared internal helpers for the sm120 baseline interpreter
// (moved from src/interpreter.cpp anonymous namespace; internal
// linkage per TU -- cross-family operand/memory/int helpers).
// unused-function warnings are silenced: each TU includes the full
// set but only uses the helpers of its own family.
#pragma once

#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunused-function"
#elif defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#endif

#include <semu/interpreter/interpreter.hpp>

namespace semu {
namespace {

using semu::fp::Rnd;

// The migration-scaffold OperandFields ops[] view was ELIMINATED: the
// interpreter reads operand values solely through the NAMED fields of the
// concrete DecodedX[_k] structs (see the per-mnemonic handlers below).  The
// generated fill_operand_fields/operand_field bridges remain for the
// decoder renderer / CLI / test harness only.
// Extract an operand field's register index (255 = absent / RZ).
std::uint64_t mem_ov_idx(const shape::OperandValue& o) {
    return static_cast<std::uint64_t>(shape::operand_value_as_i64(o));
}

// RZ (255) reads as 0.
constexpr int kRegRz = 255;

// SpecialRegister hardware encoding values (verified empirically:
// SR_LANEID=0, SR_TID.X=33, SR_CTAID.X=37 in real sm120 cubins; the rest
// follow the CUDA S2R register convention).
constexpr std::uint64_t kSrLaneid = 0;
constexpr std::uint64_t kSrClock = 1;
constexpr std::uint64_t kSrTidX = 33, kSrTidY = 34, kSrTidZ = 35;
constexpr std::uint64_t kSrCtaidX = 37, kSrCtaidY = 38, kSrCtaidZ = 39;
constexpr std::uint64_t kSrNtid = 40;
constexpr std::uint64_t kSrWarpId = 41, kSrWarpSize = 42;
constexpr std::uint64_t kSrNctaidX = 43, kSrNctaidY = 44, kSrNctaidZ = 45;
constexpr std::uint64_t kSrSmId = 46, kSrSmemBase = 47;

// Named barrier opcodes (from sm120.json BAR variants).

// Phase 6 Step 2D: replay a buffered race-event log into a RaceDetector in a
// deterministic order (sorted by (cta_id, ordinal)), independent of host
// scheduling and worker count.  Sorting groups every CTA's events together in
// the order that CTA's interpreter appended them, so the per-CTA program
// order, barrier releases and happens-before chain are preserved.  The log is
// cleared after replay.  No-op when the detector is disabled or the log empty.
void replay_race_log(RaceDetector* d, std::vector<RaceEvent>& log) {
    if (!d || !d->enabled() || log.empty()) return;
    std::sort(log.begin(), log.end(),
              [](const RaceEvent& a, const RaceEvent& b) {
                  if (a.cta != b.cta) return a.cta < b.cta;
                  return a.ordinal < b.ordinal;
              });
    for (const auto& ev : log) {
        if (ev.kind == RaceEvent::kObserve) {
            d->observe(ev.access);
        } else if (ev.kind == RaceEvent::kAtomic) {
            d->atomic_rmw(ev.access);
        } else if (ev.kind == RaceEvent::kCtaBarrier) {
            d->cta_barrier(ev.cta, ev.sm, ev.warps);
        } else if (ev.kind == RaceEvent::kFence) {
            d->fence(ev.cta, ev.sm, ev.warp, ev.scope);
        }
    }
    log.clear();
}
// True when a 32-bit FP pattern is NaN/Inf/subnormal (drives the fast-mode
// exceptional fallback classification).
bool exceptional_f32(std::uint32_t bits) {
    const float f = std::bit_cast<float>(bits);
    return std::isnan(f) || std::isinf(f) ||
           std::fpclassify(f) == FP_SUBNORMAL;
}
// True when a 64-bit FP pattern is NaN/Inf/subnormal.
bool exceptional_f64(std::uint64_t bits) {
    const double d = std::bit_cast<double>(bits);
    return std::isnan(d) || std::isinf(d) ||
           std::fpclassify(d) == FP_SUBNORMAL;
}

// Normalize a merged memory-event stream's ids: the L1 issue events use a
// per-interpreter counter and the L2 engine keeps its own event counter, so
// the two ranges collide (both start at 0).  Renumber every event globally
// (deterministic order preserved) and remap parent references.  Applies to
// BOTH the single-worker and merged parallel streams so event ids are always
// globally unique.
void normalize_memory_event_ids(std::vector<MemoryEvent>& events) {
    std::map<std::uint64_t, std::uint64_t> remap;
    std::uint64_t next_id = 0;
    for (auto& ev : events) {
        auto pit = remap.find(ev.parent_event_id);
        if (pit != remap.end()) ev.parent_event_id = pit->second;
        const std::uint64_t old = ev.event_id;
        ev.event_id = ++next_id;
        remap[old] = ev.event_id;
    }
}

// Classify an F2F result pattern according to its DESTINATION format
// (fp.hpp constants: F16=0, F32=1, F64=2, BF16=3).  The raw 16-bit F16/BF16
// results must NOT be reinterpreted as f32 — a finite half like 0x3c00 would
// look like a subnormal f32 and wrongly trigger an exceptional fallback.
bool exceptional_f2f_result(int dstfmt, std::uint32_t fout,
                            std::uint32_t fouthi) {
    if (dstfmt == 2) {  // F64 (register pair).
        return exceptional_f64((static_cast<std::uint64_t>(fouthi) << 32) |
                               fout);
    }
    if (dstfmt == 0 || dstfmt == 3) {  // F16 / BF16 in the low 16 bits.
        const std::uint16_t h = static_cast<std::uint16_t>(fout & 0xffffu);
        // exp field all-ones -> NaN/Inf; exp zero + nonzero frac -> subnormal.
        if (dstfmt == 0) {
            const unsigned exp = (h >> 10) & 0x1F;
            if (exp == 0x1F) return true;                      // NaN / Inf
            return exp == 0 && (h & 0x3FF) != 0;               // subnormal
        }
        const unsigned exp = (h >> 7) & 0xFF;
        if (exp == 0xFF) return true;                          // NaN / Inf
        return exp == 0 && (h & 0x7F) != 0;                    // subnormal
    }
    return exceptional_f32(fout);                              // F32
}

// Classify an F2F SOURCE pattern according to its SOURCE format.  A BF16
// source lives in the low 16 bits of the register; the raw 32-bit register
// value must not be read as an f32 (0x0000bf80 is a finite BF16 -1.0, not an
// f32 subnormal).
bool exceptional_f2f_source(int srcfmt, std::uint32_t src,
                            std::uint32_t src_hi) {
    if (srcfmt == 2) {  // F64 source (register pair).
        return exceptional_f64((static_cast<std::uint64_t>(src_hi) << 32) |
                               src);
    }
    if (srcfmt == 0 || srcfmt == 3) {  // F16 / BF16 in the low 16 bits.
        const std::uint16_t h = static_cast<std::uint16_t>(src & 0xffffu);
        if (srcfmt == 0) {
            const unsigned exp = (h >> 10) & 0x1F;
            if (exp == 0x1F) return true;                      // NaN / Inf
            return exp == 0 && (h & 0x3FF) != 0;               // subnormal
        }
        const unsigned exp = (h >> 7) & 0xFF;
        if (exp == 0xFF) return true;                          // NaN / Inf
        return exp == 0 && (h & 0x7F) != 0;                    // subnormal
    }
    return exceptional_f32(src);                               // F32
}

// Run-scope fenv guard (Phase 5.5 fast mode): the fast path relies on host
// round-to-nearest for all arithmetic; pin it once for the whole run / step
// sequence and restore the caller's mode afterwards (never per-instruction).
//
// The guard is MOVE-ONLY and is constructed directly via arm() on the final
// owning object (e.g. inside an std::optional) so no copy exists whose
// destructor could restore the caller's rounding mode before execution — that
// would leave the fast kernel running under the caller's mode (e.g. FE_UPWARD)
// instead of the pinned RN.
struct FenvGuard {
    int saved = FE_TONEAREST;
    bool armed = false;  // owns the "RN is set" obligation
    FenvGuard() = default;
    FenvGuard(const FenvGuard&) = delete;
    FenvGuard& operator=(const FenvGuard&) = delete;
    FenvGuard(FenvGuard&& o) noexcept
        : saved(o.saved), armed(o.armed) {
        o.armed = false;  // moved-from no longer restores
    }
    FenvGuard& operator=(FenvGuard&& o) noexcept {
        if (this != &o) {
            saved = o.saved;
            armed = o.armed;
            o.armed = false;
        }
        return *this;
    }
    // Save the caller's mode and pin RN.  Returns false (and leaves the mode
    // untouched) on any failure.
    bool arm() {
        saved = std::fegetround();
        if (saved == -1) return false;
        if (std::fesetround(FE_TONEAREST) != 0) return false;
        armed = true;
        return true;
    }
    ~FenvGuard() {
        if (armed) {
            if (std::fesetround(saved) != 0) {
                // Cannot report from a destructor; make it observable in
                // debug/test output so a lost restore is never silent.
                std::fprintf(stderr,
                             "semu: fast-mode fenv restore to mode %d "
                             "failed\n", saved);
            }
        }
    }
};

bool checked_mul4(std::int64_t a, std::int64_t* out) {
    // a * 4 with overflow check.
    if (a > INT64_MAX / 4 || a < INT64_MIN / 4) return false;
    *out = a * 4;
    return true;
}
bool checked_add(std::int64_t a, std::int64_t b, std::int64_t* out) {
    if ((b > 0 && a > INT64_MAX - b) || (b < 0 && a < INT64_MIN - b))
        return false;
    *out = a + b;
    return true;
}
// Checked `unsigned base + signed offset` (memory addresses; never wraps).
bool checked_add(std::uint64_t base, std::int64_t offset,
                 std::uint64_t* out) {
    if (offset >= 0) {
        const std::uint64_t d = static_cast<std::uint64_t>(offset);
        if (base > UINT64_MAX - d) return false;
        *out = base + d;
    } else {
        const std::uint64_t mag =
            static_cast<std::uint64_t>(-(offset + 1)) + 1;
        if (base < mag) return false;
        *out = base - mag;
    }
    return true;
}
// Checked unsigned + unsigned (never wraps).  Used to combine a GPR base with
// a uniform base where the sum could exceed 2^64 (High-2); silent wrap would
// fabricate a wrong (usually low) address.
bool checked_uadd(std::uint64_t a, std::uint64_t b, std::uint64_t* out) {
    if (a > UINT64_MAX - b) return false;
    *out = a + b;
    return true;
}
std::uint32_t resolve_sr(SpecialReg sr, int lane, int warp_id, int cta_id,
                         const LaunchEnv& env) {
    (void)cta_id;
    const int tid = warp_id * kLanesPerWarp + lane;
    switch (sr) {
        case SpecialReg::kLaneid: return static_cast<std::uint32_t>(lane);
        case SpecialReg::kTidX:
            return static_cast<std::uint32_t>(tid % env.block[0]);
        case SpecialReg::kTidY:
            return static_cast<std::uint32_t>((tid / env.block[0]) %
                                              env.block[1]);
        case SpecialReg::kTidZ:
            return static_cast<std::uint32_t>(tid / (env.block[0] *
                                                     env.block[1]));
        case SpecialReg::kCtaidX: return static_cast<std::uint32_t>(cta_id % env.grid[0]);
        case SpecialReg::kCtaidY: return static_cast<std::uint32_t>((cta_id / env.grid[0]) % env.grid[1]);
        case SpecialReg::kCtaidZ: return static_cast<std::uint32_t>(cta_id / (env.grid[0] * env.grid[1]));
        case SpecialReg::kNtidX: return env.block[0];
        case SpecialReg::kNtidY: return env.block[1];
        case SpecialReg::kNtidZ: return env.block[2];
        case SpecialReg::kNctaidX: return env.grid[0];
        case SpecialReg::kNctaidY: return env.grid[1];
        case SpecialReg::kNctaidZ: return env.grid[2];
        case SpecialReg::kClock: return 0;
        case SpecialReg::kWarpId: return static_cast<std::uint32_t>(warp_id);
        case SpecialReg::kWarpSize: return kLanesPerWarp;
        case SpecialReg::kSmemBase: return 0;
        case SpecialReg::kSmId: return static_cast<std::uint32_t>(env.sm_id);
        default: return 0;
    }
}

// ---- direct typed readers -------------------------------------------------
// These take an OperandValue straight out of the decoded instruction (the
// interpreter reads the NAMED fields of the concrete Decoded structs).  No
// slot-name matching, no lookups of any kind on the execution path.

// Read a GPR operand with RZ=0 + negate/absolute applied.
[[maybe_unused]] std::uint32_t read_reg_ov(const ThreadState& t,
                          const shape::OperandValue& o) {
    if (static_cast<shape::OperandKind>(o.kind) !=
        shape::OperandKind::kRegister)
        return 0;
    const std::uint64_t r =
        static_cast<std::uint64_t>(shape::operand_value_as_i64(o));
    std::uint32_t v = (r == 255 || r >= kNumGprs) ? 0 : t.gpr[r];
    if (o.flags & 2) v &= 0x7fffffff;  // absolute
    if (o.flags & 1) v = ~v + 1;       // negate
    return v;
}

// M5 pre-binding: GPR index from an operand value (-1 when absent / RZ / not
// a plain register).
[[maybe_unused]] int bind_idx_ov(const shape::OperandValue& o) {
    if (static_cast<shape::OperandKind>(o.kind) !=
        shape::OperandKind::kRegister)
        return -1;
    const std::uint64_t r =
        static_cast<std::uint64_t>(shape::operand_value_as_i64(o));
    if (r == 255 || r >= kNumGprs) return -1;
    return static_cast<int>(r);
}

// Read a uniform-register operand from warp state (URZ = 255 -> 0).
[[maybe_unused]] std::uint32_t read_ur_ov(const WarpState& w,
                         const shape::OperandValue& o) {
    if (static_cast<shape::OperandKind>(o.kind) !=
        shape::OperandKind::kUniformRegister)
        return 0;
    const std::uint64_t r =
        static_cast<std::uint64_t>(shape::operand_value_as_i64(o));
    if (r == 255) return 0;  // URZ
    if (r < kNumUrs) return w.ur[r];
    return 0;
}

// Read a 64-bit uniform-register PAIR (URx | UR(x+1) << 32), URZ=0.
[[maybe_unused]] std::uint64_t read_ur_pair_ov(const WarpState& w,
                              const shape::OperandValue& o) {
    if (static_cast<shape::OperandKind>(o.kind) !=
        shape::OperandKind::kUniformRegister)
        return 0;
    const std::uint64_t r =
        static_cast<std::uint64_t>(shape::operand_value_as_i64(o));
    if (r == 255) return 0;  // URZ
    if (r >= kNumUrs - 1) return 0;  // no room for the high word
    return static_cast<std::uint64_t>(w.ur[r]) |
           (static_cast<std::uint64_t>(w.ur[r + 1]) << 32);
}

// Read a 64-bit address register pair {R,R+1} (RZ=0).
[[maybe_unused]] std::uint64_t read_addr_pair_ov(const ThreadState& t,
                                const shape::OperandValue& o) {
    if (static_cast<shape::OperandKind>(o.kind) !=
        shape::OperandKind::kRegister)
        return 0;
    const std::uint64_t r =
        static_cast<std::uint64_t>(shape::operand_value_as_i64(o));
    if (r == 255 || r >= kNumGprs - 1) return 0;
    return static_cast<std::uint64_t>(t.gpr[r]) |
           (static_cast<std::uint64_t>(t.gpr[r + 1]) << 32);
}

// Extract a predicate operand per-lane; false when absent/not a predicate.
// `not` flag (bit2) inverts.
[[maybe_unused]] bool read_pred_ov(const ThreadState& t, const shape::OperandValue& o,
                  bool* out) {
    if (static_cast<shape::OperandKind>(o.kind) !=
        shape::OperandKind::kPredicate)
        return false;
    const bool not_ = (o.flags & 4) != 0;
    const std::uint64_t p =
        static_cast<std::uint64_t>(shape::operand_value_as_i64(o));
    if (p == 7) {  // PT
        *out = !not_;
        return true;
    }
    if (p < 7) {
        bool v = t.pred[p];
        if (not_) v = !v;
        *out = v;
        return true;
    }
    return false;
}

// Write a predicate destination per-lane (Pu/Pv/Pq).
[[maybe_unused]] void write_pred_ov(ThreadState& t, const shape::OperandValue& o, bool v) {
    if (static_cast<shape::OperandKind>(o.kind) !=
        shape::OperandKind::kPredicate)
        return;
    const std::uint64_t p =
        static_cast<std::uint64_t>(shape::operand_value_as_i64(o));
    if (p < 7) t.pred[p] = v;
}

// Destination write: write lo[/hi] to the GPR named by the destination
// operand value (RZ dest discards; 64-bit dest writes the pair).
[[maybe_unused]] void write_rd_ov(WarpState& w, ThreadState& t,
                 const shape::OperandValue& o, std::uint32_t lo,
                 std::uint32_t hi, bool write_hi = false) {
    (void)w;
    if (static_cast<shape::OperandKind>(o.kind) !=
        shape::OperandKind::kRegister)
        return;
    const std::uint64_t r =
        static_cast<std::uint64_t>(shape::operand_value_as_i64(o));
    if (r == 255 || r >= kNumGprs) return;  // RZ dest: discard
    t.gpr[r] = lo;
    if (write_hi && r + 1 < kNumGprs) {
        t.gpr[r + 1] = hi;
    }
}

// Unified source read: register / uniform register / UImm|SImm immediate;
// any other kind reads 0 (preserves the pre-migration FImm32-exclusion
// behavior for the FP/immediate paths).
std::uint32_t src_value(const WarpState& w, const ThreadState& t,
                        const shape::OperandValue& o) {
    const auto k = static_cast<shape::OperandKind>(o.kind);
    if (k == shape::OperandKind::kRegister)
        return read_reg_ov(t, o);
    if (k == shape::OperandKind::kUniformRegister)
        return read_ur_ov(w, o);
    if (k == shape::OperandKind::kUImm ||
        k == shape::OperandKind::kSImm)
        return static_cast<std::uint32_t>(
            shape::operand_value_as_i64(o));
    return 0;
}

}  // namespace
}  // namespace semu
#if defined(__clang__)
#pragma clang diagnostic pop
#elif defined(__GNUC__)
#pragma GCC diagnostic pop
#endif
