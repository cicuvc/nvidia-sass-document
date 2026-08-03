# sass-dec

Reverse-engineering the **NVIDIA Hopper (sm_90)** and **Blackwell (sm_100)** SASS
instruction sets from `nvdisasm`-dumped ISA description files. The goal is to
reconstruct how SASS instructions decode — encoding bit layout, functional-unit
grouping, scoreboard/latency behavior — and to write per-instruction reference
docs for every compute instruction, including microarchitecture-level analysis of
the pipeline, memory model, tensor cores, and control flow.

There is no build system: this is a *reading and interpreting* project on top of
raw ISA dumps, supported by Python extractors, per-instruction decoders, CUDA
test kernels, and research notes spanning instruction semantics and
microarchitectural speculation.

## Layout

| Path | What it is |
| --- | --- |
| `sm_90_instructions.txt` | Hopper full instruction/encoding spec (~159k lines). Grep-first; never read whole. |
| `sm_90_latencies.txt` | Hopper pipe grouping + scoreboard/latency tables (~441 lines). |
| `sm100_instructions.txt` | Blackwell full instruction/encoding spec. |
| `sm100_latencies.txt` | Blackwell pipe grouping + scoreboard/latency tables. |
| `sm_75_instructions.txt`, `sm_80_instructions.txt` | Older-arch dumps for cross-arch comparison. |
| `tools/` | stdlib-only extractors + query CLIs + per-instruction decoders (sm_90 and sm100) + bit-accurate MMA model (`hmma_model.py`). |
| `assembler/` | Hand-written SASS → cubin toolchain (sm_120) + CTypes GPU runner + scoreboard dependency checker. See `ASSEMBLER_MANUAL.md`. |
| `ASSEMBLER_MANUAL.md` | Full assembler syntax, features, and usage notes. |
| `notes/sm90/instr/` | Per-instruction reference docs for sm_90 (168 instructions). |
| `notes/sm90/arch/` | Cross-cutting microarchitecture notes for sm_90 (26 topics). |
| `notes/sm100/instr/` | Per-instruction reference docs for sm100 (20 instructions). |
| `notes/sm100/arch/` | Cross-cutting microarchitecture notes for sm100 (4 topics). |
| `notes/sm100/OVERVIEW.md` | Summary of sm_90 → sm100 encoding/capability changes. |
| `tests/` | CUDA (`.cu`) kernels that force specific SASS encodings and probe microarch behavior (177 files), plus `tests/asm_construct/` assembler round-trip + GPU tests (87 `.py` files). |
| `TODO.md` | Master checklist of sm_90 instructions to document (197/207 done). |
| `ref_memo.txt` | Curated sm_70..sm_90 opcode roster (source of the checklist). |
| `sm90.json`, `sm100.json` | Generated queryable DBs (~21 MB each, gitignored/regenerable). |

## Tooling

The specs are parsed into queryable JSON DBs — prefer them over ad-hoc `grep`.

```bash
# Parse both .txt files -> sm90.json (has a built-in validation gate)
python3 tools/parse_sm90.py

# Query the DB (sm90)
python3 tools/query_sm90.py mnem <NAME>       # variants, opcodes, format, pipe
python3 tools/query_sm90.py class <name> -v   # full CLASS block
python3 tools/query_sm90.py layout <class>    # 128-bit field map
python3 tools/query_sm90.py opcode <hex|0b|int>
python3 tools/query_sm90.py enum <Name>       # modifier value map
python3 tools/query_sm90.py table <Name>      # decode table
python3 tools/query_sm90.py pipe <MNEMONIC>   # functional-unit membership
python3 tools/query_sm90.py stats

# Same interface for sm100
python3 tools/parse_sm100.py
python3 tools/query_sm100.py mnem <NAME>
python3 tools/query_sm100.py pipe <MNEMONIC>
# ... same subcommands as query_sm90.py
```

`tools/decode_<mnem>.py` are minimal per-instruction decoders: they extract
fields from a 128-bit encoding (lo64 + hi64) and reconstruct the SASS assembly,
validated against real cuobjdump vectors.  `tools/hmma_model.py` is a
bit-accurate FDA (Fused-Dot-Add) reference model of the tensor-core
fp16/bf16/fp8 HMMA/QMMA path.

