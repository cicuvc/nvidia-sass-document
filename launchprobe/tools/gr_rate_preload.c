// LD_PRELOAD probe for NV2080_CTRL_CMD_GR_GET_SM_ISSUE_RATE_MODIFIER_V2.
//
// This avoids reimplementing the long libcuda RM-client bring-up sequence:
// it watches an existing CUDA process allocate its NV20_SUBDEVICE_0 object,
// then issues the read-only rate/throttle queries on that live object after
// each successful subdevice control until RM reports the static tables ready.

#define _GNU_SOURCE

#include <dlfcn.h>
#include <errno.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>

#define NV_IOCTL_MAGIC 'F'
#define NV_ESC_RM_CONTROL 0x2A
#define NV_ESC_RM_ALLOC 0x2B

#define NV01_DEVICE_0 0x80U
#define NV20_SUBDEVICE_0 0x2080U

#define NV2080_CTRL_CMD_GR_GET_SM_ISSUE_RATE_MODIFIER_V2 0x2080123cU
#define NV2080_CTRL_CMD_GR_GET_SM_ISSUE_RATE_MODIFIER 0x20801230U
#define NV2080_CTRL_CMD_GR_GET_SM_ISSUE_THROTTLE_CTRL 0x2080123dU
#define NV2080_CTRL_GR_SM_ISSUE_RATE_MODIFIER_V2_MAX_LIST_SIZE 0xFFU
#define NV2080_CTRL_GR_SM_ISSUE_THROTTLE_CTRL_MAX_LIST_SIZE 0xFFU

typedef int (*ioctl_fn)(int, unsigned long, ...);

typedef struct {
    uint32_t hClient;
    uint32_t hObject;
    int32_t cmd;
    uint32_t flags;
    uint64_t params;
    uint32_t paramsSize;
    int32_t status;
} nvos54_parameters_t;

typedef struct {
    uint32_t index;
    uint32_t data;
} nv_ctrl_info_t;

typedef struct {
    uint32_t listSize;
    nv_ctrl_info_t list[NV2080_CTRL_GR_SM_ISSUE_RATE_MODIFIER_V2_MAX_LIST_SIZE];
} gr_rate_params_t;

typedef struct {
    uint32_t routeFlags;
    uint32_t pad0;
    uint64_t route;
    uint8_t imla0;
    uint8_t fmla16;
    uint8_t dp;
    uint8_t fmla32;
    uint8_t ffma;
    uint8_t imla1;
    uint8_t imla2;
    uint8_t imla3;
    uint8_t imla4;
    uint8_t pad1[7];
} gr_rate_v1_params_t;

typedef struct {
    uint32_t listSize;
    nv_ctrl_info_t list[NV2080_CTRL_GR_SM_ISSUE_THROTTLE_CTRL_MAX_LIST_SIZE];
} gr_throttle_params_t;

static ioctl_fn real_ioctl;
static uint32_t subdevice;
static uint32_t subdevice_client;
static int queried;
static unsigned control_count;

static const char *rate_index_name(uint32_t index)
{
    static const char *const names[15] = {
        "FMLA16", "DP", "FMLA32", "FFMA", "IMLA0", "IMLA1", "IMLA2",
        "IMLA3", "IMLA4", "FP16", "FP32", "DFMA", "DMLA", "CTRL0",
        "CTRL1",
    };
    return index < 15 ? names[index] : "UNKNOWN";
}

static const char *speed_name(uint32_t data)
{
    static const char *const names[7] = {
        "full", "1/2", "1/4", "1/8", "1/16", "1/32", "1/64",
    };
    return data < 7 ? names[data] : "reserved";
}

static int issue_control(int fd, uint32_t client, uint32_t object,
                         uint32_t cmd, void *params, uint32_t params_size)
{
    nvos54_parameters_t p;
    memset(&p, 0, sizeof(p));
    p.hClient = client;
    p.hObject = object;
    p.cmd = (int32_t)cmd;
    p.params = (uint64_t)(uintptr_t)params;
    p.paramsSize = params_size;
    int rc = real_ioctl(fd, _IOWR(NV_IOCTL_MAGIC, NV_ESC_RM_CONTROL,
                                  nvos54_parameters_t), &p);
    if (rc < 0)
        return -errno;
    return p.status;
}

