// sm120 baseline interpreter -- vector float: FFMA/FADD/FMUL, FP64, FSET/FSETP/FMNMX/FSEL, F2F/I2F/F2I/FRND conversions.
// Split from src/interpreter.cpp (Interpreter member definitions
// moved verbatim; class, dispatch and orchestration untouched).

#include <semu/interpreter/interpreter.hpp>

#include <algorithm>
#include <cfenv>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>

#include <semu/fp/fast_fp.hpp>
#include <semu/fp/fp.hpp>
#include <semu/memory/l1tex_model.hpp>

#include "isa_shapes_fill.hpp"
#include "isa_data.hpp"

#include "sm120_shared.hpp"

namespace semu {
Status Interpreter::fp32_arith_core(WarpState& w, std::uint32_t mask,
                                    std::uint64_t rd_rv, int op, Rnd rnd,
                                    bool flush, bool sat, int fmz_val,
                                    const shape::OperandValue& opa,
                                    const shape::OperandValue& opb,
                                    const shape::OperandValue* opc) {
    // Phase 5.5: resolve the leaf policy once per instruction (M5).
    const Fp32Plan plan = plan_fp32(op, static_cast<int>(rnd), flush);
    // Source value: register / uniform register / UImm/SImm immediate.
    // (Float-bit immediates (FImm32) are NOT fed to the immediate path —
    // same as the pre-migration behavior.)
    auto src_val = [&w](const ThreadState& t,
                        const shape::OperandValue& o) -> std::uint32_t {
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
    };
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        std::uint32_t a = src_val(t, opa);
        std::uint32_t b = src_val(t, opb);
        std::uint32_t c = (op == 2) ? src_val(t, *opc) : 0;
        bool use_fast = plan.use_fast;
        if (plan.need_exceptional &&
            (exceptional_f32(a) || exceptional_f32(b) ||
             exceptional_f32(c))) {
            use_fast = false;
        }
        std::uint32_t out;
        if (use_fast) {
            if (plan.ignored_modifier) ++fast_stats_.ignored_modifier_ops;
            switch (op) {
                case 0: out = fp::fast_fadd(a, b, static_cast<int>(rnd), flush, sat); break;
                case 1: out = fp::fast_fmul(a, b, static_cast<int>(rnd), flush, sat); break;
                default: out = fp::fast_ffma(a, b, c, static_cast<int>(rnd), flush, sat); break;
            }
            // Phase 5.5 High-2: kExceptional also falls back when the
            // NATIVE RESULT is exceptional, even if all inputs were
            // finite (e.g. overflow to Inf).  The input check above only
            // caught exceptional operands; recompute with the precise
            // helper here so the fallback policy is honored.
            if (plan.need_exceptional && exceptional_f32(out)) {
                ++fast_stats_.precise_fallback_ops;
                switch (op) {
                    case 0: out = fp::fadd(a, b, rnd, flush, sat); break;
                    case 1: out = fp::fmul(a, b, rnd, flush, sat); break;
                    default: out = fp::ffma(a, b, c, rnd, fmz_val, sat); break;
                }
            } else {
                note_fast_leaf(true);
            }
        } else {
            if (fast_mode()) ++fast_stats_.precise_fallback_ops;
            switch (op) {
                case 0: out = fp::fadd(a, b, rnd, flush, sat); break;
                case 1: out = fp::fmul(a, b, rnd, flush, sat); break;
                default: out = fp::ffma(a, b, c, rnd, fmz_val, sat); break;
            }
        }
        if (rd_rv != 255 && rd_rv < kNumGprs) t.gpr[rd_rv] = out;
    }
    return Status::success();
}

Status Interpreter::do_fadd(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst) {
    const auto& d = *static_cast<const shape::DecodedFADD3*>(&inst);
    const Rnd rnd = static_cast<Rnd>(d.rnd);
    const bool flush = static_cast<int>(d.ftz) != 0;
    const bool sat = static_cast<int>(d.sat) != 0;
    return fp32_arith_core(w, mask,
                           static_cast<std::uint64_t>(
                               shape::operand_value_as_i64(d.Rd)),
                           0, rnd, flush, sat, 0, d.Ra, d.c, nullptr);
}

