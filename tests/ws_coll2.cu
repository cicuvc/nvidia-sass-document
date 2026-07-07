#include <cooperative_groups.h>
#include <cooperative_groups/reduce.h>
namespace cg = cooperative_groups;

// early return (real EXIT) then survivors do a coalesced collective
__global__ void survivors_reduce(int *a, int *out, int n) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (a[i] < 0) { out[i] = -1; return; }          // some lanes EXIT
    cg::coalesced_group g = cg::coalesced_threads(); // mask of survivors
    int s = cg::reduce(g, a[i], cg::plus<int>());
    out[i] = s;
}
// reduce/redux warp intrinsics after divergence
__global__ void redux_after_div(int *a, int *out) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (a[i] == 0) { out[i] = 0; return; }
    unsigned m = __activemask();
    int s = __reduce_add_sync(m, a[i]);
    out[i] = s;
}
