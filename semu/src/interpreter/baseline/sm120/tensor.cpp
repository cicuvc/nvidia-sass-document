// sm120 baseline interpreter -- tensor core: HMMA/QMMA/OMMA (decode-only boundary).
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
Status Interpreter::tensor_unsupported(const WarpState& w,
                                       const DecodedInstruction& inst,
                                       std::uint64_t pc, std::uint32_t mask,
                                       std::optional<Fault>* fault,
                                       const std::string& why) {
    Fault f(FaultKind::kUnsupportedInstruction,
            "instruction '" + std::string(isa::mnemonic_name(inst.mnemonic)) +
                "' (" +
                std::string(isa::variant_class_name(inst.variant_class)) +
                ") " + why +
                " is decode-only (not implemented) at pc 0x" +
                std::to_string(pc));
    f.set_warp(static_cast<std::uint32_t>(w.warp_id))
        .set_pc(pc)
        .set_active_mask(mask)
        .set_instruction(inst.word);
    if (fault) *fault = std::move(f);
    return Status::failure(Error::internal("interpreter fault"));
}

// Shared per-lane fragment execution: reads the A/B/C fragment register
// groups, runs the dense kernel for `mode`, writes the D group.
Status Interpreter::tensor_lane_core(WarpState& w, std::uint32_t mask,
                                     const DecodedInstruction& inst,
                                     std::uint64_t pc,
                                     std::optional<Fault>* fault,
                                     const tensor::Shape& shape,
                                     tensor::Format fmt, bool need_uri,
                                     bool has_re, bool has_rh, int mode,
                                     const shape::OperandValue& rd,
                                     const shape::OperandValue& ra,
                                     const shape::OperandValue& rb,
                                     const shape::OperandValue& rc,
                                     const shape::OperandValue* re,
                                     const shape::OperandValue* rh,
                                     const shape::OperandValue* uri) {
    const std::int64_t rd_v = shape::operand_value_as_i64(rd);
    const std::int64_t ra_v = shape::operand_value_as_i64(ra);
    const std::int64_t rb_v = shape::operand_value_as_i64(rb);
    const std::int64_t rc_v = shape::operand_value_as_i64(rc);

    // OMMA selection register: only sel=0 is verified legal on SM120.
    if (need_uri) {
        const std::uint32_t sel = read_ur_ov(w, *uri);  // URZ (255) reads 0
        if (sel != 0) {
            Fault f(FaultKind::kUnsupportedInstruction,
                    "OMMA.SF selector URi != 0 is decode-only (only sel=0 is "
                    "verified legal on SM120)");
            f.set_warp(static_cast<std::uint32_t>(w.warp_id)).set_pc(pc)
                .set_active_mask(mask).set_instruction(inst.word);
            if (fault) *fault = std::move(f);
            return Status::failure(Error::internal("interpreter fault"));
        }
    }

    // Fragment register base indices (RZ reads as 0; base + width must stay in
    // range per the CONDITIONS — a misaligned/overflowing group already
    // decodes as OOR_REG_ERROR / MISALIGNED_REG_ERROR in the decoder).
    const int rd_base = static_cast<int>(rd_v);
    const int ra_base = static_cast<int>(ra_v);
    const int rb_base = static_cast<int>(rb_v);
    const int rc_base = static_cast<int>(rc_v);

    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;

        std::uint32_t a[8] = {0}, b[4] = {0}, c[4] = {0};
        for (int i = 0; i < shape.regs_a; ++i) {
            const int r = ra_base + i;
            a[i] = (ra_base == 255 || r >= kNumGprs) ? 0 : t.gpr[r];
        }
        for (int i = 0; i < shape.regs_b; ++i) {
            const int r = rb_base + i;
            b[i] = (rb_base == 255 || r >= kNumGprs) ? 0 : t.gpr[r];
        }
        for (int i = 0; i < shape.regs_c; ++i) {
            const int r = rc_base + i;
            c[i] = (rc_base == 255 || r >= kNumGprs) ? 0 : t.gpr[r];
        }

        std::uint32_t out[4] = {0};
        if (mode == 0) {  // HMMA
            if (shape.k == 16) {
                tensor::hmma_k16(a, b, c, fmt, out);
            } else {
                tensor::hmma_k8(a, b, c, fmt, out);
            }
        } else if (mode == 1) {  // QMMA
            if (shape.k == 32) {
                tensor::qmma_k32(a, b, c, fmt, out);
            } else {
                tensor::qmma_k16(a, b, c, fmt, out);
            }
        } else {  // OMMA (mxfp4 block-scaled)
            if (!has_re || !has_rh)
                return tensor_unsupported(w, inst, pc, mask, fault,
                                          "(missing Re/Rh)");
            const std::uint32_t re_v = read_reg_ov(t, *re);
            const std::uint32_t rh_v = read_reg_ov(t, *rh);
            const std::uint32_t sel = 0;  // validated above
            tensor::omma_k64(a, b, c, re_v, rh_v, sel, out);
        }

        for (int i = 0; i < 4; ++i) {
            const int r = rd_base + i;
            if (rd_base == 255 || r >= kNumGprs) break;  // RZ dest: discard
            t.gpr[r] = out[i];
        }
    }
    return Status::success();
}

