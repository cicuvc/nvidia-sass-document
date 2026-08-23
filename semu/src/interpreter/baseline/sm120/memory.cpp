// sm120 baseline interpreter -- memory & sync: S2R/S2UR, LD/ST/ATOM/RED families, MEMBAR/FENCE/ERRBAR/CGAERRBAR/CCTL, LDGSTS, SYNC/ARRIVE, SHFL.
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
std::optional<SpecialReg> Interpreter::special_reg(
    const DecodedInstruction& inst) const {
    // S2R/S2UR encode the special register in the SRa operand role (the
    // `imm8` ENCODING field; the typed schema surfaces it as ops[last]).

    std::uint64_t v = 0;
    if (inst.mnemonic == isa::Mnemonic::kS2UR) {  // UPg, URd, SRa
        v = static_cast<std::uint64_t>(shape::operand_value_as_i64(
            static_cast<const shape::DecodedS2UR3*>(&inst)->SRa));
    } else {  // S2R: Rd, SRa
        v = static_cast<std::uint64_t>(shape::operand_value_as_i64(
            static_cast<const shape::DecodedS2R2*>(&inst)->SRa));
    }
    switch (v) {
        case kSrLaneid: return SpecialReg::kLaneid;
        case kSrClock: return SpecialReg::kClock;
        case kSrTidX: return SpecialReg::kTidX;
        case kSrTidY: return SpecialReg::kTidY;
        case kSrTidZ: return SpecialReg::kTidZ;
        case kSrCtaidX: return SpecialReg::kCtaidX;
        case kSrCtaidY: return SpecialReg::kCtaidY;
        case kSrCtaidZ: return SpecialReg::kCtaidZ;
        case kSrNtid: return SpecialReg::kNtidX;
        case kSrWarpId: return SpecialReg::kWarpId;
        case kSrWarpSize: return SpecialReg::kWarpSize;
        case kSrNctaidX: return SpecialReg::kNctaidX;
        case kSrNctaidY: return SpecialReg::kNctaidY;
        case kSrNctaidZ: return SpecialReg::kNctaidZ;
        case kSrSmId: return SpecialReg::kSmId;
        case kSrSmemBase: return SpecialReg::kSmemBase;
        default: return SpecialReg::kUndefined;
    }
}

// Resolve a special register value for a lane.
namespace {
}  // namespace

// ---------------------------------------------------------------------------
// Opcode handlers
// ---------------------------------------------------------------------------

Status Interpreter::do_s2r(WarpState& w, const DecodedInstruction& inst,
                           std::uint32_t mask, std::uint64_t pc,
                           std::optional<Fault>* fault) {
    auto sr = special_reg(inst);
    if (!sr) {
        Fault f(FaultKind::kUnsupportedInstruction,
                "S2R with unsupported special register at pc 0x" +
                    std::to_string(pc));
        f.set_warp(static_cast<std::uint32_t>(w.warp_id)).set_pc(pc);
        if (fault) *fault = std::move(f);
        return Status::failure(Error::internal("interpreter fault"));
    }
    const auto& d = *static_cast<const shape::DecodedS2R2*>(&inst);
    const std::uint64_t rd =
        static_cast<std::uint64_t>(shape::operand_value_as_i64(d.Rd));
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        t.gpr[static_cast<std::size_t>(rd)] =
            resolve_sr(*sr, lane, w.warp_id, w.cta_id, env_);
    }
    return Status::success();
}

Status Interpreter::do_s2ur(WarpState& w, const DecodedInstruction& inst,
                            std::uint64_t pc,
                            std::optional<Fault>* fault) {
    (void)inst; (void)fault;
    auto sr = special_reg(inst);
    if (!sr) {
        Fault f(FaultKind::kUnsupportedInstruction,
                "S2UR with unsupported special register at pc 0x" +
                    std::to_string(pc));
        f.set_warp(static_cast<std::uint32_t>(w.warp_id)).set_pc(pc);
        if (fault) *fault = std::move(f);
        return Status::failure(Error::internal("interpreter fault"));
    }
    // Uniform value: lane 0's view (warp-uniform).
    const auto& d = *static_cast<const shape::DecodedS2UR3*>(&inst);
    const std::uint64_t urd =
        static_cast<std::uint64_t>(shape::operand_value_as_i64(d.URd));
    w.ur[static_cast<std::size_t>(urd)] =
        resolve_sr(*sr, 0, w.warp_id, w.cta_id, env_);
    return Status::success();
}

namespace {

MemWidthInfo mem_sz(const DecodedInstruction& inst) {
    // All memory/atomic families carry the `sz` modifier member; the concrete
    // shape (mnemonic + form) is chosen by VARIANT CLASS — no operand count.
    const isa::VariantClass cls = inst.variant_class;
    std::uint64_t sz = 4;
    switch (inst.mnemonic) {
        case isa::Mnemonic::kLDG:
            if (cls == isa::VariantClass::kldg__sImmOffset ||
                cls == isa::VariantClass::kldg__uImmOffset) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedLDG5*>(&inst)->sz);
            } else if (cls == isa::VariantClass::kldg_256_memdesc__Ra64 ||
                       cls == isa::VariantClass::kldg_256_rml2_memdesc__Ra64) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedLDG8*>(&inst)->sz);
            } else if (cls == isa::VariantClass::kldg_memdesc__Ra64) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedLDG7_0*>(&inst)->sz);
            } else {  // kldg_256_* uniform forms
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedLDG7_1*>(&inst)->sz);
            }
            break;
        case isa::Mnemonic::kSTG:
            if (cls == isa::VariantClass::kstg__sImmOffset ||
                cls == isa::VariantClass::kstg__uImmOffset) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedSTG3*>(&inst)->sz);
            } else if (cls == isa::VariantClass::kstg_uniform__Ra32 ||
                       cls == isa::VariantClass::kstg_uniform__Ra64 ||
                       cls == isa::VariantClass::kstg_uniform__RaRZ) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedSTG4*>(&inst)->sz);
            } else if (cls == isa::VariantClass::kstg_memdesc__Ra64) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedSTG5*>(&inst)->sz);
            } else if (cls == isa::VariantClass::kstg_256_uniform__Ra32 ||
                       cls == isa::VariantClass::kstg_256_uniform__Ra64 ||
                       cls == isa::VariantClass::kstg_256_uniform__RaRZ) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedSTG6*>(&inst)->sz);
            } else {  // kstg_256_memdesc__Ra64
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedSTG7*>(&inst)->sz);
            }
            break;
        case isa::Mnemonic::kLDS:
            sz = (cls == isa::VariantClass::klds_uniform_)
                     ? static_cast<std::uint64_t>(static_cast<const shape::DecodedLDS4*>(&inst)->sz)
                     : static_cast<std::uint64_t>(static_cast<const shape::DecodedLDS3*>(&inst)->sz);
            break;
        case isa::Mnemonic::kSTS:
            sz = (cls == isa::VariantClass::ksts_uniform_)
                     ? static_cast<std::uint64_t>(static_cast<const shape::DecodedSTS4*>(&inst)->sz)
                     : static_cast<std::uint64_t>(static_cast<const shape::DecodedSTS3*>(&inst)->sz);
            break;
        case isa::Mnemonic::kLDL:
            if (cls == isa::VariantClass::kldl_uniform_) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedLDL4*>(&inst)->sz);
            } else if (cls == isa::VariantClass::kldl_memdesc_) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedLDL5*>(&inst)->sz);
            } else {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedLDL3*>(&inst)->sz);
            }
            break;
        case isa::Mnemonic::kSTL: sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedSTL3*>(&inst)->sz); break;
        case isa::Mnemonic::kLDC:
            // kldc__* (LDC [Sa_bank,Ra,..]) vs kldc_ur__* (LDC.UR [URa,Rb,..]).
            sz = (cls == isa::VariantClass::kldc_ur__URRzI ||
                  cls == isa::VariantClass::kldc_ur__URnonRzI)
                     ? static_cast<std::uint64_t>(static_cast<const shape::DecodedLDC5_1*>(&inst)->sz)
                     : static_cast<std::uint64_t>(static_cast<const shape::DecodedLDC5_0*>(&inst)->sz);
            break;
        case isa::Mnemonic::kLDCU:
            if (cls == isa::VariantClass::kldcu_ur_offs_optional_upx_) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedLDCU4*>(&inst)->sz);
            } else if (cls == isa::VariantClass::kldcu_ur_offs_) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedLDCU5*>(&inst)->sz);
            } else if (cls == isa::VariantClass::kldcu_256_ur_offs_) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedLDCU7*>(&inst)->sz);
            } else if (cls == isa::VariantClass::kldcu_256_ur_offs_optional_upx_) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedLDCU6_2*>(&inst)->sz);
            } else if (cls == isa::VariantClass::kldcu_const_RCR_) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedLDCU6_0*>(&inst)->sz);
            } else if (cls == isa::VariantClass::kldcu_const_RCxR_) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedLDCU6_1*>(&inst)->sz);
            } else if (cls == isa::VariantClass::kldcu_256_const_RCR_) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedLDCU8_0*>(&inst)->sz);
            } else {  // kldcu_256_const_RCxR_
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedLDCU8_1*>(&inst)->sz);
            }
            break;
        case isa::Mnemonic::kATOM:
            if (cls == isa::VariantClass::katom_cas__RaNonRZ_CAS ||
                cls == isa::VariantClass::katom_cas__RaNonRZ_CAST ||
                cls == isa::VariantClass::katom_cas__RaRZ_CAS ||
                cls == isa::VariantClass::katom_cas__RaRZ_CAST) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedATOM7_1*>(&inst)->sz);
            } else if (cls == isa::VariantClass::katom_arrive__Ra32_arrive ||
                       cls == isa::VariantClass::katom_arrive__Ra32_popcinc ||
                       cls == isa::VariantClass::katom_arrive__Ra64_arrive ||
                       cls == isa::VariantClass::katom_arrive__Ra64_popcinc ||
                       cls == isa::VariantClass::katom_arrive__RaRZ_arrive ||
                       cls == isa::VariantClass::katom_arrive__RaRZ_popcinc) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedATOM6_0*>(&inst)->sz);
            } else if (cls == isa::VariantClass::katom_fp__RaNonRZ ||
                       cls == isa::VariantClass::katom_fp__RaRZ ||
                       cls == isa::VariantClass::katom_int__RaNonRZ ||
                       cls == isa::VariantClass::katom_int__RaRZ) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedATOM6_1*>(&inst)->sz);
            } else {  // katom_{int,fp}_uniform__*: ATOM7 split 0
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedATOM7_0*>(&inst)->sz);
            }
            break;
        case isa::Mnemonic::kATOMS:
            if (cls == isa::VariantClass::katoms_cas__RaNonRZ ||
                cls == isa::VariantClass::katoms_cas__RaRZ ||
                cls == isa::VariantClass::katoms_cast_destRd__RaNonRZ ||
                cls == isa::VariantClass::katoms_cast_destRd__RaRZ) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedATOMS5_2*>(&inst)->sz);
            } else if (cls == isa::VariantClass::katoms_cast_destPu__RaNonRZ ||
                       cls == isa::VariantClass::katoms_cast_destPu__RaRZ) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedATOMS5_0*>(&inst)->sz);
            } else if (cls == isa::VariantClass::katoms_uniform_) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedATOMS5_1*>(&inst)->sz);
            } else if (cls == isa::VariantClass::katoms__RaNonRZ ||
                       cls == isa::VariantClass::katoms__RaRZ) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedATOMS4_1*>(&inst)->sz);
            } else {  // katoms_arrive__*: ATOMS4 split 0
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedATOMS4_0*>(&inst)->sz);
            }
            break;
        case isa::Mnemonic::kATOMG:
            if (cls == isa::VariantClass::katomg_fp__RaNonRZ ||
                cls == isa::VariantClass::katomg_fp__RaRZ ||
                cls == isa::VariantClass::katomg_int__RaNonRZ ||
                cls == isa::VariantClass::katomg_int__RaRZ) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedATOMG5*>(&inst)->sz);
            } else if (cls == isa::VariantClass::katomg_fp_uniform__memdesc ||
                       cls == isa::VariantClass::katomg_int_uniform__memdesc) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedATOMG7*>(&inst)->sz);
            } else if (cls == isa::VariantClass::katomg_cas__RaNonRZ ||
                       cls == isa::VariantClass::katomg_cas__RaRZ) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedATOMG6_1*>(&inst)->sz);
            } else {  // katomg_{int,fp}_uniform__Ra32/64/Rz: ATOMG6 split 0
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedATOMG6_0*>(&inst)->sz);
            }
            break;
        case isa::Mnemonic::kREDG:
            if (cls == isa::VariantClass::kredg_fp__RaNonRZ ||
                cls == isa::VariantClass::kredg_fp__RaRZ ||
                cls == isa::VariantClass::kredg_int__RaNonRZ ||
                cls == isa::VariantClass::kredg_int__RaRZ) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedREDG3*>(&inst)->sz);
            } else if (cls == isa::VariantClass::kredg_fp_uniform__memdesc ||
                       cls == isa::VariantClass::kredg_int_uniform__memdesc) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedREDG5*>(&inst)->sz);
            } else {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedREDG4*>(&inst)->sz);
            }
            break;
        case isa::Mnemonic::kREDS:
            sz = (cls == isa::VariantClass::katoms_reds_uniform_)
                     ? static_cast<std::uint64_t>(static_cast<const shape::DecodedREDS4*>(&inst)->sz)
                     : static_cast<std::uint64_t>(static_cast<const shape::DecodedREDS3*>(&inst)->sz);
            break;
        case isa::Mnemonic::kLDGSTS:
            if (cls == isa::VariantClass::kldgsts__desc_RRU) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedLDGSTS7*>(&inst)->sz);
            } else if (cls == isa::VariantClass::kldgsts_memdesc_) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedLDGSTS8*>(&inst)->sz);
            } else if (cls == isa::VariantClass::kldgsts__RUR ||
                       cls == isa::VariantClass::kldgsts_no_ra__RUR) {
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedLDGSTS6_0*>(&inst)->sz);
            } else {  // kldgsts__RR32U/RR64U, kldgsts_no_ra__RRU
                sz = static_cast<std::uint64_t>(static_cast<const shape::DecodedLDGSTS6_1*>(&inst)->sz);
            }
            break;
        default:
            // sz not present on this family; keep the default 32-bit width.
            break;
    }
    return mem_width_info(sz);
}

