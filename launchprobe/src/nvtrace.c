// libnvtrace.so - LD_PRELOAD interposer tracing CUDA<->driver communication.
// Hooks: open/openat/close/ioctl/mmap/munmap on /dev/nvidia* fds.
// Emits JSONL events. See include/nvrm_ioctl.h for struct provenance notes.
#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#include "nvrm_ioctl.h"
#include "doorbell_trap.h"

typedef int (*open_fn)(const char *, int, ...);
typedef int (*openat_fn)(int, const char *, int, ...);
typedef int (*close_fn)(int);
typedef int (*ioctl_fn)(int, unsigned long, ...);
typedef void *(*mmap_fn)(void *, size_t, int, int, int, off_t);
typedef void *(*mmap64_fn)(void *, size_t, int, int, int, off64_t);
typedef int (*munmap_fn)(void *, size_t);

static open_fn    real_open, real_open64;
static openat_fn  real_openat, real_openat64;
static close_fn  real_close;
static ioctl_fn  real_ioctl;
static mmap_fn   real_mmap;
static mmap64_fn real_mmap64;
static munmap_fn real_munmap;

static int          g_out_fd = -1;
static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
static __thread int g_in_hook = 0;
static bool         g_initialized = false;

#define DEV_UNKNOWN 0
#define DEV_CTL     1   // /dev/nvidiactl
#define DEV_GPU     2   // /dev/nvidiaN
#define DEV_UVM     3   // /dev/nvidia-uvm
#define DEV_OTHER   4

static uint64_t now_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + ts.tv_nsec;
}

static void resolve_syms(void)
{
    if (g_initialized) return;
    real_open    = (open_fn)dlsym(RTLD_NEXT, "open");
    real_open64  = (open_fn)dlsym(RTLD_NEXT, "open64");
    real_openat  = (openat_fn)dlsym(RTLD_NEXT, "openat");
    real_openat64 = (openat_fn)dlsym(RTLD_NEXT, "openat64");
    real_close   = (close_fn)dlsym(RTLD_NEXT, "close");
    real_ioctl   = (ioctl_fn)dlsym(RTLD_NEXT, "ioctl");
    real_mmap    = (mmap_fn)dlsym(RTLD_NEXT, "mmap");
    real_mmap64  = (mmap64_fn)dlsym(RTLD_NEXT, "mmap64");
    real_munmap  = (munmap_fn)dlsym(RTLD_NEXT, "munmap");

    const char *out = getenv("NVTRACE_OUT");
    char defpath[128];
    if (!out || !*out) {
        snprintf(defpath, sizeof(defpath), "/tmp/nvtrace-%d.jsonl", getpid());
        out = defpath;
    }
    g_out_fd = real_open(out, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    doorbell_trap_set_enabled(getenv("NVTRACE_TRAP") != NULL);
    g_initialized = true;
}

__attribute__((constructor)) static void nvtrace_init(void)
{
    resolve_syms();
}

// JSON-escape minimal (paths/hex are safe already, but be defensive)
static void json_escape(char *dst, size_t dstsz, const char *src)
{
    size_t j = 0;
    for (const char *p = src; *p && j + 2 < dstsz; p++) {
        unsigned char c = (unsigned char)*p;
        if (c == '"' || c == '\\') { dst[j++] = '\\'; dst[j++] = c; }
        else if (c >= 0x20 && c < 0x7f) dst[j++] = c;
        else { dst[j++] = '?'; }
    }
    dst[j] = 0;
}

static void emit(const char *fmt, ...)
{
    if (g_out_fd < 0) return;
    char buf[16384];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof(buf) - 2, fmt, ap);
    va_end(ap);
    if (n < 0) return;
    if (n > (int)sizeof(buf) - 2) n = sizeof(buf) - 2;
    buf[n++] = '\n';
    pthread_mutex_lock(&g_lock);
    (void)!write(g_out_fd, buf, n);
    fsync(g_out_fd);
    pthread_mutex_unlock(&g_lock);
}

