# Assembler sm90 port — hardcode audit & arch management

Status of making `assembler/` target both sm90 (Hopper/H800) and sm120
(Blackwell).  `assembler/arch.py` now holds the per-arch config; `arch=`
selects it per call (process default sm120).  This note audits every
hardcode touched or reviewed.

## Per-arch config (`assembler/arch.py`)
| | sm90 | sm120 |
|---|---|---|
| ISA db | `sm90.json` | `sm120.json` |
| `SLOT_DEFAULT_CDESC` (`#spec_const`) | c[0x0][0x208] | c[0x0][0x358] |
| kernel param base | 0x210 | 0x380 |
| `PARAM_CBANK` EIATTR + `.nv.constant0` size | 0x210 | 0x380 |

## Fixed hardcodes (audit)
1. `sm120.json` db path — `__init__.py`, `sass_matcher.create_matcher`,
   `sass_asm.py` CLI (`--arch`) → `arch.db_path()`.
2. `SPEC_CONST_MAP` c[0x0][0x358] (`sass_parser.py`) → `arch.spec_const_map()`.
3. Kernel param base 0x380 — `operand.KernelDecl.param_base` (default_factory
   from arch) and `__init__` result params → `arch.current().param_base`.
4. `PARAM_CBANK` EIATTR 0x380 (`sass_elf.py`, EIATTR 0x0a) → arch param base.
5. `.nv.constant0` size base 0x380 (`sass_elf.py`) → arch param base.
6. `ConditionEvaluator` lacked ternary `?:` — sm90 size predicates use nested
   ternaries (`IDEST_SIZE = ((sz<=4)?1:((sz==5)?2:4))*32`) while sm120's were
   simple; added tokenize `?`/`:` + `_impl` ternary.
7. `LDCU`→`ULDC` cross-arch mnemonic alias (`sass_matcher.py`).

## Confirmed arch-independent (two gens agree)
- `REGCOUNT` opcode set {0x802, 0x402, 0x882} (MOV32I/MOV.64/UMOV).
- mbarrier SYNCS opcodes 0x15b2 / 0x19a7 and EIATTR_MBARRIER flags.
- ELF section layout, EIATTR encodings, `.nv.info` device attrs.
- runner.py KPARAM parsing + launch paths.
- depcheck CFG mnemonic sets (BSSY/BSYNC/BREAK/BRX/JMX … both gens).
- usched/opex/bracket encoding logic.

## Verified on H20 (sm90)
- **ELF arch markers were the blocker**: `CUDA_ERROR_NO_BINARY_FOR_GPU` until
  three arch-specific ELF identifiers were fixed (values from nvcc):
  e_flags (sm90 0x005a055a), e_ident[EI_OSABI/ABIVERSION] (0x33/0x07), and
  the `.note.nv.tkinfo/.cuver/.nv.compat` sections are sm120-only.
- **ConditionEvaluator/matcher sm90 fixes**: ternary `?:`, and
  `DEFINED TABLES_x(a@attr,b)` arg resolution + negatable-predicate
  `Pnz@not` default.  These unlock LDG.E/STG.E and any instruction with the
  `DEFINED TABLES_*` SASS-only conditions.
- **Key semantic difference — ULDC is synchronous on sm90.**  `ULDC`
  (sm120's `LDCU`) is `INST_TYPE_COUPLED_MATH` with `dst_wr_sb=*7` (no
  scoreboard) in sm90; `LDCU` on sm120 is `DECOUPLED_WR_SCBD` with an
  encodable `dst_wr_sb`.  So a desc load must be waited on with **stall /
  NOP** (or the natural latency of following instructions), NOT a `req` —
  `req={0}` after `LDCU` waits SB0 which ULDC never writes, and the LDG can
  fault ILLEGAL_ADDRESS (700) on a garbage descriptor.  Adding NOPs after
  the ULDC clears the fault.  Test sources that load the cdesc and consume
  it via `req` (the sm120 pattern) must switch to stall/NOP for sm90.

### ULDC timing investigation (H20)
Probed the minimal stall/yield that makes a following LDG see the descriptor:
| ULDC bracket | result |
|---|---|
| yield=0, stall=0 | **ILLEGAL_ADDRESS** (desc not ready) |
| yield=0, stall≥1 | pass |
| yield=1, stall=0..7 | pass |
| `[0:7:{}:7:1]` (nvcc's exact encoding) | pass, byte-identical to nvcc |

So the synchronous ULDC needs either `yield=1` (lets the warp swap out while
the uniform datapath writes UR4/UR5) or `stall≥1`.  `req` never helps because
`dst_wr_sb=*7`.  A lone `yield=1` on the LDCU is NOT always sufficient in a
longer kernel: if the LDG's `req` only waits the *address* scoreboard (LDC.64)
and the ULDC sits earlier, the LDG can still issue before the desc lands —
put the ULDC immediately before the consumer, or give the LDG extra stall.
`sm120 LDCU` needs none of this (it is DECOUPLED and req-waits work).
- Verified on H20: kernel load+launch, param base 0x210, default cdesc
  c[0x0][0x208], LDG/STG, integer math, shared-memory roundtrip, ISETP+SEL
  predicate all pass.  sm90 LDG operand order is `Rd, desc[...]` (format
  order), matching cuobjdump — not the sm120 `desc[...], Rd` dialect.

## Test-suite status on H20 (ASSEMBLER_ARCH=sm90)
*(superseded by `sm90_resilver_audit.md`: full suite later reached **123 tests,
83 pass / 40 fail** on H20, with per-bucket analysis and follow-up actions there.)*
First snapshot: 101 tests: **61 pass / 40 fail**.  Failure buckets:
- **sm120-only instructions** (expected): QMMA/OMMA (sm90 uses QGMMA),
  tensor-map helpers, etc. — need arch-specific sources or isolation.
- **ULDC-synchronous pattern** (see above): tests that `LDCU` the cdesc then
  `req`-wait it fault on sm90; need stall/NOP adaptation.
- **Timing/latency-sensitive**: mufu/ffma latency & throughput, depbar,
  nanotrap, yield — H20 values differ from RTX 5090.
- **Harness arch assumptions**: test_arch asserts the process default is
  sm120, which is false under ASSEMBLER_ARCH=sm90.
- Pre-existing on both GPUs: test_cache_desc.

## Remaining H20-open items
- sm90-only/sm120-only instruction sets (QGMMA vs QMMA/OMMA, ULDC vs LDCU,
  …) — db switch handles encoding; test sources using sm120-only ops must be
  rewritten for Hopper.
- `.nv.compat` TCGEN05 flavour — moot now (sm90 emits no compat section).

## Tests
`tests/asm_construct/test_arch.py` — arch switching, layouts, aliases,
restoration, unknown-arch rejection (assembler-only, no GPU).
