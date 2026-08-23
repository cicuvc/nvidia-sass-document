// sm120 baseline interpreter -- TMA: UTMALDG/UTMASTG/UTMAREDG/UTMACMDFLUSH/UTMACCTL.
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
Status Interpreter::prepare_tma(WarpState& w, const DecodedInstruction& inst,
                                std::uint64_t pc, std::optional<Fault>* fault,
                                bool is_load, TmaPrepare* out) {
    // URb@1 / URa@2 in every UTMALDG/STG/REDG form (same first named fields).
    const auto& d = *static_cast<const shape::DecodedUTMALDG3*>(&inst);
    if (static_cast<shape::OperandKind>(d.URb.kind) !=
            shape::OperandKind::kUniformRegister ||
        static_cast<shape::OperandKind>(d.URa.kind) !=
            shape::OperandKind::kUniformRegister) {
        if (fault) {
            *fault = Fault(FaultKind::kUnsupportedInstruction,
                           "TMA op missing URb/URa operands")
                         .set_pc(pc)
                         .set_warp(static_cast<std::uint32_t>(w.warp_id));
        }
        return Status::failure(Error::internal("memory fault"));
    }
    const std::uint32_t urb_idx = static_cast<std::uint32_t>(
        shape::operand_value_as_i64(d.URb));
    const std::uint64_t desc_ptr = read_ur_pair_ov(w, d.URa);

    // Read the 128-byte descriptor from global memory.
    std::uint8_t blob[128] = {0};
    {
        MemValue val{};
        for (std::uint32_t chunk = 0; chunk < 8; ++chunk) {
            Status st = memory_->ldg(DevicePtr{0}, desc_ptr + chunk * 16, 0,
                                     MemWidthInfo{16, false, true}, val);
            if (st.failed()) {
                if (fault) {
                    *fault = memory_error_to_fault(
                                 st.error(), pc,
                                 static_cast<std::uint32_t>(w.warp_id))
                                 .set_active_mask(0xffffffffu);
                }
                return Status::failure(Error::internal("memory fault"));
            }
            for (int i = 0; i < 4; ++i) {
                const std::uint32_t base = chunk * 16 + i * 4;
                blob[base] = static_cast<std::uint8_t>(val[i] & 0xff);
                blob[base + 1] = static_cast<std::uint8_t>((val[i] >> 8) & 0xff);
                blob[base + 2] = static_cast<std::uint8_t>((val[i] >> 16) & 0xff);
                blob[base + 3] = static_cast<std::uint8_t>((val[i] >> 24) & 0xff);
            }
        }
    }
    auto parsed = parse_tensor_map(blob);
    if (parsed.failed()) {
        if (fault) {
            *fault = Fault(FaultKind::kUnsupportedInstruction,
                           "TMA tensor-map parse: " +
                               parsed.take_error().describe())
                         .set_pc(pc)
                         .set_warp(static_cast<std::uint32_t>(w.warp_id));
        }
        return Status::failure(Error::internal("memory fault"));
    }
    TensorMap tm = parsed.value();
    // im2col / packed-U4-U6 maps are decode-only (see tensor_map.hpp).
    if (tm.mode == TensorMapMode::kIm2col || tm.element_bytes == 0) {
        if (fault) {
            *fault = Fault(FaultKind::kUnsupportedInstruction,
                           "im2col / packed tensor maps are decode-only")
                         .set_pc(pc)
                         .set_warp(static_cast<std::uint32_t>(w.warp_id));
        }
        return Status::failure(Error::internal("memory fault"));
    }

    // Coordinate block from URb.  UTMALDG (load): block starts with
    // {dst smem, mbarrier addr, coords...}.  UTMASTG/UTMAREDG (store):
    // {src smem, coords...} (no mbarrier slot).
    const std::uint32_t coord_slot_offset = is_load ? 2 : 1;
    std::uint32_t coords[5] = {0, 0, 0, 0, 0};
    std::uint32_t smem_src = 0;   // store direction: shared source
    std::uint32_t dst_smem = 0;   // load direction: shared destination
    std::uint32_t mbar_addr = 0;
    if (is_load) {
        dst_smem = w.ur[urb_idx];
        mbar_addr = w.ur[urb_idx + 1];
    } else {
        smem_src = w.ur[urb_idx];
    }
    // SASS coordinate order: {coord[rank-1] .. coord[0]} (reversed vs PTX).
    for (std::uint32_t i = 0; i < tm.rank; ++i) {
        coords[tm.rank - 1 - i] = w.ur[urb_idx + coord_slot_offset + i];
    }

    auto expanded = expand_tile(tm, coords);
    if (expanded.failed()) {
        if (fault) {
            *fault = Fault(FaultKind::kUnsupportedInstruction,
                           "TMA tile expansion: " +
                               expanded.take_error().describe())
                         .set_pc(pc)
                         .set_warp(static_cast<std::uint32_t>(w.warp_id));
        }
        return Status::failure(Error::internal("memory fault"));
    }
    out->urb_idx = urb_idx;
    out->smem_src = smem_src;
    out->dst_smem = dst_smem;
    out->mbar_addr = mbar_addr;
    out->acc = expanded.value();
    return Status::success();
}

