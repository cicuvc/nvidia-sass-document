// sm120 baseline interpreter -- vector integer: MOV/IADD3/ISETP/IMAD, P2R/VOTE/REDUX/SHFL-, LOP3/LOP/SHF, IMNMX/ISCADD/LEA, POPC/FLO/BMSK/PRMT.
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
Status Interpreter::do_mov(WarpState& w, std::uint32_t mask,
                           const DecodedInstruction& inst, std::uint64_t pc) {
    (void)pc;
    // Move sources: MOV32I [Rd,Sb,PixMaskU04]; MOV2/3 [Rd,src].
    std::uint64_t rd = 0;
    const shape::OperandValue* src = nullptr;
    if (inst.mnemonic == isa::Mnemonic::kMOV32I) {
        const auto& d = *static_cast<const shape::DecodedMOV32I3*>(&inst);
        rd = static_cast<std::uint64_t>(shape::operand_value_as_i64(d.Rd));
        src = &d.Sb;
    } else {
        const auto& d = *static_cast<const shape::DecodedMOV2*>(&inst);
        rd = static_cast<std::uint64_t>(shape::operand_value_as_i64(d.Rd));
        src = &d.b;
    }
    const auto sk = static_cast<shape::OperandKind>(src->kind);
    // Register sources are per-lane; uniform/immediate are warp-wide.
    const std::uint32_t hoisted =
        (sk != shape::OperandKind::kRegister)
            ? src_value(w, w.threads[0], *src) : 0;
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        const std::uint32_t s =
            (sk == shape::OperandKind::kRegister)
                ? src_value(w, t, *src) : hoisted;
        if (rd != 255 && rd < kNumGprs) t.gpr[rd] = s;
    }
    return Status::success();
}


// UMOV (uniform move): URd = imm / URd = URb / URd:URd+1 = 64-bit imm.
Status Interpreter::do_iadd3(WarpState& w, std::uint32_t mask,
                             const DecodedInstruction& inst,
                             std::uint64_t pc) {
    (void)pc;
    // 6-op: [Rd,Pu,Pv,Ra,2nd,3rd]; 8-op adds [Pp,Pq] (X carry).
    const auto& d = *static_cast<const shape::DecodedIADD36*>(&inst);
    const std::uint64_t rd =
        static_cast<std::uint64_t>(shape::operand_value_as_i64(d.Rd));
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        std::uint32_t a = read_reg_ov(t, d.Ra);
        std::uint32_t b = src_value(w, t, d.b);
        std::uint32_t c = read_reg_ov(t, d.Rc);
        // read_reg_ov / src_value already apply the negate/absolute flags.
        if (rd != 255 && rd < kNumGprs) t.gpr[rd] = a + b + c;
    }
    return Status::success();
}


