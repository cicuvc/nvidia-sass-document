// Fabric instructions — distributed shared memory fabric (DS-Fabric).
// PTX ISA 9.3, sm_100+. test try_put, try_get, and submit.
//   nvcc -arch=sm_100a -cubin -o tests/fabric_test.cubin tests/fabric_test.cu
#include <cstdint>

extern "C" __global__ void fabric_try_put(uint64_t dstLeId, uint64_t dstDataOff,
                                           uint32_t srcSmem, uint32_t mbar,
                                           uint32_t size) {
    asm volatile(
        "fabric.try_put.async.shared::cta.mbarrier::complete_tx::16B.mbarrier::report::fabric.relaxed.sys.b128 [%0, %1], [%2], %3, [%4];\n"
        :: "l"(dstLeId), "l"(dstDataOff), "r"(srcSmem), "r"(size), "r"(mbar) : "memory");
}

extern "C" __global__ void fabric_try_get(uint64_t dstSmem, uint64_t srcLeId,
                                           uint64_t srcDataOff, uint32_t mbar,
                                           uint32_t size) {
    asm volatile(
        "fabric.try_get.async.shared::cta.mbarrier::complete_tx::bytes.mbarrier::report::fabric.relaxed.sys.b128 [%0], [%1, %2], %3, [%4];\n"
        :: "l"(dstSmem), "l"(srcLeId), "l"(srcDataOff), "r"(size), "r"(mbar) : "memory");
}

extern "C" __global__ void fabric_submit() {
    asm volatile("fabric.submit.cta_group::1;\n" ::: "memory");
}
