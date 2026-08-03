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
                  programmatic_serialization: bool = False) -> None:
        """Launch a kernel through ``cuLaunchKernelEx``.

        ``programmatic_serialization`` sets
        ``CU_LAUNCH_ATTRIBUTE_PROGRAMMATIC_STREAM_SERIALIZATION`` (PDL):
        the kernel may overlap with the previous kernel on the same stream,
        resolving its stream dependency programmatically via
        ``griddepcontrol`` (SASS ACQBULK / PREEXIT).
        """
        f = self.func(func_name)
        raw_args = self._kernel_param_array(args)
        gx, gy, gz = _pad3(grid)
        bx, by, bz = _pad3(block)

        attrs = None
        num_attrs = 0
        if programmatic_serialization:
            # CU_LAUNCH_ATTRIBUTE_PROGRAMMATIC_STREAM_SERIALIZATION == 6
            # (CUDA 12/13 driver); value is a 64-byte union, first member an int.
            class AttrVal(ctypes.Union):
                _fields_ = [("pad", ctypes.c_ubyte * 64)]

            class LaunchAttr(ctypes.Structure):
                _fields_ = [("id", ctypes.c_int),
                            ("pad", ctypes.c_ubyte * 4),
                            ("value", AttrVal)]

            attr = LaunchAttr()
            attr.id = 6
            ctypes.memset(ctypes.byref(attr.value), 0,
                          ctypes.sizeof(attr.value))
            ctypes.cast(ctypes.pointer(attr.value),
                        ctypes.POINTER(ctypes.c_int))[0] = 1
            attrs = ctypes.cast(ctypes.pointer(attr),
                                ctypes.POINTER(LaunchAttr))

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
                               ctypes.c_void_p(stream), attrs, 1)
            _check(_cuda().cuLaunchKernelEx(
                ctypes.byref(cfg), f, raw_args, None))
            return

        self.launch(func_name, grid=grid, block=block, args=args,
                    shared_mem=shared_mem, stream=stream)

    @staticmethod
    def _kernel_param_array(args):
        """kernelParams convention: array of pointers to uint64 arg slots."""
        if not args:
            return None
        arg_bufs = [ctypes.c_uint64(a) for a in args]
        return (ctypes.c_void_p * len(args))(
            *(ctypes.cast(ctypes.pointer(b), ctypes.c_void_p)
              for b in arg_bufs)
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


def _pad3(t, default=1):
    if isinstance(t, int):
        return t, default, default
    if len(t) >= 3:
        return t[0], t[1], t[2]
    return t[0], t[1] if len(t) > 1 else default, default