Status Interpreter::do_fmul(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst) {
    const auto& d = *static_cast<const shape::DecodedFMUL3*>(&inst);
    const Rnd rnd = static_cast<Rnd>(d.rnd);
    const bool flush = static_cast<int>(d.fmz) != 0;
    const bool sat = static_cast<int>(d.sat) != 0;
    return fp32_arith_core(w, mask,
                           static_cast<std::uint64_t>(
                               shape::operand_value_as_i64(d.Rd)),
                           1, rnd, flush, sat, 0, d.Ra, d.b, nullptr);
}

Status Interpreter::do_ffma(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst) {
    const auto& d = *static_cast<const shape::DecodedFFMA4*>(&inst);
    const Rnd rnd = static_cast<Rnd>(d.rnd);
    // FFMA needs the raw fmz value (FMZ and FTZ differ on sm120).
    const int fmz_val = static_cast<int>(d.fmz);
    const bool flush = fmz_val != 0;
    const bool sat = static_cast<int>(d.sat) != 0;
    return fp32_arith_core(w, mask,
                           static_cast<std::uint64_t>(
                               shape::operand_value_as_i64(d.Rd)),
                           2, rnd, flush, sat, fmz_val, d.Ra, d.b, &d.c);
}

Status Interpreter::fp64_arith_core(WarpState& w, std::uint32_t mask,
                                    std::uint64_t rd_rv, int op, Rnd rnd,
                                    const shape::OperandValue& opa,
                                    const shape::OperandValue& opb,
                                    const shape::OperandValue* opc) {
    // Phase 5.5: resolve the leaf policy once per instruction (M5).
    const Fp64Plan plan = plan_fp64(op, static_cast<int>(rnd));
    const bool sat = false;
    // M5 pre-binding: 64-bit pair base indices (DADD's 2nd source is the
    // named c field; DFMA adds the third source).
    const int ra_r = bind_idx_ov(opa);
    const int sb_r = bind_idx_ov(opb);
    const int rc_r = (op == 2) ? bind_idx_ov(*opc) : -1;
    auto read_pair_at = [](const ThreadState& t, int idx) -> std::uint64_t {
        if (idx < 0 || idx >= kNumGprs - 1) return 0;
        std::uint64_t lo = t.gpr[idx];
        std::uint64_t hi = t.gpr[idx + 1];
        return lo | (hi << 32);
    };
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        const std::uint64_t a = read_pair_at(t, ra_r);
        const std::uint64_t b = read_pair_at(t, sb_r);
        const std::uint64_t c = read_pair_at(t, rc_r);
        bool use_fast = plan.use_fast;
        if (plan.need_exceptional &&
            (exceptional_f64(a) || exceptional_f64(b) ||
             exceptional_f64(c))) {
            use_fast = false;
        }
        std::uint64_t out;
        if (use_fast) {
            if (plan.ignored_modifier) ++fast_stats_.ignored_modifier_ops;
            switch (op) {
                case 0: out = fp::fast_fadd64(a, b, static_cast<int>(rnd), sat); break;
                case 1: out = fp::fast_fmul64(a, b, static_cast<int>(rnd), sat); break;
                default: out = fp::fast_fma64(a, b, c, static_cast<int>(rnd), sat); break;
            }
            // Phase 5.5 High-2: kExceptional also falls back on an
            // exceptional NATIVE RESULT (overflow -> Inf) even when all
            // inputs were finite.
            if (plan.need_exceptional && exceptional_f64(out)) {
                ++fast_stats_.precise_fallback_ops;
                switch (op) {
                    case 0: out = fp::fadd64(a, b, rnd, sat); break;
                    case 1: out = fp::fmul64(a, b, rnd, sat); break;
                    default: out = fp::fma64(a, b, c, rnd, sat); break;
                }
            } else {
                note_fast_leaf(true);
            }
        } else {
            if (fast_mode()) ++fast_stats_.precise_fallback_ops;
            switch (op) {
                case 0: out = fp::fadd64(a, b, rnd, sat); break;
                case 1: out = fp::fmul64(a, b, rnd, sat); break;
                default: out = fp::fma64(a, b, c, rnd, sat); break;
            }
        }
        if (rd_rv != 255 && rd_rv < kNumGprs - 1) {
            t.gpr[rd_rv] = static_cast<std::uint32_t>(out & 0xffffffffu);
            t.gpr[rd_rv + 1] = static_cast<std::uint32_t>(out >> 32);
        }
    }
    return Status::success();
}

