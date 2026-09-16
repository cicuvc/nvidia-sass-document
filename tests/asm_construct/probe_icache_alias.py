#!/usr/bin/env python3
"""Distinguish physical-tag and virtual-tag GB202 ICC behavior with VMM aliases.

Sixteen physical code lines at 4 KiB spacing are mapped at two GPU virtual
addresses. The heap-resident code toggles its current alias after each pass,
so one kernel alternates A/B while executing identical physical lines.
A second run maps A/B to distinct physical allocations as a positive
32-tag/thrashing control.
"""

from __future__ import annotations

import argparse
import ctypes
import statistics
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import CudaModule, assemble, assemble_flat  # noqa: E402
from assembler import runner as cuda_runner  # noqa: E402
from assembler.runner import _check, _cuda  # noqa: E402


class CUmemLocation(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("id", ctypes.c_int)]


class AllocFlags(ctypes.Structure):
    _fields_ = [
        ("compressionType", ctypes.c_ubyte),
        ("gpuDirectRDMACapable", ctypes.c_ubyte),
        ("usage", ctypes.c_ushort),
        ("reserved", ctypes.c_ubyte * 4),
    ]


class CUmemAllocationProp(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("requestedHandleTypes", ctypes.c_int),
        ("location", CUmemLocation),
        ("win32HandleMetaData", ctypes.c_void_p),
        ("allocFlags", AllocFlags),
    ]


class CUmemAccessDesc(ctypes.Structure):
    _fields_ = [("location", CUmemLocation), ("flags", ctypes.c_uint)]


def words(source: str) -> bytes:
    return b"".join(struct.pack("<QQ", lo, hi)
                    for lo, hi in assemble_flat(source))


def ensure_v4_context() -> None:
    """CUDA 13 headers route cuCtxCreate to the four-argument v4 ABI.

    Use that ABI explicitly here: generic VMM mappings made in the legacy
    three-argument context created by runner.py are not device-accessible on
    this driver, even though legacy cuMemAlloc allocations are.
    """
    if 0 in cuda_runner._CTX:
        raise RuntimeError("VMM probe must create the process context first")
    lib = _cuda()
    _check(lib.cuInit(0))
    dev = ctypes.c_int()
    _check(lib.cuDeviceGet(ctypes.byref(dev), 0))
    lib.cuCtxCreate_v4.restype = ctypes.c_int
    lib.cuCtxCreate_v4.argtypes = [
        ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
        ctypes.c_uint, ctypes.c_int]
    ctx = ctypes.c_void_p()
    _check(lib.cuCtxCreate_v4(ctypes.byref(ctx), None, 0, dev.value))
    cuda_runner._CTX[0] = ctx
    # The repository runner binds the legacy unsuffixed allocation/copy
    # entry points. A v4 context requires the current 64-bit (_v2) APIs.
    lib.cuMemAlloc = lib.cuMemAlloc_v2
    lib.cuMemFree = lib.cuMemFree_v2
    lib.cuMemcpyHtoD = lib.cuMemcpyHtoD_v2
    lib.cuMemcpyDtoH = lib.cuMemcpyDtoH_v2
    lib.cuMemAlloc.restype = lib.cuMemFree.restype = ctypes.c_int
    lib.cuMemcpyHtoD.restype = lib.cuMemcpyDtoH.restype = ctypes.c_int
    lib.cuMemAlloc.argtypes = [
        ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t]
    lib.cuMemFree.argtypes = [ctypes.c_ulonglong]
    lib.cuMemcpyHtoD.argtypes = [
        ctypes.c_ulonglong, ctypes.c_void_p, ctypes.c_size_t]
    lib.cuMemcpyDtoH.argtypes = [
        ctypes.c_void_p, ctypes.c_ulonglong, ctypes.c_size_t]


def launcher(iterations: int) -> str:
    return f"""#fn icalias(out<8>, alias_a<8>, alias_b<8>) {{
    #pragma MAXREG_COUNT(32)
    LDC.64 {{R2,R3}}, #param(out);[1:7:{{}}:1:0]
    LDC.64 {{R14,R15}}, #param(alias_a);[2:7:{{}}:1:0]
    LDC.64 {{R16,R17}}, #param(alias_b);[3:7:{{}}:1:0]
    MOV32I R10, 0x{iterations:x};[7:7:{{}}:5:1]
    LOP3.LUT R18, R14, R16, RZ, 0x96;[7:7:{{2,3}}:5:1]
    LOP3.LUT R19, R15, R17, RZ, 0x96;[7:7:{{}}:5:1]
    LEPC {{R12,R13}}, #label(return);[7:7:{{}}:5:1]
    CS2R {{R20,R21}}, SR_CLOCKLO;[7:7:{{}}:5:0]
    CALL.ABS.NOINC {{R14,R15}};[7:7:{{}}:8:1]
    #def_label(return)
    CS2R {{R22,R23}}, SR_CLOCKLO;[7:7:{{}}:5:0]
""" + "    NOP;[7:7:{}:1:1]\n" * 16 + """    STG.E.64.STRONG.GPU [{R2,R3}], {R20,R21};[7:1:{1}:8:0]
    STG.E.64.STRONG.GPU [{R2,R3}+8], {R22,R23};[7:1:{}:8:0]
    EXIT;[7:7:{}:5:0]
}"""