### Assembler (`assembler/`) and running tests

SASS-by-hand kernels are assembled to cubin and run on a GPU without nvcc:

```python
from assembler import assemble, CudaModule
mod = CudaModule(assemble("#fn k(out<2048>) { ... }"))
d = mod.devmem_alloc(2048 * 4)
mod.launch("k", grid=(1,), block=(32,), args=[d])
mod.synchronize()
out = mod.device_read(d, 128)
```

- `assemble(source)` / `assemble_kernel(source)` (→ `AssembleResult`) /
  `assemble_flat(source)` (→ list of `(lo64, hi64)`).
- `CudaModule(cubin)`: `launch`, `devmem_alloc/free`, `device_read/write`,
  `device_name`.  Scoreboard dependency checking is on by default
  (`check_deps` / `strict_deps`).
- Full syntax + gotchas: **`ASSEMBLER_MANUAL.md`** (explicit register groups,
  scheduling brackets, `#fn`/`#param`/`#spec_const`, MMA result-wait rules).

Run the assembler/GPU test suite:

```bash
python3 tools/run_tests.py [-j N]      # parallel processes; timing/descriptor tests serial
```

## Key facts about the ISA (sm_90 and sm100)

- Each SASS instruction is **128 bits / 16 bytes** = hi64 `[127:64]` + lo64 `[63:0]`.
  (The file header says `WORD_SIZE 64` — ignore it; trust the 128-bit width.)
- Opcode is a **13-bit** field: `{bit[91], bits[11:0]}`.
- Registers: 8-bit GPR (`0xFF` = `RZ`), 6-bit uniform (`UR0`–`UR63`).
- Predicates: 3-bit (`PT` = 7) plus a 1-bit negate flag.
- Field names encode bit position: `BITS_<width>_<hi>_<lo>_<name>` (MSB:LSB).
- The **control/scheduling word** (`FUNIT uC` bit map) is identical between sm_90
  and sm100 — 565 named control fields at the same bit positions.
- sm100 adds `ttu_pipe` (ray-tracing/tree-traversal), drops `OPTIONAL_GSB`
  (warpgroup scoreboard), and collapses `uldc_*` classes into `LDCU`.

## Status

### sm_90 (Hopper)
| Metric | Count |
| --- | ---: |
| Instructions in scope (compute) | 207 |
| Instructions documented | 197 |
| Remaining | 5 (F2FP, RTT, QSPC, UCGABAR_GET, UCGABAR_SET) |
| Special (pending resolution) | 1 (LDCU — likely LDC variant) |
| Per-instruction notes | 168 (some consolidated: e.g. HADD2/HADD2_F32, DADD/DADD_F64) |
| Cross-cutting arch notes | 26 |
| Decoder scripts | 109 |
| Test kernels | 177 (`.cu`) + 87 assembler/GPU tests (`tests/asm_construct/test_*.py`) |

### sm100 (Blackwell)
| Metric | Count |
| --- | ---: |
| Mnemonics in spec | 261 (vs. 238 on sm_90) |
| New mnemonics | 34 added, 11 removed |
| Per-instruction notes | 20 |
| Cross-cutting arch notes | 4 |
| Overview/change-analysis | 1 (`notes/sm100/OVERVIEW.md`) |

### Major microarchitecture topics (notes/sm*/arch/)

**sm_90:** control codes and scoreboards, memory model (including L2 NUMA on H800)
, tensor-core microarch speculation (HMMA pipeline, wgmma), CUDA memory order,
TMA/mbarrier pipeline, CBU convergence-barrier state, LSU/MIO structure, 
LDC addressing modes/preset layouts, asynchronous proxy, DIV workaround, 
shared memory and l1 bank conflicts (vectorized & cp.async), encoding classification,
usched latency, cubin/ELF structure.

**sm100:** tcgen05  (tensor-core operand representation), tcgen05 microarch 
speculation (how `UTC*` instructions replace wgmma), work-stealing support 
and minor changes (eg. `redux`, `ffma2`, `st.bulk` ...)

Progress is tracked in `TODO.md`.

See `AGENTS.md` for the full spec-layout guide and the per-instruction
documentation recipe.
