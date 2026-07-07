// REDAS coverage: red.async.shared::cluster (distributed shared mem reduce), ops/types.
#include <cstdint>

#define RED(NAME, OP, TY, CTY, CN) \
extern "C" __global__ void NAME(CTY val, unsigned dst, unsigned bar) { \
    asm volatile("red.async.relaxed.cluster.shared::cluster.mbarrier::complete_tx::bytes." OP "." TY \
        " [%0], %1, [%2];" :: "r"(dst), CN(val), "r"(bar) : "memory"); \
}

RED(redas_add_u32, "add", "u32", uint32_t, "r")
RED(redas_min_u32, "min", "u32", uint32_t, "r")
RED(redas_max_u32, "max", "u32", uint32_t, "r")
RED(redas_min_s32, "min", "s32", int32_t,  "r")
RED(redas_max_s32, "max", "s32", int32_t,  "r")
RED(redas_inc_u32, "inc", "u32", uint32_t, "r")
RED(redas_dec_u32, "dec", "u32", uint32_t, "r")
RED(redas_and_b32, "and", "b32", uint32_t, "r")
RED(redas_or_b32,  "or",  "b32", uint32_t, "r")
RED(redas_xor_b32, "xor", "b32", uint32_t, "r")
RED(redas_add_u64, "add", "u64", uint64_t, "l")
