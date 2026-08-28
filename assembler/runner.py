"""Minimal CUDA Driver API wrapper for loading and running SM120 cubins.

Usage:
    from assembler import CudaModule

    cubin = open("kernel.cubin", "rb").read()
    mod = CudaModule(cubin)

    d_ptr = mod.devmem_alloc(1024)
    mod.launch("my_kernel", grid=(1,), block=(256,), args=[d_ptr])
    mod.synchronize()
    data = mod.device_read(d_ptr, 1024)
"""

from __future__ import annotations
import ctypes
import struct
import ctypes.util
from typing import Optional

# Load CUDA Driver API
_cuda_lib = None


def _cuda():
    global _cuda_lib
    if _cuda_lib is not None:
        return _cuda_lib
    path = ctypes.util.find_library("cuda")
    if path is None:
        raise RuntimeError("libcuda.so not found. Install CUDA driver.")
    _cuda_lib = ctypes.CDLL(path)
    # Set up return types
    _cuda_lib.cuInit.restype = ctypes.c_int
    _cuda_lib.cuDeviceGet.restype = ctypes.c_int
    _cuda_lib.cuCtxCreate.restype = ctypes.c_int
    _cuda_lib.cuModuleLoadData.restype = ctypes.c_int
    _cuda_lib.cuModuleGetFunction.restype = ctypes.c_int
    _cuda_lib.cuLaunchKernel.restype = ctypes.c_int
    _cuda_lib.cuMemAlloc.restype = ctypes.c_int
    _cuda_lib.cuMemFree.restype = ctypes.c_int
    _cuda_lib.cuMemcpyDtoH.restype = ctypes.c_int
    _cuda_lib.cuMemcpyHtoD.restype = ctypes.c_int
    _cuda_lib.cuMemsetD32.restype = ctypes.c_int
    _cuda_lib.cuCtxSynchronize.restype = ctypes.c_int
    _cuda_lib.cuCtxDestroy.restype = ctypes.c_int
    _cuda_lib.cuDeviceGetName.restype = ctypes.c_int
    _cuda_lib.cuDeviceGetAttribute.restype = ctypes.c_int
    _cuda_lib.cuGetErrorString.restype = ctypes.c_int
    _cuda_lib.cuGetErrorName.restype = ctypes.c_int
    return _cuda_lib


def _check(err: int) -> None:
    if err != 0:
        lib = _cuda()
        name_buf = ctypes.c_char_p()
        lib.cuGetErrorName(err, ctypes.byref(name_buf))
        desc_buf = ctypes.c_char_p()
        lib.cuGetErrorString(err, ctypes.byref(desc_buf))
        ename = name_buf.value.decode() if name_buf.value else f"0x{err:x}"
        edesc = desc_buf.value.decode() if desc_buf.value else "unknown error"
        raise RuntimeError(f"CUDA error {err} ({ename}): {edesc}")


# Process-global CUDA context shared by every CudaModule.  cuCtxCreate is
# ~0.4 s; reusing one context keeps per-module load at ~0.
_CTX: dict[int, ctypes.c_void_p] = {}


def _shared_ctx(device: int = 0) -> ctypes.c_void_p:
    """Return (creating on first use) a process-global context for a device."""
    lib = _cuda()
    if device not in _CTX:
        _check(lib.cuInit(0))
        dev = ctypes.c_int(device)
        _check(lib.cuDeviceGet(ctypes.byref(dev), device))
        ctx = ctypes.c_void_p()
        _check(lib.cuCtxCreate(ctypes.byref(ctx), 0, dev))
        _CTX[device] = ctx
    return _CTX[device]


def reset_context() -> None:
    """Destroy the shared context(s).  Call after a kernel fault so the next
    CudaModule starts fresh instead of reusing a poisoned context."""
    lib = _cuda()
    for ctx in _CTX.values():
        try:
            lib.cuCtxDestroy(ctx)
        except Exception:
            pass
    _CTX.clear()