// Store/reduce direction (shared -> global), shared by UTMASTG (plain store)
// and UTMAREDG (atomic reduce).  Emits the trace-only profiler events.
Status Interpreter::tma_store_core(WarpState& w, const DecodedInstruction& inst,
                                   std::uint64_t pc,
                                   std::optional<Fault>* fault,
                                   const TmaPrepare& prep, std::uint32_t redop,
                                   bool is_redg) {
    CtaState& cta = ctas_[static_cast<std::size_t>(w.local_cta_id)];
    const std::uint64_t warp_linear = warp_linear_id(w);
    const TileAccessSet& acc = prep.acc;
    const std::uint64_t smem_src = prep.smem_src;
    std::vector<LaneByteRange> shared_ranges;
    std::vector<LaneByteRange> global_ranges;
    for (std::size_t k = 0; k < acc.global.size(); ++k) {
        const std::uint64_t g = acc.global[k];
        const std::uint64_t s = smem_src + acc.shared[k];
        if (s > cta.shared.size() || acc.element_bytes > cta.shared.size() - s) {
            if (fault) {
                *fault = Fault(FaultKind::kIllegalMemoryAccess,
                               "TMA store shared source out of bounds")
                             .set_pc(pc)
                             .set_warp(static_cast<std::uint32_t>(w.warp_id));
            }
            return Status::failure(Error::internal("memory fault"));
        }
        MemValue src{};
        for (std::uint32_t i = 0; i < acc.element_bytes; ++i) {
            src[i / 4] |= static_cast<std::uint32_t>(cta.shared[s + i])
                          << (8 * (i % 4));
        }
        if (is_redg) {  // UTMAREDG: atomic reduce into global
            // The element type is u32 in the verified tests (the descriptor's
            // dtype drives it); a non-4-byte reduce is decode-only.
            if (acc.element_bytes != 4) {
                if (fault) {
                    *fault = Fault(
                        FaultKind::kUnsupportedInstruction,
                        "UTMAREDG element size != 4 is decode-only")
                            .set_pc(pc)
                            .set_warp(static_cast<std::uint32_t>(w.warp_id));
                }
                return Status::failure(Error::internal("memory fault"));
            }
            AtomicOp aop = AtomicOp::kAdd;
            switch (redop) {
                case 0: aop = AtomicOp::kAdd; break;
                case 1: aop = AtomicOp::kMin; break;
                case 2: aop = AtomicOp::kMax; break;
                case 3: aop = AtomicOp::kInc; break;
                case 4: aop = AtomicOp::kDec; break;
                case 5: aop = AtomicOp::kAnd; break;
                case 6: aop = AtomicOp::kOr; break;
                case 7: aop = AtomicOp::kXor; break;
                default: break;
            }
            MemValue old{};
            Status st = memory_->atom_global(g, 4, aop, src, old);
            if (st.failed()) {
                if (fault) {
                    *fault = memory_error_to_fault(
                                 st.error(), pc,
                                 static_cast<std::uint32_t>(w.warp_id))
                                 .set_active_mask(0xffffffffu);
                }
                return Status::failure(Error::internal("memory fault"));
            }
        } else {  // UTMASTG: plain store
            Status st = memory_->stg(DevicePtr{0}, g, 0,
                                     MemWidthInfo{acc.element_bytes, false,
                                                  true},
                                     src);
            if (st.failed()) {
                if (fault) {
                    *fault = memory_error_to_fault(
                                 st.error(), pc,
                                 static_cast<std::uint32_t>(w.warp_id))
                                 .set_active_mask(0xffffffffu);
                }
                return Status::failure(Error::internal("memory fault"));
            }
        }
        if (k < kLanesPerWarp) {
            shared_ranges.push_back({s, acc.element_bytes, true});
            global_ranges.push_back({g, acc.element_bytes, true});
        }
    }
    // Profiler observability.
    if (options_.model.l1tex == L1TexMode::kTraceOnly) {
        MemoryEvent ev;
        ev.kind = MemoryEventKind::kL1TexIssue;
        ev.instruction = executed_;
        ev.cta = static_cast<std::uint32_t>(w.cta_id);
        ev.warp = static_cast<std::uint32_t>(w.warp_id);
        ev.pc = pc;
        ev.mnemonic = isa::mnemonic_name(inst.mnemonic);
        ev.request_kind = "tma-store";
        ev.element_width = acc.element_bytes;
        ev.address_space = EventAddressSpace::kShared;
        ev.is_write = false;
        ev.lane_ranges = shared_ranges;
        ev.subcore = subcore_mapper_.map(warp_linear).id;
        ev.sm = sm_of_cta(static_cast<std::uint32_t>(w.cta_id));
        memory_events_.push_back(std::move(ev));
        MemoryEvent gev;
        gev.kind = MemoryEventKind::kL1TexIssue;
        gev.instruction = executed_;
        gev.cta = static_cast<std::uint32_t>(w.cta_id);
        gev.warp = static_cast<std::uint32_t>(w.warp_id);
        gev.pc = pc;
        gev.mnemonic = isa::mnemonic_name(inst.mnemonic);
        gev.request_kind = "tma-store-write";
        gev.element_width = acc.element_bytes;
        gev.address_space = EventAddressSpace::kGlobal;
        gev.is_write = true;
        gev.lane_ranges = global_ranges;
        gev.subcore = subcore_mapper_.map(warp_linear).id;
        gev.sm = sm_of_cta(static_cast<std::uint32_t>(w.cta_id));
        memory_events_.push_back(std::move(gev));
    }
    return Status::success();
}

