// doorbell_trap.c - mprotect+SIGSEGV trap over candidate BAR/userd mappings.
// Arms write traps on registered regions; on fault, decodes the store,
// logs the value, single-steps (TF), then re-arms.
#define _GNU_SOURCE
#include <fcntl.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <sys/ucontext.h>
#include <unistd.h>

#include "doorbell_trap.h"

bool decode_store_ex(const uint8_t *ip, const greg_t *gregs, const uint8_t *fp,
                     int *width, uint8_t *value16, int *insn_len);

static void raw_mprotect(uintptr_t addr, size_t len, int prot);

#define MAX_REGIONS 4096

typedef struct {
    uintptr_t base;
    size_t    len;
    int       orig_prot;
    int       fd;
    int       dev;
    bool      active;      // currently write-trapped
    bool      disabled;    // decode failed once; leave alone
} region_t;

static region_t g_regions[MAX_REGIONS];
static int      g_nregions = 0;
static bool     g_trap_enabled = false;
static bool     g_handlers_installed = false;

static struct sigaction g_old_segv;
static struct sigaction g_old_trap;
static stack_t          g_old_ss;

// provided by nvtrace.c
void nvtrace_emit_mmio(uintptr_t addr, size_t off, int width,
                       const uint8_t *value, uintptr_t rip,
                       const uint8_t *raw, int rawlen, int region_idx);
void nvtrace_emit_region(uintptr_t addr, size_t len, int prot, int fd,
                         int dev, int region_idx);
void nvtrace_emit_gpfifo(int ch, int put_idx, uint64_t seg_addr, uint32_t seg_len,
                         uint32_t entry_hi, const char *file, int seq);

#define GPPUT_OFF 0x208c   // userdOffset(0x2000) + Nvc96fControl.GPPut(0x8c), Blackwell
#define GPFIFO_ENTRIES 1024
#define SEG_DUMP_CAP (256 * 1024)
#define MAX_CHANNELS 64
#define CH_STRIDE 0x3000   // per-channel stride in the GPFIFO/userd region (alloc params)

static int      g_ring_region = -1;      // region holding GPFIFO rings + userds
static uint32_t g_last_put[MAX_CHANNELS];
static int      g_dump_seq = 0;

// --- injection state: last submission per channel + last doorbell write ---
#define INJECT_SEG_CAP (256 * 1024)
static uint64_t g_last_seg_addr[MAX_CHANNELS];
static uint32_t g_last_seg_len[MAX_CHANNELS];
static uint32_t g_last_entry_lo[MAX_CHANNELS];
static uint32_t g_last_entry_hi[MAX_CHANNELS];
static uint8_t *g_last_seg_data[MAX_CHANNELS];
static uint64_t g_pb_tail_addr[MAX_CHANNELS];   // pushbuffer tail (for VA chaining)
static uint32_t g_pb_tail_len[MAX_CHANNELS];
static int      g_db_region = -1;        // BAR doorbell page region
static size_t   g_db_off = 0;
static uint32_t g_db_val = 0;
static bool     g_db_seen = false;
// doorbell triple associated with each channel (from GPPut-advance correlation)
static int      g_ch_db_region[MAX_CHANNELS];
static size_t   g_ch_db_off[MAX_CHANNELS];
static uint32_t g_ch_db_val[MAX_CHANNELS];
static bool     g_ch_db_seen[MAX_CHANNELS];

// code-pointer history for swapcode (from inline QMD records, per channel)
#define CODE_HIST 8
static uint32_t g_code_hist[MAX_CHANNELS][CODE_HIST][4]; // +80,+84,+ec,+f0
static int      g_code_hist_n[MAX_CHANNELS];

// full segment history for "seg:K" replay selection
#define SEG_HIST 4
static uint8_t *g_shist_data[MAX_CHANNELS][SEG_HIST];
static uint64_t g_shist_addr[MAX_CHANNELS][SEG_HIST];
static uint32_t g_shist_len[MAX_CHANNELS][SEG_HIST];
static int      g_shist_n[MAX_CHANNELS];

