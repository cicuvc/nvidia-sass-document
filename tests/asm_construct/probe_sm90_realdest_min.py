#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from assembler import CudaModule, assemble

case = sys.argv[1] if len(sys.argv) > 1 else "one"
bodies = {
    "one": "    FFMA R28, R24, R25, 0f3f800000;[7:7:{}:1:0]",
    "two": "    FFMA R28, R24, R25, 0f3f800000;[7:7:{}:1:0]\n    FFMA R29, R24, R25, 0f3f800000;[7:7:{}:1:0]",
    "waw": "    FFMA R28, R24, R25, 0f3f800000;[7:7:{}:1:0]\n    FFMA R28, R24, R25, 0f3f800000;[7:7:{}:1:0]",
    "rz": "    FFMA RZ, R24, R25, 0f3f800000;[7:7:{}:1:0]",
    "r36": "    FFMA R36, R24, R25, 0f3f800000;[7:7:{}:1:0]",
    "r37": "    FFMA R37, R24, R25, 0f3f800000;[7:7:{}:1:0]",
    "r38": "    FFMA R38, R24, R25, 0f3f800000;[7:7:{}:1:0]",
    "r39": "    FFMA R39, R24, R25, 0f3f800000;[7:7:{}:1:0]",
    "read": "    FFMA R28, R24, R25, 0f3f800000;[7:7:{}:1:0]\n    FFMA R29, R28, R25, 0f3f800000;[7:7:{}:1:0]",
}
src = "\n".join([
    "#fn t(out<8>) {",
    "    #pragma MAXREG_COUNT(40)",
    "    MOV R24, 0x3f803c00;[7:7:{}:5:1]",
    "    MOV R25, 0x40003c00;[7:7:{}:5:1]",
    bodies[case],
    "    EXIT;[7:7:{}:5:0]",
    "}"])
mod = CudaModule(assemble(src, arch="sm90", check_deps=False))
out = mod.devmem_alloc(64)
mod.launch("t", grid=(1,), block=(32,), args=[out])
mod.synchronize()
print(case, "OK")