Status Interpreter::do_isetp(WarpState& w, std::uint32_t mask,
                             const DecodedInstruction& inst,
                             std::uint64_t pc) {
    (void)pc;
    // Layouts by variant class: 6 [Pu,Pv,Ra,2nd,Pp,Pr]; 5 [Pu,Pv,Ra,2nd,Pp];
    // 4 [Pu,Ra,2nd,Pr]; 3 [Pu,Ra,2nd].  The non-simple forms (kisetp*__*,
    // _EX/_noEX) carry Pv+Pp and bop; the simple forms do not.
    std::uint64_t icmp = 0, bop = 0;
    const bool rich =
        (inst.variant_class == isa::VariantClass::kisetp__RRR_RRR_noEX ||
         inst.variant_class == isa::VariantClass::kisetp__RUR_RUR_noEX ||
         inst.variant_class == isa::VariantClass::kisetp__RsIR_RIR_noEX ||
         inst.variant_class == isa::VariantClass::kisetp_64__RRR_RRR_noEX ||
         inst.variant_class == isa::VariantClass::kisetp_64__RUR_RUR_noEX ||
         inst.variant_class == isa::VariantClass::kisetp_64__RsIR_RIR_noEX ||
         inst.variant_class == isa::VariantClass::kisetp__RRR_RRR_EX ||
         inst.variant_class == isa::VariantClass::kisetp__RUR_RUR_EX ||
         inst.variant_class == isa::VariantClass::kisetp__RsIR_RIR_EX ||
         inst.variant_class == isa::VariantClass::kisetp_64__RRR_RRR_EX ||
         inst.variant_class == isa::VariantClass::kisetp_64__RUR_RUR_EX ||
         inst.variant_class == isa::VariantClass::kisetp_64__RsIR_RIR_EX);
    const bool ex =
        (inst.variant_class == isa::VariantClass::kisetp__RRR_RRR_EX ||
         inst.variant_class == isa::VariantClass::kisetp__RUR_RUR_EX ||
         inst.variant_class == isa::VariantClass::kisetp__RsIR_RIR_EX ||
         inst.variant_class == isa::VariantClass::kisetp_64__RRR_RRR_EX ||
         inst.variant_class == isa::VariantClass::kisetp_64__RUR_RUR_EX ||
         inst.variant_class == isa::VariantClass::kisetp_64__RsIR_RIR_EX);
    const shape::OperandValue* pu = nullptr;
    const shape::OperandValue* pv = nullptr;
    const shape::OperandValue* ra = nullptr;
    const shape::OperandValue* second = nullptr;
    const shape::OperandValue* pp = nullptr;
    if (rich) {
        if (ex) {
            const auto& d = *static_cast<const shape::DecodedISETP6*>(&inst);
            pu = &d.Pu; pv = &d.Pv; ra = &d.Ra; second = &d.b; pp = &d.Pp;
            icmp = static_cast<std::uint64_t>(d.icmp);
            bop = static_cast<std::uint64_t>(d.bop);
        } else {
            const auto& d = *static_cast<const shape::DecodedISETP5*>(&inst);
            pu = &d.Pu; pv = &d.Pv; ra = &d.Ra; second = &d.b; pp = &d.Pp;
            icmp = static_cast<std::uint64_t>(d.icmp);
            bop = static_cast<std::uint64_t>(d.bop);
        }
    } else {
        if (ex) {
            const auto& d = *static_cast<const shape::DecodedISETP4*>(&inst);
            pu = &d.Pu; ra = &d.Ra; second = &d.b;
            icmp = static_cast<std::uint64_t>(d.icmp);
        } else {
            const auto& d = *static_cast<const shape::DecodedISETP3*>(&inst);
            pu = &d.Pu; ra = &d.Ra; second = &d.b;
            icmp = static_cast<std::uint64_t>(d.icmp);
        }
    }
    const int pnum = static_cast<int>(shape::operand_value_as_i64(*pu));
    const auto pv_v = rich ? shape::operand_value_as_i64(*pv) : 0;
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        std::uint32_t a = read_reg_ov(t, *ra);
        std::uint32_t b = src_value(w, t, *second);
        bool r = false;
        switch (icmp) {
            case 0: r = false; break;  // F
            case 1: r = a < b; break;
            case 2: r = a == b; break;
            case 3: r = a <= b; break;
            case 4: r = a > b; break;
            case 5: r = a != b; break;
            case 6: r = a >= b; break;
            case 7: r = true; break;   // T
            default: r = false; break;
        }
        // Bop combines the comparison with Pp (AND/OR/XOR).
        bool ppv = true;
        if (rich) read_pred_ov(t, *pp, &ppv);
        switch (bop) {
            case 0: r = r && ppv; break;
            case 1: r = r || ppv; break;
            case 2: r = r != ppv; break;
            default: break;
        }
        if (pnum < 7) t.pred[static_cast<std::size_t>(pnum)] = r;
        if (rich && pv_v < 7)
            t.pred[static_cast<std::size_t>(pv_v)] = !r;
    }
    return Status::success();
}