// Blocker-4: decode the ATOMS `op` slot (AtomsOp /
// OP_ADD_MIN_MAX_INC_DEC_AND_OR_XOR_EXCH_SAFEADD) into the MemoryService
// AtomicOp, honoring the integer size (S32/S64 -> SIGNED min/max; INC/DEC are
// U32-only per the spec's CONDITIONS).  Returns nullopt for FP atomic ops
// (ATOMICFPOPS), SAFEADD, INVALID op values and illegal width/op combos — the
// caller MUST fault and must NEVER downgrade to ADD.  CAS is decoded
// separately by the presence of the Rc compare operand.
std::optional<AtomicOp> decode_atomic_op(const DecodedInstruction& inst) {
    // FP atomic (ATOMICFPOPS) variants are marked by the generated subclass
    // fp bit; they are not implemented.  op/sz are typed members resolved by
    // (mnemonic, variant class) cast — each form has its own concrete type.
    const isa::VariantClass cls = inst.variant_class;
    std::uint64_t opv = 0, szv = 0;
    std::uint8_t subclass = 0;
    switch (inst.mnemonic) {
        case isa::Mnemonic::kATOM: {
            // ATOM forms: katom_{int,fp}_uniform__* (7-op, op member),
            // katom_cas__* (7-op CAS, no op), katom_arrive__* (6-op),
            // katom_{int,fp}__* (6-op).
            if (cls == isa::VariantClass::katom_int_uniform__Ra32 ||
                cls == isa::VariantClass::katom_int_uniform__Ra64 ||
                cls == isa::VariantClass::katom_int_uniform__RaRZ ||
                cls == isa::VariantClass::katom_fp_uniform__Ra32 ||
                cls == isa::VariantClass::katom_fp_uniform__Ra64 ||
                cls == isa::VariantClass::katom_fp_uniform__RaRZ) {
                const auto& d = *static_cast<const shape::DecodedATOM7_0*>(&inst);
                opv = static_cast<std::uint64_t>(d.op);
                szv = static_cast<std::uint64_t>(d.sz);
                subclass = d.subclass;
            } else if (cls == isa::VariantClass::katom_cas__RaNonRZ_CAS ||
                       cls == isa::VariantClass::katom_cas__RaNonRZ_CAST ||
                       cls == isa::VariantClass::katom_cas__RaRZ_CAS ||
                       cls == isa::VariantClass::katom_cas__RaRZ_CAST) {
                // CAS split has no op member (opv stays 0; overridden with
                // kCas by the caller when a comparand exists).
                const auto& d = *static_cast<const shape::DecodedATOM7_1*>(&inst);
                szv = static_cast<std::uint64_t>(d.sz);
                subclass = d.subclass;
            } else if (cls == isa::VariantClass::katom_arrive__Ra32_arrive ||
                       cls == isa::VariantClass::katom_arrive__Ra32_popcinc ||
                       cls == isa::VariantClass::katom_arrive__Ra64_arrive ||
                       cls == isa::VariantClass::katom_arrive__Ra64_popcinc ||
                       cls == isa::VariantClass::katom_arrive__RaRZ_arrive ||
                       cls == isa::VariantClass::katom_arrive__RaRZ_popcinc) {
                const auto& d = *static_cast<const shape::DecodedATOM6_0*>(&inst);
                opv = static_cast<std::uint64_t>(d.op);
                szv = static_cast<std::uint64_t>(d.sz);
                subclass = d.subclass;
            } else {  // katom_{int,fp}__RaNonRZ/RaRZ
                const auto& d = *static_cast<const shape::DecodedATOM6_1*>(&inst);
                opv = static_cast<std::uint64_t>(d.op);
                szv = static_cast<std::uint64_t>(d.sz);
                subclass = d.subclass;
            }
            break;
        }
        case isa::Mnemonic::kATOMS: {
            // ATOMS forms: katoms_cas__*/katoms_cast_destRd__* (5-op CAS, no
            // op), katoms_cast_destPu__* (5-op, no op), katoms_uniform_
            // (5-op, op member), katoms__* (4-op plain), katoms_arrive__*
            // (4-op).
            if (cls == isa::VariantClass::katoms_cas__RaNonRZ ||
                cls == isa::VariantClass::katoms_cas__RaRZ ||
                cls == isa::VariantClass::katoms_cast_destRd__RaNonRZ ||
                cls == isa::VariantClass::katoms_cast_destRd__RaRZ) {
                const auto& d = *static_cast<const shape::DecodedATOMS5_2*>(&inst);
                szv = static_cast<std::uint64_t>(d.sz);
                subclass = d.subclass;
            } else if (cls == isa::VariantClass::katoms_cast_destPu__RaNonRZ ||
                       cls == isa::VariantClass::katoms_cast_destPu__RaRZ) {
                const auto& d = *static_cast<const shape::DecodedATOMS5_0*>(&inst);
                szv = static_cast<std::uint64_t>(d.sz);
                subclass = d.subclass;
            } else if (cls == isa::VariantClass::katoms_uniform_) {
                const auto& d = *static_cast<const shape::DecodedATOMS5_1*>(&inst);
                opv = static_cast<std::uint64_t>(d.op);
                szv = static_cast<std::uint64_t>(d.sz);
                subclass = d.subclass;
            } else if (cls == isa::VariantClass::katoms__RaNonRZ ||
                       cls == isa::VariantClass::katoms__RaRZ) {
                const auto& d = *static_cast<const shape::DecodedATOMS4_1*>(&inst);
                opv = static_cast<std::uint64_t>(d.op);
                szv = static_cast<std::uint64_t>(d.sz);
                subclass = d.subclass;
            } else {  // katoms_arrive__*
                const auto& d = *static_cast<const shape::DecodedATOMS4_0*>(&inst);
                opv = static_cast<std::uint64_t>(d.op);
                szv = static_cast<std::uint64_t>(d.sz);
                subclass = d.subclass;
            }
            break;
        }
        case isa::Mnemonic::kATOMG: {
            // ATOMG forms: katomg_{int,fp}__* (5-op), katomg_*_uniform__
            // memdesc (7-op), katomg_cas__* (6-op, no op), katomg_*_uniform__
            // Ra32/64/Rz (6-op, op member).
            if (cls == isa::VariantClass::katomg_fp__RaNonRZ ||
                cls == isa::VariantClass::katomg_fp__RaRZ ||
                cls == isa::VariantClass::katomg_int__RaNonRZ ||
                cls == isa::VariantClass::katomg_int__RaRZ) {
                const auto& d = *static_cast<const shape::DecodedATOMG5*>(&inst);
                opv = static_cast<std::uint64_t>(d.op);
                szv = static_cast<std::uint64_t>(d.sz);
                subclass = d.subclass;
            } else if (cls == isa::VariantClass::katomg_fp_uniform__memdesc ||
                       cls == isa::VariantClass::katomg_int_uniform__memdesc) {
                const auto& d = *static_cast<const shape::DecodedATOMG7*>(&inst);
                opv = static_cast<std::uint64_t>(d.op);
                szv = static_cast<std::uint64_t>(d.sz);
                subclass = d.subclass;
            } else if (cls == isa::VariantClass::katomg_cas__RaNonRZ ||
                       cls == isa::VariantClass::katomg_cas__RaRZ) {
                const auto& d = *static_cast<const shape::DecodedATOMG6_1*>(&inst);
                szv = static_cast<std::uint64_t>(d.sz);
                subclass = d.subclass;
            } else {  // katomg_{int,fp}_uniform__Ra32/64/Rz: 6-op split 0
                const auto& d = *static_cast<const shape::DecodedATOMG6_0*>(&inst);
                opv = static_cast<std::uint64_t>(d.op);
                szv = static_cast<std::uint64_t>(d.sz);
                subclass = d.subclass;
            }
            break;
        }
        case isa::Mnemonic::kREDG:
            if (cls == isa::VariantClass::kredg_fp__RaNonRZ ||
                cls == isa::VariantClass::kredg_fp__RaRZ ||
                cls == isa::VariantClass::kredg_int__RaNonRZ ||
                cls == isa::VariantClass::kredg_int__RaRZ) {
                const auto& d = *static_cast<const shape::DecodedREDG3*>(&inst);
                opv = static_cast<std::uint64_t>(d.op);
                szv = static_cast<std::uint64_t>(d.sz);
                subclass = d.subclass;
            } else if (cls == isa::VariantClass::kredg_fp_uniform__memdesc ||
                       cls == isa::VariantClass::kredg_int_uniform__memdesc) {
                const auto& d = *static_cast<const shape::DecodedREDG5*>(&inst);
                opv = static_cast<std::uint64_t>(d.op);
                szv = static_cast<std::uint64_t>(d.sz);
                subclass = d.subclass;
            } else {
                const auto& d = *static_cast<const shape::DecodedREDG4*>(&inst);
                opv = static_cast<std::uint64_t>(d.op);
                szv = static_cast<std::uint64_t>(d.sz);
                subclass = d.subclass;
            }
            break;
        case isa::Mnemonic::kREDS:
            if (cls == isa::VariantClass::katoms_reds_uniform_) {
                const auto& d = *static_cast<const shape::DecodedREDS4*>(&inst);
                opv = static_cast<std::uint64_t>(d.op);
                szv = static_cast<std::uint64_t>(d.sz);
                subclass = d.subclass;
            } else {
                const auto& d = *static_cast<const shape::DecodedREDS3*>(&inst);
                opv = static_cast<std::uint64_t>(d.op);
                szv = static_cast<std::uint64_t>(d.sz);
                subclass = d.subclass;
            }
            break;
        default:
            return std::nullopt;
    }
    if (subclass & 16) return std::nullopt;  // FP atomics unimplemented
    const bool signed_size = (szv == 1 || szv == 3);  // S32 / S64
    switch (opv) {
        case 0: return AtomicOp::kAdd;
        case 1: return signed_size ? AtomicOp::kMinSigned : AtomicOp::kMin;
        case 2: return signed_size ? AtomicOp::kMaxSigned : AtomicOp::kMax;
        case 3: return szv == 0 ? std::optional<AtomicOp>(AtomicOp::kInc)
                                : std::nullopt;  // INC (U32 only)
        case 4: return szv == 0 ? std::optional<AtomicOp>(AtomicOp::kDec)
                                : std::nullopt;  // DEC (U32 only)
        case 5: return AtomicOp::kAnd;
        case 6: return AtomicOp::kOr;
        case 7: return AtomicOp::kXor;
        case 8: return AtomicOp::kExch;
        case 9: return std::nullopt;  // SAFEADD (ATOMG/REDG) unimplemented
        default: return std::nullopt;  // INVALID*
    }
}

}  // namespace
Status Interpreter::resolve_mem_addr(const DecodedInstruction& inst,
                                     const ThreadState& t,
                                     const WarpState& w,
                                     std::uint64_t* addr_out,
                                     std::int64_t* off_out,
                                     std::uint64_t* width_out,
                                     AddressSpace* space_out,
                                     std::optional<Fault>* fault) {
    (void)w;
    (void)fault;
    const isa::Mnemonic m = inst.mnemonic;
    MemWidthInfo wi = mem_sz(inst);
    *width_out = wi.bytes;

    // Every memory form has a fixed base/offset pair of NAMED fields; the
    // form selects the concrete struct (variant class), the fields stay the
    // same names (Ra / Ra_offset, or URa / Sa_offset for the uniform forms).
    if (m == isa::Mnemonic::kLDG) {
        const shape::OperandValue* baseop = nullptr;
        const shape::OperandValue* offop = nullptr;
        if (inst.variant_class == isa::VariantClass::kldg__sImmOffset ||
            inst.variant_class == isa::VariantClass::kldg__uImmOffset) {
            const auto& d = *static_cast<const shape::DecodedLDG5*>(&inst);
            baseop = &d.Ra; offop = &d.Ra_offset;
        } else if (inst.variant_class == isa::VariantClass::kldg_memdesc__Ra64 ||
                   inst.variant_class == isa::VariantClass::kldg_256_memdesc__Ra64 ||
                   inst.variant_class == isa::VariantClass::kldg_256_rml2_memdesc__Ra64) {
            const auto& d = *static_cast<const shape::DecodedLDG8*>(&inst);
            baseop = &d.Ra; offop = &d.Ra_offset;
        } else {  // 256-uniform 7-op
            const auto& d = *static_cast<const shape::DecodedLDG7_1*>(&inst);
            baseop = &d.Ra; offop = &d.Ra_offset;
        }
        *addr_out = read_addr_pair_ov(t, *baseop);
        *off_out = shape::operand_value_as_i64(*offop);
        *space_out = AddressSpace::kGlobal;
        return Status::success();
    }
    if (m == isa::Mnemonic::kSTG || m == isa::Mnemonic::kSTL) {
        const shape::OperandValue* baseop = nullptr;
        const shape::OperandValue* offop = nullptr;
        if (m == isa::Mnemonic::kSTL ||
            inst.variant_class == isa::VariantClass::kstg__sImmOffset ||
            inst.variant_class == isa::VariantClass::kstg__uImmOffset) {
            const auto& d = *static_cast<const shape::DecodedSTG3*>(&inst);
            baseop = &d.Ra; offop = &d.Ra_offset;
        } else if (inst.variant_class == isa::VariantClass::kstg_uniform__Ra32 ||
                   inst.variant_class == isa::VariantClass::kstg_uniform__Ra64 ||
                   inst.variant_class == isa::VariantClass::kstg_uniform__RaRZ ||
                   inst.variant_class == isa::VariantClass::kstg_256_uniform__Ra32 ||
                   inst.variant_class == isa::VariantClass::kstg_256_uniform__Ra64 ||
                   inst.variant_class == isa::VariantClass::kstg_256_uniform__RaRZ) {
            const auto& d = *static_cast<const shape::DecodedSTG4*>(&inst);
            baseop = &d.Ra; offop = &d.Ra_offset;
        } else {  // kstg_memdesc__Ra64 / kstg_256_memdesc__Ra64
            const auto& d = *static_cast<const shape::DecodedSTG5*>(&inst);
            baseop = &d.Ra; offop = &d.Ra_offset;
        }
        *addr_out = read_addr_pair_ov(t, *baseop);
        *off_out = shape::operand_value_as_i64(*offop);
        *space_out = (m == isa::Mnemonic::kSTL) ? AddressSpace::kLocal
                                                : AddressSpace::kGlobal;
        return Status::success();
    }
    if (m == isa::Mnemonic::kLDL) {
        const shape::OperandValue* baseop = nullptr;
        const shape::OperandValue* offop = nullptr;
        if (inst.variant_class == isa::VariantClass::kldl_uniform_) {
            const auto& d = *static_cast<const shape::DecodedLDL4*>(&inst);
            baseop = &d.Ra; offop = &d.Ra_offset;
        } else if (inst.variant_class == isa::VariantClass::kldl_memdesc_) {
            const auto& d = *static_cast<const shape::DecodedLDL5*>(&inst);
            baseop = &d.Ra; offop = &d.Ra_offset;
        } else {
            const auto& d = *static_cast<const shape::DecodedLDL3*>(&inst);
            baseop = &d.Ra; offop = &d.Ra_offset;
        }
        *addr_out = read_addr_pair_ov(t, *baseop);
        *off_out = shape::operand_value_as_i64(*offop);
        *space_out = AddressSpace::kLocal;
        return Status::success();
    }
    if (m == isa::Mnemonic::kLDS || m == isa::Mnemonic::kSTS ||
        m == isa::Mnemonic::kATOMS || m == isa::Mnemonic::kREDS) {
        const shape::OperandValue* baseop = nullptr;
        const shape::OperandValue* offop = nullptr;
        if (m == isa::Mnemonic::kLDS) {
            const auto& d = *static_cast<const shape::DecodedLDS3*>(&inst);
            baseop = &d.Ra; offop = &d.Ra_offset;
        } else if (m == isa::Mnemonic::kSTS) {
            const auto& d = *static_cast<const shape::DecodedSTS3*>(&inst);
            baseop = &d.Ra; offop = &d.Ra_offset;
        } else if (m == isa::Mnemonic::kATOMS) {
            const auto& d = *static_cast<const shape::DecodedATOMS4_1*>(&inst);
            baseop = &d.Ra; offop = &d.Ra_offset;
        } else {  // REDS
            const auto& d = *static_cast<const shape::DecodedREDS3*>(&inst);
            baseop = &d.Ra; offop = &d.Ra_offset;
        }
        *addr_out = read_reg_ov(t, *baseop);
        *off_out = shape::operand_value_as_i64(*offop);
        *space_out = AddressSpace::kShared;
        return Status::success();
    }
    if (m == isa::Mnemonic::kLDC || m == isa::Mnemonic::kLDCU) {
        // Constant: bank (Sa_bank) + base (Ra / URa by form) + offset
        // (Ra_offset / Sa_offset).  Dispatched by opcode; each form reads its
        // own named fields.
        const std::uint16_t op = semu::opcode_of(inst.word.lo, inst.word.hi);
        std::uint64_t bank = 0, base_v = 0;
        std::int64_t off = 0;
        switch (op) {
            case 0xb82: {  // LDC [Rd,Sa,Sa_bank,Ra,Ra_offset]
                const auto& d = *static_cast<const shape::DecodedLDC5_0*>(&inst);
                bank = static_cast<std::uint64_t>(shape::operand_value_as_i64(d.Sa_bank));
                base_v = read_reg_ov(t, d.Ra);
                off = shape::operand_value_as_i64(d.Ra_offset);
                break;
            }
            case 0x17ac: {  // LDCU.CONST [UPg,URd,Sa,Sa_bank,URa,Sa_offset]
                const auto& d = *static_cast<const shape::DecodedLDCU6_0*>(&inst);
                bank = static_cast<std::uint64_t>(shape::operand_value_as_i64(d.Sa_bank));
                base_v = read_ur_ov(w, d.URa);
                off = shape::operand_value_as_i64(d.Sa_offset);
                break;
            }
            case 0x1dac: {  // LDCU.256.CONST [..,Sa_bank@4,URa@5,Sa_offset@6]
                const auto& d = *static_cast<const shape::DecodedLDCU8_0*>(&inst);
                bank = static_cast<std::uint64_t>(shape::operand_value_as_i64(d.Sa_bank));
                base_v = read_ur_ov(w, d.URa);
                off = shape::operand_value_as_i64(d.Sa_offset);
                break;
            }
            case 0x1bac: {  // LDCU.CONST [UPg,URd,Sa,URa,URb,Sa_offset]
                const auto& d = *static_cast<const shape::DecodedLDCU6_1*>(&inst);
                base_v = read_ur_ov(w, d.URa);
                off = shape::operand_value_as_i64(d.Sa_offset);
                break;
            }
            case 0x13ac: {  // LDCU.256.UR [..,URa@3,Sa_offset@4,..]
                const auto& d = *static_cast<const shape::DecodedLDCU6_2*>(&inst);
                base_v = read_ur_ov(w, d.URa);
                off = shape::operand_value_as_i64(d.Sa_offset);
                break;
            }
            case 0x19ac: {  // LDCU.UR [UPg,URd,URa,Sa_offset(,UPp)]
                const auto& d = *static_cast<const shape::DecodedLDCU5*>(&inst);
                base_v = read_ur_ov(w, d.URa);
                off = shape::operand_value_as_i64(d.Sa_offset);
                break;
            }
            case 0x15ac: {  // LDCU.256.CONST [..,URa@4,URb@5,Sa_offset@6,..]
                const auto& d = *static_cast<const shape::DecodedLDCU8_1*>(&inst);
                base_v = read_ur_ov(w, d.URa);
                off = shape::operand_value_as_i64(d.Sa_offset);
                break;
            }
            default:  // 0x1582 LDC.UR: no Sa_bank/Ra/Ra_offset roles
                break;
        }
        *addr_out = bank * 0x10000 + base_v + static_cast<std::uint64_t>(off);
        *space_out = AddressSpace::kConstant;
        return Status::success();
    }
    if (m == isa::Mnemonic::kATOMG || m == isa::Mnemonic::kREDG) {
        const shape::OperandValue* baseop = nullptr;
        const shape::OperandValue* offop = nullptr;
        if (inst.variant_class == isa::VariantClass::katomg_fp_uniform__memdesc ||
            inst.variant_class == isa::VariantClass::katomg_int_uniform__memdesc ||
            inst.variant_class == isa::VariantClass::kredg_fp_uniform__memdesc ||
            inst.variant_class == isa::VariantClass::kredg_int_uniform__memdesc) {
            const auto& d = *static_cast<const shape::DecodedATOMG7*>(&inst);
            baseop = &d.Ra; offop = &d.Ra_offset;
        } else {
            const auto& d = *static_cast<const shape::DecodedATOMG5*>(&inst);
            baseop = &d.Ra; offop = &d.Ra_offset;
        }
        *addr_out = read_addr_pair_ov(t, *baseop);
        *off_out = shape::operand_value_as_i64(*offop);
        *space_out = AddressSpace::kGlobal;
        return Status::success();
    }
    if (m == isa::Mnemonic::kATOM) {
        const auto& d = *static_cast<const shape::DecodedATOM6_1*>(&inst);
        *addr_out = read_reg_ov(t, d.Ra);
        *off_out = shape::operand_value_as_i64(d.Ra_offset);
        *space_out = AddressSpace::kGlobal;
        return Status::success();
    }
    return Status::failure(Error(ErrorCode::kUnimplemented,
                                 "memory address resolve for '" + std::string(isa::mnemonic_name(m)) + "'"));
}

