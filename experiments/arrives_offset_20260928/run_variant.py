#!/usr/bin/env python3
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from assembler import CudaModule

if len(sys.argv) != 4:
    raise SystemExit("usage: run_variant.py NAME TASKS ITERS")
name, tasks, iters = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
n = 256 * tasks * iters
mod = CudaModule((Path(__file__).parent / f"{name}.cubin").read_bytes())
inp = mod.devmem_alloc(n * 4)
out = mod.devmem_alloc(n * 4)
want = list(range(n))
mod.device_write(inp, struct.pack(f"<{n}I", *want))
mod.devmem_set(out, 0xFFFFFFFF, n)
mod.launch("_Z6kernelPiS_ii", grid=(1,), block=(384,),
           args=[inp, out, tasks, iters], shared_mem=16384)
mod.synchronize()
got = struct.unpack(f"<{n}I", mod.device_read(out, n * 4))
bad = [i for i, (a, b) in enumerate(zip(want, got)) if a != b]
print(f"{'PASS' if not bad else 'FAIL'} variant={name} tasks={tasks} "
      f"iters={iters} bad={bad[:8]}")
raise SystemExit(0 if not bad else 1)