Status Interpreter::do_dadd(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst) {
    const auto& d = *static_cast<const shape::DecodedDADD3*>(&inst);
    return fp64_arith_core(
        w, mask,
        static_cast<std::uint64_t>(shape::operand_value_as_i64(d.Rd)), 0,
        static_cast<Rnd>(d.rnd), d.Ra, d.c, nullptr);
}

Status Interpreter::do_dmul(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst) {
    const auto& d = *static_cast<const shape::DecodedDMUL3*>(&inst);
    return fp64_arith_core(
        w, mask,
        static_cast<std::uint64_t>(shape::operand_value_as_i64(d.Rd)), 1,
        static_cast<Rnd>(d.rnd), d.Ra, d.b, nullptr);
}

Status Interpreter::do_dfma(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst) {
    const auto& d = *static_cast<const shape::DecodedDFMA4*>(&inst);
    return fp64_arith_core(
        w, mask,
        static_cast<std::uint64_t>(shape::operand_value_as_i64(d.Rd)), 2,
        static_cast<Rnd>(d.rnd), d.Ra, d.b, &d.c);
}

Status Interpreter::fset_core(WarpState& w, std::uint32_t mask,
                              std::uint64_t fcomp, std::uint64_t bop,
                              bool ftz, const shape::OperandValue& ra,
                              const shape::OperandValue& second,
                              const shape::OperandValue* pp,
                              const shape::OperandValue& rd,
                              const shape::OperandValue* pv,
                              bool dest_is_pred) {
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        std::uint32_t a = read_reg_ov(t, ra);
        std::uint32_t b = src_value(w, t, second);
        if (ftz) {
            if (fast_mode()) {
                // Phase 5.5: kNone skips the subnormal flush and counts
                // an ignored modifier; other policies fall back to the
                // precise flush.
                if (options_.fast_fp_fallback != FastFpFallback::kNone) {
                    ++fast_stats_.precise_fallback_ops;
                    a = fp::flush_f32(a);
                    b = fp::flush_f32(b);
                } else {
                    ++fast_stats_.ignored_modifier_ops;
                }
            } else {
                a = fp::flush_f32(a);
                b = fp::flush_f32(b);
            }
        }
        const float fa = std::bit_cast<float>(a);
        const float fb = std::bit_cast<float>(b);
        const bool anan = std::isnan(fa);
        const bool bnan = std::isnan(fb);
        bool r = false;
        switch (fcomp) {
            case 0:  r = false; break;                                   // F
            case 1:  r = !anan && !bnan && fa < fb; break;               // LT
            case 2:  r = !anan && !bnan && fa == fb; break;              // EQ
            case 3:  r = !anan && !bnan && fa <= fb; break;              // LE
            case 4:  r = !anan && !bnan && fa > fb; break;               // GT
            case 5:  r = !anan && !bnan && fa != fb; break;              // NE
            case 6:  r = !anan && !bnan && fa >= fb; break;              // GE
            case 7:  r = !anan && !bnan; break;                          // NUM
            case 8:  r = anan || bnan; break;                            // NAN
            // U-variants are unordered-true: true when either operand
            // is NaN (verified on sm120: every FSETP.*U(1.0, NaN) -> 1).
            case 9:  r = anan || bnan || fa < fb; break;                  // LTU
            case 10: r = anan || bnan || fa == fb; break;                 // EQU
            case 11: r = anan || bnan || fa <= fb; break;                 // LEU
            case 12: r = anan || bnan || fa > fb; break;                  // GTU
            case 13: r = anan || bnan || fa != fb; break;                 // NEU
            case 14: r = anan || bnan || fa >= fb; break;                 // GEU
            case 15: r = true; break;                                    // T
            default: break;
        }
        // Bop combines (r) with Pp: AND/OR/XOR.  Pu = (r) BOP Pp;
        // Pv = (!r) BOP Pp (verified: FSETP Pv is NOT !Pu for OR).
        bool ppv = true;
        if (pp) read_pred_ov(t, *pp, &ppv);
        bool out = false;
        switch (bop) {
            case 0: out = r && ppv; break;  // AND
            case 1: out = r || ppv; break;  // OR
            case 2: out = r != ppv; break;  // XOR
            default: out = r; break;
        }
        bool outv = false;
        switch (bop) {
            case 0: outv = (!r) && ppv; break;
            case 1: outv = (!r) || ppv; break;
            case 2: outv = (!r) != ppv; break;
            default: outv = !r; break;
        }
        if (fast_mode()) note_fast_leaf(false);
        if (dest_is_pred) {
            write_pred_ov(t, rd, out);
            if (pv) write_pred_ov(t, *pv, outv);
        } else {  // FSET: Rd = 1.0f or 0.0f (FSET.Rd holds result).
            write_rd_ov(w, t, rd, out ? 0x3f800000u : 0u, 0);
        }
    }
    return Status::success();
}