static int classify_path(const char *path)
{
    if (!path) return DEV_UNKNOWN;
    if (strcmp(path, "/dev/nvidiactl") == 0) return DEV_CTL;
    if (strncmp(path, "/dev/nvidia-uvm", 15) == 0) return DEV_UVM;
    if (strncmp(path, "/dev/nvidia", 11) == 0) {
        char c = path[11];
        if (c >= '0' && c <= '9') return DEV_GPU;
    }
    return DEV_OTHER;
}

// lazy classify: fds can arrive via dup/inheritance; resolve via /proc
static int classify_fd(int fd)
{
    char link[64], target[256];
    snprintf(link, sizeof(link), "/proc/self/fd/%d", fd);
    ssize_t n = readlink(link, target, sizeof(target) - 1);
    if (n <= 0) return DEV_UNKNOWN;
    target[n] = 0;
    return classify_path(target);
}

static const char *dev_str(int cls)
{
    switch (cls) {
        case DEV_CTL: return "nvidiactl";
        case DEV_GPU: return "nvidia-gpu";
        case DEV_UVM: return "nvidia-uvm";
        case DEV_OTHER: return "other";
        default: return "unknown";
    }
}

// called by doorbell_trap.c (from signal handler context; keep it async-safe-ish)
void nvtrace_emit_mmio(uintptr_t addr, size_t off, int width,
                       const uint8_t *value, uintptr_t rip,
                       const uint8_t *raw, int rawlen, int region_idx)
{
    char vhex[40]; vhex[0] = 0;
    if (width > 0) {
        size_t j = 0;
        int n = width > 16 ? 16 : width;
        for (int i = n - 1; i >= 0 && j + 2 < sizeof(vhex) - 1; i--)
            j += snprintf(vhex + j, sizeof(vhex) - j, "%02x", value[i]);
        vhex[j] = 0;
    }
    char rawhex[40]; rawhex[0] = 0;
    if (raw) {
        size_t j = 0;
        for (int i = 0; i < rawlen && j + 2 < sizeof(rawhex) - 1; i++)
            j += snprintf(rawhex + j, sizeof(rawhex) - j, "%02x", raw[i]);
        rawhex[j] = 0;
    }
    if (width > 0)
        emit("{\"ev\":\"mmio_w\",\"ts\":%llu,\"tid\":%d,\"addr\":\"0x%lx\",\"off\":\"0x%zx\",\"width\":%d,\"value\":\"0x%s\",\"rip\":\"0x%lx\",\"region\":%d}",
             (unsigned long long)now_ns(), (int)syscall(SYS_gettid),
             (unsigned long)addr, off, width, vhex,
             (unsigned long)rip, region_idx);
    else
        emit("{\"ev\":\"mmio_w_undecoded\",\"ts\":%llu,\"tid\":%d,\"addr\":\"0x%lx\",\"off\":\"0x%zx\",\"rip\":\"0x%lx\",\"region\":%d,\"raw\":\"%s\"}",
             (unsigned long long)now_ns(), (int)syscall(SYS_gettid),
             (unsigned long)addr, off, (unsigned long)rip, region_idx, rawhex);
}