class CudaModule:
    """Load and launch a cubin on a CUDA-capable GPU.

    Args:
        cubin: cubin file bytes as returned by ``assemble()``.
        device: GPU device index (default 0).
    """

    def __init__(self, cubin: bytes, device: int = 0):
        lib = _cuda()
        self._dev = ctypes.c_int(device)
        self._ctx = _shared_ctx(device)
        _check(lib.cuCtxSetCurrent(self._ctx))

        self._mod = ctypes.c_void_p()
        _check(lib.cuModuleLoadData(ctypes.byref(self._mod), cubin))

        # Per-parameter sizes (bytes) from the cubin's EIATTR_KPARAM_INFO
        # records.  Sized so a kernel's kernelParams array can carry values of
        # the right width (8 for pointers, 256 for __grid_constant__ tensor
        # maps).  None means "unknown / assume 8" (e.g. nvcc cubins where we
        # haven't parsed the layout, or legacy 8-byte-only usage).
        self._param_sizes = _extract_param_sizes(cubin)

        # Cache functions
        self._funcs: dict[str, ctypes.c_void_p] = {}

    def __del__(self):
        # The context is process-global (shared across modules); it is not
        # destroyed here — see reset_context().
        pass

    @property
    def device_name(self) -> str:
        lib = _cuda()
        buf = ctypes.create_string_buffer(128)
        _check(lib.cuDeviceGetName(buf, 128, self._dev))
        return buf.value.decode()

    # ------------------------------------------------------------------
    def func(self, name: str) -> ctypes.c_void_p:
        """Get a kernel function by C++ name (auto-mangled)."""
        if name not in self._funcs:
            # Try direct name first, then mangled form _Z<N><name>
            mangled = f"_Z{len(name)}{name}"
            f = ctypes.c_void_p()
            err = _cuda().cuModuleGetFunction(
                ctypes.byref(f), self._mod, mangled.encode())
            if err != 0:
                # Fall back to exact name
                _check(
                    _cuda().cuModuleGetFunction(
                        ctypes.byref(f), self._mod, name.encode()))
            self._funcs[name] = f
        return self._funcs[name]

    def launch(self, func_name: str, *,
               grid: tuple[int, ...] = (1, 1, 1),
               block: tuple[int, ...] = (256, 1, 1),
               args: list | None = None,
               shared_mem: int = 0,
               stream: int = 0) -> None:
        """Launch a kernel function.

        Each element in ``args`` is a pointer to the argument value (e.g.,
        ``ctypes.byref(val)`` or ``ctypes.c_void_p(dev_ptr)`` for device
        pointers).
        """
        f = self.func(func_name)
        raw_args = self._kernel_param_array(args)
        gx, gy, gz = _pad3(grid)
        bx, by, bz = _pad3(block)
        _check(_cuda().cuLaunchKernel(
            f, gx, gy, gz, bx, by, bz, shared_mem,
            ctypes.c_void_p(stream), raw_args, None,
        ))

    def launch_ex(self, func_name: str, *,
                  grid: tuple[int, ...] = (1, 1, 1),
                  block: tuple[int, ...] = (256, 1, 1),
                  args: list | None = None,
                  shared_mem: int = 0,
                  stream: int = 0,
                  programmatic_serialization: bool = False,
                  cluster_dims: tuple[int, int, int] | None = None) -> None:
        """Launch a kernel through ``cuLaunchKernelEx``.

        ``programmatic_serialization`` sets
        ``CU_LAUNCH_ATTRIBUTE_PROGRAMMATIC_STREAM_SERIALIZATION`` (PDL):
        the kernel may overlap with the previous kernel on the same stream,
        resolving its stream dependency programmatically via
        ``griddepcontrol`` (SASS ACQBULK / PREEXIT).

        ``cluster_dims`` sets ``CU_LAUNCH_ATTRIBUTE_CLUSTER_DIMENSION``
        (x, y, z) — the kernel must carry the cluster EIATTRs
        (``#pragma CLUSTER(x,y,z)``) or the launch fails with
        CUDA_ERROR_INVALID_VALUE.
        """
        f = self.func(func_name)
        raw_args = self._kernel_param_array(args)
        gx, gy, gz = _pad3(grid)
        bx, by, bz = _pad3(block)

        if not (programmatic_serialization or cluster_dims):
            self.launch(func_name, grid=grid, block=block, args=args,
                        shared_mem=shared_mem, stream=stream)
            return

        # CUDA 12/13 driver launch-attribute layout:
        #   CUlaunchAttribute { CUlaunchAttributeID id; char pad[4];
        #                       CUlaunchAttributeValue value; }  (value = 64B)
        class AttrVal(ctypes.Union):
            _fields_ = [("pad", ctypes.c_ubyte * 64)]

        class LaunchAttr(ctypes.Structure):
            _fields_ = [("id", ctypes.c_int),
                        ("pad", ctypes.c_ubyte * 4),
                        ("value", AttrVal)]

        attrs = []
        if programmatic_serialization:
            # CU_LAUNCH_ATTRIBUTE_PROGRAMMATIC_STREAM_SERIALIZATION == 6;
            # value is a 64-byte union, first member an int.
            attr = LaunchAttr()
            attr.id = 6
            ctypes.memset(ctypes.byref(attr.value), 0,
                          ctypes.sizeof(attr.value))
            ctypes.cast(ctypes.pointer(attr.value),
                        ctypes.POINTER(ctypes.c_int))[0] = 1
            attrs.append(attr)
        if cluster_dims is not None:
            # CU_LAUNCH_ATTRIBUTE_CLUSTER_DIMENSION == 4; value is CUdim3
            # (3 x u32: x, y, z).
            attr = LaunchAttr()
            attr.id = 4
            ctypes.memset(ctypes.byref(attr.value), 0,
                          ctypes.sizeof(attr.value))
            dims = (ctypes.c_uint * 3)(*cluster_dims)
            ctypes.memmove(ctypes.byref(attr.value), ctypes.byref(dims),
                           12)
            attrs.append(attr)

        Arr = LaunchAttr * len(attrs)
        attr_arr = Arr(*attrs)

        class LaunchConfig(ctypes.Structure):
            _fields_ = [("gridDimX", ctypes.c_uint),
                        ("gridDimY", ctypes.c_uint),
                        ("gridDimZ", ctypes.c_uint),
                        ("blockDimX", ctypes.c_uint),
                        ("blockDimY", ctypes.c_uint),
                        ("blockDimZ", ctypes.c_uint),
                        ("sharedMemBytes", ctypes.c_uint),
                        ("hStream", ctypes.c_void_p),
                        ("attrs", ctypes.POINTER(LaunchAttr)),
                        ("numAttrs", ctypes.c_uint)]

        cfg = LaunchConfig(gx, gy, gz, bx, by, bz, shared_mem,
                           ctypes.c_void_p(stream), attr_arr, len(attrs))
        _check(_cuda().cuLaunchKernelEx(ctypes.byref(cfg), f, raw_args, None))

    def _kernel_param_array(self, args):
        """kernelParams convention: array of pointers to each argument value.

        An int arg is an 8-byte slot (pointer-sized, which the driver reads
        for 4/8-byte params); a bytes/bytearray arg supplies the raw value at
        the parameter's size (e.g. a 256-byte __grid_constant__ CUtensorMap).
        """
        if not args:
            return None
        sizes = self._param_sizes or []
        bufs = []
        for i, a in enumerate(args):
            sz = sizes[i] if i < len(sizes) else 8
            if isinstance(a, (bytes, bytearray, memoryview)):
                bufs.append(ctypes.create_string_buffer(bytes(a), max(sz, len(a))))
            else:
                bufs.append(ctypes.c_uint64(int(a)))
        return (ctypes.c_void_p * len(bufs))(
            *(ctypes.cast(ctypes.pointer(b), ctypes.c_void_p) for b in bufs)
        )

    def synchronize(self) -> None:
        """Wait for all pending GPU work."""
        _check(_cuda().cuCtxSynchronize())

    # ------------------------------------------------------------------
    def devmem_alloc(self, size: int) -> int:
        """Allocate ``size`` bytes of device memory, return pointer."""
        ptr = ctypes.c_void_p()
        _check(_cuda().cuMemAlloc(ctypes.byref(ptr), size))
        return ptr.value or 0

    def devmem_free(self, ptr: int) -> None:
        _check(_cuda().cuMemFree(ptr))

    def devmem_set(self, ptr: int, value: int, count: int) -> None:
        """Set ``count`` 32-bit values at ``ptr`` to ``value``."""
        _check(_cuda().cuMemsetD32(ptr, value, count))

    def device_read(self, ptr: int, size: int) -> bytearray:
        """Read ``size`` bytes from device memory."""
        buf = (ctypes.c_char * size)()
        _check(_cuda().cuMemcpyDtoH(buf, ptr, size))
        return bytearray(buf)

    def device_write(self, ptr: int, data: bytes) -> None:
        """Write bytes to device memory."""
        _check(
            _cuda().cuMemcpyHtoD(ptr, ctypes.c_char_p(data), len(data)))

    # ------------------------------------------------------------------
    # host-pinned memory + extra streams (live host<->device protocols,
    # e.g. the sassdbg breakpoint/patcher handshake)
    def hostmem_alloc(self, size: int) -> int:
        """Page-locked host memory; with UVA the same pointer is usable
        from kernels (LDG/STG)."""
        ptr = ctypes.c_void_p()
        _check(_cuda().cuMemAllocHost(ctypes.byref(ptr), size))
        return ptr.value or 0

    def hostmem_free(self, ptr: int) -> None:
        _check(_cuda().cuMemFreeHost(ctypes.c_void_p(ptr)))

    def managed_alloc(self, size: int) -> int:
        """Managed (unified) memory.  NOTE: unsupported on this setup —
        cuMemAllocManaged returns CUDA_ERROR_INVALID_CONTEXT (201) even with
        a current context, and plain cuMemAllocHost pinned memory FAULTS on
        device-side STG through the default cache descriptor (error 700).
        Host<->device protocols (sassdbg probe_patch) use device memory +
        cuMemcpy polling instead."""
        ptr = ctypes.c_void_p()
        _check(_cuda().cuMemAllocManaged(ctypes.byref(ptr), size, 1))
        return ptr.value or 0  # CU_MEM_ATTACH_GLOBAL

    def managed_free(self, ptr: int) -> None:
        _check(_cuda().cuMemFree(ctypes.c_void_p(ptr)))

    @staticmethod
    def host_read32(ptr: int) -> int:
        return ctypes.c_uint32.from_address(ptr).value

    @staticmethod
    def host_write32(ptr: int, value: int) -> None:
        ctypes.c_uint32.from_address(ptr).value = value

    @staticmethod
    def stream_create() -> int:
        """A non-default stream (for concurrent kernels)."""
        s = ctypes.c_void_p()
        _check(_cuda().cuStreamCreate(ctypes.byref(s), 1))  # NON_BLOCKING
        return s.value or 0

    @staticmethod
    def stream_destroy(stream: int) -> None:
        _check(_cuda().cuStreamDestroy(ctypes.c_void_p(stream)))

    @staticmethod
    def stream_query(stream: int) -> bool:
        """True when the stream has no pending work (non-blocking)."""
        err = _cuda().cuStreamQuery(ctypes.c_void_p(stream))
        if err == 0:
            return True
        if err == 600:                      # ERROR_NOT_READY
            return False
        _check(err)
        return False

    @staticmethod
    def stream_sync(stream: int) -> None:
        _check(_cuda().cuStreamSynchronize(ctypes.c_void_p(stream)))


