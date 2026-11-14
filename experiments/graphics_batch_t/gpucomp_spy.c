#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <unistd.h>

#define HOOK_COUNT 13

void *gpucomp_real_table[HOOK_COUNT];

extern void gpucomp_hook_0(void);
extern void gpucomp_hook_1(void);
extern void gpucomp_hook_2(void);
extern void gpucomp_hook_3(void);
extern void gpucomp_hook_4(void);
extern void gpucomp_hook_5(void);
extern void gpucomp_hook_6(void);
extern void gpucomp_hook_7(void);
extern void gpucomp_hook_8(void);
extern void gpucomp_hook_9(void);
extern void gpucomp_hook_10(void);
extern void gpucomp_hook_11(void);
extern void gpucomp_hook_12(void);

static void *hooks[HOOK_COUNT] = {
    gpucomp_hook_0, gpucomp_hook_1, gpucomp_hook_2, gpucomp_hook_3,
    gpucomp_hook_4, gpucomp_hook_5, gpucomp_hook_6, gpucomp_hook_7,
    gpucomp_hook_8, gpucomp_hook_9, gpucomp_hook_10, gpucomp_hook_11,
    gpucomp_hook_12,
};

static void *hooked_table[HOOK_COUNT];

static void append_bytes(int fd, const char *label, uint64_t address,
                         size_t count);

static void append_descriptor(int fd, uint64_t address)
{
    uint64_t words[32] = {0};
    int memfd = (int)syscall(SYS_openat, AT_FDCWD, "/proc/self/mem", O_RDONLY);
    if (memfd < 0)
        return;
    ssize_t got = syscall(SYS_pread64, memfd, words, sizeof(words),
                          (off_t)address);
    syscall(SYS_close, memfd);
    if (got <= 0)
        return;
    for (int i = 0; i < 32; ++i) {
        uint64_t value = words[i];
        if (value >= 0x10000 && value < 0x0000800000000000ULL) {
            char label[32];
            snprintf(label, sizeof(label), "desc+%02x", i * 8);
            append_bytes(fd, label, value, 48);
        }
    }
}

static void scan_self_for_elf(void)
{
    static int scanned;
    if (scanned)
        return;
    scanned = 1;

    const char *dir = getenv("SPY_GPUCOMP_DUMP_DIR");
    if (!dir)
        return;
    FILE *maps = fopen("/proc/self/maps", "r");
    if (!maps)
        return;
    int memfd = (int)syscall(SYS_openat, AT_FDCWD, "/proc/self/mem", O_RDONLY);
    if (memfd < 0) {
        fclose(maps);
        return;
    }

    char line[512];
    int found = 0;
    unsigned char *buf = malloc(1u << 20);
    while (buf && fgets(line, sizeof(line), maps)) {
        uint64_t lo, hi;
        char perms[8] = {0};
        if (sscanf(line, "%lx-%lx %7s", &lo, &hi, perms) != 3 ||
            perms[0] != 'r')
            continue;
        for (uint64_t at = lo; at < hi; at += (1u << 20)) {
            size_t want = (size_t)((hi - at < (1u << 20)) ? hi - at : (1u << 20));
            ssize_t got = syscall(SYS_pread64, memfd, buf, want, (off_t)at);
            if (got <= 0)
                continue;
            for (ssize_t i = 0; i + 4 <= got; ++i) {
                if (buf[i] == 0x7f && buf[i + 1] == 'E' &&
                    buf[i + 2] == 'L' && buf[i + 3] == 'F') {
                    char path[512];
                    snprintf(path, sizeof(path), "%s/found_%d.elf", dir, found++);
                    int out = (int)syscall(
                        SYS_openat, AT_FDCWD, path,
                        O_WRONLY | O_CREAT | O_TRUNC, 0644);
                    if (out >= 0) {
                        size_t dump = 65536;
                        if ((size_t)(got - i) < dump)
                            dump = (size_t)(got - i);
                        syscall(SYS_write, out, buf + i, dump);
                        syscall(SYS_close, out);
                    }
                    if (found >= 32)
                        goto done;
                }
            }
        }
    }
done:
    free(buf);
    syscall(SYS_close, memfd);
    fclose(maps);
}

static void scan_self_for_sass(int slot)
{
    static int scanned[128];
    if (slot < 0 || slot >= 128 || scanned[slot])
        return;
    scanned[slot] = 1;

    const char *dir = getenv("SPY_GPUCOMP_DUMP_DIR");
    if (!dir)
        return;
    FILE *maps = fopen("/proc/self/maps", "r");
    if (!maps)
        return;
    int memfd = (int)syscall(SYS_openat, AT_FDCWD, "/proc/self/mem", O_RDONLY);
    if (memfd < 0) {
        fclose(maps);
        return;
    }

    static const unsigned char exit_sig[8] =
        {0x4d, 0x79, 0, 0, 0, 0, 0, 0};
    static const unsigned char nop_sig[8] =
        {0x18, 0x79, 0, 0, 0, 0, 0, 0};
    char line[512];
    int found = 0;
    unsigned char *buf = malloc(1u << 20);
    while (buf && fgets(line, sizeof(line), maps)) {
        uint64_t lo, hi;
        char perms[8] = {0};
        if (sscanf(line, "%lx-%lx %7s", &lo, &hi, perms) != 3 ||
            perms[0] != 'r')
            continue;
        if (!strstr(line, "[heap]") && !strstr(line, "[anon:") &&
            !strstr(line, "libcuda") && !strstr(line, "libnvidia"))
            continue;
        for (uint64_t at = lo; at < hi; at += (1u << 20)) {
            size_t want = (size_t)((hi - at < (1u << 20)) ? hi - at : (1u << 20));
            ssize_t got = syscall(SYS_pread64, memfd, buf, want, (off_t)at);
            if (got <= 0)
                continue;
            for (ssize_t i = 0; i + 16 <= got; ++i) {
                if ((i & 15) != 0)
                    continue;
                if (!memcmp(buf + i, exit_sig, 8) ||
                    !memcmp(buf + i, nop_sig, 8)) {
                    uint64_t pos = at + (uint64_t)i;
                    uint64_t start = pos > 2048 ? pos - 2048 : at;
                    char path[512];
                    snprintf(path, sizeof(path), "%s/sass_slot%d_%d.bin",
                             dir, slot, found++);
                    int out = (int)syscall(
                        SYS_openat, AT_FDCWD, path,
                        O_WRONLY | O_CREAT | O_TRUNC, 0644);
                    if (out >= 0) {
                        unsigned char *dump = malloc(4096);
                        ssize_t n = syscall(SYS_pread64, memfd, dump, 4096,
                                            (off_t)start);
                        if (n > 0)
                            syscall(SYS_write, out, dump, (size_t)n);
                        free(dump);
                        syscall(SYS_close, out);
                    }
                    if (found >= 64)
                        goto done;
                }
            }
        }
    }
done:
    free(buf);
    syscall(SYS_close, memfd);
    fclose(maps);
}

