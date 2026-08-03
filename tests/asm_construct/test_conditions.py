import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from assembler import assemble_flat
from assembler.sass_matcher import MatchError
from assembler.sass_encoder import EncodeError

# Negative tests: CONDITIONS predicates must reject illegal encodings at
# assembly time (the GPU used to fault at runtime instead). Each case is a
# hand-written SASS line that violates a spec CONDITIONS block.

CASES = [
    # (code, expected error fragment, description)
    ("LEA.HI.X R2, P0, ~R0, ~R1, RZ, 0x1, P1;[7:7:{}:5:1]",
     "ILLEGAL_INSTR_ENCODING_ERROR", "LEA.HI.X both ~Ra+~Rb (invert exclusivity)"),
    ("LEA.HI R2, P0, -R0, -R1, R3, 0x4;[7:7:{}:5:1]",
     "ILLEGAL_INSTR_ENCODING_ERROR", "LEA.HI both -Ra+-Rb (negate exclusivity)"),
     ("IMAD.WIDE {R3,R4}, PT, R0, R1, {R5,R6};[7:7:{}:5:1]",
      "MISALIGNED_REG_ERROR", "IMAD.WIDE odd Rd (64-bit pair alignment)"),
    ("IMAD R3, R254, R1, R2;[7:7:{}:5:1]",
     "OOR_REG_ERROR", "R254 as source"),
    ("IMAD R3, R0, R1, R254;[7:7:{}:5:1]",
     "OOR_REG_ERROR", "R254 as Rc"),
    ("IMAD R3, R0, R1, R2;[7:7:{}:15:0]",
     "ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR", "usched=31 invalid opex"),
    ("P2R R2, PR, RZ, 0x7f;[7:7:{1}:15:0]",
     "ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR", "P2R usched=31 invalid opex"),
    ("P2R R2, PR, RZ, 0x7f;[7:7:{1}:12:0]",
     "ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR", "P2R usched=28 invalid opex"),
     # 64-bit dest pair must be even-aligned (2x:2x+1).  IMAD.WIDE's Rd/Rc are
     # 64-bit pairs; explicit groups are required (single R3 hits the group
     # check), and RZ as a 64-bit operand is also rejected.
     ("IMAD.WIDE {R3,R4}, PT, R0, R1, {R5,R6};[7:7:{}:5:1]",
      "MISALIGNED_REG_ERROR", "IMAD.WIDE odd Rd (64-bit pair)"),
     ("LDG.E.64 {R3,R4}, desc[{UR4,UR5}][{R6,R7}];[7:7:{}:5:1]",
      "MISALIGNED_REG_ERROR", "LDG.E.64 odd Rd (64-bit pair)"),
     # 64-bit source operand pair
     ("IMAD.WIDE {R2,R3}, PT, R0, R1, {R3,R4};[7:7:{}:5:1]",
      "MISALIGNED_REG_ERROR", "IMAD.WIDE odd Rc (64-bit addend pair)"),
     # 128-bit dest quad must be 4-aligned (4x:4x+3).  Single-register forms
     # hit the group-size check ("list every register explicitly") first, so
     # use explicit quads to exercise the alignment condition.
     ("LDG.E.128 {R2,R3,R4,R5}, desc[{UR4,UR5}][{R6,R7}];[7:7:{}:5:1]",
      "MISALIGNED_REG_ERROR", "LDG.E.128 Rd=2 (needs 4-alignment)"),
     ("LDG.E.128 {R3,R4,R5,R6}, desc[{UR4,UR5}][{R6,R7}];[7:7:{}:5:1]",
      "MISALIGNED_REG_ERROR", "LDG.E.128 Rd=3 (odd, needs 4-alignment)"),
]

ok = True
for code, fragment, desc in CASES:
    try:
        assemble_flat(code)
        print(f"FAIL  {desc}: assembled despite condition (expected '{fragment}')")
        ok = False
    except (MatchError, EncodeError) as e:
        if fragment in str(e):
            print(f"OK    {desc}: rejected -> {str(e)[-70:]}")
        else:
            print(f"FAIL  {desc}: rejected with wrong error -> {str(e)[-70:]}")
            ok = False
    except Exception as e:
        print(f"FAIL  {desc}: unexpected error -> {str(e)[-70:]}")
        ok = False

print()
print(f"=== {'ALL OK' if ok else 'SOME FAILED'} ===")
sys.exit(0 if ok else 1)
