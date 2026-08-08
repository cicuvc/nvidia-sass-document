// mini_decode.c - minimal x86-64 store instruction decoder.
// Identifies store width + source value for the SIGSEGV doorbell trap.
// Only needs to cover what compilers emit for 8/16/32/64-bit MMIO stores.
#define _GNU_SOURCE
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <sys/ucontext.h>

bool decode_store(const uint8_t *ip, const greg_t *gregs,
                  int *width, uint64_t *value, int *insn_len);

// extended: fills up to 16 bytes of store data (for SSE stores).
// `fp` is fxsave layout (from ucontext uc_mcontext.fpregs); xmm regs at offset 160.
bool decode_store_ex(const uint8_t *ip, const greg_t *gregs, const uint8_t *fp,
                     int *width, uint8_t *value16, int *insn_len)
{
    int i = 0;
    bool rex_w = false;
    uint8_t rex_r = 0;
    bool op16 = false;
    uint8_t pfx_f2 = 0, pfx_f3 = 0;

    while (i < 15) {
        uint8_t b = ip[i];
        if (b == 0x66) { op16 = true; i++; }
        else if (b == 0xf2) { pfx_f2 = 1; i++; }
        else if (b == 0xf3) { pfx_f3 = 1; i++; }
        else if (b >= 0x40 && b <= 0x4f) { rex_w = (b & 8) != 0; rex_r = (b >> 2) & 1; i++; }
        else if (b == 0xf0 ||
                 (b >= 0x2e && b <= 0x3e && (b & 0xe7) == 0x26)) { i++; }
        else break;
    }
    if (i >= 15) return false;

    uint8_t op = ip[i];

    #define REGVAL(idx) ((uint64_t)gregs[ \
        (idx)==0?REG_RAX:(idx)==1?REG_RCX:(idx)==2?REG_RDX:(idx)==3?REG_RBX: \
        (idx)==4?REG_RSP:(idx)==5?REG_RBP:(idx)==6?REG_RSI:(idx)==7?REG_RDI: \
        (idx)==8?REG_R8:(idx)==9?REG_R9:(idx)==10?REG_R10:(idx)==11?REG_R11: \
        (idx)==12?REG_R12:(idx)==13?REG_R13:(idx)==14?REG_R14:REG_R15])

    #define MODRM_LEN(m, mlen, reg) do { \
        uint8_t modrm = ip[(m)]; \
        (reg) = ((modrm >> 3) & 7) | (rex_r << 3); \
        int mod = modrm >> 6, rm = modrm & 7; \
        int len = (m) + 1; \
        if (mod != 3 && rm == 4) { len++; } \
        if (mod == 1) len += 1; \
        else if (mod == 2) len += 4; \
        else if (mod == 0 && rm == 5) len += 4; \
        (mlen) = len; \
    } while (0)

    #define XMMVAL(idx) (fp + 160 + ((idx) & 15) * 16)

    if (op == 0x0f) {
        uint8_t op2 = ip[i + 1];
        int reg, len;
        if (op2 == 0x11 || op2 == 0x29 || op2 == 0x7f) {
            // MOVUPS/MOVUPD/MOVSD/MOVSS / MOVAPD / MOVDQA/MOVDQU xmm -> m
            MODRM_LEN(i + 2, len, reg);
            int w;
            if (pfx_f3 && op2 == 0x11) w = 4;        // movss
            else if (pfx_f2 && op2 == 0x11) w = 8;   // movsd
            else w = 16;
            if (fp) memcpy(value16, XMMVAL(reg), w);
            else memset(value16, 0, w);
            *width = w;
            *insn_len = len;
            return true;
        }
        if (op2 == 0xc3) {
            // MOVNTI r/m, r
            MODRM_LEN(i + 2, len, reg);
            int w = rex_w ? 8 : 4;
            uint64_t v = REGVAL(reg) & (w == 8 ? ~0ull : (1ull << (w * 8)) - 1);
            memcpy(value16, &v, w);
            *width = w;
            *insn_len = len;
            return true;
        }
        return false;
    }
    if (op == 0x89 || op == 0x88) {
        int reg, len;
        MODRM_LEN(i + 1, len, reg);
        int w = (op == 0x88) ? 1 : op16 ? 2 : rex_w ? 8 : 4;
        uint64_t v = REGVAL(reg) & (w == 8 ? ~0ull : (1ull << (w * 8)) - 1);
        memcpy(value16, &v, w);
        *width = w;
        *insn_len = len;
        return true;
    }
    if (op == 0xc7 || op == 0xc6) {
        int reg, len;
        MODRM_LEN(i + 1, len, reg);
        if ((reg & 7) != 0) return false;
        int w = (op == 0xc6) ? 1 : op16 ? 2 : 4;
        int immb = (w == 8) ? 4 : w;
        if (rex_w && op == 0xc7) { w = 8; }
        uint64_t v = 0;
        memcpy(&v, ip + len, immb);
        memcpy(value16, &v, w);
        *width = w;
        *insn_len = len + immb;
        return true;
    }
    return false;

    #undef REGVAL
    #undef MODRM_LEN
    #undef XMMVAL
}