// scan a segment for the LAST inline QMD record (mthd 0x318) and extract
// the code-pointer words (QMD +0x80,+0x84,+0xec,+0xf0). returns true if found.
static bool seg_extract_codeptr(const uint8_t *seg, uint32_t len, uint32_t out[4])
{
    const uint32_t *d = (const uint32_t *)seg;
    uint32_t n = len / 4, i = 0;
    bool found = false;
    while (i < n) {
        uint32_t hdr = d[i];
        if (hdr == 0) {
            bool all0 = true;
            for (uint32_t j = i; j < n; j++) if (d[j]) { all0 = false; break; }
            if (all0) break;
        }
        uint32_t mthd = (hdr & 0x1FFF) * 4;
        uint32_t cnt = (hdr >> 16) & 0x1FFF;
        if (mthd == 0x318 && cnt >= 98) {
            const uint32_t *q = &d[i + 1 + 2]; // skip addr_hi/addr_lo
            out[0] = q[32]; out[1] = q[33]; out[2] = q[59]; out[3] = q[60];
            found = true;
        }
        i += 1 + cnt;
    }
    return found;
}

void nvtrace_emit_inject(int ch, uint64_t seg_addr, uint32_t seg_len,
                         const char *patch);

// find which region contains addr (or -1)
static int region_index_of(uintptr_t addr)
{
    for (int i = 0; i < g_nregions; i++)
        if (addr >= g_regions[i].base && addr < g_regions[i].base + g_regions[i].len)
            return i;
    return -1;
}

// submit a fully-formed segment on channel ch: append at pushbuffer tail,
// write GPFIFO entry, bump GPPut, ring this channel's doorbell.
static int submit_segment(int ch, const uint8_t *buf, uint32_t len,
                          const char *tag)
{
    if (g_ring_region < 0 || !g_ch_db_seen[ch]) return -1;
    region_t *ring = &g_regions[g_ring_region];

    uint64_t new_addr = g_pb_tail_addr[ch] + g_pb_tail_len[ch];
    int seg_ri = region_index_of(new_addr);
    if (seg_ri < 0 || new_addr + len >
        g_regions[seg_ri].base + g_regions[seg_ri].len) return -3;

    uint32_t put = *(volatile uint32_t *)(ring->base + ch * CH_STRIDE + GPPUT_OFF);
    uint32_t slot = put % GPFIFO_ENTRIES;
    int db_region = g_ch_db_region[ch];

    // make target regions writable (they may be write-trapped right now)
    region_t *segr = &g_regions[seg_ri];
    region_t *dbr  = &g_regions[db_region];
    raw_mprotect(segr->base, segr->len, segr->orig_prot);
    raw_mprotect(ring->base, ring->len, ring->orig_prot);
    raw_mprotect(dbr->base, dbr->len, dbr->orig_prot);

    memcpy((void *)(uintptr_t)new_addr, buf, len);
    volatile uint8_t *e = (volatile uint8_t *)(ring->base + ch * CH_STRIDE + slot * 8);
    uint32_t lo = (uint32_t)(new_addr & 0xfffffffcu) | (g_last_entry_lo[ch] & 3);
    // entry1: [7:0]=GET_HI(addr>>32) [8]=PRIV [9]=LEVEL [30:10]=LENGTH(dwords)
    //         [31]=SYNC — preserve PRIV/LEVEL/SYNC, set our addr + real length.
    uint32_t hi = (g_last_entry_hi[ch] & 0x80000300u) |
                  (uint32_t)((new_addr >> 32) & 0xff) |
                  ((len / 4) << 10);
    *(volatile uint32_t *)e = lo;
    *(volatile uint32_t *)(e + 4) = hi;
    __sync_synchronize();
    *(volatile uint32_t *)(ring->base + ch * CH_STRIDE + GPPUT_OFF) = put + 1;
    __sync_synchronize();
    *(volatile uint32_t *)(g_regions[db_region].base + g_ch_db_off[ch]) = g_ch_db_val[ch];
    __sync_synchronize();

    // update bookkeeping so a later doorbell snapshot doesn't re-dump ours
    g_last_put[ch] = put + 1;
    g_pb_tail_addr[ch] = new_addr;
    g_pb_tail_len[ch] = len;

    // restore traps
    if (segr->active) raw_mprotect(segr->base, segr->len, PROT_READ);
    if (ring->active) raw_mprotect(ring->base, ring->len,
                                   (ring->orig_prot & PROT_READ) ? PROT_READ : PROT_NONE);
    if (dbr->active) raw_mprotect(dbr->base, dbr->len, PROT_NONE);

    nvtrace_emit_inject(ch, new_addr, len, tag ? tag : "");
    return 0;
}