static int has_bytes(const unsigned char *buf, size_t size,
                     const unsigned char *needle, size_t needle_size)
{
    for (size_t i = 0; i + needle_size <= size; ++i)
        if (!memcmp(buf + i, needle, needle_size))
            return 1;
    return 0;
}

static void scan_self_for_shader_constants(int slot)
{
    static int scanned[128];
    if (slot < 0 || slot >= 128 || scanned[slot])
        return;
    scanned[slot] = 1;

    const char *dir = getenv("SPY_GPUCOMP_DUMP_DIR");
    if (!dir)
        return;
    FILE *maps = fopen("/proc/self/maps", "r");
    if (!maps)
        return;
    int memfd = (int)syscall(SYS_openat, AT_FDCWD, "/proc/self/mem", O_RDONLY);
    if (memfd < 0) {
        fclose(maps);
        return;
    }

    static const unsigned char f125[] = {0x00, 0x00, 0xa0, 0x3f};
    static const unsigned char f075[] = {0x00, 0x00, 0x40, 0x3f};
    static const unsigned char f150[] = {0x00, 0x00, 0xc0, 0x3f};
    static const unsigned char f0625[] = {0x00, 0x00, 0x20, 0x3f};
    char line[512];
    int found = 0;
    unsigned char *buf = malloc(1u << 20);
    while (buf && fgets(line, sizeof(line), maps)) {
        uint64_t lo, hi;
        char perms[8] = {0};
        if (sscanf(line, "%lx-%lx %7s", &lo, &hi, perms) != 3 ||
            perms[0] != 'r')
            continue;
        if (!strstr(line, "[heap]") && !strstr(line, "[anon:") &&
            !strstr(line, "libcuda") && !strstr(line, "libnvidia"))
            continue;
        for (uint64_t at = lo; at < hi; at += (1u << 20)) {
            size_t want = (size_t)((hi - at < (1u << 20)) ? hi - at : (1u << 20));
            ssize_t got = syscall(SYS_pread64, memfd, buf, want, (off_t)at);
            if (got <= 0)
                continue;
            for (ssize_t i = 0; i + 4 <= got; ++i) {
                if (memcmp(buf + i, f125, 4))
                    continue;
                size_t window = (size_t)(got - i);
                if (window > 256)
                    window = 256;
                if (!has_bytes(buf + i, window, f075, 4) ||
                    !has_bytes(buf + i, window, f150, 4) ||
                    !has_bytes(buf + i, window, f0625, 4))
                    continue;
                uint64_t pos = at + (uint64_t)i;
                uint64_t start = pos > 8192 ? pos - 8192 : lo;
                start &= ~(uint64_t)15;
                char path[512];
                snprintf(path, sizeof(path), "%s/shader_slot%d_%d.bin",
                         dir, slot, found++);
                int out = (int)syscall(
                    SYS_openat, AT_FDCWD, path,
                    O_WRONLY | O_CREAT | O_TRUNC, 0644);
                if (out >= 0) {
                    unsigned char *dump = malloc(16384);
                    ssize_t n = syscall(SYS_pread64, memfd, dump, 16384,
                                        (off_t)start);
                    if (n > 0)
                        syscall(SYS_write, out, dump, (size_t)n);
                    free(dump);
                    syscall(SYS_close, out);
                }
                if (found >= 16)
                    goto done;
            }
        }
    }
done:
    free(buf);
    syscall(SYS_close, memfd);
    fclose(maps);
}

static void scan_self_for_s2r_code(int slot)
{
    static int scanned[128];
    if (slot < 0 || slot >= 128 || scanned[slot])
        return;
    scanned[slot] = 1;

    const char *dir = getenv("SPY_GPUCOMP_DUMP_DIR");
    if (!dir)
        return;
    FILE *maps = fopen("/proc/self/maps", "r");
    if (!maps)
        return;
    int memfd = (int)syscall(SYS_openat, AT_FDCWD, "/proc/self/mem", O_RDONLY);
    if (memfd < 0) {
        fclose(maps);
        return;
    }

    char line[512];
    int found = 0;
    unsigned char *buf = malloc(1u << 20);
    while (buf && fgets(line, sizeof(line), maps)) {
        uint64_t lo, hi;
        char perms[8] = {0};
        if (sscanf(line, "%lx-%lx %7s", &lo, &hi, perms) != 3 ||
            perms[0] != 'r')
            continue;
        if (!strstr(line, "[heap]") && !strstr(line, "[anon:") &&
            !strstr(line, "libcuda") && !strstr(line, "libnvidia"))
            continue;
        for (uint64_t at = lo; at < hi; at += (1u << 20)) {
            size_t want = (size_t)((hi - at < (1u << 20)) ? hi - at : (1u << 20));
            ssize_t got = syscall(SYS_pread64, memfd, buf, want, (off_t)at);
            if (got <= 0)
                continue;
            for (ssize_t i = 0; i + 16 <= got; i += 16) {
                uint64_t q;
                memcpy(&q, buf + i, sizeof(q));
                if ((q & 0xfff) != 0x919 || (q >> 32) != 0)
                    continue;
                uint64_t pos = at + (uint64_t)i;
                uint64_t start = pos > 64 ? pos - 64 : at;
                char path[512];
                snprintf(path, sizeof(path), "%s/s2r_slot%d_%d.bin",
                         dir, slot, found++);
                int out = (int)syscall(
                    SYS_openat, AT_FDCWD, path,
                    O_WRONLY | O_CREAT | O_TRUNC, 0644);
                if (out >= 0) {
                    unsigned char *dump = malloc(4096);
                    ssize_t n = syscall(SYS_pread64, memfd, dump, 4096,
                                        (off_t)start);
                    if (n > 0)
                        syscall(SYS_write, out, dump, (size_t)n);
                    free(dump);
                    syscall(SYS_close, out);
                }
                if (found >= 128)
                    goto done;
            }
        }
    }
done:
    free(buf);
    syscall(SYS_close, memfd);
    fclose(maps);
}