Status Interpreter::do_fsetp(WarpState& w, std::uint32_t mask,
                             const DecodedInstruction& inst) {
    // FSETP Pu, Pv, Ra, Rb/Sb, Pp (bop combines with Pp; simple 3-op
    // form has no Pv/Pp).  FSETP5=[Pu,Pv,Ra,2nd,Pp]  FSETP3=[Pu,Ra,2nd].
    // 5-op (kfsetp__*) carries Pv/Pp; 3-op (kfsetp_simple__*) does not.
    std::uint64_t fcomp = 0, bop = 0;
    bool ftz = false;
    if (inst.variant_class == isa::VariantClass::kfsetp__RIR_RIR ||
        inst.variant_class == isa::VariantClass::kfsetp__RRR_RRR ||
        inst.variant_class == isa::VariantClass::kfsetp__RUR_RUR) {
        const auto& d = *static_cast<const shape::DecodedFSETP5*>(&inst);
        fcomp = static_cast<std::uint64_t>(d.fcomp);
        bop = static_cast<std::uint64_t>(d.bop);
        ftz = static_cast<int>(d.ftz) != 0;
        return fset_core(w, mask, fcomp, bop, ftz, d.Ra, d.b, &d.Pp, d.Pu,
                         &d.Pv, true);
    }
    const auto& d = *static_cast<const shape::DecodedFSETP3*>(&inst);
    fcomp = static_cast<std::uint64_t>(d.fcomp);
    ftz = static_cast<int>(d.ftz) != 0;
    return fset_core(w, mask, fcomp, bop, ftz, d.Ra, d.b, nullptr, d.Pu,
                     nullptr, true);
}

Status Interpreter::do_fset(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst) {
    // FSET  Rd, Ra, Rb/Sb, Pp  (Rd = 0x3f800000 or 0).
    // 4-op (kfset__*) carries Pp; 3-op (kfset_simple__*) does not.
    if (inst.variant_class == isa::VariantClass::kfset__RIR_RIR ||
        inst.variant_class == isa::VariantClass::kfset__RRR_RRR ||
        inst.variant_class == isa::VariantClass::kfset__RUR_RUR) {
        const auto& d = *static_cast<const shape::DecodedFSET4*>(&inst);
        return fset_core(w, mask,
                         static_cast<std::uint64_t>(d.fcomp),
                         static_cast<std::uint64_t>(d.bop),
                         static_cast<int>(d.ftz) != 0, d.Ra, d.b, &d.Pp,
                         d.Rd, nullptr, false);
    }
    const auto& d = *static_cast<const shape::DecodedFSET3*>(&inst);
    return fset_core(w, mask, static_cast<std::uint64_t>(d.fcomp), 0,
                     static_cast<int>(d.ftz) != 0, d.Ra, d.b, nullptr, d.Rd,
                     nullptr, false);
}