Status Interpreter::do_imad(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst,
                            std::uint64_t pc,
                            std::optional<Fault>* fault) {
    (void)pc;
    // Layouts by variant class: plain kimad__* (4-op), kimad_*_x/...x_pseudo
    // (5-op .X), kimad_wide__/kimad_hi__ (5-op with Pu; IMAD5 splits), the
    // IMAD5 getpseudo forms (GetPseudoOp tail), and kimad_wide_x/hi_x (6-op).
    const isa::VariantClass cls = inst.variant_class;
    std::uint64_t fmt = 1;
    std::uint8_t subclass = 0;
    // Named roles (family names): Rd always first; the source roles are
    // a/b/c with conventional family names per split (Ra, b|Sb|Rb, c|Rc).
    const shape::OperandValue* rd_op = nullptr;
    const shape::OperandValue* a_op = nullptr;
    const shape::OperandValue* b_op = nullptr;
    const shape::OperandValue* c_op = nullptr;
    if (cls == isa::VariantClass::kimad__RRR_RRR ||
        cls == isa::VariantClass::kimad__RRU_RRU ||
        cls == isa::VariantClass::kimad__RRsI_RRI ||
        cls == isa::VariantClass::kimad__RUR_RUR ||
        cls == isa::VariantClass::kimad__RsIR_RIR ||
        cls == isa::VariantClass::kimad_pseudo__RRU_RRU ||
        cls == isa::VariantClass::kimad_pseudo__RUR_RUR) {
        const auto& d = *static_cast<const shape::DecodedIMAD4*>(&inst);
        fmt = static_cast<std::uint64_t>(d.fmt);
        subclass = d.subclass;
        rd_op = &d.Rd; a_op = &d.Ra; b_op = &d.b; c_op = &d.c;
    } else if (cls == isa::VariantClass::kimad_wide_x__RRR_RRR ||
               cls == isa::VariantClass::kimad_wide_x__RRU_RRU ||
               cls == isa::VariantClass::kimad_wide_x__RUR_RUR ||
               cls == isa::VariantClass::kimad_wide_x__RsIR_RIR ||
               cls == isa::VariantClass::kimad_hi_x__RRR_RRR ||
               cls == isa::VariantClass::kimad_hi_x__RRU_RRU ||
               cls == isa::VariantClass::kimad_hi_x__RUR_RUR ||
               cls == isa::VariantClass::kimad_hi_x__RsIR_RIR) {
        const auto& d = *static_cast<const shape::DecodedIMAD6*>(&inst);
        fmt = static_cast<std::uint64_t>(d.fmt);
        subclass = d.subclass;
        rd_op = &d.Rd; a_op = &d.Ra; b_op = &d.b; c_op = &d.c;  // [Rd,Pu,Ra,b,c,Pp]
    } else if (cls == isa::VariantClass::kimad_pseudo__RsIR_RIR) {
        const auto& d = *static_cast<const shape::DecodedIMAD5_1*>(&inst);
        fmt = static_cast<std::uint64_t>(d.fmt);
        subclass = d.subclass;
        rd_op = &d.Rd; a_op = &d.Ra; b_op = &d.Sb; c_op = &d.Rc;
    } else if (cls == isa::VariantClass::kimad_pseudo__RRsI_RRI) {
        const auto& d = *static_cast<const shape::DecodedIMAD5_2*>(&inst);
        fmt = static_cast<std::uint64_t>(d.fmt);
        subclass = d.subclass;
        rd_op = &d.Rd; a_op = &d.Ra; b_op = &d.Rb;  // no third-source role
    } else if (cls == isa::VariantClass::kimad_pseudo__RRR_RRR) {
        const auto& d = *static_cast<const shape::DecodedIMAD5_3*>(&inst);
        fmt = static_cast<std::uint64_t>(d.fmt);
        subclass = d.subclass;
        rd_op = &d.Rd; a_op = &d.Ra; b_op = &d.Rb; c_op = &d.Rc;
    } else if (cls == isa::VariantClass::kimad_x__RRR_RRR ||
               cls == isa::VariantClass::kimad_x__RRU_RRU ||
               cls == isa::VariantClass::kimad_x__RRsI_RRI ||
               cls == isa::VariantClass::kimad_x__RUR_RUR ||
               cls == isa::VariantClass::kimad_x__RsIR_RIR ||
               cls == isa::VariantClass::kimad_x_pseudo__RRR_RRR ||
               cls == isa::VariantClass::kimad_x_pseudo__RRU_RRU ||
               cls == isa::VariantClass::kimad_x_pseudo__RRsI_RRI ||
               cls == isa::VariantClass::kimad_x_pseudo__RUR_RUR ||
               cls == isa::VariantClass::kimad_x_pseudo__RsIR_RIR) {
        const auto& d = *static_cast<const shape::DecodedIMAD5_4*>(&inst);
        fmt = static_cast<std::uint64_t>(d.fmt);
        subclass = d.subclass;
        rd_op = &d.Rd; a_op = &d.Ra; b_op = &d.b; c_op = &d.c;  // [Rd,Ra,b,c,Pp]
    } else {  // kimad_wide__* / kimgad_hi__* (+ *_pseudo): IMAD5 split 0
        const auto& d = *static_cast<const shape::DecodedIMAD5_0*>(&inst);
        fmt = static_cast<std::uint64_t>(d.fmt);
        subclass = d.subclass;
        rd_op = &d.Rd; a_op = &d.Ra; b_op = &d.b; c_op = &d.c;
    }
const std::uint64_t rd =
        static_cast<std::uint64_t>(shape::operand_value_as_i64(*rd_op));
    // The WIDE/HI distinction lives in the generated subclass flags.
    const bool is_wide = (subclass & 2) != 0;
    const bool is_hi = (subclass & 4) != 0;
    // The X-extended forms (IMAD.X / IMAD.WIDE.X / IMAD.HI.X) add carry-in
    // (from the [!]Pp predicate) and carry-out (to Pu) semantics that Phase 5
    // does not implement or verify.  Degrade them explicitly to unsupported
    // instead of silently computing a carry-less result.
    const bool is_x = (subclass & 1) != 0;
    if (is_x) {
        Fault f(FaultKind::kUnsupportedInstruction,
                "instruction '" + std::string(isa::mnemonic_name(inst.mnemonic)) + "' (" + std::string(isa::variant_class_name(inst.variant_class)) +
                    ") X carry form is not implemented at pc " +
                    std::to_string(pc));
        f.set_warp(static_cast<std::uint32_t>(w.warp_id)).set_pc(pc)
            .set_active_mask(mask).set_instruction(inst.word);
        if (fault) *fault = std::move(f);
        return Status::failure(Error::internal("interpreter fault"));
    }
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        if (is_wide) {
            // 64-bit multiply-accumulate.
            //   IMAD.WIDE: {Rd+1,Rd} = Ra*Rb + {Rc,Rc+1}  (full 64-bit)
            //   IMAD.HI:   Rd = high32(Ra*Rb + {Rc,Rc+1})
            // Ra/Rb are 32-bit; Rc is a full 64-bit register pair that is
            // used verbatim (its high half is already the 64-bit value; we
            // must NOT re-sign-extend from the low half's bit 31).
            const std::uint32_t au = read_reg_ov(t, *a_op);
            const std::uint32_t bu = src_value(w, t, *b_op);
            const bool sign = fmt != 0;
            // 32x32 -> 64-bit product bit pattern.  Signed mode sign-extends
            // the two 32-bit inputs to int64; |int32|^2 <= 2^62 so the int64
            // product never overflows.  Unsigned mode uses uint64 widths.
            std::uint64_t prod;
            if (sign) {
                const std::int64_t as = static_cast<std::int32_t>(au);
                const std::int64_t bs = static_cast<std::int32_t>(bu);
                prod = static_cast<std::uint64_t>(as * bs);
            } else {
                prod = static_cast<std::uint64_t>(au) *
                       static_cast<std::uint64_t>(bu);
            }
            std::uint64_t c = 0;
            if (c_op) {
                const auto ck = static_cast<shape::OperandKind>(c_op->kind);
                if (ck == shape::OperandKind::kRegister) {
                    const std::uint64_t r = static_cast<std::uint64_t>(
                        shape::operand_value_as_i64(*c_op));
                    if (r != 255 && r < kNumGprs - 1) {
                        c = t.gpr[r] |
                            (static_cast<std::uint64_t>(t.gpr[r + 1]) << 32);
                    }
                }
            }
            // Modular 64-bit addition (no signed-overflow UB).
            const std::uint64_t out = prod + c;
            if (rd == 255 || rd >= kNumGprs) continue;
            if (is_hi) {
                t.gpr[rd] = static_cast<std::uint32_t>(out >> 32);
            } else {  // IMAD.WIDE / IMAD.WIDE.X
                if (rd + 1 >= kNumGprs) continue;
                t.gpr[rd] = static_cast<std::uint32_t>(out & 0xffffffffu);
                t.gpr[rd + 1] = static_cast<std::uint32_t>(out >> 32);
            }
            continue;
        }
        std::uint32_t a = read_reg_ov(t, *a_op);
        std::uint32_t b = src_value(w, t, *b_op);
        std::uint32_t c = c_op ? read_reg_ov(t, *c_op) : 0;
        // IMAD.MOV: Ra=RZ -> just move c.
        if (shape::operand_value_as_i64(*a_op) == 255) {
            if (rd != 255 && rd < kNumGprs) t.gpr[rd] = c;
        } else {
            if (rd != 255 && rd < kNumGprs) t.gpr[rd] = a * b + c;
        }
    }
    return Status::success();
}

