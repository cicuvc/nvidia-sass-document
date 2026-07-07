#include <cooperative_groups.h>
#include <cooperative_groups/reduce.h>
namespace cg = cooperative_groups;

// grid-wide cooperative sync (device-wide collective)
__global__ void grid_sync(int *a, int *out) {
    cg::grid_group grid = cg::this_grid();
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    a[i] += 1;
    grid.sync();
    out[i] = a[i];
}
// genuine hardware EXIT (via asm) for a subset, then a warp collective on survivors
__global__ void asm_exit_reduce(int *a, int *out) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (a[i] < 0) { asm volatile("exit;"); }
    cg::coalesced_group g = cg::coalesced_threads();
    out[i] = cg::reduce(g, a[i], cg::plus<int>());
}