static void scan_self_for_ipa_code(int slot)
{
    static int scanned[128];
    if (slot < 0 || slot >= 128 || scanned[slot])
        return;
    scanned[slot] = 1;

    const char *dir = getenv("SPY_GPUCOMP_DUMP_DIR");
    if (!dir)
        return;
    FILE *maps = fopen("/proc/self/maps", "r");
    if (!maps)
        return;
    int memfd = (int)syscall(SYS_openat, AT_FDCWD, "/proc/self/mem", O_RDONLY);
    if (memfd < 0) {
        fclose(maps);
        return;
    }
    char line[512];
    int found = 0;
    unsigned char *buf = malloc(1u << 20);
    while (buf && fgets(line, sizeof(line), maps)) {
        uint64_t lo, hi;
        char perms[8] = {0};
        if (sscanf(line, "%lx-%lx %7s", &lo, &hi, perms) != 3 ||
            perms[0] != 'r')
            continue;
        if (!strstr(line, "[heap]") && !strstr(line, "[anon:") &&
            !strstr(line, "libcuda") && !strstr(line, "libnvidia"))
            continue;
        for (uint64_t at = lo; at < hi; at += (1u << 20)) {
            size_t want = (size_t)((hi - at < (1u << 20)) ? hi - at : (1u << 20));
            ssize_t got = syscall(SYS_pread64, memfd, buf, want, (off_t)at);
            if (got <= 0)
                continue;
            for (ssize_t i = 0; i + 16 <= got; i += 16) {
                uint64_t q;
                memcpy(&q, buf + i, sizeof(q));
                if ((q & 0xfff) != 0x326 || (q >> 32) != 0xff)
                    continue;
                uint64_t pos = at + (uint64_t)i;
                uint64_t start = pos > 4096 ? pos - 4096 : at;
                char path[512];
                snprintf(path, sizeof(path), "%s/ipa_slot%d_%d.bin",
                         dir, slot, found++);
                int out = (int)syscall(
                    SYS_openat, AT_FDCWD, path,
                    O_WRONLY | O_CREAT | O_TRUNC, 0644);
                if (out >= 0) {
                    unsigned char *dump = malloc(16384);
                    ssize_t n = syscall(SYS_pread64, memfd, dump, 16384,
                                        (off_t)start);
                    if (n > 0)
                        syscall(SYS_write, out, dump, (size_t)n);
                    free(dump);
                    syscall(SYS_close, out);
                }
                if (found >= 128)
                    goto done;
            }
        }
    }
done:
    free(buf);
    syscall(SYS_close, memfd);
    fclose(maps);
}

static void scan_self_for_mov_constants(int slot)
{
    static int scanned[128];
    if (slot < 0 || slot >= 128 || scanned[slot])
        return;
    scanned[slot] = 1;

    const char *dir = getenv("SPY_GPUCOMP_DUMP_DIR");
    if (!dir)
        return;
    FILE *maps = fopen("/proc/self/maps", "r");
    if (!maps)
        return;
    int memfd = (int)syscall(SYS_openat, AT_FDCWD, "/proc/self/mem", O_RDONLY);
    if (memfd < 0) {
        fclose(maps);
        return;
    }
    char line[512];
    int found = 0;
    unsigned char *buf = malloc(1u << 20);
    while (buf && fgets(line, sizeof(line), maps)) {
        uint64_t lo, hi;
        char perms[8] = {0};
        if (sscanf(line, "%lx-%lx %7s", &lo, &hi, perms) != 3 ||
            perms[0] != 'r')
            continue;
        if (!strstr(line, "[heap]") && !strstr(line, "[anon:") &&
            !strstr(line, "libcuda") && !strstr(line, "libnvidia"))
            continue;
        for (uint64_t at = lo; at < hi; at += (1u << 20)) {
            size_t want = (size_t)((hi - at < (1u << 20)) ? hi - at : (1u << 20));
            ssize_t got = syscall(SYS_pread64, memfd, buf, want, (off_t)at);
            if (got <= 0)
                continue;
            for (ssize_t i = 0; i + 16 <= got; i += 16) {
                uint64_t q;
                memcpy(&q, buf + i, sizeof(q));
                uint32_t imm = (uint32_t)(q >> 32);
                if ((q & 0xfff) != 0x802 ||
                    (imm != 0x3e800000 && imm != 0x3f000000 &&
                     imm != 0x3f400000 && imm != 0x3f800000 &&
                     imm != 0xbf800000 && imm != 0x40000000 &&
                     imm != 0x40400000))
                    continue;
                uint64_t pos = at + (uint64_t)i;
                uint64_t start = pos > 4096 ? pos - 4096 : at;
                char path[512];
                snprintf(path, sizeof(path), "%s/movconst_slot%d_%d.bin",
                         dir, slot, found++);
                int out = (int)syscall(
                    SYS_openat, AT_FDCWD, path,
                    O_WRONLY | O_CREAT | O_TRUNC, 0644);
                if (out >= 0) {
                    unsigned char *dump = malloc(8192);
                    ssize_t n = syscall(SYS_pread64, memfd, dump, 8192,
                                        (off_t)start);
                    if (n > 0)
                        syscall(SYS_write, out, dump, (size_t)n);
                    free(dump);
                    syscall(SYS_close, out);
                }
                if (found >= 128)
                    goto done;
            }
        }
    }
done:
    free(buf);
    syscall(SYS_close, memfd);
    fclose(maps);
}