// marker API for target programs: dlsym(RTLD_DEFAULT, "nvtrace_mark")
// "inject[ch][:patch]" resubmits the last segment captured on a channel,
// with optional dword patches "off:val,off:val" (hex).
int nvtrace_inject_last(int ch, const char *patch);
int nvtrace_inject_raw(int ch, const char *path);
void nvtrace_mark(const char *msg)
{
    char esc[256]; json_escape(esc, sizeof(esc), msg ? msg : "");
    emit("{\"ev\":\"mark\",\"ts\":%llu,\"tid\":%d,\"msg\":\"%s\"}",
         (unsigned long long)now_ns(), (int)syscall(SYS_gettid), esc);
    if (msg && !strncmp(msg, "injectraw", 9)) {
        int ch = 0;
        const char *p = msg + 9;
        if (*p >= '0' && *p <= '9') { ch = *p - '0'; p++; }
        const char *path = (*p == ':') ? p + 1 : "/tmp/rawseg.bin";
        int r = nvtrace_inject_raw(ch, path);
        emit("{\"ev\":\"inject_req\",\"ts\":%llu,\"ch\":%d,\"rc\":%d,\"raw\":1}",
             (unsigned long long)now_ns(), ch, r);
        return;
    }
    if (msg && !strncmp(msg, "inject", 6)) {
        int ch = 0;
        const char *p = msg + 6;
        if (*p >= '0' && *p <= '9') { ch = *p - '0'; p++; }
        const char *patch = (*p == ':') ? p + 1 : getenv("NVTRACE_PATCH");
        int r = nvtrace_inject_last(ch, patch);
        emit("{\"ev\":\"inject_req\",\"ts\":%llu,\"ch\":%d,\"rc\":%d}",
             (unsigned long long)now_ns(), ch, r);
    }
}

void nvtrace_emit_inject(int ch, uint64_t seg_addr, uint32_t seg_len,
                         const char *patch)
{
    char esc[256]; json_escape(esc, sizeof(esc), patch ? patch : "");
    emit("{\"ev\":\"inject\",\"ts\":%llu,\"ch\":%d,\"segAddr\":\"0x%llx\",\"segLen\":%u,\"patch\":\"%s\"}",
         (unsigned long long)now_ns(), ch, (unsigned long long)seg_addr,
         seg_len, esc);
}

void nvtrace_emit_region(uintptr_t addr, size_t len, int prot, int fd,
                         int dev, int region_idx)
{
    emit("{\"ev\":\"region\",\"ts\":%llu,\"idx\":%d,\"addr\":\"0x%lx\",\"len\":\"0x%zx\",\"prot\":\"0x%x\",\"fd\":%d,\"dev\":\"%s\"}",
         (unsigned long long)now_ns(), region_idx, (unsigned long)addr, len,
         prot, fd, dev_str(dev));
}

void nvtrace_emit_gpfifo(int ch, int put_idx, uint64_t seg_addr, uint32_t seg_len,
                         uint32_t entry_hi, const char *file, int seq)
{
    uint32_t sync = entry_hi >> 31, level = (entry_hi >> 9) & 1, priv = (entry_hi >> 8) & 1;
    char esc[300]; esc[0] = 0;
    if (file) json_escape(esc, sizeof(esc), file);
    emit("{\"ev\":\"gpfifo\",\"ts\":%llu,\"ch\":%d,\"put\":%d,\"segAddr\":\"0x%llx\",\"segLen\":%u,\"sync\":%u,\"level\":%u,\"priv\":%u,\"file\":\"%s\",\"seq\":%d}",
         (unsigned long long)now_ns(), ch, put_idx, (unsigned long long)seg_addr,
         seg_len, sync, level, priv, esc, seq);
}

