// Cluster topology implementation (SIM_PLAN Phase 3.5).

#include <semu/exec/cluster.hpp>

#include <limits>

namespace semu {

// sm120 cluster capability: max 8 CTAs per cluster (matching the CUDA
// cluster API cap; the repo's sm120 findings do not exceed this).
constexpr std::uint64_t kMaxClusterSize = 8;

StatusOr<ClusterTopology> ClusterTopology::build(
    const std::optional<std::array<std::uint32_t, 3>>& cluster_dims,
    std::uint32_t grid_x, std::uint32_t grid_y, std::uint32_t grid_z) {
    ClusterTopology t;
    // Overflow-safe grid product (independent of any caller-side check).
    const std::uint64_t gx = grid_x, gy = grid_y, gz = grid_z;
    if (gx != 0 && gy > std::numeric_limits<std::uint64_t>::max() / gx) {
        return StatusOr<ClusterTopology>::failure(Error::out_of_range(
            "grid dims overflow (x*y)"));
    }
    const std::uint64_t gxy = gx * gy;
    if (gxy != 0 && gz > std::numeric_limits<std::uint64_t>::max() / gxy) {
        return StatusOr<ClusterTopology>::failure(Error::out_of_range(
            "grid dims overflow (x*y*z)"));
    }
    t.grid_threads_ = gxy * gz;
    t.grid_dims_ = {grid_x, grid_y, grid_z};
    if (!cluster_dims.has_value()) {
        // No cluster metadata: DSMEM is not available (t.enabled_ = false).
        return StatusOr<ClusterTopology>::success(std::move(t));
    }
    const auto& d = *cluster_dims;
    if (d[0] == 0 || d[1] == 0 || d[2] == 0) {
        return StatusOr<ClusterTopology>::failure(Error::invalid_argument(
            "cluster dimensions must be non-zero (x=" +
            std::to_string(d[0]) + ",y=" + std::to_string(d[1]) + ",z=" +
            std::to_string(d[2]) + ")"));
    }
    const std::uint64_t x = d[0], y = d[1], z = d[2];
    if (x != 0 && y > std::numeric_limits<std::uint64_t>::max() / x) {
        return StatusOr<ClusterTopology>::failure(Error::out_of_range(
            "cluster dims overflow (x*y)"));
    }
    const std::uint64_t xy = x * y;
    if (xy != 0 && z > std::numeric_limits<std::uint64_t>::max() / xy) {
        return StatusOr<ClusterTopology>::failure(Error::out_of_range(
            "cluster dims overflow (x*y*z)"));
    }
    const std::uint64_t size = xy * z;
    if (size > kMaxClusterSize) {
        return StatusOr<ClusterTopology>::failure(Error::invalid_argument(
            "cluster size " + std::to_string(size) + " exceeds the sm120 "
            "cap of " + std::to_string(kMaxClusterSize)));
    }
    // 3D tiling: the grid must be divisible by the cluster per axis
    // (reviewer round 1 — a trailing partial cluster in ANY axis is
    // rejected, not guessed).
    if (grid_x % d[0] != 0 || grid_y % d[1] != 0 || grid_z % d[2] != 0) {
        return StatusOr<ClusterTopology>::failure(Error::invalid_argument(
            "grid (" + std::to_string(grid_x) + "," +
            std::to_string(grid_y) + "," + std::to_string(grid_z) +
            ") is not divisible by cluster dims (" + std::to_string(d[0]) +
            "," + std::to_string(d[1]) + "," + std::to_string(d[2]) +
            ") per axis"));
    }
    t.enabled_ = true;
    t.dims_ = d;
    t.cluster_size_ = size;
    t.cluster_size_xy_ = xy;
    t.cluster_grid_ = {gx / x, gy / y, gz / z};
    return StatusOr<ClusterTopology>::success(std::move(t));
}

}  // namespace semu