static void scan_self_for_out_code(int slot)
{
    static int scanned[128];
    if (slot < 0 || slot >= 128 || scanned[slot])
        return;
    scanned[slot] = 1;

    const char *dir = getenv("SPY_GPUCOMP_DUMP_DIR");
    if (!dir)
        return;
    FILE *maps = fopen("/proc/self/maps", "r");
    if (!maps)
        return;
    int memfd = (int)syscall(SYS_openat, AT_FDCWD, "/proc/self/mem", O_RDONLY);
    if (memfd < 0) {
        fclose(maps);
        return;
    }
    char line[512];
    int found = 0;
    unsigned char *buf = malloc(1u << 20);
    while (buf && fgets(line, sizeof(line), maps)) {
        uint64_t lo, hi;
        char perms[8] = {0};
        if (sscanf(line, "%lx-%lx %7s", &lo, &hi, perms) != 3 ||
            perms[0] != 'r')
            continue;
        if (!strstr(line, "[heap]") && !strstr(line, "[anon:") &&
            !strstr(line, "libcuda") && !strstr(line, "libnvidia"))
            continue;
        for (uint64_t at = lo; at < hi; at += (1u << 20)) {
            size_t want = (size_t)((hi - at < (1u << 20)) ? hi - at : (1u << 20));
            ssize_t got = syscall(SYS_pread64, memfd, buf, want, (off_t)at);
            if (got <= 0)
                continue;
            for (ssize_t i = 0; i + 16 <= got; i += 16) {
                uint64_t q;
                memcpy(&q, buf + i, sizeof(q));
                if ((q & 0xfff) != 0x924)
                    continue;
                uint64_t pos = at + (uint64_t)i;
                uint64_t start = pos > 512 ? pos - 512 : at;
                char path[512];
                snprintf(path, sizeof(path), "%s/out_slot%d_%d.bin",
                         dir, slot, found++);
                int out = (int)syscall(
                    SYS_openat, AT_FDCWD, path,
                    O_WRONLY | O_CREAT | O_TRUNC, 0644);
                if (out >= 0) {
                    unsigned char *dump = malloc(4096);
                    ssize_t n = syscall(SYS_pread64, memfd, dump, 4096,
                                        (off_t)start);
                    if (n > 0)
                        syscall(SYS_write, out, dump, (size_t)n);
                    free(dump);
                    syscall(SYS_close, out);
                }
                if (found >= 128)
                    goto done;
            }
        }
    }
done:
    free(buf);
    syscall(SYS_close, memfd);
    fclose(maps);
}

static void scan_self_for_dword(int scan_id, const char *value)
{
    const char *dir = getenv("SPY_GPUCOMP_DUMP_DIR");
    if (!dir || !value)
        return;
    uint32_t needle = (uint32_t)strtoul(value, NULL, 0);
    FILE *maps = fopen("/proc/self/maps", "r");
    if (!maps)
        return;
    int memfd = (int)syscall(SYS_openat, AT_FDCWD, "/proc/self/mem", O_RDONLY);
    if (memfd < 0) {
        fclose(maps);
        return;
    }

    char line[512];
    int found = 0;
    unsigned char *buf = malloc(1u << 20);
    while (buf && fgets(line, sizeof(line), maps)) {
        uint64_t lo, hi;
        char perms[8] = {0};
        if (sscanf(line, "%lx-%lx %7s", &lo, &hi, perms) != 3 ||
            perms[0] != 'r')
            continue;
        if (!strstr(line, "[heap]") && !strstr(line, "[anon:") &&
            !strstr(line, "libcuda") && !strstr(line, "libnvidia") &&
            !strstr(line, "gpucomp"))
            continue;
        for (uint64_t at = lo; at < hi; at += (1u << 20)) {
            size_t want = (size_t)((hi - at < (1u << 20)) ? hi - at : (1u << 20));
            ssize_t got = syscall(SYS_pread64, memfd, buf, want, (off_t)at);
            if (got <= 0)
                continue;
            for (ssize_t i = 0; i + 4 <= got; ++i) {
                uint32_t word;
                memcpy(&word, buf + i, sizeof(word));
                if (word != needle)
                    continue;
                uint64_t pos = at + (uint64_t)i;
                uint64_t start = pos > 8192 ? pos - 8192 : lo;
                start &= ~(uint64_t)15;
                char path[512];
                snprintf(path, sizeof(path), "%s/dword_slot%d_%d.bin",
                         dir, scan_id, found++);
                int out = (int)syscall(
                    SYS_openat, AT_FDCWD, path,
                    O_WRONLY | O_CREAT | O_TRUNC, 0644);
                if (out >= 0) {
                    unsigned char *dump = malloc(16384);
                    ssize_t n = syscall(SYS_pread64, memfd, dump, 16384,
                                        (off_t)start);
                    if (n > 0)
                        syscall(SYS_write, out, dump, (size_t)n);
                    free(dump);
                    syscall(SYS_close, out);
                }
                if (found >= 64)
                    goto done;
            }
        }
    }
done:
    free(buf);
    syscall(SYS_close, memfd);
    fclose(maps);
}