// Shared per-lane load/store/atomic loop (the old do_memory body).  The
// extractable per-instruction part (which GPR holds the dest/source/comparand
// and the atom size/order) is resolved by each do_<MNEMONIC> entry point;
// everything below is exactly the pre-refactor behavior.
Status Interpreter::mem_ldst_atom_core(
    WarpState& w, std::uint32_t mask, const DecodedInstruction& inst,
    std::uint64_t pc, std::optional<Fault>* fault, bool is_load,
    bool is_atom, std::uint64_t rd_r, std::uint64_t rb_r,
    std::uint64_t cas_r, std::uint64_t atom_sz, std::uint64_t atom_sem,
    std::uint64_t atom_sco) {
    // Phase 6 Step 2B: trace-only subcore issue event for this memory op.
    // Never changes the functional path below.  Phase 8: the raw per-lane
    // byte ranges of the COMMITTED access are collected inside the per-lane
    // loop and the event is emitted afterwards (committed-access semantics —
    // a lane that faults never appears in the profiler stream, matching the
    // race detector / L2 trace).
    std::vector<LaneByteRange> prof_lanes(kLanesPerWarp);
    std::uint32_t prof_committed = 0;
    AddressSpace prof_space = AddressSpace::kGlobal;
    std::uint32_t prof_width = 0;  // last committed lane width (atomics use
                                   // ATOMICINTSIZES, not the load/store enum)
    bool prof_is_write = is_atom || !is_load;

    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;

        std::uint64_t addr = 0;
        std::int64_t off = 0;
        std::uint64_t w_ = 0;
        AddressSpace space = AddressSpace::kGlobal;
        Status rs = resolve_mem_addr(inst, t, w, &addr, &off, &w_, &space,
                                     fault);
        if (rs.failed()) {
            if (fault) {
                *fault = Fault(FaultKind::kIllegalMemoryAccess,
                               rs.error().message())
                             .set_pc(pc)
                             .set_warp(static_cast<std::uint32_t>(w.warp_id))
                             .set_active_mask(mask);
            }
            return Status::failure(Error::internal("memory fault"));
        }
        MemWidthInfo wi = mem_sz(inst);
        wi.bytes = w_;
        if (!wi.valid) {
            if (fault) {
                *fault = Fault(FaultKind::kIllegalMemoryAccess,
                               "invalid memory width slot")
                             .set_pc(pc)
                             .set_warp(static_cast<std::uint32_t>(w.warp_id))
                             .set_active_mask(mask);
            }
            return Status::failure(Error::internal("memory fault"));
        }
        if (is_atom) {
            // ATOM/ATOMS use ATOMICINTSIZES (U32=0, S32=1, U64=2, S64=3,
            // 128=4) — not the SZ_U8_... load/store enum.
            if (atom_sz == 2 || atom_sz == 3) wi.bytes = 8;
            else if (atom_sz == 4) wi.bytes = 16;
            else wi.bytes = 4;
        }

        // Blocker-3: compute the overflow-safe EFFECTIVE address ONCE and use
        // it for the functional MemoryService call, the race detector and the
        // L2 sector trace alike.  Previously the functional path applied
        // addr+off internally while record_race_access/record_l2_access got
        // the bare `addr`, so two accesses with the same base but different
        // displacements were misjudged overlapping, different base+disp pairs
        // landing on the same byte were missed, and L2 sector/coalesce traces
        // were wrong.  Constant addresses already fold the offset in during
        // resolve_mem_addr, so no second add there.
        std::uint64_t effective = 0;
        if (space == AddressSpace::kConstant) {
            effective = addr;
        } else if (!checked_add(addr, off, &effective)) {
            if (fault) {
                *fault = Fault(FaultKind::kIllegalMemoryAccess,
                               "memory address overflow")
                             .set_pc(pc)
                             .set_warp(static_cast<std::uint32_t>(w.warp_id))
                             .set_active_mask(mask);
            }
            return Status::failure(Error::internal("memory fault"));
        }

        if (is_load) {
            // Phase 6 Step 2C: trace-only L2 event for global loads.
            if (space == AddressSpace::kGlobal) {
                record_l2_access(w, inst, pc, mask, "load", space, effective,
                                 wi.bytes, static_cast<std::uint32_t>(lane));
            }
            // Phase 6 Step 2D: race detector (shared/global only).
            if (space == AddressSpace::kShared ||
                space == AddressSpace::kGlobal) {
                record_race_access(w, inst, pc, lane, space, effective,
                                   wi.bytes, false, false, "", "");
            }
            MemValue val{};
            Status st = Status::success();
            if (space == AddressSpace::kGlobal) {
                st = memory_->ldg(DevicePtr{0}, effective, 0, wi, val);
            } else if (space == AddressSpace::kShared) {
                st = MemoryService::lds(ctas_[w.local_cta_id].shared, effective,
                                        0, wi, val);
            } else if (space == AddressSpace::kConstant) {
                st = memory_->ldc(0, effective, wi, val);
            } else {  // local (per-warp window)
                st = MemoryService::lds(w.local, effective, 0, wi, val);
            }
            if (st.failed()) {
                if (fault) {
                    *fault = memory_error_to_fault(
                                 st.error(), pc,
                                 static_cast<std::uint32_t>(w.warp_id))
                                 .set_active_mask(mask);
                }
                return Status::failure(Error::internal("memory fault"));
            }
            // Phase 7 debug capture: the load committed.
            record_debug_access(w, static_cast<std::uint32_t>(lane), space,
                                effective, wi.bytes, false, false);
            // Phase 8 profiler: record the committed lane byte range.
            prof_lanes[static_cast<std::size_t>(lane)] = {
                effective, wi.bytes, true};
            prof_committed |= (1u << lane);
            prof_space = space;
            prof_width = static_cast<std::uint32_t>(wi.bytes);
            // 128-bit loads write Rd..Rd+3; narrower write Rd (and Rd+1 for
            // 64-bit) (Blocker-3).
            if (rd_r != 255) {
                const std::uint64_t r = rd_r;
                if (r != 255 && r < kNumGprs) {
                    t.gpr[r] = val[0];
                    if (wi.bytes > 4 && r + 1 < kNumGprs) t.gpr[r + 1] = val[1];
                    if (wi.bytes > 8) {
                        if (r + 2 < kNumGprs) t.gpr[r + 2] = val[2];
                        if (r + 3 < kNumGprs) t.gpr[r + 3] = val[3];
                    }
                }
            }
            continue;
        }

        // Store / atomic: source value from Rb (or Rd for ATOMS' result).
        // 128-bit stores read Rb..Rb+3.
        MemValue val{};
        if (rb_r != 255) {
            const std::uint64_t r = rb_r;
            if (r != 255 && r < kNumGprs) {
                val[0] = t.gpr[r];
                if (wi.bytes > 4 && r + 1 < kNumGprs) val[1] = t.gpr[r + 1];
                if (wi.bytes > 8) {
                    if (r + 2 < kNumGprs) val[2] = t.gpr[r + 2];
                    if (r + 3 < kNumGprs) val[3] = t.gpr[r + 3];
                }
            }
        }
        if (is_atom) {
            // Phase 6 Step 2D: race detector observation (shared/global).
            // Decode the real sem/sco so release/acquire clock bookkeeping
            // (Blocker-2) sees the actual memory order.
            const std::uint64_t semv = atom_sem;
            const std::uint64_t scov = atom_sco;
            std::string mem_order = "relaxed";
            if (semv == 2) mem_order = "acq_rel";
            else if (semv == 3) mem_order = "mmio";
            std::string scope;
            if (scov == 0) scope = "nosco";
            else if (scov == 1) scope = "cta";
            else if (scov == 2) scope = "sm";
            else if (scov == 3) scope = "vc";
            else if (scov == 4) scope = "gpu";
            else scope = "sys";
            // High-3: decode + validate the atomic BEFORE recording any race /
            // L2 event.  The race detector and L2 trace represent COMMITTED
            // memory accesses — an atomic that faults (unsupported op / FP /
            // SAFEADD / INVALID / 128-bit width / misaligned / OOB) must never
            // appear in the race log or the L2 access trace as if it happened.
            //
            // Blocker-4: decode the REAL atomic op.  FP atomics (ATOMICFPOPS),
            // SAFEADD, INVALID op slots and unsupported width/op combinations
            // fault as kNotSupported — they are NEVER silently downgraded to
            // ADD (INC/DEC were previously run as +1, MIN/MAX as unsigned).
            AtomicOp op = AtomicOp::kAdd;
            std::optional<AtomicOp> dec = decode_atomic_op(inst);
            if (cas_r != 255) {
                dec = AtomicOp::kCas;  // ATOM/ATOMS/ATOMG.CAS / .CAST
            }
            if (!dec) {
                if (fault) {
                    *fault = Fault(FaultKind::kUnsupportedInstruction,
                                   std::string(isa::mnemonic_name(inst.mnemonic)) + " atomic op is not "
                                   "implemented (never downgraded to ADD)")
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id))
                                 .set_active_mask(mask);
                }
                return Status::failure(Error::internal("memory fault"));
            }
            op = *dec;
            // CAS compare operand (Rc) for the compare-and-swap RMW.
            const MemValue* cmp = nullptr;
            MemValue cmp_val{};
            if (op == AtomicOp::kCas) {
                if (cas_r != 255) {
                    const std::uint64_t r = cas_r;
                    if (r != 255 && r < kNumGprs) {
                        cmp_val[0] = t.gpr[r];
                        if (wi.bytes > 4 && r + 1 < kNumGprs)
                            cmp_val[1] = t.gpr[r + 1];
                        if (wi.bytes > 8) {
                            if (r + 2 < kNumGprs) cmp_val[2] = t.gpr[r + 2];
                            if (r + 3 < kNumGprs) cmp_val[3] = t.gpr[r + 3];
                        }
                        cmp = &cmp_val;
                    }
                }
            }
            MemValue old{};
            Status st = (space == AddressSpace::kGlobal)
                ? memory_->atom_global(effective, wi.bytes, op, val, old, cmp)
                : MemoryService::atom_shared(ctas_[w.local_cta_id].shared,
                                             effective, wi.bytes, op, val, old,
                                             cmp);
            if (st.failed()) {
                if (fault) {
                    *fault = memory_error_to_fault(
                                 st.error(), pc,
                                 static_cast<std::uint32_t>(w.warp_id))
                                 .set_active_mask(mask);
                }
                return Status::failure(Error::internal("memory fault"));
            }
            // The RMW committed: NOW record the race access and the L2 access
            // (committed-access semantics).
            if (space == AddressSpace::kShared ||
                space == AddressSpace::kGlobal) {
                record_race_access(w, inst, pc, static_cast<std::uint32_t>(lane),
                                   space, effective, wi.bytes, true, true,
                                   mem_order, scope);
            }
            if (space == AddressSpace::kGlobal) {
                record_l2_access(w, inst, pc, mask, "atomic", space, effective,
                                 wi.bytes, static_cast<std::uint32_t>(lane));
            }
            // Phase 7 debug capture: the atomic RMW committed.
            record_debug_access(w, static_cast<std::uint32_t>(lane), space,
                                effective, wi.bytes, true, true);
            // Phase 8 profiler: record the committed lane byte range.
            prof_lanes[static_cast<std::size_t>(lane)] = {
                effective, wi.bytes, true};
            prof_committed |= (1u << lane);
            prof_space = space;
            prof_width = static_cast<std::uint32_t>(wi.bytes);
            // Write the pre-value back to Rd (ATOM) or Rd for ATOMS.
            if (rd_r != 255) {
                const std::uint64_t r = rd_r;
                if (r != 255 && r < kNumGprs) {
                    t.gpr[r] = old[0];
                    if (wi.bytes > 4 && r + 1 < kNumGprs) t.gpr[r + 1] = old[1];
                    if (wi.bytes > 8) {
                        if (r + 2 < kNumGprs) t.gpr[r + 2] = old[2];
                        if (r + 3 < kNumGprs) t.gpr[r + 3] = old[3];
                    }
                }
            }
            continue;
        }
        // Plain store.
        Status st = Status::success();
        if (space == AddressSpace::kGlobal) {
            st = memory_->stg(DevicePtr{0}, effective, 0, wi, val);
        } else if (space == AddressSpace::kShared) {
            st = MemoryService::sts(ctas_[w.local_cta_id].shared, effective, 0,
                                    wi, val);
        } else if (space == AddressSpace::kConstant) {
            // Constant stores are illegal (read-only) — model as a fault.
            if (fault) {
                *fault = Fault(FaultKind::kIllegalMemoryAccess,
                               "store to constant address space")
                             .set_pc(pc)
                             .set_warp(static_cast<std::uint32_t>(w.warp_id));
            }
            return Status::failure(Error::internal("memory fault"));
        } else {  // local
            st = MemoryService::sts(w.local, effective, 0, wi, val);
        }
        if (st.failed()) {
            if (fault) {
                *fault = memory_error_to_fault(
                             st.error(), pc,
                             static_cast<std::uint32_t>(w.warp_id))
                             .set_active_mask(mask);
            }
            return Status::failure(Error::internal("memory fault"));
        }
        // High-3: the store committed — only now record the race access and L2
        // access (committed-access semantics, matching the atomic path).  A
        // store that faulted (OOB / misaligned / constant) never appears in the
        // race log or the L2 trace as if it happened.
        if (space == AddressSpace::kShared || space == AddressSpace::kGlobal) {
            record_race_access(w, inst, pc, static_cast<std::uint32_t>(lane),
                               space, effective, wi.bytes, true, false, "", "");
        }
        if (space == AddressSpace::kGlobal) {
            record_l2_access(w, inst, pc, mask, "store", space, effective,
                             wi.bytes, static_cast<std::uint32_t>(lane));
        }
        // Phase 7 debug capture: the store committed.
        record_debug_access(w, static_cast<std::uint32_t>(lane), space,
                            effective, wi.bytes, true, false);
        // Phase 8 profiler: record the committed lane byte range.
        prof_lanes[static_cast<std::size_t>(lane)] = {effective, wi.bytes,
                                                      true};
        prof_committed |= (1u << lane);
        prof_space = space;
        prof_width = static_cast<std::uint32_t>(wi.bytes);
    }
    // Phase 6 Step 2B / Phase 8: emit the trace-only issue event with the
    // committed per-lane ranges (never changes the functional path above).
    {
        std::string kind = "load";
        if (is_atom) kind = "atomic";
        else if (!is_load) kind = "store";
        record_memory_event(w, inst, pc, mask, kind,
                            prof_width != 0 ? prof_width : static_cast<std::uint32_t>(mem_sz(inst).bytes),
                            prof_space, prof_is_write, prof_lanes,
                            prof_committed);
    }
    return Status::success();
}

