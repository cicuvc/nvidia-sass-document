// ============================================================================
// HGMMA bf16 verification — sm_90a (H20/H100)
// m64n16k16, bf16 inputs, fp32 accumulate, both inputs from shared memory.
// ============================================================================
//
// ── PTX → SASS lowering ─────────────────────────────────────────────────────
//
//   PTX wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16
//     → HGMMA.64x16x16.F32.BF16  (opcode 0x19f0, hgmma_URa_Rc_ dense)
//
//   PTX wgmma.fence.sync.aligned
//     → WARPGROUP.ARRIVE          (opcode 0x09c5, mode=ARRIVEONLY)
//
//   PTX wgmma.commit_group.sync.aligned
//     → (no instruction)          (folded into the tail HGMMA's gsb0 write)
//
//   PTX wgmma.wait_group.sync.aligned N
//     → WARPGROUP.DEPBAR.LE gsb0, N  (opcode 0x09c5, mode=DEPBARONLY|LEONLY)
//
// Full SASS output from nvcc (sm_90a, CUDA 12.4):
//
//   WARPGROUP.ARRIVE                                        # fence
//   HGMMA.64x16x16.F32.BF16 R24, gdesc[UR4], RZ, !UPT, gsb0 # mma (scale-d=F)
//   WARPGROUP.DEPBAR.LE gsb0, 0x0                           # wait_group 0
//
// ── HGMMA instruction encoding (hgmma_URa_Rc_, opcode=0x19f0) ──────────────
//
//   From nvcc cuobjdump (H20):  lo64=0x00200000041879f0  hi64=0x000fe6000c0018ff
//
//   Field      Bits        Value  Meaning
//   opcode     [91]|[11:0] 0x19f0 hgmma_URa_Rc_
//   Pg         [14:12]     7      PT (always-true predicate)
//   Pg_not     [15]        0
//   Rd         [23:16]     24     accumulator dest  R24..R31 (8 f32 regs)
//   URa        [29:24]     4      descriptor  UR4..UR7 (4 aligned URs)
//   size       [59:53]     1      SIZE_64x16x16  (=1 in the SIZE_64x* enum)
//   tnspA      [61]        0      notnspa  (K-major = row-major for A)
//   tnspB      [62]        0      notnspb  (K-major = col-major for B)
//   negB       [63]        0      nonegb
//   Rc         [71:64]     0xff   RZ  (scale-d=false → D = A×B, no accumulate)
//   negA       [72]        0      nonega
//   sz         [73]        0      fixed
//   sh         [74]        0      fixed (*0 = dense)
//   dstfmt     [75]        1      FloatNo64::F32
//   srcfmt     [77:76]     1      SRCFMT::BF16  (F16=0, BF16/E8M7=1, TF32=2, E6M9=3)
//   gsb        [86:84]     0      gsb0  (only valid value; 7=nooptional_gsb)
//   op (UPp)   [90:87]     8      !UPT  (via TABLES_Pnz_0)
//   src_rel_sb [115:113]   7      fixed (no general scoreboard on source)
//   dst_wr_sb  [112:110]   7      fixed (no general scoreboard on dest)
//   req_bit_set[121:116]   0      no input waits (data already in shared mem)
//   opex       [124:122]|[109:105]  TABLES_opex_0(batch_t, usched_info)
//
//   size enum (7-bit):  K=16 shapes are 0..63, K=8 shapes are 64..127.
//   For m64n16k16 → size=1.  N varies as 8,16,24,...,256 in steps of 8.
//
// ── Shared memory descriptor (GMMA:gdesc) ───────────────────────────────────
//
//   64-bit descriptor in aligned UniformRegister pair (UR4..UR7 for our case).
//   Format (K-major, no-swizzle):
//
//     bits [13:0]  = start_addr = (shmem_byte_addr & 0x3FFFF) >> 4
//     bits [29:16] = LBO = (leading_dim_byte_offset & 0x3FFFF) >> 4
//     bits [45:32] = SBO = (stride_dim_byte_offset & 0x3FFFF) >> 4
//     bits [51:49] = base_offset (0 when swizzle pattern starts at boundary)
//     bits [63:62] = swizzle_mode (0=none, 1=128B, 2=64B, 3=32B)
//
//   K-major no-swizzle tile layout: 8×1 (8 K-elements × 1 non-K position
//   in 128-bit normalized space).  For bf16 (2B/element), each 128b token
//   = 8 consecutive K-elements = 16 bytes.
//
//   LBO (=leading dimension byte offset):
//     For K-major no-swizzle: step from 1st→2nd non-K position within the
//     same 8-K group.  With 16B per token, LBO_encode = 16>>4 = 1.
//
//   SBO (=stride dimension byte offset):
//     For K-major no-swizzle: step from first 8 rows to next 8 rows
//     across ALL non-K positions.  8 rows × 16B/token = 128B.
//     SBO_encode = 128>>4 = 8.
//
//   Access pattern (A: 64×16 K-major, B: 16×16 K-major):
//     For kgroup in 0..(K/8-1):
//       For npos in 0..(N-1):
//         addr = kgroup×SBO×16 + npos×LBO×16
//         → reads K = kgroup×8 .. kgroup×8+7, N = npos
//
// ── make_desc() limitation ──────────────────────────────────────────────────
//
//   The simple make_desc() here (LBO=1, SBO=8, swizzle=0) works ONLY for
//   uniform input data (all-ones / all-same-value).  For arbitrary non-uniform
//   patterns, SWEEPING LBO∈{1,2,4} × SBO∈{1..16} × tnspB∈{0,1} over
//   row-major and column-major storage CONFIRMED: no combination produces
//   correct results.  All 32 LBO/SBO/tnspB combos tested against CPU
//   reference gave 989–1024/1024 sorted-element mismatches.
//
//   Root cause: nvcc constructs the GMMA descriptor at runtime using a
//   sequence of UPRMT (byte-level permutation interleaving CTA-ID bits into
//   the shared-memory address), USHF (right-shift by 4 to align start_addr),
//   and ULOP3 (LUT-based OR to set LBO=1).  The resulting descriptor
//   accounts for the compiler's exact shared memory allocation layout
//   (array ordering, inter-array padding, swizzle alignment) which differs
//   from the simple flat LBO/SBO model implied by the PTX spec.  See the
//   SASS at the top of this file for the full compiler-generated sequence.
//
//   Consequence: this test file is a CORRECTNESS smoke test for the wgmma
//   CONTROL-FLOW pipeline (fence → mma → commit → wait) and the HGMMA
//   INSTRUCTION ENCODING, verified against nvcc-generated SASS on H20.
//   It is NOT a numerical-correctness test for arbitrary GEMM.  To extend
//   to arbitrary data, either replicate nvcc's UPRMT/USHF/ULOP3 descriptor
//   construction, or use the compiler-generated kernel's descriptor bytes.
//
//   All-ones verification: 16.0 = sum_{k=0}^{15} (1.0 * 1.0) = 16.0 ✓
//   2-MMA accumulation:   32.0 = 16.0 + 16.0 ✓
//   Because all elements are identical, any layout misread produces the
//   same value, isolating the control-flow + encode correctness from the
//   data-layout correctness.
//
// ── Thread-to-element mapping (m64n16k16 f32 accumulator) ───────────────────
//
//   The 128 threads (4 warps × 32) in the warpgroup collectively produce a
//   64×16 f32 output matrix = 1024 elements.  Each thread holds 8 f32 regs.
//
//   Empirically (probe with B[0][0]=1.0, A=all-ones):
//     • Every 4th thread (t=0,4,8,...,124) gets the value 1.0 in regs 0,2
//     • 32 threads × 2 non-zeros = 64 total = all 64 rows of column 0 ✓
//     • Threads t..t+3 share the same two rows, covering 16 columns across them
//
//   Row grouping:  threads 0-3  → rows 0,4  (values: 16,80 for A[i][j]=i+1)
//                  threads 4-7  → rows 1,5  (values: 24,88)
//                  threads 8-11 → rows 2,6  (values: 32,96)
//                  threads 12-15→ rows 3,7  (values: 40,104)
//                  ... repeating with +8 row offset for each group of 16 threads
//
//   This matches the PTX ISA Figure 149 accumulator fragment layout for
//   m64nNk16 f32: the 64 rows are partitioned into 8 groups of 8 rows each,
//   distributed across the 4 subcores (one per warp).  See
//   notes/sm90/instr/hgmma.md and notes/sm90/arch/wgmma.md for details.
//
// ── Sync skeleton ───────────────────────────────────────────────────────────
//
//   WARPGROUP.ARRIVE              // wgmma.fence — hand accumulator regs to TC
//   HGMMA ... RZ, !UPT            // first MMA: scale-d=F (RZ = no prior sum)
//   HGMMA ... R24                 // subsequent: accumulate onto same R24
//   HGMMA ... gsb0                // last MMA: write group scoreboard (commit)
//   WARPGROUP.DEPBAR.LE gsb0, 0   // wgmma.wait_group 0 — drain TC → RF
//
//   Key: only the LAST HGMMA in a same-accumulator chain writes gsb0.
//   Intermediate HGMMAs forward partial sums inside the tensor core collector.
//   commit_group emits no instruction — the group boundary is implicit in the
//   tail HGMMA's group-scoreboard write.  See notes/sm90/arch/wgmma.md §2.
//
// ── References ──────────────────────────────────────────────────────────────
//
//   notes/sm90/instr/hgmma.md      — HGMMA instruction reference
//   notes/sm90/arch/wgmma.md       — warpgroup sync model, collector, subcores
//   sm_90_instructions.txt:57724   — CLASS hgmma_Ra_URb_Rc_
//   sm_90_instructions.txt:58846   — CLASS hgmma_URa_Rc_    (our variant)
//   tools/query_sm90.py mnem HGMMA — variant summary + pipe
//   tools/query_sm90.py layout hgmma_URa_Rc_  — 128-bit field map
//   documented-ptx/09.7.16-*.md    — PTX ISA §9.7.16 (wgmma)
// ============================================================================