// submit a segment read from a file (from-scratch construction path).
int nvtrace_inject_raw(int ch, const char *path)
{
    uint8_t buf[INJECT_SEG_CAP];
    FILE *f = fopen(path, "rb");
    if (!f) return -4;
    uint32_t len = (uint32_t)fread(buf, 1, sizeof(buf), f);
    fclose(f);
    if (len == 0 || len % 4) return -5;
    return submit_segment(ch, buf, len, path);
}

// resubmit the last segment captured on channel ch, with optional dword
// patches ("off:val,off:val" hex). Returns 0 on success.
int nvtrace_inject_last(int ch, const char *patch)
{
    uint8_t buf[INJECT_SEG_CAP];
    if (!g_last_seg_data[ch]) return -1;
    uint32_t len = g_last_seg_len[ch];
    if (len > INJECT_SEG_CAP) return -2;
    memcpy(buf, g_last_seg_data[ch], len);

    if (patch && *patch) {
        char spec[512];
        snprintf(spec, sizeof(spec), "%s", patch);
        for (char *tok = strtok(spec, ","); tok; tok = strtok(NULL, ",")) {
            unsigned off, val, k;
            if (sscanf(tok, "seg:%u", &k) == 1) {
                // replay the k-th previous segment instead (1=last)
                int hn = g_shist_n[ch];
                if (k >= 1 && k <= (unsigned)(hn < SEG_HIST ? hn : SEG_HIST)) {
                    int idx = (hn - k) % SEG_HIST;
                    len = g_shist_len[ch][idx];
                    memcpy(buf, g_shist_data[ch][idx], len);
                }
                continue;
            }
            unsigned keep;
            if (sscanf(tok, "%x~%x:%x", &off, &keep, &val) == 3 && off + 4 <= len) {
                *(uint32_t *)(buf + off) = (*(uint32_t *)(buf + off) & keep) | val;
                continue;
            }
            if (sscanf(tok, "swapcode:%u", &k) == 1) {
                // replace code ptr with the k-th previous launch's (1=prev)
                int hn = g_code_hist_n[ch];
                if (k >= 1 && k <= (unsigned)(hn < CODE_HIST ? hn : CODE_HIST)) {
                    int idx = (hn - k) % CODE_HIST;
                    uint32_t *q = NULL;
                    // locate the inline QMD record inside buf
                    uint32_t tmp[4];
                    const uint32_t *d = (const uint32_t *)buf;
                    uint32_t nn = len / 4, ii = 0;
                    while (ii < nn) {
                        uint32_t hdr = d[ii];
                        uint32_t mthd = (hdr & 0x1FFF) * 4;
                        uint32_t cnt = (hdr >> 16) & 0x1FFF;
                        if (mthd == 0x318 && cnt >= 98) q = (uint32_t *)&d[ii + 1 + 2];
                        ii += 1 + cnt;
                    }
                    if (q) {
                        q[32] = g_code_hist[ch][idx][0];
                        q[33] = g_code_hist[ch][idx][1];
                        q[59] = g_code_hist[ch][idx][2];
                        q[60] = g_code_hist[ch][idx][3];
                    }
                    (void)tmp;
                }
                continue;
            }
            if (sscanf(tok, "%x:%x", &off, &val) == 2 && off + 4 <= len)
                *(uint32_t *)(buf + off) = val;
        }
    }

    return submit_segment(ch, buf, len, patch ? patch : "");
}


