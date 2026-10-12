// tcgen05.alloc.exclusive reference source (PTX ISA 9.4 / CUDA 13.4).
//
// Findings recorded in notes/sm100/arch/tcgen05_alloc_exclusive.md:
//   * .exclusive removes the power-of-2 requirement (nCols may be any multiple
//     of 32 in [32,512]).
//   * CUDA 13.4 ptxas does NOT encode nCols: the emitted SASS is byte-identical
//     for every nCols and uses __tcgen05_tmem_max_col_size (0x200 = 512) for
//     both the FIND_AND_SET request and the allocation mask, so a 96-column
//     .exclusive allocation actually consumes the whole TMEM.
//
// Build (13.4 only; 13.1 rejects '.exclusive'):
//   /usr/local/cuda-13.4/bin/nvcc -arch=sm_100a -O3 -cubin -o k.cubin \
//       tests/tcgen05_alloc_exclusive.cu
// Run on B200/B300:
//   tools/modal_tcgen05_alloc.py --hand-cubin k.cubin --function-name ...
//
// `alloc_excl96` and `alloc_excl96_twice` are the ptxas-bug reproductions.
// Patching every `MOV R?, 0x200` immediate (see the note) turns them into the
// corrected encoding; patched `alloc_excl96_twice` then returns taddr 0 and 96
// on B200 and B300.
#include <cstdint>

extern "C" __global__ void alloc_excl96(uint32_t* out) {
  __shared__ uint32_t addr[1];
  asm volatile(
      "tcgen05.alloc.exclusive.cta_group::1.sync.aligned.shared::cta.b32 "
      "[%0], 96;\n"
      :: "r"((uint32_t)__cvta_generic_to_shared(addr)) : "memory");
  __syncwarp();
  uint32_t v = addr[0];
  if (threadIdx.x == 0) out[0] = v;
  asm volatile(
      "tcgen05.dealloc.exclusive.cta_group::1.sync.aligned.b32 %0, 96;\n"
      :: "r"(v) : "memory");
  asm volatile(
      "tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;\n"
      ::: "memory");
}

// Two 96-column exclusive allocations in one CTA.  With the unpatched 13.4
// lowering the second FIND_AND_SET blocks forever (the first took all 512
// columns); with the corrected encoding it returns taddr 0 and 96.
extern "C" __global__ void alloc_excl96_twice(uint32_t* out) {
  __shared__ uint32_t a[2];
  asm volatile(
      "tcgen05.alloc.exclusive.cta_group::1.sync.aligned.shared::cta.b32 "
      "[%0], 96;\n"
      :: "r"((uint32_t)__cvta_generic_to_shared(&a[0])) : "memory");
  __syncwarp();
  asm volatile(
      "tcgen05.alloc.exclusive.cta_group::1.sync.aligned.shared::cta.b32 "
      "[%0], 96;\n"
      :: "r"((uint32_t)__cvta_generic_to_shared(&a[1])) : "memory");
  __syncwarp();
  if (threadIdx.x == 0) { out[0] = a[0]; out[1] = a[1]; }
  asm volatile(
      "tcgen05.dealloc.exclusive.cta_group::1.sync.aligned.b32 %0, 96;\n"
      :: "r"(a[0]) : "memory");
  asm volatile(
      "tcgen05.dealloc.exclusive.cta_group::1.sync.aligned.b32 %0, 96;\n"
      :: "r"(a[1]) : "memory");
  asm volatile(
      "tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;\n"
      ::: "memory");
  if (threadIdx.x == 0) out[2] = 0xff;
}

// Control: two power-of-2 allocations that fit (32 + 32) -> taddr 0, 32.
extern "C" __global__ void alloc_plain32_twice(uint32_t* out) {
  __shared__ uint32_t a[2];
  asm volatile(
      "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 "
      "[%0], 32;\n"
      :: "r"((uint32_t)__cvta_generic_to_shared(&a[0])) : "memory");
  __syncwarp();
  asm volatile(
      "tcgen05.alloc.cta_group::1.sync.aligned.shared::cta.b32 "
      "[%0], 32;\n"
      :: "r"((uint32_t)__cvta_generic_to_shared(&a[1])) : "memory");
  __syncwarp();
  if (threadIdx.x == 0) { out[0] = a[0]; out[1] = a[1]; }
  asm volatile(
      "tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 32;\n"
      :: "r"(a[0]) : "memory");
  asm volatile(
      "tcgen05.dealloc.cta_group::1.sync.aligned.b32 %0, 32;\n"
      :: "r"(a[1]) : "memory");
  asm volatile(
      "tcgen05.relinquish_alloc_permit.cta_group::1.sync.aligned;\n"
      ::: "memory");
  if (threadIdx.x == 0) out[2] = 0xff;
}

// Bare TMEM store with no tcgen05.alloc.  Columns in [0,512) succeed on
// B200/B300; column >= 512 faults with CUDA 700.  There is no "must allocate"
// hardware enforcement.  Set COL to 0/300/511 (ok) or 512/0xffff (fault).
#ifndef COL
#define COL 0u
#endif
extern "C" __global__ void stm_noalloc(uint32_t* out) {
  if (threadIdx.x < 32) {
    asm volatile("tcgen05.st.sync.aligned.32x32b.x1.b32 [%0], {%1};\n"
                 :: "r"((uint32_t)COL), "r"(0x55555555u));
    asm volatile("tcgen05.wait::st.sync.aligned;\n" ::: "memory");
  }
  __syncwarp();
  if (threadIdx.x == 0) out[0] = (uint32_t)COL;
}