static const char *esc_name(unsigned int nr)
{
    switch (nr) {
        case NV_ESC_CARD_INFO: return "CARD_INFO";
        case NV_ESC_REGISTER_FD: return "REGISTER_FD";
        case NV_ESC_ALLOC_OS_EVENT: return "ALLOC_OS_EVENT";
        case NV_ESC_FREE_OS_EVENT: return "FREE_OS_EVENT";
        case NV_ESC_STATUS_CODE: return "STATUS_CODE";
        case NV_ESC_CHECK_VERSION_STR: return "CHECK_VERSION_STR";
        case NV_ESC_IOCTL_XFER_CMD: return "IOCTL_XFER_CMD";
        case NV_ESC_ATTACH_GPUS_TO_FD: return "ATTACH_GPUS_TO_FD";
        case NV_ESC_QUERY_DEVICE_INTR: return "QUERY_DEVICE_INTR";
        case NV_ESC_SYS_PARAMS: return "SYS_PARAMS";
        case NV_ESC_EXPORT_TO_DMABUF_FD: return "EXPORT_TO_DMABUF_FD";
        case NV_ESC_WAIT_OPEN_COMPLETE: return "WAIT_OPEN_COMPLETE";
        case NV_ESC_RM_ALLOC_MEMORY_LEGACY: return "RM_ALLOC_MEMORY_LEGACY?";
        case NV_ESC_RM_FREE: return "RM_FREE?";
        case NV_ESC_RM_CONTROL: return "RM_CONTROL?";
        case NV_ESC_RM_ALLOC: return "RM_ALLOC?";
        case NV_ESC_RM_DUP_OBJECT: return "RM_DUP_OBJECT?";
        case NV_ESC_RM_SHARE: return "RM_SHARE?";
        case NV_ESC_RM_VID_HEAP_CONTROL: return "RM_VID_HEAP_CONTROL?";
        case NV_ESC_RM_MAP_MEMORY: return "RM_MAP_MEMORY?";
        case NV_ESC_RM_UNMAP_MEMORY: return "RM_UNMAP_MEMORY?";
        case NV_ESC_RM_MAP_MEMORY_DMA: return "RM_MAP_MEMORY_DMA?";
        case NV_ESC_RM_UNMAP_MEMORY_DMA: return "RM_UNMAP_MEMORY_DMA?";
        case NV_ESC_RM_UPDATE_DEVICE_MAPPING_INFO: return "RM_UPDATE_DEVICE_MAPPING_INFO?";
        case NV_ESC_RM_ALLOC_MEMORY: return "RM_ALLOC_MEMORY?";
        default: return NULL;
    }
}

#define HEXCAP 384  // bytes of arg buffer dumped as hex

static void hexdump(char *dst, size_t dstsz, const void *src, size_t len)
{
    if (len > HEXCAP) len = HEXCAP;
    size_t j = 0;
    for (size_t i = 0; i < len && j + 2 < dstsz; i++) {
        j += snprintf(dst + j, dstsz - j, "%02x", ((const uint8_t *)src)[i]);
    }
    dst[j] = 0;
}

// NV_CHANNEL_ALLOC_PARAMS field offsets (sdk alloc_channel.h, NV_MAX_SUBDEVICES=8)
// 0:hObjectError 4:hObjectBuffer 8:gpFifoOffset 16:gpFifoEntries 20:flags
// 24:hContextShare 28:hVASpace 32:hUserdMemory[8] 64:userdOffset[8]
// 128:engineType 132:cid 136:subDeviceId
static bool is_channel_class(uint32_t hClass)
{
    return (hClass & 0xff) == 0x6f;   // *_CHANNEL_GPFIFO family (c06f, c96f, ...)
}

static void decode_channel_params(uint64_t paramsVA, char *out, size_t outsz)
{
    if (!paramsVA) { out[0] = 0; return; }
    const uint8_t *p = (const uint8_t *)(uintptr_t)paramsVA;
    uint64_t gpFifoOffset, userdOffset0;
    uint32_t gpFifoEntries, flags, engineType, cid, hUserd0;
    memcpy(&gpFifoOffset, p + 8, 8);
    memcpy(&gpFifoEntries, p + 16, 4);
    memcpy(&flags, p + 20, 4);
    memcpy(&hUserd0, p + 32, 4);
    memcpy(&userdOffset0, p + 64, 8);
    memcpy(&engineType, p + 128, 4);
    memcpy(&cid, p + 132, 4);
    snprintf(out, outsz,
             ",\"chGpFifoOff\":\"0x%llx\",\"chGpFifoEntries\":%u,\"chFlags\":\"0x%x\",\"chUserdMem\":\"0x%x\",\"chUserdOff\":\"0x%llx\",\"chEngineType\":\"0x%x\",\"chCid\":%u",
             (unsigned long long)gpFifoOffset, gpFifoEntries, flags, hUserd0,
             (unsigned long long)userdOffset0, engineType, cid);
}

