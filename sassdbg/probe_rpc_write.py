import sys, struct, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from assembler import assemble, CudaModule

def probe_kernel():
    lines = ["#fn k(buf<8>) {",
             "    LDC.64 {R4, R5}, #param(buf);[0:7:{}:5:1]",
             "    S2R R1, SR_TID.X;[0:7:{}:5:1]",
             "    RPCMOV Rpc.LO, R1;[0:7:{0}:9:0]",
             "    RPCMOV R8, Rpc.LO;[0:7:{0}:9:0]",
             "    IMAD R4, R1, 0x4, R4;[7:7:{0}:5:1]"
             "    STG.E desc[{URZ,URZ}][{R4,R5}], R8;[7:7:{0}:2:0]"
             "    EXIT;[7:7:{}:5:0]",
             "}"]
    return assemble("\n".join(lines))

def run():
    cubin = probe_kernel()
    mod = CudaModule(cubin)
    d = mod.devmem_alloc(1024)
    mod.device_write(d, struct.pack("<256I", *[0] * 256))
    mod.launch("k", grid=(1,), block=(32,), args=[d])
    mod.synchronize()
    flag = struct.unpack("<32I", mod.device_read(d, 128))
    mod.devmem_free(d)
    print("OK")
    print(flag)

run()