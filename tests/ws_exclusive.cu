#include <cooperative_groups.h>
#include <cooperative_groups/reduce.h>
namespace cg = cooperative_groups;

// coalesced_group sync (divergent subset that "coalesces")
__global__ void coalesced_sync(int *a, int *out) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if (a[i] & 1) {                          // only odd-valued lanes active
        cg::coalesced_group g = cg::coalesced_threads();
        int v = a[i];
        g.sync();                            // subset sync
        out[i] = v + g.thread_rank();
    }
}

// binary_partition -> two disjoint subgroups, each syncs
__global__ void binary_part(int *a, int *out) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    cg::thread_block_tile<32> w = cg::tiled_partition<32>(cg::this_thread_block());
    auto part = cg::binary_partition(w, (a[i] & 1) != 0);
    part.sync();                             // each partition syncs its own mask
    out[i] = part.thread_rank();
}

// labeled_partition -> arbitrary disjoint groups by label
__global__ void labeled_part(int *a, int *out) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    cg::thread_block_tile<32> w = cg::tiled_partition<32>(cg::this_thread_block());
    auto part = cg::labeled_partition(w, a[i] & 3);
    part.sync();
    out[i] = part.thread_rank();
}