Status Interpreter::do_ldg(WarpState& w, std::uint32_t mask,
                           const DecodedInstruction& inst, std::uint64_t pc,
                           std::optional<Fault>* fault) {
    // 5/7/8-op: Rd is the second named field in every LDG layout.
    const auto& d = *static_cast<const shape::DecodedLDG7_0*>(&inst);
    return mem_ldst_atom_core(w, mask, inst, pc, fault, true, false,
                              mem_ov_idx(d.Rd), 255, 255, 0, 0, 0);
}


Status Interpreter::do_stg(WarpState& w, std::uint32_t mask,
                           const DecodedInstruction& inst, std::uint64_t pc,
                           std::optional<Fault>* fault) {
    std::uint64_t rb_r = 255;
    if (inst.variant_class == isa::VariantClass::kstg__sImmOffset ||
        inst.variant_class == isa::VariantClass::kstg__uImmOffset) {
        rb_r = mem_ov_idx(
            static_cast<const shape::DecodedSTG3*>(&inst)->Rb);
    } else if (inst.variant_class == isa::VariantClass::kstg_uniform__Ra32 ||
               inst.variant_class == isa::VariantClass::kstg_uniform__Ra64 ||
               inst.variant_class == isa::VariantClass::kstg_uniform__RaRZ ||
               inst.variant_class == isa::VariantClass::kstg_256_uniform__Ra32 ||
               inst.variant_class == isa::VariantClass::kstg_256_uniform__Ra64 ||
               inst.variant_class == isa::VariantClass::kstg_256_uniform__RaRZ) {
        rb_r = mem_ov_idx(
            static_cast<const shape::DecodedSTG4*>(&inst)->Rb);
    } else {  // kstg_memdesc__Ra64 / kstg_256_memdesc__Ra64
        rb_r = mem_ov_idx(
            static_cast<const shape::DecodedSTG5*>(&inst)->Rb);
    }
    return mem_ldst_atom_core(w, mask, inst, pc, fault, false, false,
                              255, rb_r, 255, 0, 0, 0);
}


Status Interpreter::do_lds(WarpState& w, std::uint32_t mask,
                           const DecodedInstruction& inst, std::uint64_t pc,
                           std::optional<Fault>* fault) {
    const auto& o = *static_cast<const shape::DecodedLDS3*>(&inst);
    return mem_ldst_atom_core(w, mask, inst, pc, fault, true, false,
                              mem_ov_idx(o.Rd), 255, 255, 0, 0, 0);
}


Status Interpreter::do_sts(WarpState& w, std::uint32_t mask,
                           const DecodedInstruction& inst, std::uint64_t pc,
                           std::optional<Fault>* fault) {
    // 3/4-op: Rb is the third named field in both layouts.
    const auto& o = *static_cast<const shape::DecodedSTS3*>(&inst);
    return mem_ldst_atom_core(w, mask, inst, pc, fault, false, false,
                              255, mem_ov_idx(o.Rb), 255, 0, 0, 0);
}


Status Interpreter::do_ldl(WarpState& w, std::uint32_t mask,
                           const DecodedInstruction& inst, std::uint64_t pc,
                           std::optional<Fault>* fault) {
    const auto& o = *static_cast<const shape::DecodedLDL3*>(&inst);
    return mem_ldst_atom_core(w, mask, inst, pc, fault, true, false,
                              mem_ov_idx(o.Rd), 255, 255, 0, 0, 0);
}


Status Interpreter::do_stl(WarpState& w, std::uint32_t mask,
                           const DecodedInstruction& inst, std::uint64_t pc,
                           std::optional<Fault>* fault) {
    const auto& o = *static_cast<const shape::DecodedSTL3*>(&inst);
    return mem_ldst_atom_core(w, mask, inst, pc, fault, false, false,
                              255, mem_ov_idx(o.Rb), 255, 0, 0, 0);
}


Status Interpreter::do_ldc(WarpState& w, std::uint32_t mask,
                           const DecodedInstruction& inst, std::uint64_t pc,
                           std::optional<Fault>* fault) {
    const auto& o = *static_cast<const shape::DecodedLDC5_0*>(&inst);
    return mem_ldst_atom_core(w, mask, inst, pc, fault, true, false,
                              mem_ov_idx(o.Rd), 255, 255, 0, 0, 0);
}