// ---------------------------------------------------------------------------
// Phase 5 compute handlers (integer/bit, FP, conversions, compares,
// collectives).  Dispatch is keyed on the decoded mnemonic because several
// encodings share an opcode (LOP3/LOP, ISCADD/LEA).
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Phase 6 memory + sync
// ---------------------------------------------------------------------------

// Decode the `sz` slot for LDS (LDSSIZE enum) and LDG/STS/LDC/LDL/STL
// (SZ_U8_S8_U16_S16_32_64_128).  Returns the MemWidthInfo.

Status Interpreter::do_p2r(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst) {
    // P2R[.B0/.B1/.B2/.B3] Rd, PR, Ra, Sb — pack predicates into Rd.
    // Roles: [Rd, Pr, Ra, 2nd].
    const auto& d = *static_cast<const shape::DecodedP2R4*>(&inst);
    const std::uint64_t insert = static_cast<std::uint64_t>(d.insert);
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        std::uint32_t base = read_reg_ov(t, d.Ra);
        std::uint32_t sel = src_value(w, t, d.b);
        std::uint32_t out = base;
        const unsigned shift = static_cast<unsigned>(8 * (insert & 3));
        for (int i = 0; i < 8; ++i) {
            if (!(sel & (1u << i))) continue;
            const bool pv = (i == 7) ? true : t.pred[i];  // P7 = PT
            const std::uint32_t bit = 1u << (i + shift);
            if (pv) out |= bit;
            else out &= ~bit;
        }
        write_rd_ov(w, t, d.Rd, out, 0);
    }
    return Status::success();
}


Status Interpreter::do_vote(WarpState& w, std::uint32_t mask,
                             const DecodedInstruction& inst) {
    // VOTE.op Rd, Pu, Pp — warp-wide reduction of Pp into Rd (bitmask),
    // Pu = result predicate (per-lane).  Roles: [Rd, Pu, Pp].
    const auto& d = *static_cast<const shape::DecodedVOTE3*>(&inst);
    const std::uint64_t op = static_cast<std::uint64_t>(d.voteop);
    // Build the warp mask of Pp over all ACTIVE lanes.
    std::uint32_t all = 0;
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        const ThreadState& t = w.threads[lane];
        bool p = false;
        read_pred_ov(t, d.Pp, &p);
        if (p) all |= (1u << lane);
    }
    const int pop = __builtin_popcount(all);
    const bool result = (op == 0) ? (pop == __builtin_popcount(mask))
        : (op == 1) ? (pop != 0)
        : (pop == __builtin_popcount(mask) || pop == 0);  // EQ
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        write_pred_ov(t, d.Pu, result);
        write_rd_ov(w, t, d.Rd, all, 0);
    }
    return Status::success();
}