Status Interpreter::do_hmma(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst, std::uint64_t pc,
                            std::optional<Fault>* fault) {
    // Dense HMMA (hmma_x8_): size 0=k8 / 1=k16 / 2=k4(TF32), srcfmt
    // 0=F16 1=BF16 2=TF32 3=E6M9, dstfmt 0=F16 1=F32 accumulator.
    std::uint64_t size = 0, srcfmt = 0, dstfmt = 0;
    bool has_re = false;
    const shape::OperandValue* opd = nullptr;
    const shape::OperandValue* opa = nullptr;
    const shape::OperandValue* opb = nullptr;
    const shape::OperandValue* opc = nullptr;
    if (inst.variant_class == isa::VariantClass::khmma_x8_) {
        const auto& d = *static_cast<const shape::DecodedHMMA5*>(&inst);
        opd = &d.Rd; opa = &d.Ra; opb = &d.Rb; opc = &d.Rc;
        size = static_cast<std::uint64_t>(d.size);
        srcfmt = static_cast<std::uint64_t>(d.srcfmt);
        dstfmt = static_cast<std::uint64_t>(d.dstfmt);
    } else {
        // HMMA7 split: sparse (_0) / indexedRF (_1); BOTH are rejected by the
        // dense-shape gate below, so the member values never matter.
        const auto& d = *static_cast<const shape::DecodedHMMA7_0*>(&inst);
        opd = &d.Rd; opa = &d.Ra; opb = &d.Rb; opc = &d.Rc;
        size = static_cast<std::uint64_t>(d.size);
        srcfmt = static_cast<std::uint64_t>(d.srcfmt);
        dstfmt = static_cast<std::uint64_t>(d.dstfmt);
        has_re = true;
    }
    if (inst.variant_class != isa::VariantClass::khmma_x8_)
        return tensor_unsupported(w, inst, pc, mask, fault,
                                  "(sparse/indexedRF variant)");
    if (dstfmt != 1)
        return tensor_unsupported(w, inst, pc, mask, fault,
                                  "(F16 accumulator)");
    if (srcfmt > 1)
        return tensor_unsupported(w, inst, pc, mask, fault,
                                  "(TF32/E6M9 source)");
    tensor::Shape shape;
    if (!tensor::hmma_shape(static_cast<int>(size),
                            static_cast<int>(srcfmt), &shape)) {
        return tensor_unsupported(w, inst, pc, mask, fault, "(shape)");
    }
    const tensor::Format fmt =
        (srcfmt == 1) ? tensor::Format::kBf16 : tensor::Format::kF16;
    return tensor_lane_core(w, mask, inst, pc, fault, shape, fmt, false, has_re,
                            false, 0, *opd, *opa, *opb, *opc, nullptr,
                            nullptr, nullptr);
}