Status Interpreter::do_atom(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst, std::uint64_t pc,
                            std::optional<Fault>* fault) {
    const isa::VariantClass cls = inst.variant_class;
    if (cls == isa::VariantClass::katom_cas__RaNonRZ_CAS ||
        cls == isa::VariantClass::katom_cas__RaNonRZ_CAST ||
        cls == isa::VariantClass::katom_cas__RaRZ_CAS ||
        cls == isa::VariantClass::katom_cas__RaRZ_CAST) {
        const auto& d = *static_cast<const shape::DecodedATOM7_1*>(&inst);
        return mem_ldst_atom_core(w, mask, inst, pc, fault, false, true,
                                  mem_ov_idx(d.Rd), mem_ov_idx(d.Rb),
                                  mem_ov_idx(d.Rc),
                                  static_cast<std::uint64_t>(d.sz),
                                  static_cast<std::uint64_t>(d.sem),
                                  static_cast<std::uint64_t>(d.sco));
    }
    if (cls == isa::VariantClass::katom_int_uniform__Ra32 ||
        cls == isa::VariantClass::katom_int_uniform__Ra64 ||
        cls == isa::VariantClass::katom_int_uniform__RaRZ ||
        cls == isa::VariantClass::katom_fp_uniform__Ra32 ||
        cls == isa::VariantClass::katom_fp_uniform__Ra64 ||
        cls == isa::VariantClass::katom_fp_uniform__RaRZ) {
        const auto& d = *static_cast<const shape::DecodedATOM7_0*>(&inst);
        return mem_ldst_atom_core(w, mask, inst, pc, fault, false, true,
                                  mem_ov_idx(d.Rd), mem_ov_idx(d.Rb),
                                  mem_ov_idx(d.Ra_offset),
                                  static_cast<std::uint64_t>(d.sz),
                                  static_cast<std::uint64_t>(d.sem),
                                  static_cast<std::uint64_t>(d.sco));
    }
    if (cls == isa::VariantClass::katom_arrive__Ra32_arrive ||
        cls == isa::VariantClass::katom_arrive__Ra32_popcinc ||
        cls == isa::VariantClass::katom_arrive__Ra64_arrive ||
        cls == isa::VariantClass::katom_arrive__Ra64_popcinc ||
        cls == isa::VariantClass::katom_arrive__RaRZ_arrive ||
        cls == isa::VariantClass::katom_arrive__RaRZ_popcinc) {
        const auto& d = *static_cast<const shape::DecodedATOM6_0*>(&inst);
        return mem_ldst_atom_core(w, mask, inst, pc, fault, false, true,
                                  mem_ov_idx(d.Rd), mem_ov_idx(d.Ra_offset),
                                  255, static_cast<std::uint64_t>(d.sz),
                                  static_cast<std::uint64_t>(d.sem),
                                  static_cast<std::uint64_t>(d.sco));
    }
    // katom_{int,fp}__RaNonRZ/RaRZ (6-op plain): rb is the fifth field.
    const auto& d = *static_cast<const shape::DecodedATOM6_1*>(&inst);
    return mem_ldst_atom_core(w, mask, inst, pc, fault, false, true,
                              mem_ov_idx(d.Rd), mem_ov_idx(d.Rb), 255,
                              static_cast<std::uint64_t>(d.sz),
                              static_cast<std::uint64_t>(d.sem),
                              static_cast<std::uint64_t>(d.sco));
}


Status Interpreter::do_atoms(WarpState& w, std::uint32_t mask,
                             const DecodedInstruction& inst, std::uint64_t pc,
                             std::optional<Fault>* fault) {
    const isa::VariantClass cls = inst.variant_class;
    if (cls == isa::VariantClass::katoms_cas__RaNonRZ ||
        cls == isa::VariantClass::katoms_cas__RaRZ ||
        cls == isa::VariantClass::katoms_cast_destRd__RaNonRZ ||
        cls == isa::VariantClass::katoms_cast_destRd__RaRZ) {
        const auto& d = *static_cast<const shape::DecodedATOMS5_2*>(&inst);
        return mem_ldst_atom_core(w, mask, inst, pc, fault, false, true,
                                  mem_ov_idx(d.Rd), mem_ov_idx(d.Rb),
                                  mem_ov_idx(d.Rc),
                                  static_cast<std::uint64_t>(d.sz), 1, 0);
    }
    if (cls == isa::VariantClass::katoms_cast_destPu__RaNonRZ ||
        cls == isa::VariantClass::katoms_cast_destPu__RaRZ) {
        const auto& d = *static_cast<const shape::DecodedATOMS5_0*>(&inst);
        return mem_ldst_atom_core(w, mask, inst, pc, fault, false, true,
                                  static_cast<std::uint64_t>(
                                      shape::operand_value_as_i64(d.Pu)),
                                  mem_ov_idx(d.Rb), mem_ov_idx(d.Rc),
                                  static_cast<std::uint64_t>(d.sz), 1, 0);
    }
    if (cls == isa::VariantClass::katoms_uniform_) {
        const auto& d = *static_cast<const shape::DecodedATOMS5_1*>(&inst);
        return mem_ldst_atom_core(w, mask, inst, pc, fault, false, true,
                                  mem_ov_idx(d.Rd), mem_ov_idx(d.Rb),
                                  mem_ov_idx(d.Ra_offset),
                                  static_cast<std::uint64_t>(d.sz), 1, 0);
    }
    if (cls == isa::VariantClass::katoms_arrive__arrive ||
        cls == isa::VariantClass::katoms_arrive__popcinc) {
        const auto& d = *static_cast<const shape::DecodedATOMS4_0*>(&inst);
        return mem_ldst_atom_core(w, mask, inst, pc, fault, false, true,
                                  mem_ov_idx(d.Rd), mem_ov_idx(d.Ra_offset),
                                  255, static_cast<std::uint64_t>(d.sz), 1, 0);
    }
    // katoms__RaNonRZ / katoms__RaRZ (4-op plain): rb is the last field.
    const auto& d = *static_cast<const shape::DecodedATOMS4_1*>(&inst);
    return mem_ldst_atom_core(w, mask, inst, pc, fault, false, true,
                              mem_ov_idx(d.Rd), mem_ov_idx(d.Rb), 255,
                              static_cast<std::uint64_t>(d.sz), 1, 0);
}


Status Interpreter::do_reds(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst, std::uint64_t pc,
                            std::optional<Fault>* fault) {
    if (inst.variant_class == isa::VariantClass::katoms_reds_uniform_) {
        const auto& o = *static_cast<const shape::DecodedREDS4*>(&inst);
        return mem_ldst_atom_core(
            w, mask, inst, pc, fault, false, true, 255, mem_ov_idx(o.Rb),
            255, static_cast<std::uint64_t>(o.sz), 1, 0);
    }
    const auto& o = *static_cast<const shape::DecodedREDS3*>(&inst);
    return mem_ldst_atom_core(
        w, mask, inst, pc, fault, false, true, 255, mem_ov_idx(o.Rb), 255,
        static_cast<std::uint64_t>(o.sz), 1, 0);
}


Status Interpreter::do_atomg(WarpState& w, std::uint32_t mask,
                             const DecodedInstruction& inst, std::uint64_t pc,
                             std::optional<Fault>* fault) {
    const isa::VariantClass cls = inst.variant_class;
    if (cls == isa::VariantClass::katomg_fp__RaNonRZ ||
        cls == isa::VariantClass::katomg_fp__RaRZ ||
        cls == isa::VariantClass::katomg_int__RaNonRZ ||
        cls == isa::VariantClass::katomg_int__RaRZ) {
        const auto& o = *static_cast<const shape::DecodedATOMG5*>(&inst);
        return mem_ldst_atom_core(
            w, mask, inst, pc, fault, false, true, mem_ov_idx(o.Rd),
            mem_ov_idx(o.Rb), 255, static_cast<std::uint64_t>(o.sz),
            static_cast<std::uint64_t>(o.sem),
            static_cast<std::uint64_t>(o.sco));
    }
    if (cls == isa::VariantClass::katomg_fp_uniform__memdesc ||
        cls == isa::VariantClass::katomg_int_uniform__memdesc) {
        const auto& o = *static_cast<const shape::DecodedATOMG7*>(&inst);
        return mem_ldst_atom_core(
            w, mask, inst, pc, fault, false, true, mem_ov_idx(o.Rd),
            mem_ov_idx(o.Rb), mem_ov_idx(o.Ra_offset),
            static_cast<std::uint64_t>(o.sz),
            static_cast<std::uint64_t>(o.sem),
            static_cast<std::uint64_t>(o.sco));
    }
    if (cls == isa::VariantClass::katomg_cas__RaNonRZ ||
        cls == isa::VariantClass::katomg_cas__RaRZ) {
        const auto& d = *static_cast<const shape::DecodedATOMG6_1*>(&inst);
        return mem_ldst_atom_core(w, mask, inst, pc, fault, false, true,
                                  mem_ov_idx(d.Rd), mem_ov_idx(d.Rb),
                                  mem_ov_idx(d.Rc),
                                  static_cast<std::uint64_t>(d.sz),
                                  static_cast<std::uint64_t>(d.sem),
                                  static_cast<std::uint64_t>(d.sco));
    }
    // katomg_{int,fp}_uniform__Ra32/64/Rz (6-op split 0).
    const auto& d = *static_cast<const shape::DecodedATOMG6_0*>(&inst);
    return mem_ldst_atom_core(w, mask, inst, pc, fault, false, true,
                              mem_ov_idx(d.Rd), mem_ov_idx(d.Rb), 255,
                              static_cast<std::uint64_t>(d.sz),
                              static_cast<std::uint64_t>(d.sem),
                              static_cast<std::uint64_t>(d.sco));
}


Status Interpreter::do_redg(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst, std::uint64_t pc,
                            std::optional<Fault>* fault) {
    // REDG forms: kredg_{fp,int}__* (3-op, rb@2), kredg_*_uniform__memdesc
    // (5-op, rb@4; sz/sem/sco through the REDG4 cast — preserved quirk), and
    // kredg_*_uniform__Ra32/64/Rz (4-op uniform, rb@3).
    if (inst.variant_class == isa::VariantClass::kredg_fp__RaNonRZ ||
        inst.variant_class == isa::VariantClass::kredg_fp__RaRZ ||
        inst.variant_class == isa::VariantClass::kredg_int__RaNonRZ ||
        inst.variant_class == isa::VariantClass::kredg_int__RaRZ) {
        const auto& o = *static_cast<const shape::DecodedREDG3*>(&inst);
        return mem_ldst_atom_core(
            w, mask, inst, pc, fault, false, true, 255, mem_ov_idx(o.Rb), 255,
            static_cast<std::uint64_t>(o.sz),
            static_cast<std::uint64_t>(o.sem),
            static_cast<std::uint64_t>(o.sco));
    }
    if (inst.variant_class == isa::VariantClass::kredg_fp_uniform__memdesc ||
        inst.variant_class == isa::VariantClass::kredg_int_uniform__memdesc) {
        const auto& o4 = *static_cast<const shape::DecodedREDG4*>(&inst);
        return mem_ldst_atom_core(
            w, mask, inst, pc, fault, false, true, 255, mem_ov_idx(o4.Rb),
            255, static_cast<std::uint64_t>(o4.sz),
            static_cast<std::uint64_t>(o4.sem),
            static_cast<std::uint64_t>(o4.sco));
    }
    const auto& o = *static_cast<const shape::DecodedREDG4*>(&inst);
    return mem_ldst_atom_core(
        w, mask, inst, pc, fault, false, true, 255, mem_ov_idx(o.Rb), 255,
        static_cast<std::uint64_t>(o.sz),
        static_cast<std::uint64_t>(o.sem),
        static_cast<std::uint64_t>(o.sco));
}


Status Interpreter::do_membar(WarpState& w, const DecodedInstruction& inst) {
    memory_->membar();
    if (race_detector_ && race_detector_->enabled()) {
        std::string scope = "gpu";
        // sco member present on membar_ / membar_async_ only (the tma
        // barrier form has no cohere-scope field).
        std::uint64_t scov = 2;
        if (inst.variant_class == isa::VariantClass::kmembar_ ||
            inst.variant_class == isa::VariantClass::kmembar_async_) {
            scov = static_cast<std::uint64_t>(
                static_cast<const shape::DecodedMEMBAR0*>(&inst)->sco);
        }
        if (scov == 0) scope = "cta";
        else if (scov == 1) scope = "sm";
        else if (scov == 3) scope = "sys";
        else if (scov == 5) scope = "vc";
        else scope = "gpu";
        RaceEvent ev;
        ev.kind = RaceEvent::kFence;
        ev.cta = static_cast<std::uint32_t>(w.cta_id);
        ev.sm = sm_of_cta(static_cast<std::uint32_t>(w.cta_id));
        ev.ordinal = race_ordinal_[ev.cta]++;
        ev.warp = static_cast<std::uint32_t>(w.warp_id);
        ev.scope = std::move(scope);
        race_log_.push_back(std::move(ev));
    }
    return Status::success();
}

Status Interpreter::do_fence(WarpState& w) {
    memory_->membar();
    if (race_detector_ && race_detector_->enabled()) {
        // FENCE (fence.g / fence.membar.gl): gpu scope.
        RaceEvent ev;
        ev.kind = RaceEvent::kFence;
        ev.cta = static_cast<std::uint32_t>(w.cta_id);
        ev.sm = sm_of_cta(static_cast<std::uint32_t>(w.cta_id));
        ev.ordinal = race_ordinal_[ev.cta]++;
        ev.warp = static_cast<std::uint32_t>(w.warp_id);
        ev.scope = "gpu";
        race_log_.push_back(std::move(ev));
    }
    return Status::success();
}