Status Interpreter::do_utmacmdflush(WarpState& w, const DecodedInstruction& inst,
                                    std::uint64_t pc) {
    (void)pc;
    // UTMACMDFLUSH (0x9b7): commit_group for the TMA bulk-async-group path.
    // Same counted-scoreboard bookkeeping as LDGDEPBAR (seal the open group on
    // the target SB).
    CtaState& cta = ctas_[static_cast<std::size_t>(w.local_cta_id)];
    if (!cta.async_open.copies.empty() || cta.async_open.committed_bytes) {
        cta.async_groups.push_back(cta.async_open);
        const auto wr = inst.schedule.dst_wr_sb;
        if (wr >= 0 && wr < static_cast<int>(cta.sb_group_count.size()))
            cta.sb_group_count[wr]++;
        cta.async_open = {};
    }
    return Status::success();
}

Status Interpreter::do_utmacctl(WarpState& w, const DecodedInstruction& inst,
                                std::uint64_t pc) {
    (void)w; (void)inst; (void)pc;
    // UTMACCTL (0x19b9 / 0x9b9): tensor-map descriptor cache control
    // (fence.proxy.tensormap / prefetch.tensormap).  The CPU model reads the
    // descriptor fresh from global every time, so invalidate/prefetch are
    // functional no-ops.
    return Status::success();
}