Status Interpreter::do_redux(WarpState& w, std::uint32_t mask,
                             const DecodedInstruction& inst) {
    // REDUX.op.sz URd, Ra — reduce active-lane Ra values into URd.
    const auto& d = *static_cast<const shape::DecodedREDUX2*>(&inst);
    const std::uint64_t op = static_cast<std::uint64_t>(d.op);
    bool first = true;
    std::uint32_t acc = 0;
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        const ThreadState& t = w.threads[lane];
        const std::uint32_t v = read_reg_ov(t, d.Ra);
        if (first) { acc = v; first = false; }
        else {
            switch (op) {
                case 0: acc &= v; break;  // AND
                case 1: acc |= v; break;  // OR
                case 2: acc ^= v; break;  // XOR
                case 4: acc = (v < acc) ? v : acc; break;  // MIN
                case 5: acc = (v > acc) ? v : acc; break;  // MAX
                default: acc += v; break;  // SUM
            }
        }
    }
    if (!first) {
        const std::uint64_t r =
            static_cast<std::uint64_t>(shape::operand_value_as_i64(d.URd));
        if (r < kNumUrs) w.ur[r] = acc;
    }
    return Status::success();
}


Status Interpreter::lut_core(WarpState& w, std::uint32_t mask,
                             std::uint32_t lut,
                             const shape::OperandValue& rd,
                             const shape::OperandValue& ra,
                             const shape::OperandValue& b,
                             const shape::OperandValue* c3) {
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        std::uint32_t a = read_reg_ov(t, ra);
        std::uint32_t bv = src_value(w, t, b);
        // LOP (2-input) has no third source; LOP3 passes Rc via c3.
        const std::uint32_t c = c3 ? read_reg_ov(t, *c3) : 0;
        std::uint32_t out = 0;
        // LOP3 truth-table: bit i = output for input (a,b,c) with a as
        // the index MSB (verified: lut 0xC0 = a&b = bits 6,7).  Index =
        // (a<<2)|(b<<1)|(c<<0).
        for (int bit = 0; bit < 32; ++bit) {
            const int idx = (((a >> bit) & 1) << 2) |
                            (((bv >> bit) & 1) << 1) |
                            ((c >> bit) & 1);
            if ((lut >> idx) & 1) out |= (1u << bit);
        }
        write_rd_ov(w, t, rd, out, 0);
    }
    return Status::success();
}

Status Interpreter::do_lop3(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst) {
    // LOP3 Rd, Ra, Rb/Sb, Rc, imm8 — 3-input logic with 8-bit LUT.  The LUT
    // forms carry imm8; the no-LUT forms put Pp (and 5-op has no tail).
    // The shape selects the concrete struct and its named fields.
    std::uint32_t lut = 0;
    const shape::OperandValue* rd = nullptr;
    const shape::OperandValue* ra = nullptr;
    const shape::OperandValue* b = nullptr;
    const shape::OperandValue* c = nullptr;
    if (inst.variant_class == isa::VariantClass::klop3_lut__RRR_RRR ||
        inst.variant_class == isa::VariantClass::klop3_lut__RUR_RUR ||
        inst.variant_class == isa::VariantClass::klop3_lut__RuIR_RIR) {
        const auto& d = *static_cast<const shape::DecodedLOP37*>(&inst);
        lut = static_cast<std::uint32_t>(shape::operand_value_as_i64(d.imm8));
        return lut_core(w, mask, lut, d.Rd, d.Ra, d.b, &d.Rc);
    }
    if (inst.variant_class == isa::VariantClass::klop3_lut_optionalPp__RRR_RRR ||
        inst.variant_class == isa::VariantClass::klop3_lut_optionalPp__RUR_RUR ||
        inst.variant_class == isa::VariantClass::klop3_lut_optionalPp__RuIR_RIR) {
        const auto& d = *static_cast<const shape::DecodedLOP36_1*>(&inst);
        lut = static_cast<std::uint32_t>(shape::operand_value_as_i64(d.imm8));
        return lut_core(w, mask, lut, d.Rd, d.Ra, d.b, &d.Rc);
    }
    (void)rd; (void)ra; (void)b; (void)c;
    // 5/6-op no-LUT and 5-op: base register layout only (no LUT table).
    const auto& d = *static_cast<const shape::DecodedLOP35*>(&inst);
    return lut_core(w, mask, lut, d.Rd, d.Ra, d.b, nullptr);
}