// structured decode for known RM ioctls; returns detail string (static buf ok: under lock-less emit)
static void decode_rm_arg(unsigned int nr, void *arg, size_t argsz, char *out, size_t outsz)
{
    out[0] = 0;
    if (!arg) return;
    switch (nr) {
        case NV_ESC_RM_ALLOC: {
            if (argsz < sizeof(nvrm_alloc_t)) break;
            nvrm_alloc_t *a = arg;
            char ch[512]; ch[0] = 0;
            if (is_channel_class(a->hClass))
                decode_channel_params(a->params, ch, sizeof(ch));
            snprintf(out, outsz, ",\"hClient\":\"0x%x\",\"hParent\":\"0x%x\",\"hObject\":\"0x%x\",\"hClass\":\"0x%x\",\"status\":\"0x%x\",\"paramsVA\":\"0x%llx\"%s",
                     a->hClient, a->hParent, a->hObject, a->hClass, a->status,
                     (unsigned long long)a->params, ch);
            return;
        }
        case NV_ESC_RM_FREE: {
            if (argsz < sizeof(nvrm_free_t)) break;
            nvrm_free_t *a = arg;
            snprintf(out, outsz, ",\"hClient\":\"0x%x\",\"hParent\":\"0x%x\",\"hObject\":\"0x%x\",\"status\":\"0x%x\"",
                     a->hClient, a->hParent, a->hObject, a->status);
            return;
        }
        case NV_ESC_RM_CONTROL: {
            if (argsz < sizeof(nvrm_control_t)) break;
            nvrm_control_t *a = arg;
            snprintf(out, outsz, ",\"hClient\":\"0x%x\",\"hObject\":\"0x%x\",\"ctrlCmd\":\"0x%x\",\"status\":\"0x%x\",\"paramsVA\":\"0x%llx\",\"paramsSize\":%u",
                     a->hClient, a->hObject, a->cmd, a->status,
                     (unsigned long long)a->params, a->paramsSize);
            return;
        }
        case NV_ESC_RM_MAP_MEMORY: {
            if (argsz < sizeof(nvrm_map_memory_t)) break;
            nvrm_map_memory_t *a = arg;
            snprintf(out, outsz, ",\"hClient\":\"0x%x\",\"hDevice\":\"0x%x\",\"hObject\":\"0x%x\",\"status\":\"0x%x\",\"offset\":\"0x%llx\",\"length\":\"0x%llx\",\"address\":\"0x%llx\",\"flags\":\"0x%x\"",
                     a->hClient, a->hDevice, a->hObject, a->status,
                     (unsigned long long)a->offset, (unsigned long long)a->length,
                     (unsigned long long)a->address, a->flags);
            return;
        }
        case NV_ESC_RM_ALLOC_MEMORY: {
            if (argsz < sizeof(nvrm_alloc_memory_t)) break;
            nvrm_alloc_memory_t *a = arg;
            snprintf(out, outsz, ",\"hClient\":\"0x%x\",\"hDevice\":\"0x%x\",\"hObject\":\"0x%x\",\"hParent\":\"0x%x\",\"status\":\"0x%x\",\"flags\":\"0x%x\",\"length\":\"0x%llx\",\"address\":\"0x%llx\"",
                     a->hClient, a->hDevice, a->hObject, a->hParent, a->status,
                     a->flags, (unsigned long long)a->length,
                     (unsigned long long)a->address);
            return;
        }
    }
}