Status Interpreter::do_errbar(WarpState& w, const DecodedInstruction& inst,
                              std::uint64_t pc) {
    (void)w; (void)inst; (void)pc;
    // Cache/error-reporting barrier emitted around MEMBAR (IVALL): functional
    // no-op in the single-writer model.
    return Status::success();
}

Status Interpreter::do_cgaerrbar(WarpState& w, const DecodedInstruction& inst,
                                  std::uint64_t pc) {
    (void)w; (void)inst; (void)pc;
    // Cluster-level error barrier: functional no-op in the single-writer
    // model.
    return Status::success();
}

Status Interpreter::do_cctl(WarpState& w, const DecodedInstruction& inst,
                            std::uint64_t pc) {
    (void)w; (void)inst; (void)pc;
    // Cache control (IVALL/WBALL around MEMBAR): functional no-op.
    return Status::success();
}

// Deterministic CTA -> SM mapping (High-3): with simulated_sm_count > 1 the
// CTA's SM is cta % count (explicit multi-SM topology shared by the race, L2
// and subcore layers); with 1 the launch's env_.sm_id applies.
std::uint32_t Interpreter::sm_of_cta(std::uint32_t cta) const {
    const std::uint32_t n =
        options_.model.simulated_sm_count > 0
            ? options_.model.simulated_sm_count
            : 1;
    if (n > 1) return cta % n;
    return static_cast<std::uint32_t>(env_.sm_id);
}

// ---------------------------------------------------------------------------
// Phase 9 subset: mbarrier / TMA / cp.async functional handlers
// ---------------------------------------------------------------------------

// Resolve a shared byte offset into the (CTA-local index, offset) pair.
// When clusters are enabled and the address's high byte is a nonzero cluster
// rank, translate to the peer CTA's shared window (DSMEM).  Cross-CTA access
// only works when the target CTA is present in THIS interpreter instance
// (single worker / the worker owning that CTA); otherwise it is a structured
// error.
std::optional<Interpreter::SharedTarget> Interpreter::resolve_shared_target(
    const WarpState& w, std::uint32_t shared_addr,
    std::optional<Fault>* fault) {
    SharedTarget out;
    const std::uint32_t rank = shared_addr >> 24;
    const std::uint32_t off = shared_addr & 0xFFFFFF;
    if (!cluster_topology_ || rank == 0) {
        out.cta_local_idx = static_cast<std::size_t>(w.local_cta_id);
        out.offset = shared_addr;
        out.target_rank = 0;
        return out;
    }
    // DSMEM: rank -> grid-linear target CTA within the source CTA's cluster.
    const std::uint64_t src_cta = static_cast<std::uint64_t>(w.cta_id);
    const std::uint64_t cluster = cluster_topology_->cluster_id(src_cta);
    if (!cluster_topology_->valid_rank(rank)) {
        if (fault) {
            *fault = Fault(FaultKind::kIllegalMemoryAccess,
                           "DSMEM rank " + std::to_string(rank) +
                               " out of range for cluster size " +
                               std::to_string(cluster_topology_->cluster_size()))
                         .set_warp(static_cast<std::uint32_t>(w.warp_id));
        }
        return std::nullopt;
    }
    const std::uint64_t tgt_cta =
        cluster_topology_->grid_cta(cluster, rank);
    // Find the target CTA's local index (must be in this worker's subset).
    std::size_t local = 0;
    bool found = false;
    for (; local < ctas_.size(); ++local) {
        if (ctas_[local].cta_id == static_cast<int>(tgt_cta)) {
            found = true;
            break;
        }
    }
    if (!found) {
        if (fault) {
            *fault = Fault(
                FaultKind::kUnsupportedInstruction,
                "DSMEM target CTA " + std::to_string(tgt_cta) +
                    " is not owned by this interpreter worker (cluster "
                    "cross-CTA access requires single-worker determinism)")
                    .set_warp(static_cast<std::uint32_t>(w.warp_id));
        }
        return std::nullopt;
    }
    out.cta_local_idx = local;
    out.offset = off;
    out.target_rank = rank;
    return out;
}

// Look up (or lazily create from the shared word) the mbarrier state for a
// shared byte offset in the source CTA.  Returns null when the shared
// address is out of the window.
MbarrierState* Interpreter::mbarrier_at(CtaState& cta,
                                        std::uint32_t shared_off,
                                        bool create_if_missing) {
    auto it = cta.mbarriers.find(shared_off);
    if (it != cta.mbarriers.end()) return &it->second;
    if (!create_if_missing) return nullptr;
    // Read the current 64-bit word at the shared offset (may be an
    // uninitialized/zero barrier; SYNCS.ARRIVE on it faults as not-initialized
    // unless the program initialized it with SYNCS.EXCH.64 first).
    MbarrierState s;
    if (shared_off <= cta.shared.size() &&
        shared_off + 8 <= cta.shared.size()) {
        std::uint64_t word = 0;
        for (int i = 0; i < 8; ++i)
            word |= static_cast<std::uint64_t>(cta.shared[shared_off + i])
                    << (8 * i);
        // A zero word is a valid "uninitialized" marker: keep initialized=false
        // so the first ARRIVE faults (matches the boundary tests).  A non-zero
        // word (written by SYNCS.EXCH.64 / STS init) seeds the logical state.
        if (word != 0) s = MbarrierState::from_init_word(word);
    }
    auto [it2, _] = cta.mbarriers.emplace(shared_off, s);
    return &it2->second;
}

// Functional LDGSTS (cp.async): perform the global->shared copy per active
// lane and accumulate committed bytes into the CTA's open async group.  Also
// records the trace-only coupled prediction (kept from the old trace-only
// path).
Status Interpreter::do_ldgsts(WarpState& w, std::uint32_t mask,
                              const DecodedInstruction& inst, std::uint64_t pc,
                              std::optional<Fault>* fault) {
    CtaState& cta = ctas_[static_cast<std::size_t>(w.local_cta_id)];
    std::uint32_t goff[kLanesPerWarp] = {};
    std::uint32_t soff[kLanesPerWarp] = {};
    // LDGSTS layouts vary: 6-op A [Rb,Rb_URc,Rb_offset,Ra,Ra_offset,Pnz];
    // 6-op B [Rb,Rb_offset,Ra,Ra_URc,Ra_offset,Pnz]; 7-op memdesc
    // [Rb,Rb_URc,Rb_offset,memdesc,Ra_URd,Ra,Ra_offset,Pnz]; 7-op desc_RRU
    // [Rb,Rb_offset,memdesc,Ra_URc,Ra,Ra_offset,Pnz].  Distinguish by the
    // kind of ops[1] (uniform register => A/memdesc, immediate => B/desc_RRU).
    std::uint64_t wide = 0, szv = 0;
    // LDGSTS6 (RUR/RR32U/RR64U/no-ra) vs kldgsts__desc_RRU (7-op) and
    // kldgsts_memdesc_ (8-op) — each form reads its own named fields.  The
    // shared-side base register (ops[0]) always is the `Rb` role; the
    // offset roles are Rb_offset / Ra_offset; the global base is `Ra`.
    const shape::OperandValue* sbase_op = nullptr;
    const shape::OperandValue* goff_op = nullptr;
    const shape::OperandValue* soff_op = nullptr;
    const shape::OperandValue* gbase_op = nullptr;
    // Uniform base (Ra_URc / Ra_URd) contributes the high 32 bits on the
    // RR/memdesc layouts; the RUR layouts carry none (base stays 0).
    std::uint64_t ur_base = 0;
    if (inst.variant_class != isa::VariantClass::kldgsts__desc_RRU &&
        inst.variant_class != isa::VariantClass::kldgsts_memdesc_) {
        const bool is_rur =
            inst.variant_class == isa::VariantClass::kldgsts__RUR ||
            inst.variant_class == isa::VariantClass::kldgsts_no_ra__RUR;
        if (is_rur) {
            const auto& d = *static_cast<const shape::DecodedLDGSTS6_0*>(&inst);
            wide = static_cast<std::uint64_t>(d.input_reg_sz_64_dist);
            szv = static_cast<std::uint64_t>(d.sz);
            sbase_op = &d.Rb; gbase_op = &d.Ra;
            goff_op = &d.Ra_offset; soff_op = &d.Rb_offset;
        } else {
            const auto& d = *static_cast<const shape::DecodedLDGSTS6_1*>(&inst);
            wide = static_cast<std::uint64_t>(d.input_reg_sz_64_dist);
            szv = static_cast<std::uint64_t>(d.sz);
            sbase_op = &d.Rb; gbase_op = &d.Ra;
            goff_op = &d.Ra_offset; soff_op = &d.Rb_offset;
            ur_base = read_ur_pair_ov(w, d.Ra_URc);
        }
    } else if (inst.variant_class == isa::VariantClass::kldgsts_memdesc_) {
        // 8-op memdesc: [Rb,Rb_URc,Rb_offset,memdesc,Ra_URd,Ra,Ra_offset,Pnz]
        const auto& d = *static_cast<const shape::DecodedLDGSTS8*>(&inst);
        wide = static_cast<std::uint64_t>(d.input_reg_sz_64_dist);
        szv = static_cast<std::uint64_t>(d.sz);
        sbase_op = &d.Rb; gbase_op = &d.Ra;
        goff_op = &d.Ra_offset; soff_op = &d.Rb_offset;
        ur_base = read_ur_pair_ov(w, d.Ra_URd);
    } else {
        // 7-op desc_RRU: [Rb,Rb_offset,memdesc,Ra_URc,Ra,Ra_offset,Pnz]
        const auto& d = *static_cast<const shape::DecodedLDGSTS7*>(&inst);
        wide = static_cast<std::uint64_t>(d.input_reg_sz_64_dist);
        szv = static_cast<std::uint64_t>(d.sz);
        sbase_op = &d.Rb; gbase_op = &d.Ra;
        goff_op = &d.Ra_offset; soff_op = &d.Rb_offset;
        ur_base = read_ur_pair_ov(w, d.Ra_URc);
    }
    const std::int64_t rao_v = shape::operand_value_as_i64(*goff_op);
    const std::int64_t rbo_v = shape::operand_value_as_i64(*soff_op);
    const std::uint32_t ew = szv == 1 ? 8u : szv == 2 ? 16u : 4u;

    std::uint32_t goff_valid_mask = 0;
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        const std::uint64_t s = read_reg_ov(t, *sbase_op);
        std::uint64_t g = 0;
        if (wide) {
            g = read_addr_pair_ov(t, *gbase_op);
        } else {
            g = read_reg_ov(t, *gbase_op);
        }
        std::uint64_t gadd = 0, gv = 0, sv = 0;
        if (!checked_uadd(g, ur_base, &gadd) ||
            !checked_add(gadd, rao_v, &gv) ||
            !checked_add(s, rbo_v, &sv)) {
            continue;  // lane excluded: address computation failed
        }
        goff[lane] = static_cast<std::uint32_t>(gv);
        soff[lane] = static_cast<std::uint32_t>(sv);
        goff_valid_mask |= (1u << lane);
        MemValue val{};
        Status st = memory_->ldg(DevicePtr{0}, gv, 0,
                                 MemWidthInfo{ew, false, true}, val);
        if (st.failed()) {
            if (fault) {
                *fault = memory_error_to_fault(
                             st.error(), pc,
                             static_cast<std::uint32_t>(w.warp_id))
                             .set_active_mask(mask & (1u << lane));
            }
            return Status::failure(Error::internal("memory fault"));
        }
        if (sv > cta.shared.size() || ew > cta.shared.size() - sv) {
            if (fault) {
                *fault = Fault(FaultKind::kIllegalMemoryAccess,
                               "LDGSTS shared destination out of bounds")
                             .set_pc(pc)
                             .set_warp(static_cast<std::uint32_t>(w.warp_id))
                             .set_active_mask(mask & (1u << lane));
            }
            return Status::failure(Error::internal("memory fault"));
        }
        for (std::uint32_t i = 0; i < ew; ++i) {
            cta.shared[sv + i] =
                static_cast<std::uint8_t>((val[i / 4] >> (8 * (i % 4))) & 0xff);
        }
        // Race + profiler observability: the committed global read range and
        // the shared write range.
        if (race_detector_ && race_detector_->enabled()) {
            record_race_access(w, inst, pc, static_cast<std::uint32_t>(lane),
                               AddressSpace::kGlobal, gv, ew, false, false, "",
                               "");
            record_race_access(w, inst, pc, static_cast<std::uint32_t>(lane),
                               AddressSpace::kShared, sv, ew, true, false, "",
                               "");
        }
    }
    // cp.async committed-bytes accounting: each lane commits `ew` bytes.
    const std::uint32_t committed = static_cast<std::uint32_t>(
        __builtin_popcount(goff_valid_mask)) * ew;
    if (committed) {
        cta.async_open.copies.push_back(
            CtaState::AsyncCopy{committed, 0});
        cta.async_open.committed_bytes += committed;
    }
    // Trace-only coupled prediction (kept for the L1TEX profiler).  The
    // coupled event carries ldgsts_goff/ldgsts_soff, which the profiler uses
    // to recompute the extended access-set counters — so no separate raw
    // event is emitted here (the profiler's expansion must match this
    // functional copy exactly; tests verify that).
    if (options_.model.l1tex == L1TexMode::kTraceOnly) {
        record_coupled_l1_to_shared(w, inst, pc, goff_valid_mask, goff, soff,
                                    ew, goff_valid_mask != mask);
    }
    // Phase 7 debug capture: shared writes committed.
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(goff_valid_mask & (1u << lane))) continue;
        record_debug_access(w, static_cast<std::uint32_t>(lane),
                            AddressSpace::kShared, soff[lane], ew, true, false);
    }
    return Status::success();
}