Status Interpreter::do_fmnmx(WarpState& w, std::uint32_t mask,
                             const DecodedInstruction& inst) {
    // FMNMX Rd[, Pu], Ra, Rb/Sb, Pp  (Pp: PT=min, !PT=max; .NAN
    // propagate; XORSIGN: result sign = sign(Ra) XOR sign(Rb)).
    // 4-op form: [Rd,Ra,2nd,Pp]; 5-op (kfmnmx_pred__*) form:
    // [Rd,Pu,Ra,2nd,Pp].
    std::uint64_t nan = 0, xorsign_val = 0;
    bool ftz = false;
    const shape::OperandValue* rd = nullptr;
    const shape::OperandValue* rra = nullptr;
    const shape::OperandValue* rb = nullptr;
    const shape::OperandValue* rpp = nullptr;
    if (inst.variant_class == isa::VariantClass::kfmnmx_pred__RIR_RIR ||
        inst.variant_class == isa::VariantClass::kfmnmx_pred__RRR_RRR ||
        inst.variant_class == isa::VariantClass::kfmnmx_pred__RUR_RUR) {
        // 5-op [Rd,Pu,Ra,2nd,Pp]
        const auto& d = *static_cast<const shape::DecodedFMNMX5*>(&inst);
        rd = &d.Rd; rra = &d.Ra; rb = &d.b; rpp = &d.Pp;
        nan = static_cast<std::uint64_t>(d.nan);
        xorsign_val = static_cast<std::uint64_t>(d.xorsign);
        ftz = static_cast<int>(d.ftz) != 0;
    } else {
        // 4-op [Rd,Ra,2nd,Pp]
        const auto& d = *static_cast<const shape::DecodedFMNMX4*>(&inst);
        rd = &d.Rd; rra = &d.Ra; rb = &d.b; rpp = &d.Pp;
        nan = static_cast<std::uint64_t>(d.nan);
        xorsign_val = static_cast<std::uint64_t>(d.xorsign);
        ftz = static_cast<int>(d.ftz) != 0;
    }
    const bool xorsign = xorsign_val != 0;
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        std::uint32_t a = read_reg_ov(t, *rra);
        std::uint32_t b = src_value(w, t, *rb);
        if (ftz) {
            if (fast_mode()) {
                if (options_.fast_fp_fallback != FastFpFallback::kNone) {
                    ++fast_stats_.precise_fallback_ops;
                    a = fp::flush_f32(a);
                    b = fp::flush_f32(b);
                } else {
                    ++fast_stats_.ignored_modifier_ops;
                }
            } else {
                a = fp::flush_f32(a);
                b = fp::flush_f32(b);
            }
        }
        // Pp=PT (7) is "min" per the test; !PT is max.  (pred value == 7
        // AND not inverted) is min, anything else is max.
        const std::uint64_t ppv_v =
            static_cast<std::uint64_t>(shape::operand_value_as_i64(*rpp));
        const bool is_max = !(ppv_v == 7 && !(rpp->flags & 4));
        const float fa = std::bit_cast<float>(a);
        const float fb = std::bit_cast<float>(b);
        const bool a_nan = std::isnan(fa);
        const bool b_nan = std::isnan(fb);
        std::uint32_t out;
        bool nan_propagated = false;
        if (nan && (a_nan || b_nan)) {
            // .NAN: propagate a NaN (canonicalize like arithmetic).
            out = fp::kCanonicalNan32;
            nan_propagated = true;
        } else if (a_nan || b_nan) {
            // nonan: return the non-NaN operand.
            out = a_nan ? b : a;
            nan_propagated = true;
        } else {
            // min/max of two numbers; ties pick b on min per the test
            // (+0/-0 handled by comparing as IEEE float).
            const bool pick_b = is_max ? (fb >= fa) : (fb <= fa);
            out = pick_b ? b : a;
        }
        // XORSIGN only applies to the selected min/max value, NOT to a
        // NaN-propagated result.
        if (xorsign && !nan_propagated) {
            // XORSIGN: result sign = sign(a) XOR sign(b).
            const std::uint32_t sa = (a >> 31) & 1;
            const std::uint32_t sb_ = (b >> 31) & 1;
            const std::uint32_t ns = sa ^ sb_;
            out = (out & 0x7fffffffu) | (ns << 31);
        }
        if (fast_mode()) note_fast_leaf(false);
        write_rd_ov(w, t, *rd, out, 0);
    }
    return Status::success();
}

Status Interpreter::do_fsel(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst) {
    // FSEL Rd, Ra, Rb/Sb, Pp (select Ra when Pp true, else Rb/Sb).
    // Roles: [Rd, Ra, 2nd, Pp].
    const auto& d = *static_cast<const shape::DecodedFSEL4*>(&inst);
    const bool ftz = static_cast<int>(d.ftz) != 0;
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        std::uint32_t a = read_reg_ov(t, d.Ra);
        if (ftz) {
            if (fast_mode()) {
                if (options_.fast_fp_fallback != FastFpFallback::kNone) {
                    ++fast_stats_.precise_fallback_ops;
                    a = fp::flush_f32(a);
                } else {
                    ++fast_stats_.ignored_modifier_ops;
                }
            } else {
                a = fp::flush_f32(a);
            }
        }
        std::uint32_t b = src_value(w, t, d.b);
        bool p = false;
        read_pred_ov(t, d.Pp, &p);
        if (fast_mode()) note_fast_leaf(false);
        write_rd_ov(w, t, d.Rd, p ? a : b, 0);
    }
    return Status::success();
}