Status Interpreter::do_qmma(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst, std::uint64_t pc,
                            std::optional<Fault>* fault) {
    // Dense QMMA (qmma_): size 0=k16 / 1=k32, dstfmt(ntz) 0=F16 1=F32.
    std::uint64_t size = 0, dstfmt = 0;
    std::uint64_t sfa = 0, sfb = 0, sf = 0, ssz = 1;
    bool need_uri = false;
    bool has_re = false, has_rh = false;
    const shape::OperandValue* opd = nullptr;
    const shape::OperandValue* opa = nullptr;
    const shape::OperandValue* opb = nullptr;
    const shape::OperandValue* opc = nullptr;
    const shape::OperandValue* uri = nullptr;
    // QMMA forms: kqmma_ / kqmma_rowcol_ (5-op), kqmma_sp_/_sp_rowcol_
    // (7-op), kqmma_scale_ (8-op), kqmma_sp_scale_ (9-op).
    if (inst.variant_class == isa::VariantClass::kqmma_ ||
        inst.variant_class == isa::VariantClass::kqmma_rowcol_) {
        const auto& d = *static_cast<const shape::DecodedQMMA5*>(&inst);
        opd = &d.Rd; opa = &d.Ra; opb = &d.Rb; opc = &d.Rc;
        size = static_cast<std::uint64_t>(d.size);
        dstfmt = static_cast<std::uint64_t>(d.dstfmt);
        sfa = static_cast<std::uint64_t>(d.srcFmtA);
        sfb = static_cast<std::uint64_t>(d.srcFmtB);
    } else if (inst.variant_class == isa::VariantClass::kqmma_sp_ ||
               inst.variant_class == isa::VariantClass::kqmma_sp_rowcol_) {
        const auto& d = *static_cast<const shape::DecodedQMMA7*>(&inst);
        opd = &d.Rd; opa = &d.Ra; opb = &d.Rb; opc = &d.Rc;
        size = static_cast<std::uint64_t>(d.size);
        dstfmt = static_cast<std::uint64_t>(d.dstfmt);
        sfa = static_cast<std::uint64_t>(d.srcFmtA);
        sfb = static_cast<std::uint64_t>(d.srcFmtB);
        has_re = true;
    } else if (inst.variant_class == isa::VariantClass::kqmma_scale_) {
        const auto& d = *static_cast<const shape::DecodedQMMA8*>(&inst);
        opd = &d.Rd; opa = &d.Ra; opb = &d.Rb; opc = &d.Rc;
        uri = &d.URi;
        size = static_cast<std::uint64_t>(d.size);
        dstfmt = static_cast<std::uint64_t>(d.dstfmt);
        sfa = static_cast<std::uint64_t>(d.srcFmtA);
        sfb = static_cast<std::uint64_t>(d.srcFmtB);
        sf = static_cast<std::uint64_t>(d.sf);
        ssz = static_cast<std::uint64_t>(d.scaleVectorSz);
        need_uri = true;
        has_re = has_rh = true;
    } else {
        const auto& d = *static_cast<const shape::DecodedQMMA9*>(&inst);
        opd = &d.Rd; opa = &d.Ra; opb = &d.Rb; opc = &d.Rc;
        uri = &d.URi;
        size = static_cast<std::uint64_t>(d.size);
        dstfmt = static_cast<std::uint64_t>(d.dstfmt);
        sfa = static_cast<std::uint64_t>(d.srcFmtA);
        sfb = static_cast<std::uint64_t>(d.srcFmtB);
        sf = static_cast<std::uint64_t>(d.sf);
        ssz = static_cast<std::uint64_t>(d.scaleVectorSz);
        need_uri = true;
        has_re = has_rh = true;
    }
    if (inst.variant_class != isa::VariantClass::kqmma_)
        return tensor_unsupported(w, inst, pc, mask, fault,
                                  "(sparse/rowcol/scale variant)");
    if (dstfmt != 1)
        return tensor_unsupported(w, inst, pc, mask, fault,
                                  "(F16 accumulator)");
    tensor::Shape shape;
    if (!tensor::qmma_shape(static_cast<int>(size), &shape)) {
        return tensor_unsupported(w, inst, pc, mask, fault, "(shape)");
    }
    tensor::Format fmt = tensor::Format::kFp8E4M3;
    // SM120 QMMA srcFmt mapping (verified against real hardware on RTX
    // 5090, CUDA 13.1: field value drives the SRCFMTA_qmma enum in the
    // spec).  E4M3=0 E5M2=1 E3M4=2 E3M2=3 E2M3=4.  Field 5 is named
    // E2M1 in the spec but empirically behaves EXACTLY like field 4
    // (E2M3) on sm120 — no distinct E2M1 QMMA format exists here.
    switch (sfa) {
        case 0: fmt = tensor::Format::kFp8E4M3; break;
        case 1: fmt = tensor::Format::kFp8E5M2; break;
        case 2: fmt = tensor::Format::kFp8E3M4; break;
        case 3: fmt = tensor::Format::kFp8E3M2; break;
        case 4:
        case 5: fmt = tensor::Format::kFp8E2M3; break;
        default: return tensor_unsupported(w, inst, pc, mask, fault,
                                           "(srcFmtA)");
    }
    (void)sf; (void)ssz; (void)sfb;  // scale-vector fields: decode-gated above
    return tensor_lane_core(w, mask, inst, pc, fault, shape, fmt, need_uri, has_re,
                            has_rh, 1, *opd, *opa, *opb, *opc, nullptr, nullptr,
                            uri);
}