static void log_open(const char *pathname, int flags, int fd, const char *via)
{
    int cls = classify_path(pathname);
    if (cls == DEV_CTL || cls == DEV_GPU || cls == DEV_UVM) {
        char esc[512]; json_escape(esc, sizeof(esc), pathname);
        emit("{\"ev\":\"open\",\"ts\":%llu,\"tid\":%d,\"path\":\"%s\",\"dev\":\"%s\",\"fd\":%d,\"flags\":\"0x%x\",\"via\":\"%s\"}",
             (unsigned long long)now_ns(), (int)syscall(SYS_gettid), esc,
             dev_str(cls), fd, flags, via);
    }
}

static mode_t open_mode_arg(int flags, va_list ap)
{
    return (flags & O_CREAT) ? va_arg(ap, mode_t) : 0;
}

int open(const char *pathname, int flags, ...)
{
    resolve_syms();
    va_list ap; va_start(ap, flags);
    mode_t mode = open_mode_arg(flags, ap); va_end(ap);
    int ret = real_open(pathname, flags, mode);
    if (ret >= 0 && !g_in_hook) log_open(pathname, flags, ret, "open");
    return ret;
}

int open64(const char *pathname, int flags, ...)
{
    resolve_syms();
    va_list ap; va_start(ap, flags);
    mode_t mode = open_mode_arg(flags, ap); va_end(ap);
    int ret = real_open64(pathname, flags, mode);
    if (ret >= 0 && !g_in_hook) log_open(pathname, flags, ret, "open64");
    return ret;
}

int openat(int dirfd, const char *pathname, int flags, ...)
{
    resolve_syms();
    va_list ap; va_start(ap, flags);
    mode_t mode = open_mode_arg(flags, ap); va_end(ap);
    int ret = real_openat(dirfd, pathname, flags, mode);
    if (ret >= 0 && !g_in_hook) log_open(pathname, flags, ret, "openat");
    return ret;
}

int openat64(int dirfd, const char *pathname, int flags, ...)
{
    resolve_syms();
    va_list ap; va_start(ap, flags);
    mode_t mode = open_mode_arg(flags, ap); va_end(ap);
    int ret = real_openat64(dirfd, pathname, flags, mode);
    if (ret >= 0 && !g_in_hook) log_open(pathname, flags, ret, "openat64");
    return ret;
}

int close(int fd)
{
    resolve_syms();
    if (!g_in_hook) {
        int cls = classify_fd(fd);
        if (cls == DEV_CTL || cls == DEV_GPU || cls == DEV_UVM) {
            emit("{\"ev\":\"close\",\"ts\":%llu,\"tid\":%d,\"fd\":%d,\"dev\":\"%s\"}",
                 (unsigned long long)now_ns(), (int)syscall(SYS_gettid), fd, dev_str(cls));
        }
    }
    return real_close(fd);
}