Status Interpreter::do_utmaldg(WarpState& w, const DecodedInstruction& inst,
                               std::uint64_t pc,
                               std::optional<Fault>* fault) {
    CtaState& cta = ctas_[static_cast<std::size_t>(w.local_cta_id)];
    const std::uint64_t warp_linear = warp_linear_id(w);
    TmaPrepare prep;
    Status ps = prepare_tma(w, inst, pc, fault, /*is_load=*/true, &prep);
    if (ps.failed()) return ps;
    const TileAccessSet& acc = prep.acc;
    // UTMALDG: global -> shared.  Copy every element; the shared side is
    // contiguous (row-major box) starting at dst_smem.
    std::vector<LaneByteRange> shared_ranges;
    std::vector<LaneByteRange> global_ranges;
    for (std::size_t k = 0; k < acc.global.size(); ++k) {
        const std::uint64_t g = acc.global[k];
        const std::uint64_t s = prep.dst_smem + acc.shared[k];
        MemValue val{};
        Status st = memory_->ldg(DevicePtr{0}, g, 0,
                                 MemWidthInfo{acc.element_bytes, false, true},
                                 val);
        if (st.failed()) {
            if (fault) {
                *fault = memory_error_to_fault(
                             st.error(), pc,
                             static_cast<std::uint32_t>(w.warp_id))
                             .set_active_mask(0xffffffffu);
            }
            return Status::failure(Error::internal("memory fault"));
        }
        if (s > cta.shared.size() || acc.element_bytes > cta.shared.size() - s) {
            if (fault) {
                *fault = Fault(FaultKind::kIllegalMemoryAccess,
                               "UTMALDG shared destination out of bounds")
                             .set_pc(pc)
                             .set_warp(static_cast<std::uint32_t>(w.warp_id));
            }
            return Status::failure(Error::internal("memory fault"));
        }
        for (std::uint32_t i = 0; i < acc.element_bytes; ++i) {
            cta.shared[s + i] =
                static_cast<std::uint8_t>((val[i / 4] >> (8 * (i % 4))) &
                                          0xff);
        }
    }
    // Completion: decrement the mbarrier's pending tx by the tile bytes
    // (cp.async.bulk.tensor ... mbarrier::complete_tx::bytes).
    if (prep.mbar_addr != 0) {
        auto* st = mbarrier_at(cta, prep.mbar_addr, /*create_if_missing=*/true);
        if (!st) {
            if (fault) {
                *fault = Fault(FaultKind::kIllegalMemoryAccess,
                               "UTMALDG mbarrier out of shared window")
                             .set_pc(pc)
                             .set_warp(static_cast<std::uint32_t>(w.warp_id));
            }
            return Status::failure(Error::internal("memory fault"));
        }
        const std::uint64_t tile_bytes = acc.global.size() * acc.element_bytes;
        MbarrierResult r =
            mbarrier_arrive(st, 0, tile_bytes, /*tx_is_complete=*/true);
        if (r.fault) {
            if (fault) {
                *fault = Fault(FaultKind::kIllegalMemoryAccess, r.error)
                             .set_pc(pc)
                             .set_warp(static_cast<std::uint32_t>(w.warp_id));
            }
            return Status::failure(Error::internal("memory fault"));
        }
        const std::uint64_t nw = st->encode();
        if (prep.mbar_addr <= cta.shared.size() &&
            prep.mbar_addr + 8 <= cta.shared.size()) {
            for (int i = 0; i < 8; ++i)
                cta.shared[prep.mbar_addr + i] =
                    static_cast<std::uint8_t>((nw >> (8 * i)) & 0xff);
        }
    }
    // Profiler / race observability: the committed access set.
    if (options_.model.l1tex == L1TexMode::kTraceOnly) {
        for (std::size_t k = 0; k < acc.global.size(); ++k) {
            if (k >= kLanesPerWarp) break;
            shared_ranges.push_back(
                {prep.dst_smem + acc.shared[k], acc.element_bytes, true});
            global_ranges.push_back({acc.global[k], acc.element_bytes, true});
        }
        MemoryEvent ev;
        ev.kind = MemoryEventKind::kL1TexIssue;
        ev.instruction = executed_;
        ev.cta = static_cast<std::uint32_t>(w.cta_id);
        ev.warp = static_cast<std::uint32_t>(w.warp_id);
        ev.pc = pc;
        ev.mnemonic = "UTMALDG";
        ev.request_kind = "tma-load";
        ev.element_width = acc.element_bytes;
        ev.address_space = EventAddressSpace::kShared;
        ev.is_write = true;
        ev.lane_ranges = shared_ranges;
        ev.subcore = subcore_mapper_.map(warp_linear).id;
        ev.sm = sm_of_cta(static_cast<std::uint32_t>(w.cta_id));
        memory_events_.push_back(std::move(ev));
        MemoryEvent gev;
        gev.kind = MemoryEventKind::kL1TexIssue;
        gev.instruction = executed_;
        gev.cta = static_cast<std::uint32_t>(w.cta_id);
        gev.warp = static_cast<std::uint32_t>(w.warp_id);
        gev.pc = pc;
        gev.mnemonic = "UTMALDG";
        gev.request_kind = "tma-load-read";
        gev.element_width = acc.element_bytes;
        gev.address_space = EventAddressSpace::kGlobal;
        gev.is_write = false;
        gev.lane_ranges = global_ranges;
        gev.subcore = subcore_mapper_.map(warp_linear).id;
        gev.sm = sm_of_cta(static_cast<std::uint32_t>(w.cta_id));
        memory_events_.push_back(std::move(gev));
    }
    return Status::success();
}

