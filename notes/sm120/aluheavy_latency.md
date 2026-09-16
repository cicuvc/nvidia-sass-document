# GB202 ALU-Heavy pipeline latency

Silicon: RTX 5090 (GB202, sm_120), 2026-09-16.  Reproducer:
[`probe_aluheavy_latency.py`](../../tests/asm_construct/probe_aluheavy_latency.py).

```bash
python3 tests/asm_construct/probe_aluheavy_latency.py --reps 3
python3 tests/asm_construct/probe_aluheavy_latency.py --isolated \
    --gaps 1,2,3,4,5,6,7,8 --reps 3
```

## Covered instruction set

The probe covers the complete measured ALU-Heavy catalog:

```text
BMSK F2FP F2IP I2FP I2I I2IP IABS IADD3 ISCADD ISCADD32I
LEA LOP LOP3 LOP32I P2R PLOP3 PRMT PSETP R2P SGXT SHF SHL SHR
HMNMX2 HSET2 HSETP2
```

The main sweep puts every gap in one kernel.  Representative members of every
result class were re-run with `--isolated`, one module per gap, to remove PC,
fetch-block, and preceding-instance phase effects.  As in the ALU-Lite probe,
fine means many stall-1 NOPs and coarse means a few NOPs carrying larger stall
counts.  Values below are nominal producer-to-consumer issue gaps.

## GPR result matrix

### ALU-Heavy consumer

Every tested GPR-producing ALU-Heavy instruction is visible to an `IADD3`
consumer at **gap 2**, in both fine and coarse layouts.  Gap 1 is stale or
undefined.  This is the uniform same-leaf bypass event:

```text
ALU Heavy execute -> ALU Heavy local bypass: ready = issue + 2
```

This includes conversions, `P2R`, packed-half compare/minmax, permute, funnel
shift, and scaled-address operations; their different arithmetic functions do
not change the same-leaf result-ready point.

### ALU-Lite consumer

| ready boundary | producers |
|---|---|
| **2** | `IABS`, `I2I`, `I2IP` |
| 3 fine / **4 safe coarse** | `BMSK`, `F2FP`, `F2IP`, `I2FP`, `IADD3`, `ISCADD`, `ISCADD32I`, `LEA`, `LOP`, `LOP3`, `LOP32I`, `P2R`, `PRMT`, `SGXT`, `SHF`, `SHL`, `SHR`, `HMNMX2`, `HSET2` |

Thus the ALU-Heavy-to-ALU-Lite crossing normally adds a routing/collection
stage.  Three simple narrow/unary result classes reach the ALU-Lite consumer
through an earlier path.

### FMA-Lite consumer

| ready boundary | producers |
|---|---|
| **2** | `IADD3`, `LOP`, `LOP3`, `PRMT`, `SHL`, `SGXT`, `HMNMX2`, `HSET2` |
| 3 fine / **4 safe coarse** | `BMSK`, `F2FP`, `F2IP`, `I2FP`, `I2I`, `I2IP`, `IABS`, `ISCADD`, `ISCADD32I`, `LEA`, `LOP32I`, `P2R`, `SHF`, `SHR` |

`FADD Rd, producer_result, RZ` is the detector.  It preserves even the narrow
integer results used by `F2IP/I2I/I2IP` in this configuration, so these rows
are value-observed rather than inferred from timing.

The split is not explained by the architectural result width: every entry
writes one 32-bit GPR.  It requires either multiple result-formation subpaths
inside ALU Heavy or producer-tag-dependent steering through the cross-leaf
bypass network.  A simulator should model the two producer classes rather
than assign one ALU-Heavy-to-FMA-Lite latency.

The isolated `IADD3 -> FADD` boundary of 2 supersedes the older combined-gap
survey's apparent boundary of 3.  Re-running that older harness with one gap
per module also produces 2 (and likewise changes `FADD -> IADD3` from 3 to 2).
Thus the old extra "cross-pipe cycle" was an instruction-position/issue-group
phase effect, not intrinsic transport latency.

## Predicate result matrix

The tested predicate producers are:

- `IADD3.Pu` carry;
- `PSETP` and `PLOP3`;
- `R2P` whole-predicate-file update;
- packed-half `HSETP2`.

| consumer | arithmetic predicate producers (`IADD3.Pu/PSETP/PLOP3/HSETP2`) | `R2P` |
|---|---:|---:|
| ALU-Lite selector (`SEL ..., P0`) | 3 fine / **4 coarse** | 3 fine / **4 coarse** |
| `P2R` predicate-file read | **2** | 3 fine / **4 coarse** |
| instruction guard | 7 fine / **12 coarse** | 7 fine / **12 coarse** |
| CBU branch | 7 fine / **12 coarse** | 7 fine / **12 coarse** |

This adds an important distinction to the ALU-Lite result:

- a predicate computed by ALU Heavy can loop directly into the ALU-Heavy
  `P2R` path at gap 2;
- `R2P` is a file/merge update rather than an arithmetic predicate result and
  does not use that loopback;
- selector consumption still crosses to ALU Lite and needs the 3/4 path;
- effective predication and CBU distribution remain the same slow 7/12 path
  seen for ALU-Lite predicate producers.

Hence predicate-file read visibility and effective instruction predication
are separate microarchitectural events.

## Relationship to the static latency tables

The static `TABLE_TRUE(GPR)` row for `FXU_WITHOUT_DUALALU` gives 6 for the
ordinary FXU, DUALALU, FMAI, IMAD and FP16 consumer columns.  Silicon instead
shows stable consumer-specific boundaries of 2 or 3/4.

`HMNMX2/HSET2/HSETP2` are dynamically ALU Heavy but remain members of the
static `FP16_OPS` latency class; their table row is therefore a separate
conservative classification.  Their measured bypass events nevertheless
join the ALU-Heavy classes above.

For predicate results, the non-DUAL FXU row gives 5 to ordinary math
predicate readers and 13 to branch/non-math readers.  The measured local paths
are again earlier (2 or 3/4), while the coarse guard/branch boundary of 12 is
close to the conservative 13.

The table should therefore remain scheduling metadata, not the execution
pipeline itself.

## Initial simulator model

```text
issue / operand collection
        |
        +-- ALU-Heavy internal operation
        |       |
        |       +-- same-leaf GPR bypass ---------------- ready t+2
        |       +-- producer-class cross-leaf bypass
        |       |       ALU-Lite/FMA-Lite fast class ---- ready t+2
        |       |       normal crossing ----------------- ready t+4 safe
        |       +-- arithmetic predicate -> P2R loopback  ready t+2
        |       `-- predicate -> ALU-Lite selector ------- ready t+4 safe
        |
        `-- effective predicate / CBU distribution ------- ready t+12 coarse
```

These are RAW consumer-visible events.  They do not yet locate final GPR
parity-bank commit, predicate-file physical write, or result-queue release.
Those must remain separate from bypass readiness in the cycle model.
