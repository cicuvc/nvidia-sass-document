// sm120 baseline interpreter -- scalar/uniform: UMOV/UIADD3/USHF/LDCU.
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
Status Interpreter::do_umov(WarpState& w, const DecodedInstruction& inst,
                            std::uint64_t pc) {
    (void)pc;
    // Roles: [UPg, URd, source].  imm64 is a generated subclass flag.
    const auto& d = *static_cast<const shape::DecodedUMOV3*>(&inst);
    const std::uint64_t u =
        static_cast<std::uint64_t>(shape::operand_value_as_i64(d.URd));
    if (u == 255 || u >= kNumUrs) return Status::success();
    const bool is_imm64 = (d.subclass & 8) != 0;
    const std::uint32_t val = static_cast<std::uint32_t>(
        shape::operand_value_as_i64(d.b));
    w.ur[static_cast<std::size_t>(u)] = val;
    // imm64 form writes the 64-bit immediate to URd:URd+1.
    if (is_imm64 && u + 1 < kNumUrs) {
        w.ur[static_cast<std::size_t>(u + 1)] =
            static_cast<std::uint32_t>(
                static_cast<std::uint64_t>(
                    shape::operand_value_as_i64(d.b)) >>
                32);
    }
    return Status::success();
}


// UIADD3 (uniform): URd = URa + URb + URc (with optional negate / RIR imm).
// URc == 255 (UZ, the encoder's "no third reg" pin) means the addend comes
// from the Sb immediate (pos5) instead.  Roles: [UPg,URd,UPu,UPv,URa,
// <URb|Sb>,URc(,UPp,UPq)].
Status Interpreter::do_uiadd3(WarpState& w, const DecodedInstruction& inst,
                              std::uint64_t pc) {
    (void)pc;
    // Roles: [UPg, URd, UPu, UPv, URa, <URb|Sb>, URc] (+UPp/UPq on the 9-op
    // form).  The first seven fields share offsets across UIADD37/39.
    const auto& d = *static_cast<const shape::DecodedUIADD37*>(&inst);
    const std::uint64_t u =
        static_cast<std::uint64_t>(shape::operand_value_as_i64(d.URd));
    if (u == 255 || u >= kNumUrs) return Status::success();
    std::uint32_t a = 0;
    if (static_cast<shape::OperandKind>(d.URa.kind) ==
        shape::OperandKind::kUniformRegister) {
        const std::uint64_t av =
            static_cast<std::uint64_t>(shape::operand_value_as_i64(d.URa));
        if (av != 255) {
            a = read_ur_ov(w, d.URa);
            if (d.URa.flags & 1) a = ~a + 1;
        }
    }
    std::uint32_t b = 0;
    if (static_cast<shape::OperandKind>(d.b.kind) ==
        shape::OperandKind::kUniformRegister) {
        const std::uint64_t bv =
            static_cast<std::uint64_t>(shape::operand_value_as_i64(d.b));
        if (bv != 255) b = read_ur_ov(w, d.b);
    }
    std::uint32_t c = 0;
    const bool urc_ok =
        static_cast<shape::OperandKind>(d.URc.kind) ==
            shape::OperandKind::kUniformRegister &&
        static_cast<std::uint64_t>(shape::operand_value_as_i64(d.URc)) !=
            255;
    if (urc_ok) {
        c = read_ur_ov(w, d.URc);
        if (d.URc.flags & 1) c = ~c + 1;
    } else {
        // URIst: URc absent (UZ pin) — the addend comes from the Sb
        // immediate at the b slot (RIR form).
        const auto kk = static_cast<shape::OperandKind>(d.b.kind);
        if (kk == shape::OperandKind::kUImm ||
            kk == shape::OperandKind::kSImm) {
            c = static_cast<std::uint32_t>(
                shape::operand_value_as_i64(d.b));
            if (d.b.flags & 1) c = ~c + 1;
        }
    }
    w.ur[static_cast<std::size_t>(u)] = a + b + c;
    return Status::success();
}


// USHF (uniform shift): URd = URa << 2nd (or >> for the R form).  The
// direction lives in the SDIR modifier encoded at bit76 (memdesc): L=0, R=1.
Status Interpreter::do_ushf(WarpState& w, const DecodedInstruction& inst,
                            std::uint64_t pc) {
    (void)pc;
    // Roles: [UPg, URd, URa, <URb|Sb>, URc].
    const auto& d = *static_cast<const shape::DecodedUSHF5*>(&inst);
    const std::uint64_t u =
        static_cast<std::uint64_t>(shape::operand_value_as_i64(d.URd));
    if (u == 255 || u >= kNumUrs) return Status::success();
    if (static_cast<shape::OperandKind>(d.URa.kind) !=
        shape::OperandKind::kUniformRegister)
        return Status::success();
    std::uint32_t a = read_ur_ov(w, d.URa);
    const auto sk = static_cast<shape::OperandKind>(d.b.kind);
    const std::uint32_t s =
        (sk == shape::OperandKind::kUImm ||
         sk == shape::OperandKind::kSImm)
            ? static_cast<std::uint32_t>(shape::operand_value_as_i64(d.b))
            : 0;
    // SDIR: L=0 / R=1 at bit76 of the 128-bit word.
    const bool shift_right = ((inst.word.hi >> 12) & 1) != 0;
    w.ur[static_cast<std::size_t>(u)] =
        shift_right ? (a >> (s & 31)) : (a << (s & 31));
    return Status::success();
}


Status Interpreter::do_ldcu(WarpState& w, std::uint32_t mask,
                            const DecodedInstruction& inst, std::uint64_t pc,
                            std::optional<Fault>* fault) {
    // LDCU has no GPR Rd (uniform dest); the pre-refactor path kept rd=255
    // (result not surfaced) — preserved.
    return mem_ldst_atom_core(w, mask, inst, pc, fault, true, false,
                              255, 255, 255, 0, 0, 0);
}


}  // namespace semu