int ioctl(int fd, unsigned long request, ...)
{
    resolve_syms();
    va_list ap; va_start(ap, request);
    void *arg = va_arg(ap, void *);
    va_end(ap);

    if (g_in_hook) return real_ioctl(fd, request, arg);

    unsigned int type = _IOC_TYPE(request);
    if (type != NV_IOCTL_MAGIC && type != 'U')   // 'U' = UVM (unverified, log raw)
        return real_ioctl(fd, request, arg);

    int cls = classify_fd(fd);
    if (cls == DEV_UNKNOWN || cls == DEV_OTHER)
        return real_ioctl(fd, request, arg);

    g_in_hook = 1;
    unsigned int nr    = _IOC_NR(request);
    unsigned int sz    = _IOC_SIZE(request);
    unsigned int dir   = _IOC_DIR(request);
    const char  *name  = esc_name(nr);

    // snapshot arg buffer before the call (in params)
    uint8_t pre[HEXCAP]; char prehex[HEXCAP * 2 + 8]; prehex[0] = 0;
    size_t prelen = sz < HEXCAP ? sz : HEXCAP;
    if (arg && (dir & _IOC_WRITE)) {
        memcpy(pre, arg, prelen);
        hexdump(prehex, sizeof(prehex), pre, prelen);
    }

    // decode xfer wrapper: log inner cmd
    char xfer[128]; xfer[0] = 0;
    if (nr == NV_ESC_IOCTL_XFER_CMD && arg && sz >= sizeof(nv_ioctl_xfer_t)) {
        nv_ioctl_xfer_t *x = arg;
        const char *inner = esc_name(x->cmd);
        if (inner)
            snprintf(xfer, sizeof(xfer), ",\"innerCmd\":\"0x%x\",\"innerName\":\"%s\",\"innerSize\":%u", x->cmd, inner, x->size);
        else
            snprintf(xfer, sizeof(xfer), ",\"innerCmd\":\"0x%x\",\"innerSize\":%u", x->cmd, x->size);
    }

    int ret = real_ioctl(fd, request, arg);

    uint8_t post[HEXCAP]; char posthex[HEXCAP * 2 + 8]; posthex[0] = 0;
    if (arg && (dir & _IOC_READ)) {
        memcpy(post, arg, prelen);
        hexdump(posthex, sizeof(posthex), post, prelen);
    }

    char detail[1024]; decode_rm_arg(nr, arg, sz, detail, sizeof(detail));

    char namebuf[64];
    if (!name) { snprintf(namebuf, sizeof(namebuf), "0x%x", nr); name = namebuf; }

    emit("{\"ev\":\"ioctl\",\"ts\":%llu,\"tid\":%d,\"fd\":%d,\"dev\":\"%s\",\"name\":\"%s\",\"nr\":\"0x%x\",\"size\":%u,\"dir\":\"0x%x\",\"ret\":%d%s%s,\"pre\":\"%s\",\"post\":\"%s\"}",
         (unsigned long long)now_ns(), (int)syscall(SYS_gettid), fd, dev_str(cls),
         name, nr, sz, dir, ret, xfer, detail, prehex, posthex);
    g_in_hook = 0;
    return ret;
}

static void log_mmap(int fd, void *ret, size_t length, int prot, int flags, unsigned long long offset, const char *via)
{
    int cls = classify_fd(fd);
    if (cls == DEV_CTL || cls == DEV_GPU || cls == DEV_UVM) {
        g_in_hook = 1;
        emit("{\"ev\":\"mmap\",\"ts\":%llu,\"tid\":%d,\"fd\":%d,\"dev\":\"%s\",\"addr\":\"0x%lx\",\"len\":\"0x%lx\",\"prot\":\"0x%x\",\"flags\":\"0x%x\",\"offset\":\"0x%llx\",\"via\":\"%s\"}",
             (unsigned long long)now_ns(), (int)syscall(SYS_gettid), fd, dev_str(cls),
             (unsigned long)ret, (unsigned long)length, prot, flags, offset, via);
        g_in_hook = 0;
        doorbell_trap_register(ret, length, prot, fd, cls);
    }
}

void *mmap(void *addr, size_t length, int prot, int flags, int fd, off_t offset)
{
    resolve_syms();
    void *ret = real_mmap(addr, length, prot, flags, fd, offset);
    if (ret != MAP_FAILED && fd >= 0 && !g_in_hook)
        log_mmap(fd, ret, length, prot, flags, (unsigned long long)offset, "mmap");
    return ret;
}

void *mmap64(void *addr, size_t length, int prot, int flags, int fd, off64_t offset)
{
    resolve_syms();
    void *ret = real_mmap64(addr, length, prot, flags, fd, offset);
    if (ret != MAP_FAILED && fd >= 0 && !g_in_hook)
        log_mmap(fd, ret, length, prot, flags, (unsigned long long)offset, "mmap64");
    return ret;
}

int munmap(void *addr, size_t length)
{
    resolve_syms();
    return real_munmap(addr, length);
}