def _pad3(t, default=1):
    if isinstance(t, int):
        return t, default, default
    if len(t) >= 3:
        return t[0], t[1], t[2]
    return t[0], t[1] if len(t) > 1 else default, default


def _extract_param_sizes(cubin: bytes) -> list[int] | None:
    """Per-parameter byte sizes from the cubin's EIATTR_KPARAM_INFO records.

    KPARAM items are 16 bytes: ``04 17 0c 00 00 00 00 00 00 <off4> <flags4>``
    with the payload's u32[1] = (offset<<16)|ordinal at byte +8 and u32[2]
    (size code ``(size << 2) | 1``, low 16 bits 0xf000) at byte +12.
    Returns a list indexed by parameter ordinal, or None if nothing parsed
    (e.g. a cubin we did not generate).
    """
    sizes = {}
    pat = b"\x04\x17\x0c\x00\x00\x00\x00\x00"   # 9-byte prefix; byte 9 is the
    i = 0                                        # param-index low byte (varies)
    while True:
        j = cubin.find(pat, i)
        if j < 0:
            break
        off = struct.unpack_from("<I", cubin, j + 8)[0]
        flags = struct.unpack_from("<I", cubin, j + 12)[0]
        if (flags & 0xf000) == 0xf000:
            ordinal = off & 0xffff
            size = ((flags >> 16) - 1) >> 2
            if 1 <= size <= (1 << 16):
                sizes[ordinal] = size
        i = j + 1
    if not sizes:
        return None
    return [sizes[o] for o in sorted(sizes)]