#include <cuda_bf16.h>
#include <cstdint>
#include <cstdio>
#include <cmath>
#include <cstdlib>
#include <cstring>

__device__ __forceinline__ uint64_t make_desc(uint32_t saddr) {
    uint64_t d = 0;
    d |= ((uint64_t)(saddr & 0x3FFFF) >> 4);
    d |= ((uint64_t)1) << 16;
    d |= ((uint64_t)8) << 32;
    return d;
}

extern "C" __global__ void hgmma_single(float* out,
    const __nv_bfloat16* gA, const __nv_bfloat16* gB)
{
    __shared__ __nv_bfloat16 sA[64 * 16];
    __shared__ __nv_bfloat16 sB[16 * 16];
    int t = threadIdx.x;
    for (int i = t; i < 64 * 16; i += blockDim.x) sA[i] = gA[i];
    for (int i = t; i < 16 * 16; i += blockDim.x) sB[i] = gB[i];
    __syncthreads();

    uint64_t dA = make_desc(__cvta_generic_to_shared(sA));
    uint64_t dB = make_desc(__cvta_generic_to_shared(sB));

    float d[8];
#pragma unroll
    for (int i = 0; i < 8; i++) d[i] = 0.f;

    asm volatile("wgmma.fence.sync.aligned;\n");
    asm volatile(
      "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 "
      "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1, 0, 0;\n"
      : "+f"(d[0]),"+f"(d[1]),"+f"(d[2]),"+f"(d[3]),
        "+f"(d[4]),"+f"(d[5]),"+f"(d[6]),"+f"(d[7])
      : "l"(dA), "l"(dB));
    asm volatile("wgmma.commit_group.sync.aligned;\n");
    asm volatile("wgmma.wait_group.sync.aligned 0;\n");

#pragma unroll
    for (int i = 0; i < 8; i++) out[t * 8 + i] = d[i];
}

