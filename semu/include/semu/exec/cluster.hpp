#pragma once

#include <array>
#include <cstdint>
#include <string>

#include <semu/memory/memory.hpp>
#include <semu/core/status.hpp>

// Cluster DSMEM address translation (SIM_PLAN Phase 3.5).
//
// Distributed shared memory: a shared-memory access may explicitly target a
// peer CTA inside the same cluster.  The sm120 logical DSMEM address is
//   logical = (cluster_cta_rank << 24) | offset
// i.e. rank = address[31:24], offset = address[23:0] (hardware probe
// tests/smem_cluster_dsmem.cu measured a per-rank delta of 0x1000000).
//
// Rules enforced here:
//   - DSMEM is an EXPLICIT mode (SharedAccessMode::kDistributed); ordinary
//     shared accesses (kLocal) never interpret the high 8 bits, because a
//     rank-0 DSMEM address is legal and a local offset's high bits may be
//     zero too.
//   - The rank is the cluster-internal CTA rank, NOT the grid-linear CTA id
//     and NOT the Context allocation-owner sequence.
//   - source and target must belong to the same cluster; cross-cluster,
//     absent rank, disabled cluster and offset/range past the target window
//     are structured errors.
//   - Normal shared domain isolation (source_domain == owner) is unchanged;
//     only a successful cluster-membership translation authorizes a
//     different source domain.

namespace semu {

// Explicit shared access mode: kLocal = current CTA only; kDistributed =
// DSMEM (address[31:24] = cluster rank).
enum class SharedAccessMode : std::uint8_t {
    kLocal = 0,
    kDistributed = 1,
};

// The result of a DSMEM translation: full identity of the access (P3-GAP
// identity contract — stable allocation_id + offset, never host addresses).
//
// Authorization: `context_nonce` + `launch_generation` form an
// unforgeable capability.  Each is a full 64-bit field (no bit-width
// truncation, codex review round 3): `context_nonce` is unique per Context
// (a process-global monotonic counter), `launch_generation` is the full
// per-launch counter and overflows to a structured error instead of
// wrapping.  A translation minted by Context A can never be replayed on
// Context B (even when both use the identical deterministic allocation
// sequence), and a stale translation from an earlier launch of the same
// Context is rejected.  Both fields are set at translation time and
// revalidated on every access call; a backend cannot construct them
// without the runtime.
//
// The trusted access descriptor (kind / alignment / space / width) is
// bound into the capability: read_shared only accepts kLoad, write_shared
// only kStore, atomic_shared only kAtomic — a translation minted for one
// operation cannot be re-used for another (reviewer round 2).
struct TranslatedSharedAddress {
    std::uint64_t context_nonce = 0;   // full 64-bit Context nonce
    std::uint64_t launch_generation = 0;  // full 64-bit launch counter
    std::uint64_t source_cta = 0;      // grid-linear source CTA
    std::uint64_t cluster_id = 0;      // cluster-linear id
    std::uint64_t target_rank = 0;     // rank within the cluster
    std::uint64_t target_cta = 0;      // grid-linear target CTA
    std::uint64_t logical_address = 0; // DSMEM logical address (rank<<24|off)
    AllocationId allocation;           // target shared allocation
    std::uint64_t allocation_offset = 0;  // offset within the allocation
    DevicePtr address{};               // final translated DevicePtr
    std::uint64_t width = 0;
    std::uint64_t alignment = 1;       // required alignment (bound)
    AddressSpace space = AddressSpace::kShared;  // bound space
    AccessKind kind = AccessKind::kLoad;  // bound operation kind
    SharedAccessMode mode = SharedAccessMode::kLocal;
};

// Stable cluster topology for one launch, built from the kernel's declared
// cluster metadata and the launch grid (P3-GAP cluster legality).
class ClusterTopology {
public:
    // Build from kernel cluster dims + launch grid.  Fails when:
    //   - cluster dims are absent (cluster disabled; DSMEM unavailable);
    //   - any cluster dim or grid dim is zero;
    //   - grid % cluster != 0 per-axis (a trailing partial cluster in any
    //     axis is rejected, not guessed);
    //   - any product overflows;
    //   - cluster size exceeds the sm120 capability cap.
    static StatusOr<ClusterTopology> build(
        const std::optional<std::array<std::uint32_t, 3>>& cluster_dims,
        std::uint32_t grid_x, std::uint32_t grid_y, std::uint32_t grid_z);

