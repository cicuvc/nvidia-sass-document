// Try direct I2I SASS encoding — write raw encoding for I2I.SAT.U8 R4, R5
// opcode 0x238 for RRR variant: bits[11:0]=0x238, bit91=0
// dstfmt [77:76] = 0 (U8), Rd [23:16] = 4, Rb [39:32] = 5
// Pg [14:12] = 7 (PT)

// Manually construct lo64 and hi64 for I2I.SAT.U8 R4, R5
__global__ void i2i_raw_sm75(int* out, int* in) {
    int val = in[0];
    int result;
    // This is a raw I2I encoding injected via inline ASM with .explicit mode
    // We can't do this in CUDA inline PTX, but let's try to force emission
    // by using the PTX mov + bit-cast to force compiler

    // Try: use sub.s32 to force a wide->narrow pattern
    result = (int)(unsigned short)(val); // C-style truncate to u16
    out[0] = result;
}

__global__ void i2i_raw_s8_sm75(int* out, int* in) {
    int val = in[0];
    int result;
    // Force s8 truncation
    result = (int)(signed char)(val); // C-style truncate to s8
    out[0] = result;
}