// snapshot GPFIFO entries + pushbuffer segments when the doorbell rings
static void snapshot_submission(void)
{
    if (g_ring_region < 0) return;
    region_t *ring = &g_regions[g_ring_region];

    const char *dir = getenv("NVTRACE_DUMP_DIR");
    if (!dir) dir = "/tmp";

    // userd GPPut for channel i lives at i*CH_STRIDE + GPPUT_OFF; entries at i*CH_STRIDE
    for (int ch = 0; ch < MAX_CHANNELS; ch++) {
        size_t choff = (size_t)ch * CH_STRIDE;
        if (choff + GPPUT_OFF + 4 > ring->len) break;
        uint32_t put = *(volatile uint32_t *)(ring->base + choff + GPPUT_OFF);
        if (put == g_last_put[ch]) continue;

        // this channel advanced right after a doorbell write: associate
        if (g_db_seen) {
            g_ch_db_region[ch] = g_db_region;
            g_ch_db_off[ch] = g_db_off;
            g_ch_db_val[ch] = g_db_val;
            g_ch_db_seen[ch] = true;
        }

        uint32_t n = put - g_last_put[ch];
        if (n > GPFIFO_ENTRIES) { g_last_put[ch] = put - GPFIFO_ENTRIES; n = GPFIFO_ENTRIES; }

        for (uint32_t i = g_last_put[ch]; i < put; i++) {
            uint32_t slot = i % GPFIFO_ENTRIES;
            const volatile uint8_t *e =
                (const volatile uint8_t *)(ring->base + choff + slot * 8);
            uint32_t lo, hi;
            memcpy(&lo, (const void *)e, 4);
            memcpy(&hi, (const void *)(e + 4), 4);

            uint64_t seg_addr = ((uint64_t)(hi & 0xff) << 32) | (lo & 0xfffffffcu);
            uint32_t seg_len = ((hi >> 10) & 0x1fffff) * 4;
            if (seg_len == 0 || seg_len > SEG_DUMP_CAP) continue;

            // segment VA is also a valid CPU VA in this process (UVM unified map);
            // only read it if we know a mapping contains it (avoid wild reads)
            bool known = false;
            for (int k = 0; k < g_nregions; k++) {
                if (seg_addr >= g_regions[k].base &&
                    seg_addr + seg_len <= g_regions[k].base + g_regions[k].len) {
                    known = true;
                    break;
                }
            }
            if (!known) {
                nvtrace_emit_gpfifo(ch, (int)i, seg_addr, seg_len, hi, NULL, -1);
                continue;
            }

            // record for injection replay
            if (seg_len <= INJECT_SEG_CAP) {
                if (!g_last_seg_data[ch])
                    g_last_seg_data[ch] = malloc(INJECT_SEG_CAP);
                if (g_last_seg_data[ch]) {
                    memcpy(g_last_seg_data[ch],
                           (const void *)(uintptr_t)seg_addr, seg_len);
                    g_last_seg_addr[ch] = seg_addr;
                    g_last_seg_len[ch] = seg_len;
                    g_last_entry_lo[ch] = lo;
                    g_last_entry_hi[ch] = hi;
                }
                g_pb_tail_addr[ch] = seg_addr;
                g_pb_tail_len[ch] = seg_len;
                uint32_t cp[4];
                if (seg_extract_codeptr(g_last_seg_data[ch], seg_len, cp)) {
                    int idx = g_code_hist_n[ch] % CODE_HIST;
                    memcpy(g_code_hist[ch][idx], cp, sizeof(cp));
                    g_code_hist_n[ch]++;
                }
                // full segment history
                int sidx = g_shist_n[ch] % SEG_HIST;
                if (!g_shist_data[ch][sidx])
                    g_shist_data[ch][sidx] = malloc(INJECT_SEG_CAP);
                if (g_shist_data[ch][sidx]) {
                    memcpy(g_shist_data[ch][sidx], g_last_seg_data[ch], seg_len);
                    g_shist_addr[ch][sidx] = seg_addr;
                    g_shist_len[ch][sidx] = seg_len;
                    g_shist_n[ch]++;
                }
            }

            char path[256];
            snprintf(path, sizeof(path), "%s/nvtrace-seg-%d-%04d.bin", dir,
                     (int)getpid(), g_dump_seq);
            int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
            if (fd >= 0) {
                const uint8_t *src = (const uint8_t *)(uintptr_t)seg_addr;
                size_t left = seg_len;
                while (left) {
                    ssize_t w = write(fd, src, left);
                    if (w <= 0) break;
                    src += w; left -= (size_t)w;
                }
                close(fd);
            }
            nvtrace_emit_gpfifo(ch, (int)i, seg_addr, seg_len, hi, path, g_dump_seq);
            g_dump_seq++;
        }
        g_last_put[ch] = put;
    }
}
static __thread int g_step_region = -1;   // region being single-stepped