Status Interpreter::do_lop(WarpState& w, std::uint32_t mask,
                           const DecodedInstruction& inst) {
    // LOP  Rd, Ra, Rb/Sb — AND/OR/XOR/PASS_B (2-input op mapped to the
    // matching 3-input truth table with Rc=0): AND=0x80, OR=0xfe,
    // XOR=0x96, PASS_B=0xcc.
    std::uint64_t lop = 0;
    // 5-op forms (klop_imm_ / klop_noimm__*) vs 4-op optional-Pp forms.
    const shape::DecodedLOP5* d5 = nullptr;
    const shape::DecodedLOP4* d4 = nullptr;
    if (inst.variant_class == isa::VariantClass::klop_imm_ ||
        inst.variant_class == isa::VariantClass::klop_noimm__RRR_RRR ||
        inst.variant_class == isa::VariantClass::klop_noimm__RUR_RUR) {
        d5 = static_cast<const shape::DecodedLOP5*>(&inst);
        lop = static_cast<std::uint64_t>(d5->lop);
    } else {
        d4 = static_cast<const shape::DecodedLOP4*>(&inst);
        lop = static_cast<std::uint64_t>(d4->lop);
    }
    (void)d4; (void)d5;
    
    std::uint32_t lut = 0;
    switch (lop) {
        case 0: lut = 0x80; break;  // AND
        case 1: lut = 0xfe; break;  // OR
        case 2: lut = 0x96; break;  // XOR
        case 3: lut = 0xcc; break;  // PASS_B
        default: break;
    }
    if (d5) return lut_core(w, mask, lut, d5->Rd, d5->Ra, d5->b, nullptr);
    return lut_core(w, mask, lut, d4->Rd, d4->Ra, d4->b, nullptr);
}

Status Interpreter::do_shf(WarpState& w, std::uint32_t mask,
                           const DecodedInstruction& inst) {
    // SHF.L/.R Rd, Ra, 2nd, 3rd (shift count = 2nd & 0x1f).  hilo selects
    // which register holds the value being shifted; dir the direction.
    const auto& d = *static_cast<const shape::DecodedSHF4*>(&inst);
    const std::uint64_t dir = static_cast<std::uint64_t>(d.dir);
    const std::uint64_t hilo = static_cast<std::uint64_t>(d.hilo);
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        std::uint32_t a = read_reg_ov(t, d.Ra);
        std::uint32_t b = src_value(w, t, d.b);
        std::uint32_t c = read_reg_ov(t, d.c);
        const unsigned sh = b & 0x1f;
        std::uint32_t out;
        if (dir == 0) {  // L
            if (hilo == 0) {
                out = (sh == 0) ? a : (a << sh);
            } else {
                out = (sh == 0) ? c : ((c << sh) | (a >> (32 - sh)));
            }
        } else {  // R
            if (hilo == 0) {
                out = (sh == 0) ? a : ((c << (32 - sh)) | (a >> sh));
            } else {
                out = (sh == 0) ? c : (c >> sh);
            }
        }
        write_rd_ov(w, t, d.Rd, out, 0);
    }
    return Status::success();
}


Status Interpreter::do_iabs(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst) {
    const auto& d = *static_cast<const shape::DecodedIABS2*>(&inst);
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        std::uint32_t b = src_value(w, t, d.b);
        const std::uint32_t out = (b & 0x80000000u)
            ? ((b == 0x80000000u) ? b : (~b + 1)) : b;
        write_rd_ov(w, t, d.Rd, out, 0);
    }
    return Status::success();
}


Status Interpreter::do_imnmx(WarpState& w, std::uint32_t mask,
                             const DecodedInstruction& inst) {
    // IMNMX Rd, Ra, 2nd, Pp — signed min/max (Pp: PT=min, !PT=max).
    // Roles: [Pu, Pv, Rd, Ra, 2nd, Pp(, Pq)].
    // 7-op (with Pq) = the non-"nopred" IMNMX classes.
    const bool has_pq =
        inst.variant_class == isa::VariantClass::kimnmx_64__RRR_RRR ||
        inst.variant_class == isa::VariantClass::kimnmx__RRR_RRR ||
        inst.variant_class == isa::VariantClass::kimnmx_64__RIR_RsIR ||
        inst.variant_class == isa::VariantClass::kimnmx__RIR_RsIR ||
        inst.variant_class == isa::VariantClass::kimnmx_64__RUR_RUR ||
        inst.variant_class == isa::VariantClass::kimnmx__RUR_RUR;
    const shape::OperandValue* rd = nullptr;
    const shape::OperandValue* ra = nullptr;
    const shape::OperandValue* b = nullptr;
    const shape::OperandValue* pp = nullptr;
    if (has_pq) {
        const auto& d = *static_cast<const shape::DecodedIMNMX7*>(&inst);
        rd = &d.Rd; ra = &d.Ra; b = &d.b; pp = &d.Pp;
    } else {
        const auto& d = *static_cast<const shape::DecodedIMNMX6*>(&inst);
        rd = &d.Rd; ra = &d.Ra; b = &d.b; pp = &d.Pp;
    }
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        std::int32_t a = static_cast<std::int32_t>(read_reg_ov(t, *ra));
        std::int32_t bv = static_cast<std::int32_t>(src_value(w, t, *b));
        bool do_min = true;
        read_pred_ov(t, *pp, &do_min);
        std::int32_t out = do_min ? (a < bv ? a : bv) : (a > bv ? a : bv);
        write_rd_ov(w, t, *rd, static_cast<std::uint32_t>(out), 0);
    }
    return Status::success();
}