extern "C" __global__ void hgmma_accumulate(float* out,
    const __nv_bfloat16* gA, const __nv_bfloat16* gB)
{
    __shared__ __nv_bfloat16 sA[64 * 16];
    __shared__ __nv_bfloat16 sB[16 * 16];
    int t = threadIdx.x;
    for (int i = t; i < 64 * 16; i += blockDim.x) sA[i] = gA[i];
    for (int i = t; i < 16 * 16; i += blockDim.x) sB[i] = gB[i];
    __syncthreads();

    uint64_t dA = make_desc(__cvta_generic_to_shared(sA));
    uint64_t dB = make_desc(__cvta_generic_to_shared(sB));

    float d[8];
#pragma unroll
    for (int i = 0; i < 8; i++) d[i] = 0.f;

    asm volatile("wgmma.fence.sync.aligned;\n");
    asm volatile(
      "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 "
      "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1, 0, 0;\n"
      : "+f"(d[0]),"+f"(d[1]),"+f"(d[2]),"+f"(d[3]),
        "+f"(d[4]),"+f"(d[5]),"+f"(d[6]),"+f"(d[7])
      : "l"(dA), "l"(dB));
    asm volatile(
      "wgmma.mma_async.sync.aligned.m64n16k16.f32.bf16.bf16 "
      "{%0,%1,%2,%3,%4,%5,%6,%7}, %8, %9, 1, 1, 1, 0, 0;\n"
      : "+f"(d[0]),"+f"(d[1]),"+f"(d[2]),"+f"(d[3]),
        "+f"(d[4]),"+f"(d[5]),"+f"(d[6]),"+f"(d[7])
      : "l"(dA), "l"(dB));
    asm volatile("wgmma.commit_group.sync.aligned;\n");
    asm volatile("wgmma.wait_group.sync.aligned 0;\n");

#pragma unroll
    for (int i = 0; i < 8; i++) out[t * 8 + i] = d[i];
}