Status Interpreter::do_utmastg(WarpState& w, const DecodedInstruction& inst,
                               std::uint64_t pc,
                               std::optional<Fault>* fault) {
    TmaPrepare prep;
    Status ps = prepare_tma(w, inst, pc, fault, /*is_load=*/false, &prep);
    if (ps.failed()) return ps;
    return tma_store_core(w, inst, pc, fault, prep, 0, /*is_redg=*/false);
}

Status Interpreter::do_utmaredg(WarpState& w, const DecodedInstruction& inst,
                                std::uint64_t pc,
                                std::optional<Fault>* fault) {
    TmaPrepare prep;
    Status ps = prepare_tma(w, inst, pc, fault, /*is_load=*/false, &prep);
    if (ps.failed()) return ps;
    // RedOp (UTMAREDG): the `op` modifier member (RedOp enum, bits[89:87]).

    const bool is3 =
        inst.variant_class == isa::VariantClass::kutmaredg__UUU ||
        inst.variant_class == isa::VariantClass::kutmaredg_one__UUU;
    const std::uint32_t redop =
        is3 ? static_cast<std::uint32_t>(
                  static_cast<const shape::DecodedUTMAREDG3*>(&inst)->op)
            : static_cast<std::uint32_t>(
                  static_cast<const shape::DecodedUTMAREDG5*>(&inst)->op);
    return tma_store_core(w, inst, pc, fault, prep, redop, /*is_redg=*/true);
}

// Phase 6 Step 2B: trace-only subcore issue event.  Records the warp's stable

// Phase 6 Step 2B: trace-only subcore issue event.  Records the warp's stable
// subcore mapping + issue sequence.  Ordinary LDG/STG/LDS/STS/atomic/constant
// requests NEVER feed the UnifiedV1 estimator (it models the coupled
// L1-read -> shared-write transfer only); that path goes through
// record_coupled_l1_to_shared.
}  // namespace semu
