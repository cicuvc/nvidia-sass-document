extern "C" __global__ void opex2_iadd(int *out, int a)
{
    out[threadIdx.x] = a + 0x1234;
}

extern "C" __global__ void opex2_fadd(float *out, float a)
{
    out[threadIdx.x] = a + 1.25f;
}

extern "C" __global__ void opex2_lop(unsigned *out, unsigned a)
{
    out[threadIdx.x] = a & 0x1234u;
}