// LDGDEPBAR: seal the open async group and count it on the target SB.
Status Interpreter::do_syncs(WarpState& w, std::uint32_t mask,
                             const DecodedInstruction& inst, std::uint64_t pc,
                             std::optional<Fault>* fault) {
    const std::uint16_t op = semu::opcode_of(inst.word.lo, inst.word.hi);
    // Guard: SYNCS.EXCH/CAS/LD are uniform-predicate guarded (@UPg); the
    // others carry a per-lane Pg (typically PT).  resolve_guard returns true
    // for PT; for uniform predicates the group already filtered per-lane.  We
    // accept an all-zeros guard meaning "every lane skipped" — execute_group
    // already returned for exec_mask == 0.
    (void)mask;

    // Operand layouts are FIXED per opcode — every SYNCS opcode has one
    // deterministic role order (ARRIVE and TCNT share 0x19a7 and are told
    // apart by variant class; they differ only in the [Ra,..] anchor + Rb
    // position):
    //   ARRIVE    0x19a7 arr [Rd,Ra,Ra_URc,Ra_offset,Rb]  trio 1,2,3 Rb@4
    //   TCNT      0x19a7 tcnt[Ra,Ra_URc,Ra_offset,Rb]      trio 0,1,2 Rb@3
    //   PHASECHK  0x15a7     [Pu,Ra,Ra_URc,Ra_offset,Rb]   trio 1,2,3 Rb@4
    //   LD        0x15b1     [Rd,Ra,Ra_URc,Ra_offset]      trio 1,2,3
    //   CCTL      0x19b1     [Ra,Ra_URc,Ra_offset]         trio 0,1,2
    //   CCTL.ALL  0x9b1 / FLUSH 0x3a7                      (no address)
    //   EXCH      0x15b2     [UPg,URd,URa,URa_offset,URb]  URa@2 off@3
    //   CAS       0x13b2     [UPg,URd,URa,URa_offset,URb,URc]
    //   LD.64     0x19b2     [UPg,URd,URa,URa_offset]
    // Shared target = [Ra + URc + Ra_offset] (Ra is RZ for mbarrier ops);
    // the uniform forms use [URa + URa_offset]; each opcode reads the named
    // fields of its concrete DecodedSYNCS*_k struct.
    std::uint32_t addr = 0;
    switch (op) {
        case 0x19a7:  // ARRIVE vs TCNT (variant-class discriminated)
            if (inst.variant_class == isa::VariantClass::ksyncs_arrive_) {
                const auto& d =
                    *static_cast<const shape::DecodedSYNCS5_1*>(&inst);
                addr = static_cast<std::uint32_t>(
                    read_reg_ov(w.threads[0], d.Ra) +
                    read_ur_ov(w, d.Ra_URc) +
                    static_cast<std::uint64_t>(
                        shape::operand_value_as_i64(d.Ra_offset)));
            } else {
                const auto& d =
                    *static_cast<const shape::DecodedSYNCS4_2*>(&inst);
                addr = static_cast<std::uint32_t>(
                    read_reg_ov(w.threads[0], d.Ra) +
                    read_ur_ov(w, d.Ra_URc) +
                    static_cast<std::uint64_t>(
                        shape::operand_value_as_i64(d.Ra_offset)));
            }
            break;
        case 0x15a7: {  // PHASECHK
            const auto& d =
                *static_cast<const shape::DecodedSYNCS5_0*>(&inst);
            addr = static_cast<std::uint32_t>(
                read_reg_ov(w.threads[0], d.Ra) +
                read_ur_ov(w, d.Ra_URc) +
                static_cast<std::uint64_t>(
                    shape::operand_value_as_i64(d.Ra_offset)));
            break;
        }
        case 0x15b1: {  // LD
            const auto& d =
                *static_cast<const shape::DecodedSYNCS4_0*>(&inst);
            addr = static_cast<std::uint32_t>(
                read_reg_ov(w.threads[0], d.Ra) +
                read_ur_ov(w, d.Ra_URc) +
                static_cast<std::uint64_t>(
                    shape::operand_value_as_i64(d.Ra_offset)));
            break;
        }
        case 0x19b1: {  // CCTL
            const auto& d =
                *static_cast<const shape::DecodedSYNCS3*>(&inst);
            addr = static_cast<std::uint32_t>(
                read_reg_ov(w.threads[0], d.Ra) +
                read_ur_ov(w, d.Ra_URc) +
                static_cast<std::uint64_t>(
                    shape::operand_value_as_i64(d.Ra_offset)));
            break;
        }
        case 0x15b2: {  // EXCH
            const auto& d =
                *static_cast<const shape::DecodedSYNCS5_2*>(&inst);
            addr = static_cast<std::uint32_t>(
                read_ur_ov(w, d.URa) +
                static_cast<std::uint64_t>(
                    shape::operand_value_as_i64(d.URa_offset)));
            break;
        }
        case 0x13b2: {  // CAS
            const auto& d =
                *static_cast<const shape::DecodedSYNCS6*>(&inst);
            addr = static_cast<std::uint32_t>(
                read_ur_ov(w, d.URa) +
                static_cast<std::uint64_t>(
                    shape::operand_value_as_i64(d.URa_offset)));
            break;
        }
        case 0x19b2: {  // LD.64
            const auto& d =
                *static_cast<const shape::DecodedSYNCS6*>(&inst);
            addr = static_cast<std::uint32_t>(
                read_ur_ov(w, d.URa) +
                static_cast<std::uint64_t>(
                    shape::operand_value_as_i64(d.URa_offset)));
            break;
        }
        default:  // CCTL.ALL / FLUSH: no shared target
            break;
    }

    CtaState* cta = &ctas_[static_cast<std::size_t>(w.local_cta_id)];
    // Uniform atomics operate on the CURRENT CTA's shared window (no DSMEM
    // translation needed — EXCH/CAS/LD are local shared memory ops).
    switch (op) {
        case 0x19a7: {  // ARRIVE / TCNT (expect_tx/complete_tx; same opcode)
            std::uint64_t paramtype = 0, retval = 0;
            const shape::OperandValue* rd_op = nullptr;
            if (inst.variant_class == isa::VariantClass::ksyncs_arrive_) {
                // SYNCS5 split 1 = ARRIVE (paramtype/retval members).
                const auto& d =
                    *static_cast<const shape::DecodedSYNCS5_1*>(&inst);
                paramtype = static_cast<std::uint64_t>(d.paramtype);
                retval = static_cast<std::uint64_t>(d.retval);
                rd_op = &d.Rd;
            } else {
                // SYNCS4 split 2 = TCNT (retval member; Rb@3).
                const auto& d =
                    *static_cast<const shape::DecodedSYNCS4_2*>(&inst);
                retval = static_cast<std::uint64_t>(d.retval);
            }
            auto* st = mbarrier_at(*cta, addr, /*create_if_missing=*/true);
            if (!st) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess,
                                   "SYNCS.ARRIVE at out-of-window shared "
                                   "address")
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            const std::uint64_t rv =
                (inst.variant_class == isa::VariantClass::ksyncs_arrive_)
                    ? read_reg_ov(
                          w.threads[0],
                          static_cast<const shape::DecodedSYNCS5_1&>(inst).Rb)
                    : read_reg_ov(
                          w.threads[0],
                          static_cast<const shape::DecodedSYNCS4_2&>(inst)
                              .Rb);  // Rb
            std::uint32_t inc = 0;
            std::uint64_t tx = 0;
            bool tx_is_complete = false;
            switch (paramtype) {
                case 0: inc = 1; tx = rv; break;          // A1TR
                case 1: inc = 1; tx = 0; break;           // A1T0
                case 2: inc = 0; tx = 1; break;           // A0T1
                case 3: inc = 0; tx = rv; break;          // A0TR (expect_tx)
                case 4: inc = 0; tx = rv; tx_is_complete = true; break;  // A0TX
                case 5: inc = static_cast<std::uint32_t>(rv); break;     // ART0
                default: {
                    if (fault) {
                        *fault = Fault(FaultKind::kInvalidInstruction,
                                       "SYNCS.ARRIVE invalid paramtype")
                                     .set_pc(pc)
                                     .set_warp(static_cast<std::uint32_t>(w.warp_id));
                    }
                    return Status::failure(Error::internal("memory fault"));
                }
            }
            MbarrierResult r = mbarrier_arrive(st, inc, tx, tx_is_complete);
            if (r.fault) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess, r.error)
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id))
                                 .set_active_mask(mask);
                }
                return Status::failure(Error::internal("memory fault"));
            }
            // Mirror the new state word back into shared memory.
            const std::uint64_t nw = st->encode();
            if (addr <= cta->shared.size() && addr + 8 <= cta->shared.size()) {
                for (int i = 0; i < 8; ++i)
                    cta->shared[addr + i] =
                        static_cast<std::uint8_t>((nw >> (8 * i)) & 0xff);
            }
            // Token (retval OLDSTATE): write the old state word into Rd
            // (64-bit pair for TRANS64).  TCNT has no Rd role.
            if (retval == 0 && rd_op) {
                const std::uint64_t reg = static_cast<std::uint64_t>(
                    shape::operand_value_as_i64(*rd_op));
                if (reg != 255 && reg + 1 < kNumGprs) {
                    w.threads[0].gpr[reg] =
                        static_cast<std::uint32_t>(r.old_word & 0xffffffffu);
                    w.threads[0].gpr[reg + 1] =
                        static_cast<std::uint32_t>(r.old_word >> 32);
                }
            }
            return Status::success();
        }
        case 0x15a7: {  // PHASECHK / try_wait.parity (SYNCS5 split 0)
            const auto& d5 =
                *static_cast<const shape::DecodedSYNCS5_0*>(&inst);
            const std::uint64_t pnum = static_cast<std::uint64_t>(
                shape::operand_value_as_i64(d5.Pu));
            const std::uint64_t parity =
                (read_reg_ov(w.threads[0], d5.Rb) >> 31) & 1;  // Rb
            auto* st = mbarrier_at(*cta, addr, /*create_if_missing=*/true);
            if (!st) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess,
                                   "SYNCS.PHASECHK at out-of-window shared "
                                   "address")
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            MbarrierResult r = mbarrier_phasechk(*st, static_cast<std::uint32_t>(parity));
            if (r.fault) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess, r.error)
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id))
                                 .set_active_mask(mask);
                }
                return Status::failure(Error::internal("memory fault"));
            }
            if (pnum < 7) {
                for (int lane = 0; lane < kLanesPerWarp; ++lane) {
                    if (mask & (1u << lane))
                        w.threads[lane].pred[pnum] = r.predicate;
                }
            }
            return Status::success();
        }
        case 0x19b1: {  // CCTL per-address (.IV / .WB)
            const auto& d =
                *static_cast<const shape::DecodedSYNCS3*>(&inst);
            auto* st = mbarrier_at(*cta, addr, /*create_if_missing=*/true);
            if (!st) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess,
                                   "SYNCS.CCTL at out-of-window shared address")
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            const std::uint64_t cctlop =
                static_cast<std::uint64_t>(d.cctlop);
            if (cctlop == 0) mbarrier_invalidate(st);  // IV
            // WB is a writeback hint: functional no-op.
            return Status::success();
        }
        case 0x9b1: {  // CCTL.ALL (.IVALL / .WBALL)
            const auto& d =
                *static_cast<const shape::DecodedSYNCS0*>(&inst);
            const std::uint64_t cctlop =
                static_cast<std::uint64_t>(d.cctlop);
            if (cctlop == 0) {
                for (auto& [_, st] : cta->mbarriers) {
                    mbarrier_invalidate(&st);
                }
            }
            return Status::success();
        }
        case 0x15b1: {  // LD: load barrier state (64-bit) into GPR Rd
            auto* st = mbarrier_at(*cta, addr, /*create_if_missing=*/true);
            if (!st) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess,
                                   "SYNCS.LD at out-of-window shared address")
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            const auto& d4 =
                *static_cast<const shape::DecodedSYNCS4_0*>(&inst);
            const std::uint64_t reg = static_cast<std::uint64_t>(
                shape::operand_value_as_i64(d4.Rd));
            const std::uint64_t nw = st->encode();
            if (reg != 255 && reg + 1 < kNumGprs) {
                w.threads[0].gpr[reg] =
                    static_cast<std::uint32_t>(nw & 0xffffffffu);
                w.threads[0].gpr[reg + 1] =
                    static_cast<std::uint32_t>(nw >> 32);
            }
            return Status::success();
        }
        case 0x3a7: {  // flush: decode-only
            if (fault) {
                *fault = Fault(FaultKind::kUnsupportedInstruction,
                               "SYNCS.FLUSH is decode-only (not implemented)")
                             .set_pc(pc)
                             .set_warp(static_cast<std::uint32_t>(w.warp_id));
            }
            return Status::failure(Error::internal("memory fault"));
        }
        case 0x15b2: {  // EXCH.64: uniform shared atomic exchange (mbarrier.init)
            const std::uint64_t urd = static_cast<std::uint64_t>(
                shape::operand_value_as_i64(
                    static_cast<const shape::DecodedSYNCS5_2&>(inst).URd));
            const std::uint64_t new_val =
                read_ur_pair_ov(
                    w, static_cast<const shape::DecodedSYNCS5_2&>(inst).URb);
            if (addr > cta->shared.size() || addr + 8 > cta->shared.size()) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess,
                                   "SYNCS.EXCH.64 out of shared window")
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            std::uint64_t old_val = 0;
            for (int i = 0; i < 8; ++i)
                old_val |= static_cast<std::uint64_t>(cta->shared[addr + i])
                           << (8 * i);
            for (int i = 0; i < 8; ++i)
                cta->shared[addr + i] =
                    static_cast<std::uint8_t>((new_val >> (8 * i)) & 0xff);
            // Re-seed the mbarrier logical state from the exchanged word
            // (mbarrier.init writes the init encoding here).
            if (new_val != 0) {
                cta->mbarriers[addr] = MbarrierState::from_init_word(new_val);
            } else {
                cta->mbarriers.erase(addr);
            }
            if (urd != 255 && urd + 1 < kNumUrs) {
                w.ur[urd] = static_cast<std::uint32_t>(old_val & 0xffffffffu);
                w.ur[urd + 1] = static_cast<std::uint32_t>(old_val >> 32);
            }
            return Status::success();
        }
        case 0x13b2: {  // CAS.64: uniform shared atomic compare-and-swap
            const std::uint64_t urd = static_cast<std::uint64_t>(
                shape::operand_value_as_i64(
                    static_cast<const shape::DecodedSYNCS6&>(inst).URd));
            if (addr > cta->shared.size() || addr + 8 > cta->shared.size()) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess,
                                   "SYNCS.CAS.64 out of shared window")
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            std::uint64_t old_val = 0;
            for (int i = 0; i < 8; ++i)
                old_val |= static_cast<std::uint64_t>(cta->shared[addr + i])
                           << (8 * i);
            const std::uint64_t cmp =
                read_ur_pair_ov(
                    w, static_cast<const shape::DecodedSYNCS6&>(inst).URc);
            if (old_val == cmp) {
                const std::uint64_t new_val =
                    read_ur_pair_ov(
                        w, static_cast<const shape::DecodedSYNCS6&>(inst)
                               .URb);
                for (int i = 0; i < 8; ++i)
                    cta->shared[addr + i] =
                        static_cast<std::uint8_t>((new_val >> (8 * i)) & 0xff);
                if (new_val != 0) {
                    cta->mbarriers[addr] = MbarrierState::from_init_word(new_val);
                } else {
                    cta->mbarriers.erase(addr);
                }
            }
            if (urd != 255 && urd + 1 < kNumUrs) {
                w.ur[urd] = static_cast<std::uint32_t>(old_val & 0xffffffffu);
                w.ur[urd + 1] = static_cast<std::uint32_t>(old_val >> 32);
            }
            return Status::success();
        }
        case 0x19b2: {  // LD.64: uniform shared load
            const std::uint64_t urd = static_cast<std::uint64_t>(
                shape::operand_value_as_i64(
                    static_cast<const shape::DecodedSYNCS6&>(inst).URd));
            if (addr > cta->shared.size() || addr + 8 > cta->shared.size()) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess,
                                   "SYNCS.LD.64 out of shared window")
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            std::uint64_t v = 0;
            for (int i = 0; i < 8; ++i)
                v |= static_cast<std::uint64_t>(cta->shared[addr + i]) << (8 * i);
            if (urd != 255 && urd + 1 < kNumUrs) {
                w.ur[urd] = static_cast<std::uint32_t>(v & 0xffffffffu);
                w.ur[urd + 1] = static_cast<std::uint32_t>(v >> 32);
            }
            return Status::success();
        }
        default:
            return do_unsupported(w, inst, pc, mask, fault);
    }
}

