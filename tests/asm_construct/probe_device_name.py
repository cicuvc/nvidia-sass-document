#!/usr/bin/env python3
"""Print CUDA device name + compute capability."""

import ctypes

cuda = ctypes.CDLL("libcuda.so.1")
cuda.cuInit(0)
dev = ctypes.c_int()
cuda.cuDeviceGet(ctypes.byref(dev), 0)
buf = ctypes.create_string_buffer(128)
cuda.cuDeviceGetName(buf, 128, dev)
major, minor = ctypes.c_int(), ctypes.c_int()
cuda.cuDeviceGetAttribute(ctypes.byref(major), 75, dev)
cuda.cuDeviceGetAttribute(ctypes.byref(minor), 76, dev)
sms = ctypes.c_int()
cuda.cuDeviceGetAttribute(ctypes.byref(sms), 16, dev)
print(f"device={buf.value.decode()} sm={major.value}{minor.value} "
      f"SMs={sms.value}")