Status Interpreter::do_f2f(WarpState& w, std::uint32_t mask,
                           const DecodedInstruction& inst) {
    // F2F Rd, Rb/Sb/URb (src/dst format in the combined dstfmt.srcfmt
    // slot).  Roles: [Rd, source].  RIR forms (source = Sb immediate) are
    // not executed — same as the pre-migration has_rb gate, identified by
    // the operand kind (Register only).
    const auto& d = *static_cast<const shape::DecodedF2F2*>(&inst);
    if (static_cast<shape::OperandKind>(d.b.kind) !=
        shape::OperandKind::kRegister)
        return Status::success();
    const std::uint64_t fmt =
        static_cast<std::uint64_t>(d.dstfmt_srcfmt);
    const Rnd rnd = static_cast<Rnd>(d.rnd);
    const bool ftz = static_cast<int>(d.ftz) != 0;
    const bool sat = false;  // F2F has no SAT modifier (was always 0)
    const int rb_r = bind_idx_ov(d.b);
    const std::uint64_t rd_rv =
        static_cast<std::uint64_t>(shape::operand_value_as_i64(d.Rd));
    // Combined fmt codes (DSTFMT_SRCFMT_*): F16.F32=17, BF16.F32=20,
    // F32.F16=10, BF16.F16=12, F16.BF16=33, F32.BF16=34, F64.F16=11,
    // F64.BF16=35, F16.F64=25, F32.F64=26, BF16.F64=28.
    int dstfmt = 0, srcfmt = 0;
    switch (fmt) {
        case 17: dstfmt = 0; srcfmt = 1; break;   // F16.F32
        case 19: dstfmt = 2; srcfmt = 1; break;   // F64.F32
        case 20: dstfmt = 3; srcfmt = 1; break;   // BF16.F32
        case 10: dstfmt = 1; srcfmt = 0; break;   // F32.F16
        case 12: dstfmt = 3; srcfmt = 0; break;   // BF16.F16
        case 33: dstfmt = 0; srcfmt = 3; break;   // F16.BF16
        case 34: dstfmt = 1; srcfmt = 3; break;   // F32.BF16
        case 11: dstfmt = 2; srcfmt = 0; break;   // F64.F16
        case 35: dstfmt = 2; srcfmt = 3; break;   // F64.BF16
        case 25: dstfmt = 0; srcfmt = 2; break;   // F16.F64
        case 26: dstfmt = 1; srcfmt = 2; break;   // F32.F64
        case 28: dstfmt = 3; srcfmt = 2; break;   // BF16.F64
        default: break;
    }
    // M5 pre-binding: F64 source pair base + dest index (used by both the
    // fast and the precise path below; hoisted out of the lane loop).
    // Hoisted policy flag (Medium-7 / perf): under kNone the exceptional
    // input/result classification is skipped entirely; only kExceptional
    // pays for it.
    const bool exc_policy =
        options_.fast_fp_fallback == FastFpFallback::kExceptional;
    auto read_f64_pair = [](const ThreadState& t, int idx) {
        if (idx < 0 || idx >= kNumGprs - 1) return std::uint64_t{0};
        return t.gpr[idx] |
               (static_cast<std::uint64_t>(t.gpr[idx + 1]) << 32);
    };
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        std::uint32_t src = read_reg_ov(t, d.b);
        std::uint32_t out = 0;
        std::uint32_t outhi = 0;
        // Phase 5.5: fast F2F for native host conversions (RN, no
        // FTZ/FMZ/SAT).  Fallback policy routes exceptional inputs and
        // modifier mismatches to the precise helpers.
        if (fast_mode() && rnd == Rnd::kRn && !ftz && !sat) {
            std::uint32_t src_hi = 0;
            bool exceptional = false;
            if (srcfmt == 2) {  // F64 source: read the {Rb,Rb+1} pair and
                                // classify the FULL 64-bit pattern as a
                                // double (not two separate f32s — High-3).
                const std::uint64_t pair = read_f64_pair(t, rb_r);
                src_hi = static_cast<std::uint32_t>(pair >> 32);
                exceptional = exc_policy && exceptional_f64(pair);
            } else {
                // Format-aware source classification (round-3 Blocker):
                // a BF16/F16 source lives in the low 16 bits; the raw
                // 32-bit register value is not a meaningful f32.
                exceptional = exc_policy &&
                    exceptional_f2f_source(srcfmt, src, src_hi);
            }
            std::uint32_t fout = 0, fouthi = 0;
            if (!exceptional &&
                fp::fast_f2f(src, src_hi, dstfmt, srcfmt, &fout,
                             &fouthi)) {
                // Fast conversion produced a native result.  Under
                // kExceptional, a native RESULT that is exceptional (e.g.
                // finite F32 -> F16 overflow to Inf) also falls back.
                // Exactly ONE precise_fallback_ops increment per lane/leaf:
                // fall through to the common exit below (Issue-2 round-2 —
                // no double counting).
                const bool result_exc =
                    exc_policy && exceptional_f2f_result(dstfmt, fout,
                                                         fouthi);
                if (!result_exc) {
                    note_fast_leaf(true);
                    if (rd_rv != 255 && rd_rv < kNumGprs) {
                        t.gpr[rd_rv] = fout;
                        if (dstfmt == 2 && rd_rv < kNumGprs - 1)
                            t.gpr[rd_rv + 1] = fouthi;
                    }
                    continue;
                }
            }
            // Common fallback exit: reached when the input is exceptional,
            // fast_f2f cannot handle the (dstfmt,srcfmt) pair natively, or
            // the native result was exceptional.  Counted exactly once.
            ++fast_stats_.precise_fallback_ops;
        }
        if (dstfmt == 2) {
            std::uint32_t f32;
            if (srcfmt == 0) f32 = fp::f16_to_f32(
                static_cast<std::uint16_t>(src & 0xffffu));
            else if (srcfmt == 3) f32 = src & 0xffff0000u;
            else f32 = src;
            if (ftz) f32 = fp::flush_f32(f32);
            const double dbl = static_cast<double>(
                std::bit_cast<float>(f32));
            const std::uint64_t d = std::bit_cast<std::uint64_t>(dbl);
            out = static_cast<std::uint32_t>(d & 0xffffffffu);
            outhi = static_cast<std::uint32_t>(d >> 32);
        } else if (srcfmt == 2) {
            // 64-bit source (F16/BF16/F32 <- F64): read the {Rb,Rb+1}
            // pair as the F64 value and downconvert DIRECTLY from the
            // FP64 bit pattern (no FP32 intermediate — avoids double
            // rounding and preserves directed rounding).
            const std::uint64_t pair = read_f64_pair(t, rb_r);
            if (dstfmt == 1) {  // F32.F64
                out = fp::f64_to_f32(pair, rnd, ftz, sat);
            } else if (dstfmt == 0) {  // F16.F64
                out = fp::f64_to_f16(pair, rnd, ftz, sat);
            } else if (dstfmt == 3) {  // BF16.F64
                out = fp::f64_to_bf16(pair, rnd, ftz, sat);
            }
        } else {
            out = fp::f2f(src, dstfmt, srcfmt, rnd, ftz, sat);
        }
        if (rd_rv != 255 && rd_rv < kNumGprs) {
            t.gpr[rd_rv] = out;
            if (dstfmt == 2 && rd_rv < kNumGprs - 1)
                t.gpr[rd_rv + 1] = outhi;
        }
        (void)outhi;
    }
    return Status::success();
}