def install(mod: CudaModule, address: int) -> None:
    # line 0 is control/return; lines 1--15 are 4 KiB apart.
    first = words("""    IADD3 R10, R10, -0x1, RZ;[7:7:{}:5:1]
    ISETP.NE.AND P0, PT, R10, RZ, PT;[7:7:{}:13:1]
    @P0 JMX {R14,R15}, 0x1000;[7:7:{}:6:0]
    RET.ABS.NODEC {R12,R13}, 0x0;[7:7:{}:8:1]
""")
    mod.device_write(address, first)
    for i in range(1, 15):
        mod.device_write(address + i * 0x1000,
                         words(f"JMX {{R14,R15}}, 0x{(i + 1) * 0x1000:x};"
                               "[7:7:{}:6:0]"))
    mod.device_write(address + 15 * 0x1000, words("""    LOP3.LUT R14, R14, R18, RZ, 0x96;[7:7:{}:5:1]
    LOP3.LUT R15, R15, R19, RZ, 0x96;[7:7:{}:5:1]
    JMX {R14,R15}, 0x0;[7:7:{}:6:0]
"""))


class Vmm:
    def __init__(self, same_physical: bool):
        lib = _cuda()
        for name in (
            "cuMemGetAllocationGranularity", "cuMemCreate",
            "cuMemAddressReserve", "cuMemMap", "cuMemSetAccess",
            "cuMemUnmap", "cuMemAddressFree", "cuMemRelease",
        ):
            getattr(lib, name).restype = ctypes.c_int
        lib.cuMemGetAllocationGranularity.argtypes = [
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(CUmemAllocationProp), ctypes.c_int]
        lib.cuMemCreate.argtypes = [
            ctypes.POINTER(ctypes.c_ulonglong), ctypes.c_size_t,
            ctypes.POINTER(CUmemAllocationProp), ctypes.c_ulonglong]
        lib.cuMemAddressReserve.argtypes = [
            ctypes.POINTER(ctypes.c_ulonglong), ctypes.c_size_t,
            ctypes.c_size_t, ctypes.c_ulonglong, ctypes.c_ulonglong]
        lib.cuMemMap.argtypes = [
            ctypes.c_ulonglong, ctypes.c_size_t, ctypes.c_size_t,
            ctypes.c_ulonglong, ctypes.c_ulonglong]
        lib.cuMemSetAccess.argtypes = [
            ctypes.c_ulonglong, ctypes.c_size_t,
            ctypes.POINTER(CUmemAccessDesc), ctypes.c_size_t]
        lib.cuMemUnmap.argtypes = [ctypes.c_ulonglong, ctypes.c_size_t]
        lib.cuMemAddressFree.argtypes = [ctypes.c_ulonglong, ctypes.c_size_t]
        lib.cuMemRelease.argtypes = [ctypes.c_ulonglong]
        # runner.py intentionally leaves most driver prototypes implicit;
        # VMM addresses require an explicit 64-bit destination type.
        lib.cuMemcpyHtoD.argtypes = [
            ctypes.c_ulonglong, ctypes.c_void_p, ctypes.c_size_t]
        prop = CUmemAllocationProp(
            type=1, requestedHandleTypes=0,
            location=CUmemLocation(1, 0),
            win32HandleMetaData=None, allocFlags=AllocFlags())
        gran = ctypes.c_size_t()
        _check(lib.cuMemGetAllocationGranularity(
            ctypes.byref(gran), ctypes.byref(prop), 0))
        self.size = max(gran.value, 2 << 20)
        handles = []
        nhandles = 1 if same_physical else 2
        for _ in range(nhandles):
            handle = ctypes.c_ulonglong()
            _check(lib.cuMemCreate(ctypes.byref(handle), self.size,
                                   ctypes.byref(prop), 0))
            handles.append(handle.value)
        self.handles = handles
        self.addrs = []
        access = CUmemAccessDesc(CUmemLocation(1, 0), 3)
        for i in range(2):
            ptr = ctypes.c_ulonglong()
            _check(lib.cuMemAddressReserve(
                ctypes.byref(ptr), self.size, 0, 0, 0))
            _check(lib.cuMemMap(ptr.value, self.size, 0,
                                handles[0 if same_physical else i], 0))
            _check(lib.cuMemSetAccess(ptr.value, self.size,
                                      ctypes.byref(access), 1))
            self.addrs.append(ptr.value)

    def close(self) -> None:
        lib = _cuda()
        for address in self.addrs:
            _check(lib.cuMemUnmap(address, self.size))
            _check(lib.cuMemAddressFree(address, self.size))
        for handle in self.handles:
            _check(lib.cuMemRelease(handle))


def measure(mod: CudaModule, out: int, a: int, b: int,
            iterations: int, reps: int = 5) -> float:
    samples = []
    for rep in range(reps + 1):
        mod.launch("icalias", grid=(1,), block=(32,), args=[out, a, b])
        mod.synchronize()
        if rep:
            t0, t1 = struct.unpack("<QQ", mod.device_read(out, 16))
            samples.append((t1 - t0) & ((1 << 64) - 1))
    visits = iterations + 15 * (iterations - 1)
    return statistics.median(samples) / visits


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("single", "same", "different"))
    ns = p.parse_args()
    iterations = 4096
    ensure_v4_context()
    mod = CudaModule(assemble(launcher(iterations), check_deps=True))
    out = mod.devmem_alloc(16)
    try:
        experiments = {
            "single": ("single_alias", True),
            "same": ("same_physical", True),
            "different": ("different_physical", False),
        }
        label, same = experiments[ns.mode]
        mapping = Vmm(same)
        try:
            a, b = mapping.addrs
            install(mod, a)
            if not same:
                install(mod, b)
            value = measure(mod, out, a,
                            a if ns.mode == "single" else b,
                            iterations)
            print(f"{label} alias_a=0x{a:x} alias_b=0x{b:x} "
                  f"cycles_per_visit={value:.6f}")
        finally:
            mapping.close()
    finally:
        mod.devmem_free(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