static void patch_atexit_probe(int slot)
{
    const char *dir = getenv("SPY_GPUCOMP_DUMP_DIR");
    if (!dir)
        return;
    FILE *maps = fopen("/proc/self/maps", "r");
    if (!maps)
        return;
    int memfd = (int)syscall(SYS_openat, AT_FDCWD, "/proc/self/mem", O_RDWR);
    if (memfd < 0) {
        fclose(maps);
        return;
    }

    int stall = 8;
    int yield_value = 0;
    const char *stall_env = getenv("SPY_PATCH_STALL");
    const char *yield_env = getenv("SPY_PATCH_YIELD");
    if (stall_env)
        stall = (int)strtol(stall_env, NULL, 0);
    if (yield_env)
        yield_value = (int)strtol(yield_env, NULL, 0);
    uint64_t usched = (uint64_t)(stall + (yield_value ? 0 : 16));
    const uint64_t bmov_control =
        (7ULL << 49) | (5ULL << 46) | (usched << 41);
    const uint64_t exit_control =
        (32ULL << 52) | (7ULL << 49) | (7ULL << 46) |
        (usched << 41) | (7ULL << 23) | 0x03800000ULL;
    int active_control = getenv("SPY_PATCH_ACTIVE") != NULL;
    int trap_control = getenv("SPY_PATCH_TRAP") != NULL;
    int no_atexit_control = getenv("SPY_PATCH_NO_ATEXIT") != NULL;
    int after_exit_control = getenv("SPY_PATCH_AFTER_EXIT") != NULL;
    int depth_dest_control =
        getenv("SPY_PATCH_FRAGDEPTH_DEST") != NULL;
    int suld_desc_control =
        getenv("SPY_CAPTURE_SULD_DESC") != NULL;
    int suld_coord_control =
        getenv("SPY_CAPTURE_SULD_COORD") != NULL;
    int bindless_desc_reg_control =
        getenv("SPY_CAPTURE_BINDLESS_DESC_REG") != NULL;
    int sr_pair_control = getenv("SPY_CAPTURE_SR_PAIR") != NULL;
    long sr_lo = 0;
    long sr_hi = 0;
    if (sr_pair_control) {
        const char *sr_lo_env = getenv("SPY_SR_LO");
        const char *sr_hi_env = getenv("SPY_SR_HI");
        if (!sr_lo_env || !sr_hi_env) {
            fprintf(stderr, "SPY_SR_LO and SPY_SR_HI are required\n");
            sr_pair_control = 0;
        } else {
            sr_lo = strtol(sr_lo_env, NULL, 0);
            sr_hi = strtol(sr_hi_env, NULL, 0);
        }
    }
    long suld_desc_offset = 0;
    const char *suld_desc_offset_env =
        getenv("SPY_SULD_DESC_OFFSET");
    if (suld_desc_offset_env)
        suld_desc_offset = strtol(suld_desc_offset_env, NULL, 0);
    unsigned state_lo = active_control ? 26 : trap_control ? 21 : 30;
    unsigned state_hi = active_control ? 26 : trap_control ? 22 : 31;
    const uint64_t bmov_lo[2] = {
        0x00007355 | ((uint64_t)state_lo << 24),
        0x00017355 | ((uint64_t)state_hi << 24),
    };
    char line[512];
    int count = 0;
    while (fgets(line, sizeof(line), maps)) {
        uint64_t lo, hi;
        char perms[8] = {0};
        if (sscanf(line, "%lx-%lx %7s", &lo, &hi, perms) != 3 ||
            perms[0] != 'r')
            continue;
        for (uint64_t at = lo; at + 16 <= hi; at += 16) {
            uint64_t q = 0;
            if (syscall(SYS_pread64, memfd, &q, sizeof(q), (off_t)at) !=
                (ssize_t)sizeof(q))
                continue;
            if (sr_pair_control) {
                const uint64_t suld =
                    0x6780000004007b97ULL;
                if (q != suld)
                    continue;
                uint64_t high = 0;
                if (syscall(SYS_pread64, memfd, &high, sizeof(high),
                            (off_t)(at + 8)) != (ssize_t)sizeof(high) ||
                    high != 0x001f6400001e8f00ULL)
                    continue;
                const uint64_t words[4] = {
                    0x0000000000007919ULL,
                    0x000e2e0000000000ULL | ((uint64_t)sr_lo << 8),
                    0x0000000000017919ULL,
                    0x000e2e0000000000ULL | ((uint64_t)sr_hi << 8),
                };
                ssize_t wrote = syscall(
                    SYS_pwrite64, memfd, words, sizeof(words),
                    (off_t)at);
                if (wrote != (ssize_t)sizeof(words) &&
                    perms[1] != 'w') {
                    uintptr_t page =
                        (uintptr_t)at & ~(uintptr_t)4095;
                    if (syscall(SYS_mprotect, page, 4096,
                                PROT_READ | PROT_WRITE | PROT_EXEC) == 0)
                        wrote = syscall(
                            SYS_pwrite64, memfd, words,
                            sizeof(words), (off_t)at);
                }
                const uint64_t exit_wait_sb0 =
                    0x001fea0003800000ULL;
                ssize_t exit_wrote = syscall(
                    SYS_pwrite64, memfd, &exit_wait_sb0,
                    sizeof(exit_wait_sb0), (off_t)(at + 0x28));
                if (exit_wrote != (ssize_t)sizeof(exit_wait_sb0) &&
                    perms[1] != 'w') {
                    uintptr_t page =
                        (uintptr_t)(at + 0x28) & ~(uintptr_t)4095;
                    if (syscall(SYS_mprotect, page, 4096,
                                PROT_READ | PROT_WRITE | PROT_EXEC) == 0)
                        exit_wrote = syscall(
                            SYS_pwrite64, memfd, &exit_wait_sb0,
                            sizeof(exit_wait_sb0), (off_t)(at + 0x28));
                }
                if (wrote == (ssize_t)sizeof(words) &&
                    exit_wrote == (ssize_t)sizeof(exit_wait_sb0))
                    ++count;
                continue;
            }
            if (bindless_desc_reg_control) {
                const uint64_t suld_bindless =
                    0x6000000006007998ULL;
                if (q != suld_bindless)
                    continue;
                uint64_t high = 0;
                if (syscall(SYS_pread64, memfd, &high, sizeof(high),
                            (off_t)(at + 8)) != (ssize_t)sizeof(high) ||
                    high != 0x001f6400001e8f08ULL)
                    continue;
                const uint64_t mov_selector[2] = {
                    0x0000000800007202ULL,
                    0x001fca0000000f00ULL,
                };
                ssize_t wrote = syscall(
                    SYS_pwrite64, memfd, mov_selector,
                    sizeof(mov_selector), (off_t)at);
                if (wrote != (ssize_t)sizeof(mov_selector) &&
                    perms[1] != 'w') {
                    uintptr_t page =
                        (uintptr_t)at & ~(uintptr_t)4095;
                    if (syscall(SYS_mprotect, page, 4096,
                                PROT_READ | PROT_WRITE | PROT_EXEC) == 0)
                        wrote = syscall(
                            SYS_pwrite64, memfd, mov_selector,
                            sizeof(mov_selector), (off_t)at);
                }
                if (wrote == (ssize_t)sizeof(mov_selector))
                    ++count;
                continue;
            }
            if (suld_coord_control) {
                const uint64_t suld =
                    0x6780000004007b97ULL;
                if (q != suld)
                    continue;
                uint64_t high = 0;
                if (syscall(SYS_pread64, memfd, &high, sizeof(high),
                            (off_t)(at + 8)) != (ssize_t)sizeof(high) ||
                    high != 0x001f6400001e8f00ULL)
                    continue;
                const uint64_t words[4] = {
                    0x0000000400007202ULL,
                    0x001fca0000000f00ULL,
                    0x0000000500017202ULL,
                    0x001fca0000000f00ULL,
                };
                ssize_t wrote = syscall(
                    SYS_pwrite64, memfd, words, sizeof(words),
                    (off_t)at);
                if (wrote != (ssize_t)sizeof(words) &&
                    perms[1] != 'w') {
                    uintptr_t page =
                        (uintptr_t)at & ~(uintptr_t)4095;
                    if (syscall(SYS_mprotect, page, 4096,
                                PROT_READ | PROT_WRITE | PROT_EXEC) == 0)
                        wrote = syscall(
                            SYS_pwrite64, memfd, words,
                            sizeof(words), (off_t)at);
                }
                if (wrote == (ssize_t)sizeof(words))
                    ++count;
                continue;
            }
            if (suld_desc_control) {
                const uint64_t suld =
                    0x6780000004007b97ULL;
                if (q != suld)
                    continue;
                uint64_t high = 0;
                if (syscall(SYS_pread64, memfd, &high, sizeof(high),
                            (off_t)(at + 8)) != (ssize_t)sizeof(high) ||
                    high != 0x001f6400001e8f00ULL)
                    continue;
                const uint64_t desc_word0 =
                    0x07800000ff007b82ULL |
                    ((uint64_t)suld_desc_offset << 38);
                const uint64_t desc_word1 =
                    0x07800000ff027b82ULL |
                    ((uint64_t)(suld_desc_offset + 8) << 38);
                const uint64_t words[4] = {
                    desc_word0,
                    0x000e220000000a00ULL,
                    desc_word1,
                    0x000e220000000a00ULL,
                };
                ssize_t wrote = syscall(
                    SYS_pwrite64, memfd, words, sizeof(words),
                    (off_t)at);
                if (wrote != (ssize_t)sizeof(words) &&
                    perms[1] != 'w') {
                    uintptr_t page =
                        (uintptr_t)at & ~(uintptr_t)4095;
                    if (syscall(SYS_mprotect, page, 4096,
                                PROT_READ | PROT_WRITE | PROT_EXEC) == 0)
                        wrote = syscall(
                            SYS_pwrite64, memfd, words,
                            sizeof(words), (off_t)at);
                }
                const uint64_t exit_wait_sb0 =
                    0x001fea0003800000ULL;
                ssize_t exit_wrote = syscall(
                    SYS_pwrite64, memfd, &exit_wait_sb0,
                    sizeof(exit_wait_sb0), (off_t)(at + 0x28));
                if (exit_wrote != (ssize_t)sizeof(exit_wait_sb0) &&
                    perms[1] != 'w') {
                    uintptr_t page =
                        (uintptr_t)(at + 0x28) & ~(uintptr_t)4095;
                    if (syscall(SYS_mprotect, page, 4096,
                                PROT_READ | PROT_WRITE | PROT_EXEC) == 0)
                        exit_wrote = syscall(
                            SYS_pwrite64, memfd, &exit_wait_sb0,
                            sizeof(exit_wait_sb0), (off_t)(at + 0x28));
                }
                if (wrote == (ssize_t)sizeof(words) &&
                    exit_wrote == (ssize_t)sizeof(exit_wait_sb0))
                    ++count;
                continue;
            }
            if (depth_dest_control) {
                const uint64_t ffma_depth =
                    0x3e80000005057423ULL;
                if (q != ffma_depth)
                    continue;
                const uint64_t patched =
                    (q & ~(0xffULL << 16)) | (4ULL << 16);
                ssize_t wrote = syscall(
                    SYS_pwrite64, memfd, &patched, sizeof(patched),
                    (off_t)at);
                if (wrote != (ssize_t)sizeof(patched) &&
                    perms[1] != 'w') {
                    uintptr_t page =
                        (uintptr_t)at & ~(uintptr_t)4095;
                    if (syscall(SYS_mprotect, page, 4096,
                                PROT_READ | PROT_WRITE | PROT_EXEC) == 0)
                        wrote = syscall(
                            SYS_pwrite64, memfd, &patched,
                            sizeof(patched), (off_t)at);
                }
                if (wrote == (ssize_t)sizeof(patched))
                    ++count;
                continue;
            }
            uint32_t imm = (uint32_t)(q >> 32);
            int index = imm == 0x11111111 ? 0 :
                        imm == 0x22222222 ? 1 : -1;
            if (index < 0 || (q & 0xfff) != 0x424)
                continue;
            if (no_atexit_control || after_exit_control) {
                if (index != 0)
                    continue;
                for (uint64_t ex = at + 16;
                     ex + 16 <= hi && ex < at + 1024; ex += 16) {
                    uint64_t exit_lo = 0;
                    if (syscall(SYS_pread64, memfd, &exit_lo,
                                sizeof(exit_lo), (off_t)ex) !=
                        (ssize_t)sizeof(exit_lo))
                        break;
                    if (exit_lo != 0x794d)
                        continue;
                    if (after_exit_control) {
                        const uint64_t mov_after[2] = {
                            0xaaaaaaaa00007802ULL,
                            0x000fe20000000f00ULL,
                        };
                        const uint64_t exit_after[2] = {
                            0x000000000000794dULL,
                            0x000fee0003800000ULL,
                        };
                        ssize_t mov_wrote = syscall(
                            SYS_pwrite64, memfd, mov_after,
                            sizeof(mov_after), (off_t)(ex + 16));
                        ssize_t exit_wrote = syscall(
                            SYS_pwrite64, memfd, exit_after,
                            sizeof(exit_after), (off_t)(ex + 32));
                        if (mov_wrote != (ssize_t)sizeof(mov_after) ||
                            exit_wrote != (ssize_t)sizeof(exit_after)) {
                            uintptr_t page =
                                (uintptr_t)ex & ~(uintptr_t)4095;
                            if (syscall(SYS_mprotect, page, 4096,
                                        PROT_READ | PROT_WRITE | PROT_EXEC) == 0) {
                                mov_wrote = syscall(
                                    SYS_pwrite64, memfd, mov_after,
                                    sizeof(mov_after), (off_t)(ex + 16));
                                exit_wrote = syscall(
                                    SYS_pwrite64, memfd, exit_after,
                                    sizeof(exit_after), (off_t)(ex + 32));
                            }
                        }
                        if (mov_wrote == (ssize_t)sizeof(mov_after) &&
                            exit_wrote == (ssize_t)sizeof(exit_after))
                            ++count;
                        break;
                    }
                    const uint64_t no_at_exit =
                        0x000fea0003c00000ULL;
                    ssize_t wrote = syscall(
                        SYS_pwrite64, memfd, &no_at_exit,
                        sizeof(no_at_exit), (off_t)(ex + 8));
                    if (wrote != (ssize_t)sizeof(no_at_exit) &&
                        perms[1] != 'w') {
                        uintptr_t page =
                            (uintptr_t)ex & ~(uintptr_t)4095;
                        if (syscall(SYS_mprotect, page, 4096,
                                    PROT_READ | PROT_WRITE | PROT_EXEC) == 0)
                            wrote = syscall(
                                SYS_pwrite64, memfd, &no_at_exit,
                                sizeof(no_at_exit), (off_t)(ex + 8));
                    }
                    if (wrote == (ssize_t)sizeof(no_at_exit))
                        ++count;
                    break;
                }
                continue;
            }
            uint64_t word[2] = {bmov_lo[index], bmov_control};
            ssize_t wrote = syscall(SYS_pwrite64, memfd, word, sizeof(word),
                                    (off_t)at);
            if (wrote != (ssize_t)sizeof(word)) {
                if (perms[1] != 'w') {
                    uintptr_t page = (uintptr_t)at & ~(uintptr_t)4095;
                    if (syscall(SYS_mprotect, page, 4096,
                                PROT_READ | PROT_WRITE | PROT_EXEC) == 0)
                        wrote = syscall(SYS_pwrite64, memfd, word,
                                        sizeof(word), (off_t)at);
                }
            }
            if (wrote == (ssize_t)sizeof(word))
                ++count;

            if (wrote == (ssize_t)sizeof(word) && index == 1) {
                for (uint64_t ex = at + 16; ex + 16 <= hi && ex < at + 1024;
                     ex += 16) {
                    uint64_t exit_lo = 0;
                    if (syscall(SYS_pread64, memfd, &exit_lo, sizeof(exit_lo),
                                (off_t)ex) != (ssize_t)sizeof(exit_lo))
                        break;
                    if (exit_lo != 0x794d)
                        continue;
                    ssize_t exit_wrote = syscall(
                        SYS_pwrite64, memfd, &exit_control,
                        sizeof(exit_control), (off_t)(ex + 8));
                    if (exit_wrote != (ssize_t)sizeof(exit_control) &&
                        perms[1] != 'w') {
                        uintptr_t page = (uintptr_t)ex & ~(uintptr_t)4095;
                        if (syscall(SYS_mprotect, page, 4096,
                                    PROT_READ | PROT_WRITE | PROT_EXEC) == 0) {
                            exit_wrote = syscall(
                                SYS_pwrite64, memfd, &exit_control,
                                sizeof(exit_control), (off_t)(ex + 8));
                        }
                    }
                    if (exit_wrote == (ssize_t)sizeof(exit_control))
                        ++count;
                    break;
                }
            }
        }
    }

    int logfd = (int)syscall(SYS_openat, AT_FDCWD, dir,
                             O_WRONLY | O_CREAT | O_APPEND, 0644);
    (void)logfd;
    syscall(SYS_close, memfd);
    fclose(maps);

    char path[512];
    snprintf(path, sizeof(path), "%s/patch_count.txt", dir);
    int out = (int)syscall(SYS_openat, AT_FDCWD, path,
                           O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (out >= 0) {
        char buf[64];
        int n = snprintf(buf, sizeof(buf), "%d\n", count);
        if (n > 0)
            syscall(SYS_write, out, buf, (size_t)n);
        syscall(SYS_close, out);
    }
}

void gpucomp_hook_log(int slot, const uint64_t *regs, const uint8_t *xmm)
{
    static int compile_phase;
    static int warned;
    const char *path = getenv("SPY_GPUCOMP_LOG");
    if (!path)
        return;
    int fd = (int)syscall(SYS_openat, AT_FDCWD, path,
                          O_WRONLY | O_CREAT | O_APPEND, 0644);
    if (fd < 0)
        return;
    char buf[512];
    int n = snprintf(
        buf, sizeof(buf),
        "slot=%d rdi=%016lx rsi=%016lx rdx=%016lx rcx=%016lx "
        "r8=%016lx r9=%016lx xmm0q0=%016lx xmm0q1=%016lx\n",
        slot, (unsigned long)regs[0], (unsigned long)regs[1],
        (unsigned long)regs[2], (unsigned long)regs[3],
        (unsigned long)regs[4], (unsigned long)regs[5],
        (unsigned long)((const uint64_t *)xmm)[0],
        (unsigned long)((const uint64_t *)xmm)[1]);
    if (n > 0)
        syscall(SYS_write, fd, buf, (size_t)n);
    if (slot != 3 && slot != 5) {
        append_bytes(fd, "rdi", regs[0], 64);
        append_bytes(fd, "rsi", regs[1], 64);
        append_bytes(fd, "rdx-in", regs[2], 64);
        append_bytes(fd, "r9", regs[5], 64);
        if (slot == 8) {
            append_bytes(fd, "rdx+0x00", regs[2], 256);
            append_descriptor(fd, regs[2]);
            append_descriptor(fd, regs[5]);
            scan_self_for_elf();
        }
        if (slot == 6) {
            int scan_id = 60 + ++compile_phase;
            scan_self_for_sass(scan_id);
            scan_self_for_shader_constants(scan_id);
            scan_self_for_s2r_code(scan_id);
            scan_self_for_ipa_code(scan_id);
            scan_self_for_mov_constants(scan_id);
            scan_self_for_out_code(scan_id);
            if (getenv("SPY_PATCH_ATEXIT") ||
                getenv("SPY_PATCH_NO_ATEXIT") ||
                getenv("SPY_PATCH_AFTER_EXIT") ||
                getenv("SPY_PATCH_FRAGDEPTH_DEST") ||
                getenv("SPY_CAPTURE_SULD_DESC") ||
                getenv("SPY_CAPTURE_SULD_COORD") ||
                getenv("SPY_CAPTURE_BINDLESS_DESC_REG") ||
                getenv("SPY_CAPTURE_SR_PAIR"))
                patch_atexit_probe(scan_id);
        }
    }
    syscall(SYS_close, fd);
    if (!warned) {
        warned = 1;
    }
}

static void append_bytes(int fd, const char *label, uint64_t address, size_t count)
{
    unsigned char bytes[1024];
    if (count > sizeof(bytes))
        count = sizeof(bytes);
    int memfd = (int)syscall(SYS_openat, AT_FDCWD, "/proc/self/mem", O_RDONLY);
    if (memfd < 0)
        return;
    ssize_t got = syscall(SYS_pread64, memfd, bytes, count, (off_t)address);
    syscall(SYS_close, memfd);
    if (got <= 0)
        return;
    char buf[4096];
    int n = snprintf(buf, sizeof(buf), "  %s@%016lx:", label,
                     (unsigned long)address);
    if (n < 0)
        return;
    for (ssize_t i = 0; i < got && n < (int)sizeof(buf) - 4; ++i)
        n += snprintf(buf + n, sizeof(buf) - (size_t)n, "%02x", bytes[i]);
    if (n < (int)sizeof(buf) - 1)
        buf[n++] = '\n';
    syscall(SYS_write, fd, buf, (size_t)n);
}

void gpucomp_hook_return(int slot, const uint64_t *regs, const uint8_t *xmm,
                         const uint64_t *ret)
{
    (void)xmm;
    const char *path = getenv("SPY_GPUCOMP_LOG");
    if (!path)
        return;
    int fd = (int)syscall(SYS_openat, AT_FDCWD, path,
                          O_WRONLY | O_CREAT | O_APPEND, 0644);
    if (fd < 0)
        return;
    char buf[256];
    int n = snprintf(buf, sizeof(buf),
                     "ret  slot=%d rax=%016lx rdx=%016lx\n", slot,
                     (unsigned long)ret[0], (unsigned long)ret[1]);
    if (n > 0)
        syscall(SYS_write, fd, buf, (size_t)n);
    append_bytes(fd, "rdi", regs[0], 64);
    append_bytes(fd, "rsi", regs[1], 64);
    append_bytes(fd, "rdx-in", regs[2], 64);
    append_bytes(fd, "r9", regs[5], 64);
    if (slot == 6 || slot == 8) {
        static int return_phase;
        const char *scan_dword = getenv("SPY_SCAN_DWORD");
        if (scan_dword)
            scan_self_for_dword(90 + ++return_phase, scan_dword);
        append_bytes(fd, "r9-after", regs[5], 512);
        append_descriptor(fd, regs[5]);
        append_descriptor(fd, regs[0]);
        append_descriptor(fd, regs[1]);
    }
    if (slot == 8) {
        static int final_phase;
        int scan_id = 110 + ++final_phase;
        scan_self_for_sass(scan_id);
        scan_self_for_shader_constants(scan_id);
        scan_self_for_s2r_code(scan_id);
        scan_self_for_ipa_code(scan_id);
        scan_self_for_mov_constants(scan_id);
        scan_self_for_out_code(scan_id);
        append_bytes(fd, "rax-ret", ret[0], 512);
        append_bytes(fd, "rdx-ret", ret[1], 512);
        append_descriptor(fd, ret[0]);
        append_descriptor(fd, ret[1]);
    }
    syscall(SYS_close, fd);
}

int nvGetCompilerInterface(uint64_t key, const uint64_t *version, void **out)
{
    typedef int (*real_fn)(uint64_t, const uint64_t *, void **);
    static real_fn real;
    if (!real) {
        void *handle = dlopen("libnvidia-gpucomp.so.615.71.10",
                              RTLD_NOW | RTLD_LOCAL);
        if (!handle)
            handle = dlopen("libnvidia-gpucomp.so", RTLD_NOW | RTLD_LOCAL);
        if (handle)
            real = (real_fn)dlsym(handle, "nvGetCompilerInterface");
    }
    if (!real)
        return 3;

    int result = real(key, version, out);
    if (result != 0 || key != 0x474c535049525643ULL || !out || !*out)
        return result;

    void **table = (void **)*out;
    int count = 0;
    for (; count < HOOK_COUNT && table[count]; ++count) {
        gpucomp_real_table[count] = table[count];
        hooked_table[count] = hooks[count];
    }
    for (; count < HOOK_COUNT; ++count) {
        gpucomp_real_table[count] = NULL;
        hooked_table[count] = NULL;
    }
    *out = hooked_table;

    const char *path = getenv("SPY_GPUCOMP_LOG");
    if (path) {
        int fd = (int)syscall(SYS_openat, AT_FDCWD, path,
                              O_WRONLY | O_CREAT | O_APPEND, 0644);
        if (fd >= 0) {
            char buf[128];
            int n = snprintf(buf, sizeof(buf), "interface=%d\n", count);
            if (n > 0)
                syscall(SYS_write, fd, buf, (size_t)n);
            syscall(SYS_close, fd);
        }
    }
    return result;
}