Status Interpreter::do_omma(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst, std::uint64_t pc,
                            std::optional<Fault>* fault) {
    // OMMA.SF (mxfp4 block-scaled): only the verified 2X-scale E8 e2m1
    // configuration is implemented (gpu_waiver — see capability manifest).
    std::uint64_t sf = 0, ssz = 1, sfa = 0, sfb = 0;
    const shape::OperandValue* opd = nullptr;
    const shape::OperandValue* opa = nullptr;
    const shape::OperandValue* opb = nullptr;
    const shape::OperandValue* opc = nullptr;
    const shape::OperandValue* re = nullptr;
    const shape::OperandValue* rh = nullptr;
    const shape::OperandValue* uri = nullptr;
    if (inst.variant_class == isa::VariantClass::komma_scale_) {
        const auto& d = *static_cast<const shape::DecodedOMMA8*>(&inst);
        opd = &d.Rd; opa = &d.Ra; opb = &d.Rb; opc = &d.Rc;
        re = &d.Re; rh = &d.Rh; uri = &d.URi;
        sf = static_cast<std::uint64_t>(d.sf);
        ssz = static_cast<std::uint64_t>(d.scaleVectorSz);
        sfa = static_cast<std::uint64_t>(d.srcFmtA);
        sfb = static_cast<std::uint64_t>(d.srcFmtB);
    } else {
        const auto& d = *static_cast<const shape::DecodedOMMA9*>(&inst);
        opd = &d.Rd; opa = &d.Ra; opb = &d.Rb; opc = &d.Rc;
        re = &d.Re; rh = &d.Rh; uri = &d.URi;
        sf = static_cast<std::uint64_t>(d.sf);
        ssz = static_cast<std::uint64_t>(d.scaleVectorSz);
        sfa = static_cast<std::uint64_t>(d.srcFmtA);
        sfb = static_cast<std::uint64_t>(d.srcFmtB);
    }
    if (inst.variant_class != isa::VariantClass::komma_scale_)
        return tensor_unsupported(w, inst, pc, mask, fault,
                                  "(sparse/scale variant)");
    if (sf != 0) return tensor_unsupported(w, inst, pc, mask, fault,
                                           "(non-E8 scale)");
    if (ssz != 1) return tensor_unsupported(w, inst, pc, mask, fault,
                                            "(4X scale vector)");
    if (sfa != 0 || sfb != 0) return tensor_unsupported(w, inst, pc, mask,
                                                        fault,
                                                        "(E0M3 source)");
    tensor::Shape shape;
    if (!tensor::omma_shape(&shape)) {
        return tensor_unsupported(w, inst, pc, mask, fault, "(shape)");
    }
    const tensor::Format fmt = tensor::Format::kFp8E4M3;  // unused for gdfs
    return tensor_lane_core(w, mask, inst, pc, fault, shape, fmt, true, true, true,
                            2, *opd, *opa, *opb, *opc, re, rh, uri);
}

// Phase 5 compute — one function per instruction (2b-3 plan-b + refactor).
// Per-instruction entry points with a small number of shared per-lane cores
// (the core is parameterized by the instruction's extracted operands/modifiers;
// each do_<MNEMONIC> just casts the concrete shape and forwards).
// ===========================================================================

}  // namespace semu
