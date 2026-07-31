import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble, CudaModule
import struct

cubin = assemble('''
#fn carry_test(out<32>) {
    LDCU.64 UR4, c[0x0][0x358];[0:7:{}:1:0]
    LDC.64 R6, #param(out);[0:7:{}:1:0]

    MOV32I R0, 0xFFFFFFFF;[7:7:{}:1:0]
    MOV32I R1, 0xFFFFFFFF;[7:7:{}:1:0]
    MOV32I R2, 0xFFFFFFFF;[7:7:{}:4:1]

    IADD3 R3, P0, P1, R0, R1, R2;[7:7:{}:5:0]
    IADD3.X R3, P0, P1, R0, R1, R2, P0, P1;[7:7:{}:5:0]
    STG.E desc[UR4][R6.64], R3;[7:1:{0}:1:0]

    P2R R3, PR, RZ, 0x7f;[7:7:{1}:1:0]
    STG.E desc[UR4][R6.64+0x4], R3;[7:1:{}:1:0]

    P2R.B1 R5, PR, RZ, 0x7f;[7:7:{1}:5:1]
    STG.E desc[UR4][R6.64+0x8], R5;[7:1:{}:1:0]

    P2R.B2 R5, PR, RZ, 0x7f;[7:7:{1}:5:1]
    STG.E desc[UR4][R6.64+0xC], R5;[7:1:{}:1:0]

    P2R.B3 R5, PR, RZ, 0x7f;[7:7:{1}:5:1]
    STG.E desc[UR4][R6.64+0x10], R5;[7:1:{}:1:0]

    EXIT;[7:7:{}:5:0]
}
''')

Path('x.cubin').write_bytes(cubin)

mod = CudaModule(cubin)
d = mod.devmem_alloc(20)
mod.launch("carry_test", grid=1, block=1, args=[d])
mod.synchronize()
vals = struct.unpack("<5I", mod.device_read(d, 20))

print(f"d[0] = 0x{vals[0]:08x}")
print(f"d[1] = 0x{vals[1]:032b}")
print(f"d[2] = 0x{vals[2]:032b}")
print(f"d[3] = 0x{vals[3]:032b}")
print(f"d[4] = 0x{vals[4]:032b}")

mod.devmem_free(d)