// UBLKRED coverage: cp.reduce.async.bulk (non-tensor), global<-shared reduce.
#include <cstdint>

// global-dst bulk_group form: many redop/type combos
#define GRED(NAME, OP, TY) \
extern "C" __global__ void NAME(void* __restrict__ g, const void* __restrict__ s, int n) { \
    unsigned ss = __cvta_generic_to_shared(s); \
    asm volatile("cp.reduce.async.bulk.global.shared::cta.bulk_group." OP "." TY " [%0], [%1], %2;" \
        :: "l"(g), "r"(ss), "r"(n) : "memory"); \
    asm volatile("cp.async.bulk.commit_group;"); \
}

GRED(g_add_u32, "add", "u32")
GRED(g_min_u32, "min", "u32")
GRED(g_max_u32, "max", "u32")
GRED(g_inc_u32, "inc", "u32")
GRED(g_dec_u32, "dec", "u32")
GRED(g_and_b32, "and", "b32")
GRED(g_or_b32,  "or",  "b32")
GRED(g_xor_b32, "xor", "b32")
GRED(g_add_s32, "add", "s32")
GRED(g_add_u64, "add", "u64")
GRED(g_min_s64, "min", "s64")
GRED(g_add_f32, "add", "f32")
GRED(g_add_f64, "add", "f64")
GRED(g_add_f16, "add.noftz", "f16")
GRED(g_add_bf16,"add.noftz", "bf16")
GRED(g_min_f16, "min", "f16")

// shared::cluster-dst mbarrier form
extern "C" __global__ void s_add_u32(const void* __restrict__ s, const void* __restrict__ d, int n) {
    unsigned ss = __cvta_generic_to_shared(s);
    unsigned dd = __cvta_generic_to_shared(d);
    __shared__ uint64_t bar;
    unsigned b = __cvta_generic_to_shared(&bar);
    asm volatile("cp.reduce.async.bulk.shared::cluster.shared::cta.mbarrier::complete_tx::bytes.add.u32"
        " [%0], [%1], %2, [%3];" :: "r"(dd), "r"(ss), "r"(n), "r"(b) : "memory");
}
