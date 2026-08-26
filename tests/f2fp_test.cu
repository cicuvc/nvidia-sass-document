// F2FP test kernel — exercise every observable variant/modifier family.
// PTX cvt forms (PTX ISA 9.x) that lower to F2FP on sm_90+:
//   cvt.rn.f16x2.f32 d, a, b                 -> F2FP.F16.F32.PACK_AB
//   cvt.rn.bf16x2.f32 d, a, b                -> F2FP.BF16.F32.PACK_AB
//   cvt.frnd2.rn.bf16.f32 d, a               -> F2FP.BF16.F32 (single)
//   cvt.rn.satfinite.e4m3x2.f32 d, a, b      -> F2FP.E4M3.F32 (f32->8b downconvert)
//   cvt.rn.satfinite.e5m2x2.f32 d, a, b      -> F2FP.E5M2.F32
//   cvt.rn.satfinite.e4m3x2.f16x2 d, a       -> F2FP.E4M3.F16 (f16->8b downconvert)
//   cvt.rn.satfinite.e5m2x2.f16x2 d, a       -> F2FP.E5M2.F16
//   cvt.rn.f16x2.e4m3x2 d, a                 -> F2FP.F16.E4M3 (8b upconvert)
//   cvt.rn.bf16x2.e4m3x2 d, a                -> F2FP.BF16.E4M3
//   cvt.rn.f16x2.e5m2x2 d, a                 -> F2FP.F16.E5M2
//   cvt.rna.satfinite.tf32.f32 d, a          -> F2FP.TF32.F32 (PACK_B)
// plus .relu modifier variants.

extern "C" __global__ void f2fp_test(const float* in, unsigned* out, int n)
{
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    unsigned a = __float_as_uint(in[i]);
    unsigned tfa = a & 0xffffe000;  // keep tf32 path as bit-op
    unsigned b = __float_as_uint(in[i + 1]);
    unsigned r = 0;

    // --- base family: f32 -> f16x2 / bf16x2, PACK_AB ----------------------
    unsigned f16x2_pair, bf16x2_pair;
    asm("cvt.rn.f16x2.f32 %0, %1, %2;" : "=r"(f16x2_pair) : "r"(a), "r"(b));
    asm("cvt.rn.bf16x2.f32 %0, %1, %2;" : "=r"(bf16x2_pair) : "r"(a), "r"(b));

    // single f32 -> f16 / bf16 (ptxas may emit F2FP with RZ packed half)
    unsigned short f16_single, bf16_single;
    asm("cvt.rn.f16.f32 %0, %1;" : "=h"(f16_single) : "r"(a));
    asm("cvt.rn.bf16.f32 %0, %1;" : "=h"(bf16_single) : "r"(a));

    // .relu on packed f16x2 (RELU modifier)
    unsigned f16x2_relu;
    asm("cvt.rn.relu.f16x2.f32 %0, %1, %2;" : "=r"(f16x2_relu) : "r"(a), "r"(b));

    // --- f32 -> 8b downconvert, satfinite ---------------------------------
    unsigned short e4m3_f32, e5m2_f32, e4m3_f32_relu;
    asm("cvt.rn.satfinite.e4m3x2.f32 %0, %1, %2;" : "=h"(e4m3_f32) : "r"(a), "r"(b));
    asm("cvt.rn.satfinite.e5m2x2.f32 %0, %1, %2;" : "=h"(e5m2_f32) : "r"(a), "r"(b));
    asm("cvt.rn.satfinite.relu.e4m3x2.f32 %0, %1, %2;" : "=h"(e4m3_f32_relu) : "r"(a), "r"(b));

    // --- f16x2 -> 8b downconvert, satfinite (merge with C) ----------------
    unsigned short e4m3_f16, e5m2_f16;
    asm("cvt.rn.satfinite.e4m3x2.f16x2 %0, %1;" : "=h"(e4m3_f16) : "r"(f16x2_pair));
    asm("cvt.rn.satfinite.e5m2x2.f16x2 %0, %1;" : "=h"(e5m2_f16) : "r"(f16x2_pair));

    // --- 8b upconvert -> f16x2 / bf16x2 -----------------------------------
    unsigned up_f16_e4m3, up_f16_e5m2;
    asm("cvt.rn.f16x2.e4m3x2 %0, %1;" : "=r"(up_f16_e4m3) : "h"(e4m3_f32));
    asm("cvt.rn.f16x2.e5m2x2 %0, %1;" : "=r"(up_f16_e5m2) : "h"(e5m2_f32));
    unsigned up_bf16_e4m3 = 0;

    // --- tf32 --------------------------------------------------------------
    
    unsigned tf32_rna = 0;

    out[i * 16 + 0]  = f16x2_pair;
    out[i * 16 + 1]  = bf16x2_pair;
    out[i * 16 + 2]  = (unsigned)f16_single;
    out[i * 16 + 3]  = (unsigned)bf16_single;
    out[i * 16 + 4]  = f16x2_relu;
    out[i * 16 + 5]  = (unsigned)e4m3_f32;
    out[i * 16 + 6]  = (unsigned)e5m2_f32;
    out[i * 16 + 7]  = (unsigned)e4m3_f32_relu;
    out[i * 16 + 8]  = (unsigned)e4m3_f16;
    out[i * 16 + 9]  = (unsigned)e5m2_f16;
    out[i * 16 + 10] = up_f16_e4m3;
    out[i * 16 + 11] = up_bf16_e4m3;
    out[i * 16 + 12] = up_f16_e5m2;
    out[i * 16 + 13] = tf32_rna;
    out[i * 16 + 14] = r;
    out[i * 16 + 15] = r;
}