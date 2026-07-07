#include <cooperative_groups.h>
#include <cooperative_groups/reduce.h>
#include <cooperative_groups/scan.h>
namespace cg = cooperative_groups;

// cluster (CGA) sync
__global__ void __cluster_dims__(2,1,1) cluster_sync(int *a, int *out) {
    cg::cluster_group cl = cg::this_cluster();
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    cl.sync();
    out[i] = a[i] + cl.block_rank();
}

// warp-level collective reduce/scan (may lower to WARPSYNC.COLLECTIVE?)
__global__ void warp_reduce(int *a, int *out) {
    cg::thread_block_tile<32> w = cg::tiled_partition<32>(cg::this_thread_block());
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    int s = cg::reduce(w, a[i], cg::plus<int>());
    int sc = cg::exclusive_scan(w, a[i], cg::plus<int>());
    out[i] = s + sc;
}

// block-level collective
__global__ void block_reduce(int *a, int *out) {
    cg::thread_block b = cg::this_thread_block();
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    b.sync();
    out[i] = a[i];
}