static void try_query(int fd)
{
    gr_rate_params_t rate;
    gr_rate_v1_params_t rate_v1;
    gr_throttle_params_t throttle;
    uint32_t i;

    if (subdevice == 0 || queried)
        return;

    memset(&rate, 0, sizeof(rate));
    int status = issue_control(fd, subdevice_client, subdevice,
                               NV2080_CTRL_CMD_GR_GET_SM_ISSUE_RATE_MODIFIER_V2,
                               &rate, sizeof(rate));
    if (status != 0)
        return;

    queried = 1;
    fprintf(stderr, "[gr-rate] handles: client=0x%x subdevice=0x%x\n",
            subdevice_client, subdevice);
    fprintf(stderr, "[gr-rate] SM issue-rate modifiers: %u entries\n",
            rate.listSize);
    for (i = 0; i < rate.listSize; ++i) {
        fprintf(stderr,
                "[gr-rate]   [%02u] index=0x%02x %-7s data=0x%x %s\n",
                i, rate.list[i].index, rate_index_name(rate.list[i].index),
                rate.list[i].data, speed_name(rate.list[i].data));
    }

    fprintf(stderr, "[gr-rate] individual V2 index queries:\n");
    for (i = 0; i <= 0xE; ++i) {
        gr_rate_params_t one;
        memset(&one, 0, sizeof(one));
        one.listSize = 1;
        one.list[0].index = i;
        status = issue_control(fd, subdevice_client, subdevice,
                               NV2080_CTRL_CMD_GR_GET_SM_ISSUE_RATE_MODIFIER_V2,
                               &one, sizeof(one));
        if (status == 0) {
            fprintf(stderr,
                    "[gr-rate]   index=0x%02x %-7s data=0x%x %s\n",
                    i, rate_index_name(i), one.list[0].data,
                    speed_name(one.list[0].data));
        } else {
            fprintf(stderr,
                    "[gr-rate]   index=0x%02x %-7s unsupported status=0x%x\n",
                    i, rate_index_name(i), status);
        }
    }

    memset(&rate_v1, 0, sizeof(rate_v1));
    status = issue_control(fd, subdevice_client, subdevice,
                           NV2080_CTRL_CMD_GR_GET_SM_ISSUE_RATE_MODIFIER,
                           &rate_v1, sizeof(rate_v1));
    if (status == 0) {
        fprintf(stderr,
                "[gr-rate] V1: imla0=%u fmla16=%u dp=%u fmla32=%u ffma=%u "
                "imla1=%u imla2=%u imla3=%u imla4=%u\n",
                rate_v1.imla0, rate_v1.fmla16, rate_v1.dp, rate_v1.fmla32,
                rate_v1.ffma, rate_v1.imla1, rate_v1.imla2, rate_v1.imla3,
                rate_v1.imla4);
    } else {
        fprintf(stderr, "[gr-rate] V1 query status=0x%x\n", status);
    }

    memset(&throttle, 0, sizeof(throttle));
    status = issue_control(fd, subdevice_client, subdevice,
                           NV2080_CTRL_CMD_GR_GET_SM_ISSUE_THROTTLE_CTRL,
                           &throttle, sizeof(throttle));
    if (status == 0) {
        fprintf(stderr, "[gr-rate] SM issue-throttle controls: %u entries\n",
                throttle.listSize);
        for (i = 0; i < throttle.listSize; ++i) {
            fprintf(stderr, "[gr-rate]   [%02u] index=0x%02x data=0x%x\n",
                    i, throttle.list[i].index, throttle.list[i].data);
        }
    } else {
        fprintf(stderr, "[gr-rate] throttle query status=0x%x\n", status);
    }
    fflush(stderr);
}

int ioctl(int fd, unsigned long request, ...)
{
    va_list ap;
    void *arg;
    unsigned int nr;
    unsigned int size;

    if (real_ioctl == NULL)
        real_ioctl = (ioctl_fn)dlsym(RTLD_NEXT, "ioctl");

    va_start(ap, request);
    arg = va_arg(ap, void *);
    va_end(ap);

    nr = _IOC_NR(request);
    size = _IOC_SIZE(request);

    int rc = real_ioctl(fd, request, arg);

    if (rc == 0 && nr == NV_ESC_RM_ALLOC && arg != NULL &&
        (size == 32 || size == 48)) {
        const unsigned char *raw = arg;
        int32_t object_class;
        memcpy(&object_class, raw + 12, sizeof(object_class));
        if ((uint32_t)object_class == NV20_SUBDEVICE_0) {
            memcpy(&subdevice_client, raw + 0, sizeof(subdevice_client));
            memcpy(&subdevice, raw + 8, sizeof(subdevice));
        }
    } else if (rc == 0 && nr == NV_ESC_RM_CONTROL && arg != NULL &&
               size == sizeof(nvos54_parameters_t)) {
        const nvos54_parameters_t *p = arg;
        if (subdevice != 0 && p->hObject == subdevice &&
            ++control_count >= 4) {
            try_query(fd);
        }
    }

    return rc;
}