Status Interpreter::do_iscadd(WarpState& w, std::uint32_t mask,
                              const DecodedInstruction& inst) {
    // ISCADD Rd, Pu, Ra, 2nd, scaleU5 — (Ra + (2nd << scaleU5)).
    // Roles: [Rd, Pu, Ra, 2nd, scaleU5].
    const auto& d = *static_cast<const shape::DecodedISCADD5*>(&inst);
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        std::uint32_t a = read_reg_ov(t, d.Ra);
        std::uint32_t b = src_value(w, t, d.b);
        const unsigned sh = static_cast<unsigned>(
            shape::operand_value_as_i64(d.scaleU5) & 0x1f);
        write_rd_ov(w, t, d.Rd, a + (b << sh), 0);
    }
    return Status::success();
}


Status Interpreter::do_lea(WarpState& w, std::uint32_t mask,
                           const DecodedInstruction& inst) {
    // LEA[.HI][.X] Rd, Pu, Ra, 2nd, [Rc,] scaleU5(, Pp).
    //   LO: Rd = low32((Ra << N) + 2nd)
    //   HI: Rd = high32((Ra << N) + 2nd + Rc)
    // Layouts (by variant class): 5-op [Rd,Pu,Ra,2nd,scaleU5] (klea_*_imm/
    // noimm non-x, scaleU5@4, no Rc); 6-op +Rc|scaleU5 or x-form Pp
    // (LEA6 split 0 = non-x @5, 1 = x-form @4); 7-op +Pp (scaleU5@5).
    std::uint64_t hilo = 0;
    const shape::OperandValue* rd_op = nullptr;
    const shape::OperandValue* ra_op = nullptr;
    const shape::OperandValue* b_op = nullptr;   // the 2nd operand (src_value)
    const shape::OperandValue* c_op = nullptr;   // null => no Rc role
    const shape::OperandValue* scale_op = nullptr;
    if (inst.variant_class == isa::VariantClass::klea_hi_imm_sx32__RuIR_RIR ||
        inst.variant_class == isa::VariantClass::klea_hi_noimm_sx32__RRR_RRR ||
        inst.variant_class == isa::VariantClass::klea_hi_noimm_sx32__RUR_RUR ||
        inst.variant_class == isa::VariantClass::klea_lo_imm__RuIR_RIR ||
        inst.variant_class == isa::VariantClass::klea_lo_noimm__RRR_RRR ||
        inst.variant_class == isa::VariantClass::klea_lo_noimm__RUR_RUR) {
        const auto& d = *static_cast<const shape::DecodedLEA5*>(&inst);
        hilo = static_cast<std::uint64_t>(d.hilo);
        rd_op = &d.Rd; ra_op = &d.Ra;
        b_op = &d.b; c_op = nullptr; scale_op = &d.scaleU5;
    } else if (inst.variant_class == isa::VariantClass::klea_hi_noimm__RRR_RRR ||
               inst.variant_class == isa::VariantClass::klea_hi_noimm__RUR_RUR ||
               inst.variant_class == isa::VariantClass::klea_hi_imm__RRuI_RRI ||
               inst.variant_class == isa::VariantClass::klea_hi_imm__RuIR_RIR) {
        // 6-op non-x (LEA6 split 0): [..,Rc,scaleU5].
        const auto& d = *static_cast<const shape::DecodedLEA6_0*>(&inst);
        hilo = static_cast<std::uint64_t>(d.hilo);
        rd_op = &d.Rd; ra_op = &d.Ra;
        b_op = &d.b; c_op = &d.c; scale_op = &d.scaleU5;
    } else if (inst.variant_class == isa::VariantClass::klea_hi_noimm_sx32_x__RRR_RRR ||
               inst.variant_class == isa::VariantClass::klea_hi_noimm_sx32_x__RUR_RUR ||
               inst.variant_class == isa::VariantClass::klea_hi_imm_sx32_x__RuIR_RIR ||
               inst.variant_class == isa::VariantClass::klea_lo_imm_x__RuIR_RIR ||
               inst.variant_class == isa::VariantClass::klea_lo_noimm_x__RRR_RRR ||
               inst.variant_class == isa::VariantClass::klea_lo_noimm_x__RUR_RUR) {
        // 6-op x-form (LEA6 split 1): [..,scaleU5,Pp], no Rc.
        const auto& d = *static_cast<const shape::DecodedLEA6_1*>(&inst);
        hilo = static_cast<std::uint64_t>(d.hilo);
        rd_op = &d.Rd; ra_op = &d.Ra;
        b_op = &d.b; c_op = nullptr; scale_op = &d.scaleU5;
    } else {
        // 7-op +Pp: [..,Rc,scaleU5,Pp].
        const auto& d = *static_cast<const shape::DecodedLEA7*>(&inst);
        hilo = static_cast<std::uint64_t>(d.hilo);
        rd_op = &d.Rd; ra_op = &d.Ra;
        b_op = &d.b; c_op = &d.c; scale_op = &d.scaleU5;
    }
    const std::uint64_t scale_v =
        static_cast<std::uint64_t>(shape::operand_value_as_i64(*scale_op));
    const unsigned sh = static_cast<unsigned>(scale_v & 0x1f);
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        std::uint32_t a = read_reg_ov(t, *ra_op);
        std::uint32_t b = src_value(w, t, *b_op);
        std::uint32_t c = c_op ? read_reg_ov(t, *c_op) : 0;
        const std::uint64_t sum = (static_cast<std::uint64_t>(a) << sh) +
                                  b + (hilo ? c : 0);
        const std::uint32_t out = (hilo == 0)
            ? static_cast<std::uint32_t>(sum & 0xffffffffu)
            : static_cast<std::uint32_t>(sum >> 32);
        write_rd_ov(w, t, *rd_op, out, 0);
    }
    return Status::success();
}