Status Interpreter::cvtx_core(WarpState& w, std::uint32_t mask, Rnd rnd,
                              bool ftz, int dstfmt, int srcfmt, bool is_i2f,
                              const shape::OperandValue& rd,
                              const shape::OperandValue& src) {
    const bool sat = false;
    // Source operand: register (Rb/URb) or Sb immediate.
    const auto src_kind = static_cast<shape::OperandKind>(src.kind);
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        const std::uint32_t val =
            (src_kind == shape::OperandKind::kRegister)
                ? read_reg_ov(t, src)
                : static_cast<std::uint32_t>(
                      shape::operand_value_as_i64(src));
        std::uint64_t out = 0;
        if (fast_mode()) {
            // Phase 5.5 fast conversions.  I2F: RN + F32/F64 destination
            // are native host casts (bit-exact); otherwise fall back.
            // F2I: checked-range fast conversion; out-of-range / NaN /
            // Inf / unsupported format routes to the precise saturating
            // helper (no UB on any path).
            if (is_i2f) {
                const int f = dstfmt == 3 ? 2
                             : dstfmt == 1 ? 0
                             : dstfmt == 4 ? 3
                             : 1;  // map to fp F16=0 F32=1 F64=2 BF16=3
                std::uint32_t fout = 0, fouthi = 0;
                if (rnd == Rnd::kRn &&
                    fp::fast_i2f(val, f, srcfmt, &fout, &fouthi)) {
                    note_fast_leaf(true);
                    write_rd_ov(w, t, rd, fout, fouthi, f == 2);
                    continue;
                }
                ++fast_stats_.precise_fallback_ops;
            } else {  // F2I
                std::uint32_t fout = 0;
                if (fp::fast_f2i(val, dstfmt, static_cast<int>(rnd), ftz,
                                 &fout)) {
                    note_fast_leaf(true);
                    write_rd_ov(w, t, rd, fout, 0, false);
                    continue;
                }
                ++fast_stats_.precise_fallback_ops;
            }
        }
        if (is_i2f) {
            // I2F dstfmt enum: Float32 F32=2, Float64 F64=3,
            // DSTFMT_F16_F32_BF16 F16=1 F32=2 BF16=4.  Map to the fp
            // constants (F16=0 F32=1 F64=2 BF16=3).
            int f = 1;
            switch (dstfmt) {
                case 1: f = 0; break;  // F16
                case 2: f = 1; break;  // F32
                case 3: f = 2; break;  // F64
                case 4: f = 3; break;  // BF16
                default: f = 1; break;
            }
            out = fp::i2f(val, f, srcfmt, rnd, sat);
        } else {
            out = fp::f2i(val, dstfmt, srcfmt, rnd, ftz, false);
        }
        // F64 destinations (I2F.F64, dstfmt==3) write a register pair.
        const bool f64_dst = (is_i2f && dstfmt == 3);
        write_rd_ov(w, t, rd, static_cast<std::uint32_t>(out),
                    static_cast<std::uint32_t>(out >> 32), f64_dst);
    }
    return Status::success();
}