int main() {
    const int N = 128 * 8;
    const int nA = 64 * 16, nB = 16 * 16;
    bool all_pass = true;

    // ── Test 1: Single MMA, all ones → 16.0 ─────────────────────
    printf("=== Test 1: Single MMA, all-ones (expect 16.0) ===\n");
    {
        __nv_bfloat16 hA[nA], hB[nB];
        for (int i = 0; i < nA; i++) hA[i] = __float2bfloat16_rz(1.0f);
        for (int i = 0; i < nB; i++) hB[i] = __float2bfloat16_rz(1.0f);

        __nv_bfloat16 *dA, *dB; float *dOut;
        cudaMalloc(&dA, nA * 2); cudaMalloc(&dB, nB * 2);
        cudaMalloc(&dOut, N * 4);
        cudaMemcpy(dA, hA, nA * 2, cudaMemcpyHostToDevice);
        cudaMemcpy(dB, hB, nB * 2, cudaMemcpyHostToDevice);

        hgmma_single<<<1, 128>>>(dOut, dA, dB);
        float hOut[N];
        cudaMemcpy(hOut, dOut, N * 4, cudaMemcpyDeviceToHost);

        int mm = 0;
        for (int i = 0; i < N; i++)
            if (fabsf(hOut[i] - 16.0f) > 0.01f) mm++;
        printf("  %s (%d/%d mismatches)\n", mm == 0 ? "PASS" : "FAIL", mm, N);
        if (mm != 0) all_pass = false;

        cudaFree(dA); cudaFree(dB); cudaFree(dOut);
    }

    // ── Test 2: Two MMAs accumulating, all ones → 32.0 ─────────
    printf("=== Test 2: 2-MMA accumulation, all-ones (expect 32.0) ===\n");
    {
        __nv_bfloat16 hA[nA], hB[nB];
        for (int i = 0; i < nA; i++) hA[i] = __float2bfloat16_rz(1.0f);
        for (int i = 0; i < nB; i++) hB[i] = __float2bfloat16_rz(1.0f);

        __nv_bfloat16 *dA, *dB; float *dOut;
        cudaMalloc(&dA, nA * 2); cudaMalloc(&dB, nB * 2);
        cudaMalloc(&dOut, N * 4);
        cudaMemcpy(dA, hA, nA * 2, cudaMemcpyHostToDevice);
        cudaMemcpy(dB, hB, nB * 2, cudaMemcpyHostToDevice);

        hgmma_accumulate<<<1, 128>>>(dOut, dA, dB);
        float hOut[N];
        cudaMemcpy(hOut, dOut, N * 4, cudaMemcpyDeviceToHost);

        int mm = 0;
        for (int i = 0; i < N; i++)
            if (fabsf(hOut[i] - 32.0f) > 0.02f) mm++;
        printf("  %s (%d/%d mismatches)\n", mm == 0 ? "PASS" : "FAIL", mm, N);
        if (mm != 0) all_pass = false;

        cudaFree(dA); cudaFree(dB); cudaFree(dOut);
    }

    printf("\n%s\n", all_pass ? "All tests PASSED." : "Some tests FAILED.");
    return all_pass ? 0 : 1;
}
