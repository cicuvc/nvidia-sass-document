// launchprobe: best-known NVIDIA RM ioctl numbers and argument struct layouts.
//
// Sources of truth:
//   - NV_ESC_* (200..218): /usr/src/nvidia-580.65.06/common/inc/nv-ioctl-numbers.h (local, authoritative)
//   - RM_* (0x20..0x50 range): NOT shipped in the open kernel modules (closed RM).
//     Numbers/structs below are the classic layouts that circulated with older
//     public nv.h releases and match widely-available strace decodes of CUDA.
//     They are marked "best-known" and must be validated empirically (NOTES.md).
#pragma once

#include <stdint.h>

#define NV_IOCTL_MAGIC 'F'   // 0x46
#define NV_IOCTL_BASE  200

// --- local-header escapes (authoritative) ---
#define NV_ESC_CARD_INFO           (NV_IOCTL_BASE + 0)
#define NV_ESC_REGISTER_FD         (NV_IOCTL_BASE + 1)
#define NV_ESC_ALLOC_OS_EVENT      (NV_IOCTL_BASE + 6)
#define NV_ESC_FREE_OS_EVENT       (NV_IOCTL_BASE + 7)
#define NV_ESC_STATUS_CODE         (NV_IOCTL_BASE + 9)
#define NV_ESC_CHECK_VERSION_STR   (NV_IOCTL_BASE + 10)
#define NV_ESC_IOCTL_XFER_CMD      (NV_IOCTL_BASE + 11)
#define NV_ESC_ATTACH_GPUS_TO_FD   (NV_IOCTL_BASE + 12)
#define NV_ESC_QUERY_DEVICE_INTR   (NV_IOCTL_BASE + 13)
#define NV_ESC_SYS_PARAMS          (NV_IOCTL_BASE + 14)
#define NV_ESC_EXPORT_TO_DMABUF_FD (NV_IOCTL_BASE + 17)
#define NV_ESC_WAIT_OPEN_COMPLETE  (NV_IOCTL_BASE + 18)

typedef struct {
    uint32_t cmd;
    uint32_t size;
    uint64_t ptr;
} nv_ioctl_xfer_t;

// --- best-known RM escapes (validate!) ---
#define NV_ESC_RM_ALLOC_MEMORY_LEGACY 0x27  // old pre-VAS alloc, rare on modern drivers
#define NV_ESC_RM_FREE                0x29
#define NV_ESC_RM_CONTROL             0x2A
#define NV_ESC_RM_ALLOC               0x2B
#define NV_ESC_RM_DUP_OBJECT          0x34
#define NV_ESC_RM_SHARE               0x35
#define NV_ESC_RM_VID_HEAP_CONTROL    0x4A
#define NV_ESC_RM_MAP_MEMORY          0x4E
#define NV_ESC_RM_UNMAP_MEMORY        0x4F
#define NV_ESC_RM_MAP_MEMORY_DMA      0x51
#define NV_ESC_RM_UNMAP_MEMORY_DMA    0x52
#define NV_ESC_RM_UPDATE_DEVICE_MAPPING_INFO 0x5E
#define NV_ESC_RM_ALLOC_MEMORY        0x5D  // modern (VAS-aware) memory alloc

// Classic struct layouts (best-known).
// RM_ALLOC wire layout verified from hexdump (run2, event 247):
//   {hClient,hParent,hObject,hClass} u32x4, then NvP64 params @16, status u32 @24.
typedef struct {           // NV_ESC_RM_ALLOC (48 bytes on driver 580)
    uint32_t hClient;
    uint32_t hParent;
    uint32_t hObject;      // out (libcuda pre-fills client-chosen handle)
    uint32_t hClass;
    uint64_t params;       // class-specific alloc params ptr (userspace VA)
    uint32_t status;       // out
    uint32_t pad0;
    uint64_t rsvd[2];
} nvrm_alloc_t;

typedef struct {           // NV_ESC_RM_FREE
    uint32_t hClient;
    uint32_t hParent;
    uint32_t hObject;
    uint32_t status;       // out
} nvrm_free_t;

typedef struct {           // NV_ESC_RM_CONTROL
    uint32_t hClient;
    uint32_t hObject;
    uint32_t cmd;
    uint32_t status;       // out
    uint64_t params;       // ctrl params ptr
    uint32_t paramsSize;
} nvrm_control_t;

typedef struct {           // NV_ESC_RM_MAP_MEMORY
    uint32_t hClient;
    uint32_t hDevice;
    uint32_t hObject;      // memory object
    uint32_t status;       // out
    uint64_t offset;
    uint64_t length;
    uint64_t address;      // in/out: requested/returned VA
    uint32_t flags;
} nvrm_map_memory_t;

typedef struct {           // NV_ESC_RM_UNMAP_MEMORY
    uint32_t hClient;
    uint32_t hDevice;
    uint32_t hObject;
    uint32_t status;
    uint32_t flags;
    uint64_t address;
} nvrm_unmap_memory_t;

typedef struct {           // NV_ESC_RM_ALLOC_MEMORY (0x5D, best-known)
    uint32_t hClient;
    uint32_t hDevice;
    uint32_t hObject;      // out
    uint32_t hParent;
    uint32_t status;       // out
    uint32_t flags;
    uint32_t attr;
    uint64_t attr2;
    uint64_t length;
    uint64_t alignment;
    uint64_t offset;
    uint64_t limit;
    uint64_t address;      // in/out
} nvrm_alloc_memory_t;

typedef struct {           // NV_ESC_CARD_INFO entry
    uint32_t valid;
    uint32_t domain;
    uint8_t  bus, slot, function, _pad0;
    uint16_t vendor_id, device_id;
    uint32_t gpu_id;
    uint16_t interrupt_line, _pad1;
    uint64_t reg_address, reg_size, fb_address, fb_size;
    uint32_t minor_number;
    uint8_t  dev_name[10];
} nv_card_info_t;

typedef struct {           // NV_ESC_CHECK_VERSION_STR
    uint32_t cmd;          // subcommand
    uint32_t reply;
    char     versionString[64];
} nv_version_t;