Status Interpreter::do_i2f(WarpState& w, std::uint32_t mask,
                           const DecodedInstruction& inst) {
    // Roles: [Rd, source]; source is a register (Rb/URb) or the Sb
    // immediate.  Sat is absent from the schema (was always 0); no ftz.
    const auto& d = *static_cast<const shape::DecodedI2F2*>(&inst);
    return cvtx_core(w, mask, static_cast<Rnd>(d.rnd), false,
                     static_cast<int>(d.dstfmt),
                     static_cast<int>(d.srcfmt), true, d.Rd, d.b);
}

Status Interpreter::do_f2i(WarpState& w, std::uint32_t mask,
                           const DecodedInstruction& inst) {
    // Roles: [Rd, source].  F2I has no sat member (was always 0).
    const auto& d = *static_cast<const shape::DecodedF2I2*>(&inst);
    return cvtx_core(w, mask, static_cast<Rnd>(d.rnd),
                     static_cast<int>(d.ftz) != 0,
                     static_cast<int>(d.dstfmt),
                     static_cast<int>(d.srcfmt), false, d.Rd, d.b);
}

Status Interpreter::do_frnd(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst) {
    // FRND Rd, Rb/Sb/URb — round to integral.  Roles: [Rd, source].
    const auto& d = *static_cast<const shape::DecodedFRND2*>(&inst);
    const Rnd rnd = static_cast<Rnd>(d.rnd);
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        std::uint32_t a = read_reg_ov(t, d.b);
        const float f = std::bit_cast<float>(a);
        float r;
        switch (rnd) {
            case Rnd::kRm: r = std::floor(f); break;
            case Rnd::kRp: r = std::ceil(f); break;
            case Rnd::kRz: r = std::trunc(f); break;
            default: r = std::nearbyint(f); break;
        }
        if (fast_mode()) note_fast_leaf(false);
        write_rd_ov(w, t, d.Rd, std::bit_cast<std::uint32_t>(r), 0);
    }
    return Status::success();
}


}  // namespace semu