// ARRIVES (0x19b0): cp.async.mbarrier.arrive[.noinc].  Couples the current
// thread's outstanding LDGSTS group to the mbarrier at [URc+off]:
//   .TRANSCNT (barop=2): the group's committed bytes decrement the barrier's
//     pending tx count once the copies land (immediate in the synchronous
//     model).
//   .ARVCNT (barop=1): arrive without incrementing (cp.async.mbarrier.arrive
//     .noinc).
//   .LEGACY (barop=0): legacy arrive-count form (decode-only).
Status Interpreter::do_arrives(WarpState& w, const DecodedInstruction& inst,
                               std::uint64_t pc,
                               std::optional<Fault>* fault) {
    CtaState& cta = ctas_[static_cast<std::size_t>(w.local_cta_id)];
    // Layout: [Ra,Ra_URc,Ra_offset] — the shared target is [URc + off].
    const auto& d = *static_cast<const shape::DecodedARRIVES3*>(&inst);
    const std::uint64_t base = read_ur_ov(w, d.Ra_URc);
    const std::int64_t off = shape::operand_value_as_i64(d.Ra_offset);
    const std::uint32_t addr = static_cast<std::uint32_t>(
        base + static_cast<std::uint64_t>(off));

    const std::uint64_t barop = static_cast<std::uint64_t>(d.barop);
    auto* st = mbarrier_at(cta, addr, /*create_if_missing=*/true);
    if (!st) {
        if (fault) {
            *fault = Fault(FaultKind::kIllegalMemoryAccess,
                           "ARRIVES at out-of-window shared address")
                         .set_pc(pc)
                         .set_warp(static_cast<std::uint32_t>(w.warp_id));
        }
        return Status::failure(Error::internal("memory fault"));
    }
    // Consume the sealed LDGSTS group's committed bytes (TRANSCNT).
    if (barop == 2) {  // TRANSCNT
        std::uint64_t group_bytes = 0;
        if (!cta.async_groups.empty()) {
            group_bytes = cta.async_groups.back().committed_bytes;
        } else if (cta.async_open.committed_bytes) {
            group_bytes = cta.async_open.committed_bytes;
        }
        if (group_bytes) {
            MbarrierResult r =
                mbarrier_arrive(st, 0, group_bytes, /*tx_is_complete=*/true);
            if (r.fault) {
                if (fault) {
                    *fault = Fault(FaultKind::kIllegalMemoryAccess, r.error)
                                 .set_pc(pc)
                                 .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            const std::uint64_t nw = st->encode();
            if (addr <= cta.shared.size() && addr + 8 <= cta.shared.size()) {
                for (int i = 0; i < 8; ++i)
                    cta.shared[addr + i] =
                        static_cast<std::uint8_t>((nw >> (8 * i)) & 0xff);
            }
        }
        return Status::success();
    }
    if (barop == 1) {  // ARVCNT (noinc arrive)
        // Arrive without incrementing: leave the arrival count unchanged, but
        // validate the barrier is initialized.
        MbarrierResult r = mbarrier_phasechk(*st, st->phase);
        if (r.fault) {
            if (fault) {
                *fault = Fault(FaultKind::kIllegalMemoryAccess, r.error)
                             .set_pc(pc)
                             .set_warp(static_cast<std::uint32_t>(w.warp_id));
            }
            return Status::failure(Error::internal("memory fault"));
        }
        return Status::success();
    }
    // LEGACY: decode-only.
    if (fault) {
        *fault = Fault(FaultKind::kUnsupportedInstruction,
                       "ARRIVES.LDGSTSBAR.64.LEGACY is decode-only")
                     .set_pc(pc)
                     .set_warp(static_cast<std::uint32_t>(w.warp_id));
    }
    return Status::failure(Error::internal("memory fault"));
}

// High-4: warp-linear id across the whole launch.  ceil(block_threads/32) so
// a block smaller than 32 threads still gives each warp a distinct id (floor
// division collapsed every warp of such a block onto the same id).
std::uint64_t Interpreter::warp_linear_id(const WarpState& w) const {
    const std::uint64_t block_threads = static_cast<std::uint64_t>(
        env_.block[0]) * env_.block[1] * env_.block[2];
    const std::uint64_t warps_per_cta =
        (block_threads + kLanesPerWarp - 1) / kLanesPerWarp;
    return static_cast<std::uint64_t>(w.cta_id) * warps_per_cta +
           static_cast<std::uint64_t>(w.warp_id);
}

// ---------------------------------------------------------------------------
// Phase 9 subset: TMA family (UTMALDG / UTMASTG / UTMAREDG /
// UTMACMDFLUSH / UTMACCTL)
// ---------------------------------------------------------------------------
// UTMALDG: tensor load (global -> shared).  One elected thread issues it on
// the uniform datapath.  URb is the coordinate block:
//   {URb+0 = dst smem, URb+1 = mbarrier addr, URb+2 = coord[rank-1], ...,
//    last = coord[0]}  (2D verified; higher ranks follow ISRC_B_SIZE).
// URa = 64-bit pointer to the 128-byte tensor-map descriptor in global memory.
// The copy engine decrements the mbarrier's pending tx count by the tile
// bytes as data lands (complete_tx) — that flips the phase when drained.
//
// UTMASTG / UTMAREDG: tensor store / reduce (shared -> global).  URb block:
//   {URb+0 = shared src, URb+1 = coord[rank-1], ..., coord[0]} (no mbarrier).
// Completion is via the bulk-async-group (UTMACMDFLUSH + DEPBAR.LE).
//
// All are decode-only safe: an unparseable descriptor / im2col / swizzle tile
// faults as kNotSupported rather than fabricating a wrong copy.
// ===========================================================================
// Phase 9 subset: TMA family — one handler per instruction (plan-b refactor).
// prepare_tma fetches/parses the 128-byte tensor-map descriptor + coordinate
// block and expands the tile; do_utmaldg/do_utmastg/do_utmaredg then run the
// direction-specific copy; flush/ctl are standalone no-ops.
// ===========================================================================

// URb (coordinate block base) / URa (128-bit descriptor pointer pair) sit at
// ops[1]/ops[2] in every UTMALDG/UTMASTG/UTMAREDG form (the desc forms append
// desc/URe at [3]/[4]).  Fetches the descriptor, parses the tensor map,
// reads the coordinate block from URb and expands the tile.  On success `out`
// carries the committed access set + the direction-specific URb fields.
std::uint32_t Interpreter::special_register_value(SpecialReg sr,
                                                  std::uint32_t cta_id,
                                                  std::uint32_t warp_id,
                                                  int lane) const {
    return resolve_sr(sr, lane, static_cast<int>(warp_id),
                      static_cast<int>(cta_id), env_);
}

// Phase 9 tensor core: HMMA / QMMA / OMMA (dense F32-accumulator shapes).
//
// Functional semantics is delegated to semu::tensor (the C++ port of
// tools/hmma_model.py), so the interpreter result equals the Python model
// bit-for-bit by construction.  Per lane the handler reads the lane's own
// fragment registers (consecutive words from each base operand), folds the
// k-products via the engine's fragment functions and writes the 4 F32
// accumulator words to Rd..Rd+3.
//
// Hardware contract: HMMA/QMMA/OMMA results are NOT scoreboarded on the
// tensor pipe (INST_TYPE_COUPLED_MATH).  A D read closer than ~16 instructions
// after the MMA faults 0x715 on SM120; the interpreter is synchronous, so it
// does not need the padding itself, but hand-written tests keep the NOPs to
// stay faithful to the hardware contract (see AGENTS.md / ASSEMBLER_MANUAL.md).
// ===========================================================================
// Phase 9 tensor core — one handler per mnemonic (plan-b refactor).  The
// per-lane fragment compute is the shared `tensor_lane_core` (mode:
// 0=HMMA 1=QMMA 2=OMMA); each do_<MNEMONIC> casts its concrete shape, applies
// the dense-shape gates and resolves tensor::Shape/Format.
// ===========================================================================

// Unsupported tensor variant fault (sparse / indexedRF / rowcol / scale /
// F16-accumulator alternatives are decode-only).
Status Interpreter::do_shfl(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst) {
    // SHFL.idx/mode Pu, Rd, Ra, Sb/Rb, Rc/Sc — warp shuffle.
    // Roles: [Pu, Rd, Ra, 2nd (idx), 3rd (segment base)].
    const auto& d = *static_cast<const shape::DecodedSHFL5*>(&inst);
    const std::uint64_t mode = static_cast<std::uint64_t>(d.shflmd);
    // Gather all active-lane Ra values (per-lane).
    std::array<std::uint32_t, kLanesPerWarp> vals{};
    for (int lane = 0; lane < kLanesPerWarp; ++lane)
        vals[lane] = read_reg_ov(w.threads[lane], d.Ra);
    const auto seg_kind = static_cast<shape::OperandKind>(d.c.kind);
    const std::int64_t seg_v = shape::operand_value_as_i64(d.c);
    const auto idx_kind = static_cast<shape::OperandKind>(d.b.kind);
    for (int lane = 0; lane < kLanesPerWarp; ++lane) {
        if (!(mask & (1u << lane))) continue;
        ThreadState& t = w.threads[lane];
        if (!t.active || t.exited) continue;
        const std::uint32_t seg =
            (seg_kind == shape::OperandKind::kRegister && seg_v != 255)
            ? read_reg_ov(t, d.c) & 0x1f
            : 0;
        std::uint32_t idx = 0;
        if (idx_kind == shape::OperandKind::kUImm ||
            idx_kind == shape::OperandKind::kSImm) {
            idx = static_cast<std::uint32_t>(
                      shape::operand_value_as_i64(d.b)) &
                  0x1f;
        } else if (idx_kind == shape::OperandKind::kRegister) {
            idx = read_reg_ov(t, d.b) & 0x1f;
        }
        int srclane = -1;
        const int laneid = lane;
        switch (mode) {
            case 0:  // IDX: source lane = seg_base + idx
                srclane = static_cast<int>(seg + (idx & 0x1f));
                break;
            case 1:  // UP: source lane = lane - idx (own if out of range)
                srclane = laneid - static_cast<int>(idx);
                break;
            case 2:  // DOWN: source lane = lane + idx (own if >= bound)
                srclane = laneid + static_cast<int>(idx);
                break;
            case 3:  // BFLY: source lane = lane ^ idx
                srclane = laneid ^ static_cast<int>(idx);
                break;
            default: break;
        }
        const bool valid = (srclane >= 0 && srclane < kLanesPerWarp);
        if (valid && (mask & (1u << srclane))) {
            write_rd_ov(w, t, d.Rd, vals[srclane], 0);
            write_pred_ov(t, d.Pu, true);
        } else {
            write_rd_ov(w, t, d.Rd, vals[lane], 0);
            write_pred_ov(t, d.Pu, false);
        }
    }
    return Status::success();
}


}  // namespace semu