static region_t *find_region(uintptr_t addr)
{
    for (int i = 0; i < g_nregions; i++) {
        region_t *r = &g_regions[i];
        if (r->active && addr >= r->base && addr < r->base + r->len)
            return r;
    }
    return NULL;
}

static int region_index(region_t *r)
{
    return (int)(r - g_regions);
}

static void raw_mprotect(uintptr_t addr, size_t len, int prot)
{
    syscall(SYS_mprotect, (void *)addr, len, prot);
}

static void sigsegv_handler(int sig, siginfo_t *si, void *vctx)
{
    ucontext_t *ctx = vctx;
    uintptr_t fault = (uintptr_t)si->si_addr;
    region_t *r = find_region(fault);

    if (!r) {
        // not ours: chain or default
        if (g_old_segv.sa_flags & SA_SIGINFO) {
            if (g_old_segv.sa_sigaction) { g_old_segv.sa_sigaction(sig, si, vctx); return; }
        } else if (g_old_segv.sa_handler == SIG_DFL || g_old_segv.sa_handler == SIG_IGN) {
            sigaction(SIGSEGV, &g_old_segv, NULL);
            return;  // re-raise on return path via default
        } else if (g_old_segv.sa_handler) {
            g_old_segv.sa_handler(sig);
            return;
        }
        sigaction(SIGSEGV, &g_old_segv, NULL);
        return;
    }

    greg_t *gregs = ctx->uc_mcontext.gregs;
    uintptr_t rip = (uintptr_t)gregs[REG_RIP];
    int width = 0, ilen = 0;
    uint8_t value[16];
    memset(value, 0, sizeof(value));

    if (decode_store_ex((const uint8_t *)rip, gregs,
                        (const uint8_t *)ctx->uc_mcontext.fpregs,
                        &width, value, &ilen)) {
        nvtrace_emit_mmio(fault, fault - r->base, width, value, rip, NULL, 0,
                          region_index(r));
        // learn which region is the GPFIFO/userd region: writes at channel
        // userd GPPut offsets (i*CH_STRIDE + GPPUT_OFF)
        size_t woff = fault - r->base;
        if (width == 4 && woff >= GPPUT_OFF &&
            (woff - GPPUT_OFF) % CH_STRIDE == 0)
            g_ring_region = region_index(r);
        // record BAR doorbell writes (write-only small page) for replay
        if (width == 4 && r->dev == 2 && r->len <= 0x40000 &&
            !(r->orig_prot & PROT_READ)) {
            g_db_region = region_index(r);
            g_db_off = woff;
            memcpy(&g_db_val, value, 4);
            g_db_seen = true;
        }
        // allow the write, single-step, then re-arm
        raw_mprotect(r->base, r->len, r->orig_prot | PROT_READ | PROT_WRITE);
        r->active = false;
        g_step_region = region_index(r);
        gregs[REG_EFL] |= 0x100;  // TF
        return;
    }

    // unknown instruction: dump bytes, permanently disable trap on this region
    nvtrace_emit_mmio(fault, fault - r->base, 0, 0, rip,
                      (const uint8_t *)rip, 16, region_index(r));
    raw_mprotect(r->base, r->len, r->orig_prot);
    r->active = false;
    r->disabled = true;
}