Status Interpreter::bitops_core(WarpState& w, std::uint32_t mask,
                                std::uint64_t cw, int mode,
                                const shape::OperandValue& rd,
                                const shape::OperandValue& a,
                                const shape::OperandValue* b,
                                const shape::OperandValue* c3) {
    // mode: 0=POPC 1=FLO 2=BMSK 3=PRMT (op positionally identified).
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        std::uint32_t av = read_reg_ov(t, a);
        std::uint32_t bv = b ? src_value(w, t, *b) : 0;
        std::uint32_t out = 0;
        if (mode == 0) {  // POPC
            out = static_cast<std::uint32_t>(__builtin_popcount(av));
        } else if (mode == 1) {  // FLO
            // FLO = find leading one (like __builtin_clz on the first
            // set bit).  Returns 0xffffffff when input is 0.
            out = (av == 0) ? 0xffffffffu
                : static_cast<std::uint32_t>(31 - __builtin_clz(av));
        } else if (mode == 2) {  // BMSK
            // BMSK[.C/.W] Rd, Ra, Rb: Ra = POSITION, Rb = WIDTH.
            //   Rd = ((1 << width) - 1) << pos (truncated to 32 bits).
            //   .C (clamp, default): pos>=32 -> 0; width>=32 -> all bits
            //      below pos (natural 32-bit truncation).
            //   .W (wrap): pos & 31 and width & 31 first.
            std::uint32_t pos = av;
            std::uint32_t width = bv;
            const bool wrap = cw != 0;
            if (wrap) {
                pos &= 31;
                width &= 31;
            }
            if (pos >= 32) {
                out = 0;  // .C: position out of range -> 0
            } else if (width == 0) {
                out = 0;
            } else if (width >= 32) {
                // all bits below pos (for pos=0 -> 0xFFFFFFFF).
                out = ~0u << pos;
            } else {
                out = ((1u << width) - 1u) << pos;
            }
        } else {  // PRMT
            // PRMT Rd, Ra, 2nd(sel), 3rd — byte permute.  sel[2:0]=src
            // byte, sel[3]=zero/upper, sel[7:4] ignored.  (test_prmt.)
            const std::uint32_t sel = src_value(w, t, *b);
            const std::uint32_t srcb = read_reg_ov(t, *c3);
            for (int i = 0; i < 4; ++i) {
                const unsigned c = (sel >> (4 * i)) & 0xf;
                if (c & 8) {
                    out |= ((c & 4) ? 0xffu : 0u) << (8 * i);
                } else {
                    const unsigned by = (c & 3) * 8;
                    out |= ((av >> by) & 0xff) << (8 * i);
                }
            }
            (void)srcb;
        }
        write_rd_ov(w, t, rd, out, 0);
    }
    return Status::success();
}

Status Interpreter::do_popc(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst) {
    // POPC [Rd,src].
    const auto& d = *static_cast<const shape::DecodedPOPC2*>(&inst);
    return bitops_core(w, mask, 0, 0, d.Rd, d.b, nullptr, nullptr);
}

Status Interpreter::do_flo(WarpState& w, std::uint32_t mask,
                           const DecodedInstruction& inst) {
    // FLO [Rd,Pu,src].
    const auto& d = *static_cast<const shape::DecodedFLO3*>(&inst);
    return bitops_core(w, mask, 0, 1, d.Rd, d.b, nullptr, nullptr);
}

Status Interpreter::do_bmsk(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst) {
    // BMSK [Rd,Ra,2nd].
    const auto& d = *static_cast<const shape::DecodedBMSK3*>(&inst);
    return bitops_core(w, mask, static_cast<std::uint64_t>(d.cw), 2,
                       d.Rd, d.Ra, &d.b, nullptr);
}

Status Interpreter::do_prmt(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst) {
    // PRMT [Rd,Ra,2nd,3rd].
    const auto& d = *static_cast<const shape::DecodedPRMT4*>(&inst);
    return bitops_core(w, mask, 0, 3, d.Rd, d.Ra, &d.b, &d.c);
}

}  // namespace semu