    bool enabled() const { return enabled_; }
    std::uint64_t cluster_size() const { return cluster_size_; }
    const std::array<std::uint32_t, 3>& dims() const { return dims_; }
    const std::array<std::uint32_t, 3>& grid_dims() const { return grid_dims_; }
    // Number of clusters per axis (grid_dims / cluster_dims).
    const std::array<std::uint64_t, 3>& cluster_grid_dims() const {
        return cluster_grid_;
    }
    std::uint64_t grid_threads() const { return grid_threads_; }

    // 3D cluster tiling (reviewer round 1).  CTA ids are x-fast linearized:
    //   cta(x,y,z) = z*gx*gy + y*gx + x
    // A cluster tiles the grid per-axis: cluster (ccx,ccy,ccz) covers
    //   x in [ccx*cx, (ccx+1)*cx), y in [ccy*cy, ...), z in [ccz*cz, ...).
    // The cluster-linear id is ccz*Cgx*Cgy + ccy*Cgx + ccx and the
    // cluster-internal rank is rz*cx*cy + ry*cx + rx where rx = x%cx etc.

    // Grid-linear CTA -> cluster-linear id.
    std::uint64_t cluster_id(std::uint64_t grid_cta) const {
        auto [x, y, z] = decode_cta(grid_cta);
        return (z / dims_[2]) * cluster_grid_[0] * cluster_grid_[1] +
               (y / dims_[1]) * cluster_grid_[0] + (x / dims_[0]);
    }
    // Grid-linear CTA -> cluster-internal rank.
    std::uint64_t cta_rank(std::uint64_t grid_cta) const {
        auto [x, y, z] = decode_cta(grid_cta);
        const std::uint64_t rx = x % dims_[0];
        const std::uint64_t ry = y % dims_[1];
        const std::uint64_t rz = z % dims_[2];
        return rz * cluster_size_xy_ + ry * dims_[0] + rx;
    }
    // (cluster-linear id, rank) -> grid-linear CTA.
    std::uint64_t grid_cta(std::uint64_t cluster, std::uint64_t rank) const {
        const std::uint64_t ccx = cluster % cluster_grid_[0];
        const std::uint64_t ccy = (cluster / cluster_grid_[0]) %
                                  cluster_grid_[1];
        const std::uint64_t ccz = cluster / (cluster_grid_[0] *
                                             cluster_grid_[1]);
        const std::uint64_t rx = rank % dims_[0];
        const std::uint64_t ry = (rank / dims_[0]) % dims_[1];
        const std::uint64_t rz = rank / cluster_size_xy_;
        const std::uint64_t x = ccx * dims_[0] + rx;
        const std::uint64_t y = ccy * dims_[1] + ry;
        const std::uint64_t z = ccz * dims_[2] + rz;
        return z * grid_dims_[0] * grid_dims_[1] + y * grid_dims_[0] + x;
    }
    bool valid_rank(std::uint64_t rank) const {
        return rank < cluster_size_;
    }

    // Total number of clusters in the grid.
    std::uint64_t cluster_count() const {
        return cluster_grid_[0] * cluster_grid_[1] * cluster_grid_[2];
    }

private:
    // Decode a grid-linear CTA into (x, y, z) (x-fast linearization).
    std::array<std::uint64_t, 3> decode_cta(std::uint64_t grid_cta) const {
        const std::uint64_t x = grid_cta % grid_dims_[0];
        const std::uint64_t y = (grid_cta / grid_dims_[0]) % grid_dims_[1];
        const std::uint64_t z = grid_cta / (grid_dims_[0] * grid_dims_[1]);
        return {x, y, z};
    }

    bool enabled_ = false;
    std::array<std::uint32_t, 3> dims_{1, 1, 1};     // cluster dims (cx,cy,cz)
    std::array<std::uint32_t, 3> grid_dims_{1, 1, 1};  // launch grid
    std::array<std::uint64_t, 3> cluster_grid_{1, 1, 1};  // clusters per axis
    std::uint64_t cluster_size_ = 1;
    std::uint64_t cluster_size_xy_ = 1;  // cx * cy
    std::uint64_t grid_threads_ = 1;
};

}  // namespace semu