static void sigtrap_handler(int sig, siginfo_t *si, void *vctx)
{
    (void)sig; (void)si;
    ucontext_t *ctx = vctx;
    if (g_step_region >= 0) {
        region_t *r = &g_regions[g_step_region];
        // re-arm: writable bit off; keep reads allowed
        int prot = (r->orig_prot & PROT_READ) ? PROT_READ : PROT_NONE;
        if (r->orig_prot & PROT_READ) prot |= (r->orig_prot & PROT_EXEC);
        raw_mprotect(r->base, r->len, prot);
        r->active = true;
        int stepped = g_step_region;
        g_step_region = -1;
        ctx->uc_mcontext.gregs[REG_EFL] &= ~0x100ull;
        // a completed write to a BAR doorbell page => work was submitted;
        // snapshot GPFIFO entries + pushbuffer segments now that stores landed
        if (r->dev == 2 && r->len <= 0x40000 && !(r->orig_prot & PROT_READ))
            snapshot_submission();
        (void)stepped;
        return;
    }
    if (g_old_trap.sa_flags & SA_SIGINFO) {
        if (g_old_trap.sa_sigaction) { g_old_trap.sa_sigaction(sig, si, vctx); return; }
    } else if (g_old_trap.sa_handler && g_old_trap.sa_handler != SIG_DFL &&
               g_old_trap.sa_handler != SIG_IGN) {
        g_old_trap.sa_handler(sig);
        return;
    }
}

void doorbell_trap_install(void)
{
    if (g_handlers_installed) return;
    g_handlers_installed = true;

    // alternate signal stack
    stack_t ss;
    ss.ss_sp = malloc(256 * 1024);
    ss.ss_size = 256 * 1024;
    ss.ss_flags = 0;
    sigaltstack(&ss, &g_old_ss);

    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_flags = SA_SIGINFO | SA_ONSTACK;

    sa.sa_sigaction = sigsegv_handler;
    sigaction(SIGSEGV, &sa, &g_old_segv);

    sa.sa_sigaction = sigtrap_handler;
    sigaction(SIGTRAP, &sa, &g_old_trap);
}

void doorbell_trap_set_enabled(bool en)
{
    g_trap_enabled = en;
}

// decide whether a fresh mmap is a doorbell/userd candidate
bool doorbell_candidate(int dev, int prot, size_t len)
{
    if (!(prot & PROT_WRITE)) return false;
    if (dev == 2 /*DEV_GPU*/ && len <= 0x40000) return true;   // BAR windows (64KB write-only doorbell page!)
    if (dev == 1 /*DEV_CTL*/ && len <= 0x10000) return true;   // userd/notify pages
    if (getenv("NVTRACE_TRAP_ALL") && len <= 0x4000000) return true;
    return false;
}

void doorbell_trap_register(void *addr, size_t len, int prot, int fd, int dev)
{
    if (!g_trap_enabled) return;
    if (!doorbell_candidate(dev, prot, len)) return;
    if (g_nregions >= MAX_REGIONS) return;

    doorbell_trap_install();

    region_t *r = &g_regions[g_nregions];
    r->base = (uintptr_t)addr;
    r->len = len;
    r->orig_prot = prot;
    r->fd = fd;
    r->dev = dev;
    r->active = false;
    r->disabled = false;
    g_nregions++;

    // arm: drop write permission
    int newprot = prot & ~(PROT_WRITE | PROT_EXEC);
    if (!(newprot & PROT_READ)) newprot = PROT_NONE;
    if (mprotect(addr, len, newprot) == 0) {
        r->active = true;
        nvtrace_emit_region(r->base, r->len, prot, fd, dev, g_nregions - 1);
    } else {
        g_nregions--;  // failed; drop
    }
}
